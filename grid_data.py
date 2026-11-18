"""Read published hourly load and enforce a local day-ahead forecast origin."""
from collections import Counter
import csv
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import math
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from urllib.request import urlopen
from zoneinfo import ZoneInfo

SOURCE = "https://data.open-power-system-data.org/time_series/2020-10-06/time_series_60min_singleindex.csv"
SOURCE_SHA256 = "6a7f2bc571314cbf9c321cc03437691cd4be95c3a6f075e60ff99e8035c704c8"
AREAS = {"DE": "Europe/Berlin", "AT": "Europe/Vienna"}
FIRST_DAY = date(2017, 1, 1)
LAST_DAY = date(2020, 9, 30)
LAGS = (48, 72, 168, 336, 504, 672)
FEATURE_GROUPS = {"recent": (0, 1), "weekly": (2, 3, 4, 5), "calendar": (6, 7, 8, 9, 10)}
ONE_HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class Record:
    target: datetime
    day: date
    origin: datetime
    load: float
    scale: float
    lag_week: float
    features: tuple[float, ...]
    local_day_hours: int


def sha256(path: Path) -> str:
    with path.open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def fetch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=path.parent) as folder:
        temporary = Path(folder) / path.name
        with urlopen(SOURCE, timeout=60) as response, temporary.open("wb") as target:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > 160_000_000:
                    raise ValueError("Hourly CSV download exceeded 160 MB")
                target.write(chunk)
        if sha256(temporary) != SOURCE_SHA256:
            raise ValueError("Published snapshot SHA-256 mismatch")
        temporary.replace(path)


def read_series(path: Path) -> tuple[dict, dict]:
    series = {area: {} for area in AREAS}
    counts = Counter()
    columns = {area: f"{area}_load_actual_entsoe_transparency" for area in AREAS}
    first_needed = datetime.combine(FIRST_DAY, time.min, timezone.utc) - timedelta(days=29)
    last_needed = datetime.combine(LAST_DAY + timedelta(days=1), time.max, timezone.utc)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"utc_timestamp", *columns.values()}
        if not required.issubset(reader.fieldnames or []):
            raise ValueError("Missing OPSD UTC or load columns")
        previous = None
        for row in reader:
            counts["source_rows"] += 1
            target = datetime.fromisoformat(row["utc_timestamp"])
            if target.utcoffset() != timedelta() or target.minute or target.second or target.microsecond:
                raise ValueError("Expected UTC measurements on an hourly grid")
            if previous is not None and target <= previous:
                raise ValueError("Duplicate or decreasing UTC timestamp")
            if previous is not None and target != previous + ONE_HOUR:
                counts["absent_utc_hours"] += int((target - previous) / ONE_HOUR) - 1
            previous = target
            if not first_needed <= target <= last_needed:
                continue
            for area, column in columns.items():
                value = row[column].strip()
                if not value:
                    counts[f"{area}_missing_load"] += 1
                    continue
                load = float(value)
                if not math.isfinite(load) or load <= 0:
                    counts[f"{area}_nonpositive_or_nonfinite_load"] += 1
                    continue
                series[area][target] = load
    return series, dict(counts)


def local_day_hours(day: date, zone: ZoneInfo) -> int:
    start = datetime.combine(day, time.min, zone).astimezone(timezone.utc)
    tomorrow = datetime.combine(day + timedelta(days=1), time.min, zone).astimezone(timezone.utc)
    return int((tomorrow - start) / ONE_HOUR)


def origin_for(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day - timedelta(days=1), time(hour=12), zone).astimezone(timezone.utc)


def make_records(series: dict[datetime, float], zone: ZoneInfo) -> tuple[list[Record], int]:
    records = []
    missing_features = 0
    for target, observed in series.items():
        local = target.astimezone(zone)
        day = local.date()
        if not FIRST_DAY <= day <= LAST_DAY:
            continue
        origin = origin_for(day, zone)
        history = [target - lag * ONE_HOUR for lag in LAGS]
        if max(history) >= origin:
            raise ValueError("A lag is unavailable at the forecast origin")
        if any(timestamp not in series for timestamp in history):
            missing_features += 1
            continue
        lags = tuple(series[timestamp] for timestamp in history)
        scale = median(lags[2:])
        hour = 2 * math.pi * local.hour / 24
        weekday = 2 * math.pi * local.weekday() / 7
        x = tuple(lag / scale for lag in lags) + (
            math.sin(hour), math.cos(hour), math.sin(weekday), math.cos(weekday),
            float(local.weekday() >= 5),
        )
        records.append(Record(target, day, origin, observed, scale, lags[2], x, local_day_hours(day, zone)))
    return records, missing_features
