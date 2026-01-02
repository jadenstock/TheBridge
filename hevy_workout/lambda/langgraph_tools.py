"""
LangGraph/LangChain tool wrappers for Hevy read helpers.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional, List

from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

import hevy_tools


def _get_api_key() -> str:
    api_key = os.environ.get("HEVY_API_KEY")
    if not api_key:
        raise ValueError("HEVY_API_KEY is not set")
    return api_key


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# ---------- Tool 1: workouts in range (LLM-friendly formatted) ----------
class WorkoutsWindow(BaseModel):
    days: int = Field(
        default=14,
        description="Number of days back from now to fetch workouts (UTC).",
        gt=0,
        le=365,
    )


def _tool_fetch_workouts(window: WorkoutsWindow) -> str:
    api_key = _get_api_key()
    return hevy_tools.fetch_and_format_recent_workouts(api_key=api_key, days=window.days)


workouts_tool = StructuredTool.from_function(
    func=_tool_fetch_workouts,
    name="get_workouts_formatted",
    description="Fetch workouts for the past N days and return an LLM-readable text block (kg converted to lbs, notes preserved).",
)


# ---------- Tool 2: exercise frequency summary ----------
class FrequencyWindow(BaseModel):
    days: int = Field(
        default=14,
        description="Number of days back from now to summarize exercise frequency.",
        gt=0,
        le=365,
    )


def _tool_exercise_frequency(window: FrequencyWindow) -> str:
    api_key = _get_api_key()
    return hevy_tools.fetch_recent_exercise_frequency(api_key=api_key, days=window.days)


exercise_frequency_tool = StructuredTool.from_function(
    func=_tool_exercise_frequency,
    name="get_exercise_frequency",
    description="Summarize exercise frequency over the past N days (sessions, sets, reps, duration, volume) sorted by sessions.",
)


# ---------- Tool 3: exercise trend ----------
class ExerciseTrendParams(BaseModel):
    exercise_id: str = Field(..., description="Hevy exercise template id.")
    days: int = Field(
        default=90,
        description="Number of days back from now to analyze trends.",
        gt=0,
        le=365,
    )


def _tool_exercise_trend(params: ExerciseTrendParams) -> str:
    api_key = _get_api_key()
    end = hevy_tools.ensure_utc(_utc_now())
    start = end - timedelta(days=params.days)
    return hevy_tools.fetch_exercise_trend(
        api_key=api_key,
        exercise_id=params.exercise_id,
        start_date=start,
        end_date=end,
    )


exercise_trend_tool = StructuredTool.from_function(
    func=_tool_exercise_trend,
    name="get_exercise_trend",
    description="Exercise-specific trend over the past N days: session-by-session volume, max set volume, max weight, est 1RM, duration/distance, and notes.",
)

# ---------- Tool 4: latest coach doc ----------


def _tool_latest_coach_doc() -> str:
    return hevy_tools.fetch_latest_coach_doc()


coach_doc_tool = StructuredTool.from_function(
    func=_tool_latest_coach_doc,
    name="get_latest_coach_doc",
    description="Fetch the most recent coach doc from S3 and return its contents.",
)

# ---------- Tool 5: latest weekly goals doc ----------


def _tool_latest_weekly_goal_doc() -> str:
    return hevy_tools.fetch_latest_weekly_goal_doc()


weekly_goal_doc_tool = StructuredTool.from_function(
    func=_tool_latest_weekly_goal_doc,
    name="get_latest_weekly_goal_doc",
    description="Fetch the most recent weekly goals doc from S3 and return its contents.",
)


# ---------- Tool 6: search exercise templates ----------
class TemplateSearchParams(BaseModel):
    query: str = Field(..., description="Case-insensitive substring to match exercise template titles.")
    max_results: int = Field(
        default=30,
        description="Maximum number of matches to return.",
        gt=1,
        le=200,
    )


def _tool_search_exercise_templates(params: TemplateSearchParams) -> str:
    api_key = _get_api_key()
    return hevy_tools.search_exercise_templates(api_key=api_key, query=params.query, max_results=params.max_results)


exercise_template_search_tool = StructuredTool.from_function(
    func=_tool_search_exercise_templates,
    name="search_exercise_templates",
    description="Search Hevy exercise templates by title and return matching names + ids (useful for finding template IDs).",
)


def get_tools() -> List[StructuredTool]:
    """
    Convenience accessor for all Hevy tools.
    """
    return [
        workouts_tool,
        exercise_frequency_tool,
        exercise_trend_tool,
        coach_doc_tool,
        weekly_goal_doc_tool,
        exercise_template_search_tool,
    ]
