"""
Biweekly coach doc refresher.

- Runs every 2 weeks.
- Gathers: last 14 days workouts, exercise frequency, latest weekly goal doc, latest coach doc.
- Produces a minimally changed coach doc (incremental updates), saves to S3, and posts a summary of changes to Slack.
"""

import json
import os
from importlib import import_module
from datetime import datetime, timedelta
from typing import Dict, Any

hevy_tools = import_module("hevy_tools")

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-5.1"


def load_system_prompt() -> str:
    prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "prompts", "coach_doc_refresher.txt"))
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def call_openai(system: str, user: str, api_key: str, max_tokens: int = 1500) -> str:
    import urllib.request

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_completion_tokens": max_tokens,
    }
    req = urllib.request.Request(
        OPENAI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def post_to_slack(token: str, channel: str, text: str) -> Dict[str, Any]:
    import urllib.request

    payload = {"channel": channel, "text": text}
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        if not data.get("ok"):
            raise RuntimeError(f"Slack postMessage failed: {data}")
        return data


def handler(event, context):
    print("Coach doc refresher event:", json.dumps(event))
    hevy_api_key = os.environ.get("HEVY_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = os.environ.get("WEEKLY_GOALS_CHANNEL", "")

    if not all([hevy_api_key, openai_key, slack_token, channel]):
        return {"statusCode": 500, "body": "Missing configuration"}

    # Gather context
    latest_coach_doc = hevy_tools.fetch_latest_coach_doc()
    latest_weekly_goals = hevy_tools.fetch_latest_weekly_goal_doc()
    workouts_text = hevy_tools.fetch_and_format_recent_workouts(api_key=hevy_api_key, days=14)
    frequency_text = hevy_tools.fetch_recent_exercise_frequency(api_key=hevy_api_key, days=60)

    user_prompt = (
        "Review and minimally update the coach doc. Keep structure and make small, justified changes only.\n\n"
        f"Latest coach doc:\n{latest_coach_doc}\n\n"
        f"Latest weekly goals:\n{latest_weekly_goals}\n\n"
        f"Workouts (last 14d):\n{workouts_text}\n\n"
        f"Exercise frequency (last 60d):\n{frequency_text}\n\n"
        "Return the full updated coach doc. Then, provide a short summary of changes (for Slack)."
    )

    system_prompt = load_system_prompt()
    updated_doc = call_openai(system_prompt, user_prompt, openai_key, max_tokens=1400)

    # Persist updated doc
    key = hevy_tools.write_coach_doc(updated_doc)

    # Extract change summary (naive: last paragraph after a delimiter if present)
    summary = "Updated coach doc saved."
    if "\nSummary:" in updated_doc:
        summary = updated_doc.split("\nSummary:", 1)[-1].strip()
    slack_text = f"🗂️ Coach doc refreshed (minimal changes).\nSaved to s3://{key}\nChanges:\n{summary}"
    post_to_slack(slack_token, channel, slack_text)

    return {"statusCode": 200, "body": json.dumps({"success": True, "s3_key": key})}
