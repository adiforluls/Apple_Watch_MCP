"""
Parse Apple Health export.xml into pandas DataFrames.

The export.xml file can be hundreds of MB, so we use iterparse to stream
records rather than loading the whole tree into memory.
"""
from __future__ import annotations

import pandas as pd
from lxml import etree
from pathlib import Path
from functools import lru_cache


# Common HKQuantityTypeIdentifiers we care about for the Watch
WATCH_TYPES = {
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierActiveEnergyBurned": "active_calories",
    "HKQuantityTypeIdentifierBasalEnergyBurned": "basal_calories",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance_km",
    "HKQuantityTypeIdentifierAppleExerciseTime": "exercise_minutes",
    "HKQuantityTypeIdentifierAppleStandTime": "stand_minutes",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
    "HKQuantityTypeIdentifierVO2Max": "vo2max",
    "HKCategoryTypeIdentifierSleepAnalysis": "sleep",
}


@lru_cache(maxsize=1)
def load_records(export_path: str) -> pd.DataFrame:
    """Parse the export.xml into a long-format DataFrame.

    Columns: type, source, unit, start, end, value
    """
    path = Path(export_path)
    if not path.exists():
        raise FileNotFoundError(f"Apple Health export not found: {export_path}")

    rows = []
    # iterparse streams elements as they close, so we can clear them and keep memory flat.
    for _, elem in etree.iterparse(str(path), tag="Record"):
        rtype = elem.get("type")
        if rtype not in WATCH_TYPES:
            elem.clear()
            continue
        raw = elem.get("value")
        try:
            value = float(raw) if raw is not None else None
        except ValueError:
            value = raw  # sleep stages etc. are strings
        rows.append({
            "type": WATCH_TYPES[rtype],
            "source": elem.get("sourceName"),
            "unit": elem.get("unit"),
            "start": elem.get("startDate"),
            "end": elem.get("endDate"),
            "value": value,
        })
        elem.clear()

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["start"] = pd.to_datetime(df["start"], utc=True)
    df["end"] = pd.to_datetime(df["end"], utc=True)
    return df


def filter_by_type(df: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Filter rows for a single metric, sorted by time."""
    return df[df["type"] == metric].sort_values("start").reset_index(drop=True)


def daily_summary(df: pd.DataFrame, metric: str, agg: str = "sum") -> pd.DataFrame:
    """Aggregate a metric per local day. agg ∈ {'sum','mean','max','min'}."""
    sub = filter_by_type(df, metric)
    if sub.empty:
        return sub
    sub = sub.copy()
    sub["day"] = sub["start"].dt.tz_convert("UTC").dt.date  # swap to local TZ if needed
    grouped = sub.groupby("day")["value"].agg(agg).reset_index()
    grouped.columns = ["day", f"{metric}_{agg}"]
    return grouped
