"""
AI-powered natural language activity search using Claude tool use.
Translates natural language queries into structured activity filters.
"""
import json
import os
from datetime import date, timedelta
from pathlib import Path

import anthropic

BIOMARKERS_CONFIG_PATH = Path(__file__).parent.parent / "biomarkers_config.json"


def _get_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        try:
            cfg = json.loads(BIOMARKERS_CONFIG_PATH.read_text())
            key = cfg.get("anthropic_api_key")
        except Exception:
            pass
    if not key:
        raise ValueError("Anthropic API key not configured.")
    return key


SEARCH_TOOL = {
    "name": "search_activities",
    "description": "Search and filter the user's workout/activity database. Returns matching activities sorted as specified.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sport": {
                "type": "string",
                "enum": ["all", "Running", "Cycling"],
                "description": "Filter by sport type. Use 'all' to include both.",
            },
            "date_start": {
                "type": "string",
                "description": "Start date for the search range (YYYY-MM-DD). Omit for no lower bound.",
            },
            "date_end": {
                "type": "string",
                "description": "End date for the search range (YYYY-MM-DD). Omit for no upper bound.",
            },
            "min_distance_km": {
                "type": "number",
                "description": "Minimum distance in kilometers.",
            },
            "max_distance_km": {
                "type": "number",
                "description": "Maximum distance in kilometers.",
            },
            "min_duration_min": {
                "type": "number",
                "description": "Minimum duration in minutes.",
            },
            "max_duration_min": {
                "type": "number",
                "description": "Maximum duration in minutes.",
            },
            "min_pace_min_km": {
                "type": "number",
                "description": "Minimum pace in min/km (slower limit). For cycling, this is converted from speed.",
            },
            "max_pace_min_km": {
                "type": "number",
                "description": "Maximum pace in min/km (faster limit). Lower number = faster pace.",
            },
            "min_avg_hr": {
                "type": "number",
                "description": "Minimum average heart rate (bpm).",
            },
            "max_avg_hr": {
                "type": "number",
                "description": "Maximum average heart rate (bpm).",
            },
            "min_elevation_m": {
                "type": "number",
                "description": "Minimum elevation gain in meters.",
            },
            "min_avg_watts": {
                "type": "number",
                "description": "Minimum average power in watts.",
            },
            "name_contains": {
                "type": "string",
                "description": "Search for activities whose name contains this text (case-insensitive).",
            },
            "sort_by": {
                "type": "string",
                "enum": ["date", "distance_km", "duration_min", "pace_min_km", "avg_hr", "elevation_m", "suffer_score", "avg_watts"],
                "description": "Field to sort results by.",
            },
            "sort_dir": {
                "type": "string",
                "enum": ["asc", "desc"],
                "description": "Sort direction. 'desc' for longest/highest first, 'asc' for shortest/lowest first.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results to return (default 20, max 100).",
            },
        },
        "required": [],
    },
}

SUMMARIZE_TOOL = {
    "name": "summarize_results",
    "description": "After searching, provide a brief natural-language summary of what was found.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "A 1-2 sentence summary of the search results for the user.",
            },
        },
        "required": ["summary"],
    },
}


def parse_query(query: str) -> dict:
    """
    Use Claude to interpret a natural language query and extract structured filters.
    Returns a dict with filter parameters for the activities endpoint.
    """
    api_key = _get_api_key()
    client = anthropic.Anthropic(api_key=api_key)

    today_str = date.today().isoformat()
    current_year = date.today().year

    system = f"""You are a search assistant for a health dashboard's activity log.
Today's date is {today_str}. The current year is {current_year}.

The user will ask questions about their workout history in natural language.
Your job is to call the search_activities tool with the right filters.

Important rules:
- "fastest" means sort by pace ascending (lowest pace = fastest)
- "longest" by distance means sort by distance_km descending
- "longest" by time means sort by duration_min descending
- "hardest" means sort by suffer_score descending or avg_hr descending
- "most elevation" means sort by elevation_m descending
- For time periods: "last month" = previous calendar month, "this year" = {current_year}-01-01 to {today_str}
- "last 3 months" = 90 days back from today
- If user says "over 100km" that means min_distance_km=100
- If user says "under 5 min/km pace" that means max_pace_min_km=5 (faster than 5 min/km)
- Default limit is 10 unless user specifies otherwise (e.g., "top 5", "show 20")
- Always set sort_by and sort_dir to match the user's intent
"""

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=512,
        system=system,
        tools=[SEARCH_TOOL],
        tool_choice={"type": "tool", "name": "search_activities"},
        messages=[{"role": "user", "content": query}],
    )

    # Extract the tool call parameters
    for block in response.content:
        if block.type == "tool_use" and block.name == "search_activities":
            return block.input

    return {}


def generate_summary(query: str, filters: dict, results: list, total: int) -> str:
    """Generate a natural language summary of the search results."""
    api_key = _get_api_key()
    client = anthropic.Anthropic(api_key=api_key)

    context = f"User asked: \"{query}\"\nFilters applied: {json.dumps(filters)}\nFound {total} matching activities, showing {len(results)}.\n"
    if results:
        # Include top 3 results as context
        preview = results[:3]
        context += "Top results:\n"
        for r in preview:
            parts = [r.get("date", ""), r.get("type", ""), r.get("name", "")]
            if r.get("distance_km"):
                parts.append(f"{r['distance_km']:.1f}km")
            if r.get("duration_min"):
                h, m = divmod(int(r["duration_min"]), 60)
                parts.append(f"{h}h{m}m" if h else f"{m}m")
            if r.get("pace_min_km"):
                p = r["pace_min_km"]
                parts.append(f"{int(p)}:{int((p%1)*60):02d}/km")
            context += "  - " + " | ".join(p for p in parts if p) + "\n"

    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        system="You are a concise sports analytics assistant. Summarize the search results in 1-2 sentences. Be specific with numbers. Do not use emojis.",
        messages=[{"role": "user", "content": context}],
    )

    return response.content[0].text if response.content else ""
