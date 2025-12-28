"""
Helper functions for Hevy read endpoints and LLM-friendly formatting.
Designed to be wrapped as LangChain tools later.
"""

from datetime import datetime, timedelta, timezone
import json
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional


def kg_to_lbs(kg: Optional[float]) -> Optional[float]:
    if kg is None:
        return None
    return round(kg * 2.20462, 1)


def parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """
    Parse ISO-ish strings from Hevy (supports both Z and +00:00).
    """
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def ensure_utc(dt: datetime) -> datetime:
    """
    Ensure a datetime is timezone-aware in UTC.
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def fetch_workouts_range(api_key: str, start_date: datetime, end_date: datetime, page_size: int = 50) -> List[Dict[str, Any]]:
    """
    Fetch workouts in a date range (inclusive) with pagination.
    """
    from urllib.parse import quote

    workouts: List[Dict[str, Any]] = []
    page = 1

    while True:
        start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        url = (
            f"https://api.hevyapp.com/v1/workouts?"
            f"start_date={quote(start_str)}&end_date={quote(end_str)}&page_size={page_size}&page={page}"
        )

        headers = {"accept": "application/json", "api-key": api_key}
        req = urllib.request.Request(url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            raise RuntimeError(f"Hevy API error {e.code}: {error_body}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Network error fetching workouts: {str(e)}")

        page_workouts = data.get("workouts", [])
        workouts.extend(page_workouts)

        page_count = data.get("page_count", page)
        if page >= page_count or not page_workouts:
            break
        page += 1

    return workouts


def fetch_workout_by_id(api_key: str, workout_id: str) -> Dict[str, Any]:
    """
    Fetch a single workout by ID.
    """
    url = f"https://api.hevyapp.com/v1/workouts/{workout_id}"
    headers = {"accept": "application/json", "api-key": api_key}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise RuntimeError(f"Hevy API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error fetching workout {workout_id}: {str(e)}")


def format_workouts_for_llm(workouts: List[Dict[str, Any]]) -> str:
    """
    Render workouts as a readable text block, converting kg->lbs and keeping notes.
    """
    if not workouts:
        return "No workouts found for the requested window."

    lines: List[str] = []

    # Sort most recent first
    sorted_workouts = sorted(workouts, key=lambda w: w.get("start_time", ""), reverse=True)
    for w in sorted_workouts:
        title = w.get("title", "Untitled Workout")
        start_time = w.get("start_time", "")
        end_time = w.get("end_time", "")
        desc = w.get("description")

        lines.append(f"Workout: {title}")
        lines.append(f"  Start: {start_time} | End: {end_time}")
        if desc:
            lines.append(f"  Notes: {desc}")

        exercises = w.get("exercises", [])
        if not exercises:
            lines.append("  Exercises: none logged")
            continue

        for idx, ex in enumerate(exercises, 1):
            ex_title = ex.get("title", "Unknown Exercise")
            ex_notes = ex.get("notes")
            lines.append(f"  {idx}. {ex_title}")
            if ex_notes:
                lines.append(f"     Exercise notes: {ex_notes}")

            sets = ex.get("sets", [])
            if not sets:
                lines.append("     Sets: none")
                continue

            for s_idx, s in enumerate(sets, 1):
                set_type = s.get("type")
                weight_lbs = kg_to_lbs(s.get("weight_kg"))
                reps = s.get("reps")
                distance = s.get("distance_meters")
                duration = s.get("duration_seconds")
                rpe = s.get("rpe")
                custom_metric = s.get("custom_metric")

                parts = [f"Set {s_idx}"]
                if set_type:
                    parts.append(f"({set_type})")
                if weight_lbs is not None:
                    parts.append(f"{weight_lbs} lbs")
                if reps is not None:
                    parts.append(f"x {reps} reps")
                if distance is not None:
                    parts.append(f"{distance} m")
                if duration is not None:
                    parts.append(f"{duration} s")
                if rpe is not None:
                    parts.append(f"RPE {rpe}")
                if custom_metric is not None:
                    parts.append(f"custom_metric={custom_metric}")

                lines.append("     " + " ".join(parts))

        lines.append("")  # blank line between workouts

    return "\n".join(lines).strip()


def fetch_and_format_recent_workouts(api_key: str, days: int = 14) -> str:
    """
    Convenience wrapper to get recent workouts and format for LLM consumption.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    workouts = fetch_workouts_range(api_key, start_date, end_date)
    return format_workouts_for_llm(workouts)


