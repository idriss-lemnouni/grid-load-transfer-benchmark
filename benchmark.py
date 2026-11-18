"""Tune day-ahead demand models with rolling origins and test cross-area transfer."""
from collections import defaultdict
import csv
from datetime import date
import json
import math
from pathlib import Path
from statistics import mean

from zoneinfo import ZoneInfo

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from grid_data import AREAS, FEATURE_GROUPS, SOURCE, SOURCE_SHA256, make_records, read_series, sha256
from report import write_report

FOLDS = (date(2019, 1, 1), date(2019, 5, 1), date(2019, 9, 1), date(2020, 1, 1))
TEST_START = FOLDS[-1]
FAMILIES = ("ridge_0.1", "ridge_1", "ridge_10", "hgb_7", "hgb_15")


def features(rows, dropped=()):
    return np.array([
        [value for index, value in enumerate(row.features) if index not in dropped] for row in rows
    ])


def model(name):
    family, value = name.split("_")
    if family == "ridge":
        return make_pipeline(StandardScaler(), Ridge(alpha=float(value)))
    return HistGradientBoostingRegressor(
        max_leaf_nodes=int(value), max_iter=100, learning_rate=0.07,
        early_stopping=False, random_state=42
    )


def fit(name, rows, dropped=()):
    if len(rows) < 24 * 30:
        raise ValueError("A training fold needs at least 30 days of eligible hourly samples")
    return model(name).fit(features(rows, dropped), [row.load / row.scale for row in rows])


def fold_partitions(records):
    for start, stop in zip(FOLDS, FOLDS[1:]):
        validation = [row for row in records if start <= row.day < stop]
        if not validation:
            raise ValueError(f"No validation rows in {start} to {stop}")
        cutoff = min(row.origin for row in validation)
        yield [row for row in records if row.target < cutoff], validation


def predictions(estimator, rows, dropped=()):
    return estimator.predict(features(rows, dropped)) * np.array([row.scale for row in rows])


def train(records):
    scores = defaultdict(list)
    residuals = defaultdict(list)
    fold_counts = []
    for fitting, validation in fold_partitions(records):
        fold_counts.append({"train": len(fitting), "validation": len(validation)})
        actual = np.array([row.load for row in validation])
        scale = np.array([row.scale for row in validation])
        naive_mae = np.mean([abs(row.load - row.lag_week) for row in fitting])
        if naive_mae <= 0:
            raise ValueError("Seasonal MASE reference must have positive error")
        for name in FAMILIES:
            error = np.abs(predictions(fit(name, fitting), validation) - actual)
            scores[name].append(float(np.mean(error) / naive_mae))
            residuals[name].extend(error / scale)
    selected = min(FAMILIES, key=lambda name: mean(scores[name]))
    radius = sequential_radius(residuals[selected], 0.8)
    return selected, radius, dict(scores), fold_counts


def sequential_radius(errors, level):
    if not errors or not 0 < level < 1:
        raise ValueError("An interval needs calibration residuals and a level in (0,1)")
    position = min(len(errors), math.ceil((len(errors) + 1) * level)) - 1
    return float(sorted(errors)[position])


def score(rows, point, lower, upper, naive_scale):
    if not rows or naive_scale <= 0:
        raise ValueError("Test needs eligible observations and a positive reference MAE")
    y = np.array([row.load for row in rows])
    mae = float(np.mean(np.abs(y - point)))
    result = {"rows": len(rows), "mae_mw": mae, "mase": mae / naive_scale}
    if lower is not None:
        result.update({
            "coverage_80pct": float(np.mean((y >= lower) & (y <= upper))),
            "mean_width_mw": float(np.mean(upper - lower)),
            "pinball_lower_0.1_mw": float(np.mean(np.maximum(0.1 * (y - lower), -0.9 * (y - lower)))),
            "pinball_upper_0.9_mw": float(np.mean(np.maximum(0.9 * (y - upper), -0.1 * (y - upper)))),
        })
    return result


def segments(rows, point, high_threshold):
    grouped = defaultdict(list)
    for row, predicted in zip(rows, point):
        error = float(abs(row.load - predicted))
        grouped[f"month:{row.day:%Y-%m}"].append(error)
        grouped["weekend" if row.day.weekday() >= 5 else "weekday"].append(error)
        if row.load >= high_threshold:
            grouped["high_load_vs_train_p90"].append(error)
        if row.local_day_hours != 24:
            grouped[f"dst:{row.local_day_hours}h"].append(error)
    return {key: {"rows": len(values), "mae_mw": mean(values)} for key, values in sorted(grouped.items())}


def benchmark(path: Path, out: Path, threads: int = 2) -> dict:
    digest = sha256(path)
    if digest != SOURCE_SHA256:
        raise ValueError(f"OPSD snapshot SHA-256 mismatch: {digest}")
    series, quality = read_series(path)
    calibration = {}
    fitting = {}
    test = {}
    summary = {"source": SOURCE, "sha256": digest, "source_bytes": path.stat().st_size,
               "quality": quality, "areas": {}, "test": {}}
    scored_rows = []
    with threadpool_limits(limits=threads):
        for area, zone in AREAS.items():
            rows, dropped = make_records(series[area], ZoneInfo(zone))
            test[area] = [row for row in rows if row.day >= TEST_START]
            if not test[area]:
                raise ValueError(f"No eligible test hours in {area}")
            cutoff = min(row.origin for row in test[area])
            fitting[area] = [row for row in rows if row.target < cutoff]
            selection, radius, scores, folds = train(rows)
            calibration[area] = (selection, radius)
            summary["areas"][area] = {
                "lost_rows_missing_lags": dropped, "folds": folds, "validation_mase": scores,
                "selected": selection, "interval_radius_in_load_scale": radius,
                "final_fit_rows": len(fitting[area]), "fixed_training_cutoff_utc": cutoff.isoformat(),
            }
        for target, rows in test.items():
            naive_scale = mean(abs(row.load - row.lag_week) for row in fitting[target])
            high = float(np.quantile([row.load for row in fitting[target]], 0.9))
            weekly = np.array([row.lag_week for row in rows])
            target_scores = {"weekly_naive": score(rows, weekly, None, None, naive_scale)}
            scales = np.array([row.scale for row in rows])
            for source, (name, radius) in calibration.items():
                choice = "within_area" if source == target else f"transfer_{source}"
                point = predictions(fit(name, fitting[source]), rows)
                lower, upper = point - radius * scales, point + radius * scales
                result = score(rows, point, lower, upper, naive_scale)
                result["segments"] = segments(rows, point, high)
                if source == target:
                    result["ablation_mae_delta_mw"] = {}
                    for group, indices in FEATURE_GROUPS.items():
                        ablated = predictions(fit(name, fitting[source], indices), rows, indices)
                        result["ablation_mae_delta_mw"][group] = score(
                            rows, ablated, None, None, naive_scale
                        )["mae_mw"] - result["mae_mw"]
                target_scores[choice] = result
                scored_rows.extend(
                    (target, source, row.target.isoformat(), row.origin.isoformat(),
                     row.load, float(baseline), float(predicted), float(lo), float(hi))
                    for row, baseline, predicted, lo, hi in zip(rows, weekly, point, lower, upper)
                )
            summary["test"][target] = target_scores
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with (out / "predictions.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(("target_area", "training_area", "target_utc", "origin_utc", "actual_mw",
                         "weekly_naive_mw", "prediction_mw", "lower_mw", "upper_mw"))
        writer.writerows(scored_rows)
    write_report(out / "forecast.html", summary)
    return summary
