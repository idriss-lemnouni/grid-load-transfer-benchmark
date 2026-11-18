"""Render publication figures from verified run artifacts."""
from pathlib import Path
import argparse
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter

INK = "#172b3b"
MUTED = "#526575"
TEAL = "#007e78"
BLUE = "#4069ba"
ORANGE = "#b9502d"
SOFT = "#d5e1e7"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 11, "text.color": INK,
    "axes.labelcolor": INK, "axes.titlecolor": INK, "xtick.color": MUTED,
    "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
    "axes.edgecolor": SOFT, "axes.axisbelow": True, "grid.color": SOFT,
    "grid.linewidth": 0.7, "legend.frameon": False,
})


def save(fig, out, name, title, note):
    fig.suptitle(title, x=0.055, y=0.96, ha="left", fontsize=21, fontweight="bold")
    fig.text(0.055, 0.035, note, ha="left", color=MUTED, fontsize=9)
    fig.tight_layout(rect=(0.025, .085, .995, .87), pad=1.5)
    fig.savefig(out / (name + ".png"), dpi=180, facecolor="white")
    plt.close(fig)

def render(metrics, out):
    areas = json.loads(metrics.read_text(encoding="utf-8"))["test"]
    zones = [("DE", "Germany", "transfer_AT"), ("AT", "Austria", "transfer_DE")]
    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    for i, (name, key, color) in enumerate(
        [("Weekly naive", "weekly_naive", "#8496a5"), ("Within area", "within_area", TEAL),
         ("Transferred", "transfer", BLUE)]
    ):
        bars = ax.bar([j + (i - 1) * .23 for j in range(2)],
                      [areas[z][transfer if key == "transfer" else key]["mase"] for z, _, transfer in zones],
                      width=.21, color=color, label=name)
        ax.bar_label(bars, fmt="%.3f", padding=3, fontsize=9)
    ax.set(xticks=[0, 1], xticklabels=[z[1] for z in zones], ylabel="MASE (lower is better)", ylim=(0, 1.05))
    ax.legend(loc="upper center", ncol=3, fontsize=9)
    ax.grid(axis="y")
    save(fig, out, "forecast-comparison", "Forecast error against weekly persistence",
         "January–September 2020 · 6,575 held-out hours per area · MASE uses the target area’s training baseline")

    fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.6))
    for ax, (zone, title, transfer) in zip(axes, zones):
        for key, label, color in (("within_area", "Within area", TEAL), (transfer, "Transferred", BLUE)):
            months = sorted((k, v["mae_mw"]) for k, v in areas[zone][key]["segments"].items() if k.startswith("month:"))
            ax.plot(range(1, len(months) + 1), [y for _, y in months], "o-", label=label, color=color)
        ax.set(title=title, xlabel="Month of 2020", ylabel="MAE (MW)", xticks=range(1, len(months) + 1))
        ax.grid(axis="y")
    axes[0].legend(fontsize=9)
    save(fig, out, "monthly-errors", "Forecast error changes through the holdout",
         "Fixed models over the 2020 holdout · y-scales differ because the two areas have different demand levels")

    fig, ax = plt.subplots(figsize=(9.5, 4.6))
    for i, (zone, title, transfer) in enumerate(zones):
        for key, color, marker, offset in (("within_area", TEAL, "o", -.12), (transfer, BLUE, "s", .12)):
            metrics = areas[zone][key]
            x = metrics["coverage_80pct"]
            ax.scatter(x, i + offset, color=color, marker=marker, s=75,
                       label=("Within area" if key == "within_area" else "Transferred") if i == 0 else None)
            ax.annotate(f"{x:.1%}  ·  {metrics['mean_width_mw']:,.0f} MW wide",
                        (x, i + offset), xytext=(8, -4), textcoords="offset points", fontsize=9)
    ax.axvline(.8, color=ORANGE, linestyle="--", linewidth=1.3, label="Nominal 80%")
    ax.set(yticks=[0, 1], yticklabels=[z[1] for z in zones], ylim=(-.46, 1.5), xlim=(.66, 1.02),
           xlabel="Observed coverage of the 80% prediction interval")
    ax.xaxis.set_major_formatter(PercentFormatter(1))
    ax.legend(loc="upper left", ncol=3, fontsize=9)
    ax.grid(axis="x")
    save(fig, out, "interval-calibration", "Transfer changes interval coverage and width",
         "Coverage is the share of measured hours inside the interval · widths are mean interval widths in MW")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, default=Path("reports/holdout-metrics.json"))
    parser.add_argument("--out", type=Path, default=Path("figures/results"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    render(args.metrics, args.out)