def format_exercise_frequency(
    workouts: List[Dict[str, Any]],
    start_date: datetime,
    end_date: datetime,
) -> str:
    """
    Summarize exercise frequency across workouts for LLM consumption.
    Sorted by number of sessions an exercise appears in.
    """
    if not workouts:
        return f"No workouts found between {start_date.isoformat()} and {end_date.isoformat()}."

    stats: Dict[str, Dict[str, Any]] = {}

    for w in workouts:
        workout_id = w.get("id")
        workout_start = parse_iso_datetime(w.get("start_time"))
        if workout_start and (workout_start < start_date or workout_start > end_date):
            continue
        exercises = w.get("exercises", [])
        seen_in_workout = set()

        for ex in exercises:
            template_id = ex.get("exercise_template_id") or f"title:{ex.get('title','Unknown Exercise')}"
            if template_id not in stats:
                stats[template_id] = {
                    "title": ex.get("title", "Unknown Exercise"),
                    "sessions": set(),
                    "sets": 0,
                    "reps": 0,
                    "duration_seconds": 0,
                    "volume_kg": 0.0,  # sum of weight*reps across sets
                }

            # Track sessions (workout-level)
            if workout_id and template_id not in seen_in_workout:
                stats[template_id]["sessions"].add(workout_id)
                seen_in_workout.add(template_id)

            # Aggregate sets/reps/duration
            for s in ex.get("sets", []):
                stats[template_id]["sets"] += 1
                reps = s.get("reps")
                if isinstance(reps, (int, float)):
                    stats[template_id]["reps"] += reps
                weight = s.get("weight_kg")
                if isinstance(weight, (int, float)) and isinstance(reps, (int, float)):
                    stats[template_id]["volume_kg"] += weight * reps
                duration = s.get("duration_seconds")
                if isinstance(duration, (int, float)):
                    stats[template_id]["duration_seconds"] += duration

    # Convert sessions sets to counts and sort
    entries = []
    for template_id, data in stats.items():
        session_count = len(data["sessions"])
        if session_count == 0:
            continue
        entries.append(
            {
                "template_id": template_id,
                "title": data["title"],
                "session_count": session_count,
                "sets": data["sets"],
                "reps": data["reps"],
                "duration_seconds": data["duration_seconds"],
                "volume_kg": data["volume_kg"],
            }
        )

    if not entries:
        return f"No exercise data found between {start_date.isoformat()} and {end_date.isoformat()}."

    entries.sort(key=lambda e: (-e["session_count"], e["title"]))

    lines = [
        f"Exercise frequency {start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')} (sorted by sessions):"
    ]
    for idx, e in enumerate(entries, 1):
        duration_str = ""
        if e["duration_seconds"]:
            minutes = round(e["duration_seconds"] / 60, 1)
            duration_str = f", duration {int(e['duration_seconds'])}s ({minutes} min)"
        reps_str = f", reps {int(e['reps'])}" if e["reps"] else ""
        sets_str = f", sets {e['sets']}" if e["sets"] else ""
        volume_str = ""
        if e["volume_kg"]:
            volume_lbs = kg_to_lbs(e["volume_kg"])
            volume_str = f", total volume {volume_lbs} lbs"
        lines.append(
            f"{idx}. {e['title']} (id: {e['template_id']}): "
            f"sessions {e['session_count']}{sets_str}{reps_str}{duration_str}{volume_str}"
        )

    return "\n".join(lines)


def fetch_exercise_frequency(api_key: str, start_date: datetime, end_date: datetime) -> str:
    """
    Fetch workouts in range and return frequency summary formatted for LLMs.
    """
    start_date = ensure_utc(start_date)
    end_date = ensure_utc(end_date)
    workouts = fetch_workouts_range(api_key, start_date, end_date)
    return format_exercise_frequency(workouts, start_date, end_date)


