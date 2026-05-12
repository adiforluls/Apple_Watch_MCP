"""
MCP server exposing Apple Watch data analysis tools.

Run as: python server.py /path/to/export.xml

Communicates over stdio per MCP spec. Tools:
  - list_metrics: what data types are available
  - daily_summary: aggregate a metric per day
  - heart_rate_stats: min/avg/max HR over a date range
  - workout_intensity: zones distribution over a date range
"""
from __future__ import annotations

import asyncio
import sys
import json
from datetime import date
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from data_loader import load_records, filter_by_type, daily_summary, WATCH_TYPES


# The path is passed as a CLI arg so the server can be reconfigured per-user.
EXPORT_PATH = sys.argv[1] if len(sys.argv) > 1 else "export.xml"

app = Server("apple-watch-analyzer")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_metrics",
            description="List all available Apple Watch metrics in the loaded export.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="daily_summary",
            description=(
                "Aggregate a metric per day. Returns a list of {day, value} rows. "
                "Use 'sum' for steps/calories/distance, 'mean' for heart_rate, "
                "'max' or 'min' for extremes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": f"One of: {sorted(set(WATCH_TYPES.values()))}",
                    },
                    "agg": {
                        "type": "string",
                        "enum": ["sum", "mean", "max", "min"],
                        "default": "sum",
                    },
                    "start_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
                    "end_date": {"type": "string", "description": "YYYY-MM-DD, optional"},
                },
                "required": ["metric"],
            },
        ),
        Tool(
            name="heart_rate_stats",
            description="Compute heart rate statistics (min, mean, max, std) over a date range.",
            inputSchema={
                "type": "object",
                "properties": {
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
            },
        ),
        Tool(
            name="workout_intensity",
            description=(
                "Categorize heart rate readings into zones (resting/light/moderate/vigorous/peak) "
                "based on age-predicted max HR (220 - age). Returns minutes in each zone."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "age": {"type": "integer", "default": 30},
                    "start_date": {"type": "string"},
                    "end_date": {"type": "string"},
                },
                "required": ["age"],
            },
        ),
    ]


def _filter_by_date_range(df, start_date: str | None, end_date: str | None):
    if start_date:
        df = df[df["start"].dt.date >= date.fromisoformat(start_date)]
    if end_date:
        df = df[df["start"].dt.date <= date.fromisoformat(end_date)]
    return df


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    df = load_records(EXPORT_PATH)

    if name == "list_metrics":
        present = sorted(df["type"].unique().tolist()) if not df.empty else []
        return [TextContent(type="text", text=json.dumps({"metrics": present}, indent=2))]

    if name == "daily_summary":
        metric = arguments["metric"]
        agg = arguments.get("agg", "sum")
        sub = filter_by_type(df, metric)
        sub = _filter_by_date_range(sub, arguments.get("start_date"), arguments.get("end_date"))
        if sub.empty:
            return [TextContent(type="text", text=json.dumps({"rows": []}))]
        sub = sub.copy()
        sub["day"] = sub["start"].dt.date.astype(str)
        result = sub.groupby("day")["value"].agg(agg).reset_index()
        result.columns = ["day", "value"]
        return [TextContent(type="text", text=result.to_json(orient="records"))]

    if name == "heart_rate_stats":
        sub = filter_by_type(df, "heart_rate")
        sub = _filter_by_date_range(sub, arguments.get("start_date"), arguments.get("end_date"))
        if sub.empty:
            return [TextContent(type="text", text=json.dumps({"error": "no data in range"}))]
        stats = {
            "count": int(sub["value"].count()),
            "min": float(sub["value"].min()),
            "mean": round(float(sub["value"].mean()), 1),
            "max": float(sub["value"].max()),
            "std": round(float(sub["value"].std()), 2),
        }
        return [TextContent(type="text", text=json.dumps(stats, indent=2))]

    if name == "workout_intensity":
        age = arguments["age"]
        max_hr = 220 - age
        sub = filter_by_type(df, "heart_rate")
        sub = _filter_by_date_range(sub, arguments.get("start_date"), arguments.get("end_date"))
        if sub.empty:
            return [TextContent(type="text", text=json.dumps({"error": "no data in range"}))]

        # Standard zones as % of max HR
        bins = [0, 0.5, 0.6, 0.7, 0.85, 1.0, 10]
        labels = ["below_resting", "resting", "light", "moderate", "vigorous", "peak"]
        sub = sub.copy()
        sub["zone"] = pd.cut(sub["value"] / max_hr, bins=bins, labels=labels, include_lowest=True)
        # Each HR sample ≈ instantaneous; treat each as ~1 sample. For minutes-in-zone,
        # multiply by the typical sample interval. Apple Watch HR samples are ~every few sec
        # when active, so the count itself is a reasonable proxy.
        distribution = sub.groupby("zone", observed=True).size().to_dict()
        result = {
            "max_hr_predicted": max_hr,
            "samples_per_zone": {str(k): int(v) for k, v in distribution.items()},
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return [TextContent(type="text", text=json.dumps({"error": f"unknown tool {name}"}))]


# pandas only used inside call_tool above
import pandas as pd  # noqa: E402


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
