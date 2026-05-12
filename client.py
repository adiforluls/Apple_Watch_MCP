"""
Minimal MCP client for the apple-watch-analyzer server.

Spawns the server as a subprocess, lists tools, runs a few calls,
prints results. This is the "host" role in MCP terminology.

Run as: python client.py /path/to/export.xml
"""
from __future__ import annotations

import asyncio
import sys
import json

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


EXPORT_PATH = sys.argv[1] if len(sys.argv) > 1 else "export.xml"


async def main():
    # Tell the client how to launch the server (stdio transport).
    server_params = StdioServerParameters(
        command="python",
        args=["server.py", EXPORT_PATH],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. Discovery: what tools are available?
            tools = await session.list_tools()
            print("=== Available tools ===")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description[:80]}...")

            # 2. List metrics present in the export
            print("\n=== Metrics in export ===")
            result = await session.call_tool("list_metrics", {})
            print(result.content[0].text)

            # 3. Daily step count for a week
            print("\n=== Daily steps (last week of data) ===")
            result = await session.call_tool(
                "daily_summary",
                {"metric": "steps", "agg": "sum"},
            )
            rows = json.loads(result.content[0].text)
            for row in rows[-7:]:
                print(f"  {row['day']}: {int(row['value'])} steps")

            # 4. Heart rate stats
            print("\n=== Heart rate stats (all data) ===")
            result = await session.call_tool("heart_rate_stats", {})
            print(result.content[0].text)

            # 5. Workout intensity zones
            print("\n=== Workout intensity zones (age 30) ===")
            result = await session.call_tool("workout_intensity", {"age": 30})
            print(result.content[0].text)


if __name__ == "__main__":
    asyncio.run(main())