def fetch_recent_exercise_frequency(api_key: str, days: int = 14) -> str:
    """
    Convenience wrapper for exercise frequency over the last N days.
    """
    end_date = ensure_utc(datetime.utcnow())
    start_date = end_date - timedelta(days=days)
    return fetch_exercise_frequency(api_key, start_date, end_date)


def fetch_exercise_history_range(api_key: str, exercise_id: str, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]]:
    """
    Fetch exercise history rows for a template within a date range.
    """
    from urllib.parse import quote
    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    end_str = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (
        f"https://api.hevyapp.com/v1/exercise_history/{exercise_id}"
        f"?start_date={quote(start_str)}&end_date={quote(end_str)}"
    )
    headers = {"accept": "application/json", "api-key": api_key}
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("exercise_history", [])
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise RuntimeError(f"Hevy API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Network error fetching exercise history: {str(e)}")


def format_exercise_trend(
    history_rows: List[Dict[str, Any]],
    workouts: List[Dict[str, Any]],
    exercise_id: str,
    start_date: datetime,
    end_date: datetime,
) -> str:
    """
    Summarize per-set metrics, per-session frequency, and notes for one exercise.
    Handles both weight/reps and duration-based exercises.
    """
    if not history_rows:
        return f"No history for exercise {exercise_id} between {start_date.strftime('%Y-%m-%d')} and {end_date.strftime('%Y-%m-%d')}."

    # Per-session grouping
    sessions = {}
    for row in history_rows:
        wid = row.get("workout_id")
        if not wid:
            continue
        sessions.setdefault(wid, {"sets": [], "start": row.get("workout_start_time")})
        sessions[wid]["sets"].append(row)

    # Aggregate metrics
    total_sets = len(history_rows)
    total_reps = 0
    total_volume_kg = 0.0
    max_weight_kg = 0.0
    max_est_1rm_kg = 0.0
    total_duration = 0.0
    max_duration = 0.0
    has_weight = False
    has_duration = False
    has_distance = False
    total_distance = 0.0
    max_distance = 0.0

    for row in history_rows:
        reps = row.get("reps")
        weight = row.get("weight_kg")
        duration = row.get("duration_seconds")
        distance = row.get("distance_meters")

        if isinstance(reps, (int, float)):
            total_reps += reps
        if isinstance(weight, (int, float)):
            has_weight = True
            if isinstance(reps, (int, float)):
                total_volume_kg += weight * reps
            max_weight_kg = max(max_weight_kg, weight)
            if isinstance(reps, (int, float)) and reps > 0:
                # Epley 1RM estimate
                est = weight * (1 + reps / 30)
                max_est_1rm_kg = max(max_est_1rm_kg, est)
        if isinstance(duration, (int, float)):
            has_duration = True
            total_duration += duration
            max_duration = max(max_duration, duration)
        if isinstance(distance, (int, float)):
            has_distance = True
            total_distance += distance
            max_distance = max(max_distance, distance)

    total_volume_lbs = kg_to_lbs(total_volume_kg)
    max_weight_lbs = kg_to_lbs(max_weight_kg)
    max_est_1rm_lbs = kg_to_lbs(max_est_1rm_kg)

    # Collect notes from workout payloads for this exercise
    notes_log = []
    for w in workouts:
        w_start = parse_iso_datetime(w.get("start_time"))
        if w_start and (w_start < start_date or w_start > end_date):
            continue
        for ex in w.get("exercises", []):
            if ex.get("exercise_template_id") == exercise_id:
                if ex.get("notes"):
                    notes_log.append(
                        f"{w.get('start_time','')[:10]} — {ex.get('notes')}"
                    )

    # Build readable output
    lines = [
        f"Exercise trend for {exercise_id} ({start_date.strftime('%Y-%m-%d')} → {end_date.strftime('%Y-%m-%d')}):",
        f"- Sessions: {len(sessions)} | Sets: {total_sets}",
    ]

    if has_weight:
        lines.append(
            f"- Weight metrics: max weight {max_weight_lbs} lbs; est 1RM {max_est_1rm_lbs} lbs; total volume {total_volume_lbs} lbs"
        )
    if has_duration:
        minutes = round(total_duration / 60, 1)
        lines.append(
            f"- Duration metrics: total {int(total_duration)}s ({minutes} min); max set {int(max_duration)}s"
        )
    if has_distance:
        miles = round(total_distance / 1609.34, 2)
        lines.append(
            f"- Distance metrics: total {int(total_distance)} m ({miles} mi); max set {int(max_distance)} m"
        )
    if total_reps:
        lines.append(f"- Total reps: {int(total_reps)}")

    # Session trends (oldest -> newest)
    lines.append("- Session trends (oldest → newest):")
    sorted_sessions_asc = sorted(
        sessions.items(),
        key=lambda kv: kv[1]["start"] or "",
    )
    for wid, info in sorted_sessions_asc[:30]:
        s_sets = info["sets"]
        sess_reps = 0
        sess_volume = 0.0
        sess_max_wt = 0.0
        sess_est_1rm = 0.0
        sess_duration = 0.0
        sess_distance = 0.0
        sess_max_set_volume = 0.0

        for s in s_sets:
            reps = s.get("reps")
            weight = s.get("weight_kg")
            duration = s.get("duration_seconds")
            distance = s.get("distance_meters")
            if isinstance(reps, (int, float)):
                sess_reps += reps
            if isinstance(weight, (int, float)):
                sess_max_wt = max(sess_max_wt, weight)
                if isinstance(reps, (int, float)):
                    sess_volume += weight * reps
                    sess_max_set_volume = max(sess_max_set_volume, weight * reps)
                    est = weight * (1 + reps / 30) if reps > 0 else weight
                    sess_est_1rm = max(sess_est_1rm, est)
            if isinstance(duration, (int, float)):
                sess_duration += duration
            if isinstance(distance, (int, float)):
                sess_distance += distance

        parts = [info["start"] or "unknown", f"{len(s_sets)} sets"]
        if sess_volume:
            parts.append(f"vol {kg_to_lbs(sess_volume)} lbs")
        if sess_max_set_volume:
            parts.append(f"max set vol {kg_to_lbs(sess_max_set_volume)} lbs")
        if sess_max_wt:
            parts.append(f"max {kg_to_lbs(sess_max_wt)} lbs")
        if sess_est_1rm:
            parts.append(f"1RM {kg_to_lbs(sess_est_1rm)} lbs")
        if sess_reps and not sess_volume:
            parts.append(f"reps {int(sess_reps)}")
        if sess_duration:
            parts.append(f"dur {int(sess_duration)}s")
        if sess_distance:
            parts.append(f"dist {int(sess_distance)}m")

        lines.append("  • " + " | ".join(parts) + f" (workout {wid})")
    if len(sorted_sessions_asc) > 30:
        lines.append(f"  • ... and {len(sorted_sessions_asc)-30} more sessions")

    # Notes
    if notes_log:
        lines.append("- Exercise notes (most recent first):")
        for note in notes_log[:10]:
            lines.append(f"  • {note}")
        if len(notes_log) > 10:
            lines.append(f"  • ... and {len(notes_log)-10} more notes")
    else:
        lines.append("- Exercise notes: none logged in this window.")

    return "\n".join(lines)


def fetch_exercise_trend(api_key: str, exercise_id: str, start_date: datetime, end_date: datetime) -> str:
    """
    Fetch history + workouts and render an LLM-friendly trend summary for one exercise.
    """
    start_date = ensure_utc(start_date)
    end_date = ensure_utc(end_date)
    history = fetch_exercise_history_range(api_key, exercise_id, start_date, end_date)
    # API efficiency: only fetch workouts that appear in history
    unique_workout_ids = {row.get("workout_id") for row in history if row.get("workout_id")}
    workouts = []
    for wid in unique_workout_ids:
        try:
            workouts.append(fetch_workout_by_id(api_key, wid))
        except Exception as e:
            # Skip missing/bad workouts but keep processing
            workouts.append({"id": wid, "start_time": None, "exercises": [], "notes_error": str(e)})
    return format_exercise_trend(history, workouts, exercise_id, start_date, end_date)


def fetch_recent_exercise_trend(api_key: str, exercise_id: str, days: int = 90) -> str:
    end_date = ensure_utc(datetime.utcnow())
    start_date = end_date - timedelta(days=days)
    return fetch_exercise_trend(api_key, exercise_id, start_date, end_date)
