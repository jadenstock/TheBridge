"""
Daily workout planner agent.

Scheduled Mon/Wed/Fri noon PT:
- Pull latest weekly goal doc, recent workouts (last 9 days to include two days before week), and propose 1-3 workout options for today that advance weekly goals and respect recent sessions.
- Post to Slack thread.

Thread replies:
- Refine based on user input and mid-workout updates (equipment issues, soreness).
- Use exercise frequency/trends to set targets (not full set-by-set prescription).
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from importlib import import_module

from config import get_agent_config, get_openai_api_url, load_prompt_text

hevy_tools = import_module("hevy_tools")

AGENT_CONFIG = get_agent_config("daily_planner")
OPENAI_API_URL = get_openai_api_url()
MODEL = AGENT_CONFIG["model"]
TEMPERATURE = AGENT_CONFIG["temperature"]
PROMPT_FILE = AGENT_CONFIG["prompt_file"]
MAX_COMPLETION_TOKENS = AGENT_CONFIG["max_completion_tokens"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_prompt() -> str:
    """Load the system prompt configured for the daily planner."""
    return load_prompt_text(__file__, PROMPT_FILE)


def post_slack_message(token: str, channel: str, text: str, thread_ts: str = None) -> Dict[str, Any]:
    import urllib.request

    payload = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts

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


def call_openai(system: str, user: str, openai_key: str) -> str:
    import urllib.request

    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": TEMPERATURE,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
    }
    req = urllib.request.Request(
        OPENAI_API_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {openai_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]


def log_draft_length(draft: str, context_label: str) -> None:
    """Record the character count of the OpenAI draft to aid debugging."""
    length = len(draft) if draft else 0
    print(f"[daily_planner] {context_label} draft length: {length} chars")


def handler(event, context):
    openai_key = os.environ["OPENAI_API_KEY"]
    hevy_api_key = os.environ["HEVY_API_KEY"]
    slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = event.get("channel_id") or os.environ.get("WEEKLY_GOALS_CHANNEL", "")
    table_name = os.environ.get("CONVERSATION_TABLE_NAME")
    user_message = event.get("user_message")

    event_type = "thread_reply" if event.get("is_thread_reply") else "scheduled"
    print(f"[daily_planner] Handling {event_type} request for channel {channel or 'unknown'} user {event.get('user_id')}")

    if not slack_token or not channel:
        return {"statusCode": 500, "body": "Slack not configured"}

    system_prompt = load_prompt()

    if event.get("is_thread_reply"):
        return handle_thread(event, system_prompt, openai_key, hevy_api_key, slack_token, channel, table_name)
    else:
        return handle_scheduled(
            system_prompt,
            openai_key,
            hevy_api_key,
            slack_token,
            channel,
            table_name,
            user_message=user_message,
        )


def build_context(hevy_api_key: str, days_workouts: int = 9, days_frequency: int = 30) -> str:
    weekly_goal = hevy_tools.fetch_latest_weekly_goal_doc()
    workouts = hevy_tools.fetch_and_format_recent_workouts(api_key=hevy_api_key, days=days_workouts)
    freq = hevy_tools.fetch_recent_exercise_frequency(api_key=hevy_api_key, days=days_frequency)
    return f"Weekly goals:\n{weekly_goal}\n\nRecent workouts (last {days_workouts}d):\n{workouts}\n\nExercise frequency (last {days_frequency}d):\n{freq}"


def handle_scheduled(
    system_prompt,
    openai_key,
    hevy_api_key,
    slack_token,
    channel,
    table_name,
    user_message: str | None = None,
):
    context = build_context(hevy_api_key, days_workouts=9, days_frequency=30)
    user_prompt = (
        "Scheduled daily planner kickoff for today. Propose 1-3 workout options aligned to weekly goals, "
        "respecting last 2 days for recovery. Include main lifts/accessories and targets where clear. "
        "Keep concise for Slack.\n\nContext:\n" + context
    )
    if user_message:
        user_prompt += f"\n\nUser request: {user_message}"
    draft = call_openai(system_prompt, user_prompt, openai_key)
    log_draft_length(draft, "scheduled")
    resp = post_slack_message(slack_token, channel, draft)
    thread_ts = resp.get("ts")
    if table_name and thread_ts:
        store_message(table_name, thread_ts, "assistant", draft, agent="daily_planner")
    return {"statusCode": 200, "body": json.dumps({"thread_ts": thread_ts, "posted": True})}


def handle_thread(event, system_prompt, openai_key, hevy_api_key, slack_token, channel, table_name):
    thread_ts = event.get("thread_ts")
    user_text = event.get("user_message", "")
    if not thread_ts:
        return {"statusCode": 400, "body": "Missing thread_ts"}

    history = get_history(table_name, thread_ts) if table_name else []
    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history])
    context = build_context(hevy_api_key, days_workouts=9, days_frequency=30)

    user_prompt = (
        f"Thread refinement for today's workout.\nUser said: {user_text}\n\n"
        f"Prior thread:\n{history_text}\n\nContext:\n{context}\n\n"
        "Adjust plan/targets respecting soreness/equipment notes. Keep concise."
    )
    draft = call_openai(system_prompt, user_prompt, openai_key)
    log_draft_length(draft, "thread")
    resp = post_slack_message(slack_token, channel, draft, thread_ts=thread_ts)
    if table_name:
        store_message(table_name, thread_ts, "user", user_text, agent="daily_planner")
        store_message(table_name, thread_ts, "assistant", draft, agent="daily_planner")
    return {"statusCode": 200, "body": json.dumps({"thread_ts": thread_ts, "posted": True})}


# Shared storage helpers
import boto3

dynamodb = boto3.resource("dynamodb")


def store_message(table_name: str, thread_ts: str, role: str, message_text: str, agent: str):
    table = dynamodb.Table(table_name)
    ttl = int((datetime.utcnow() + timedelta(days=7)).timestamp())
    table.put_item(
        Item={
            "thread_id": thread_ts,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "role": role,
            "message_text": message_text,
            "agent": agent,
            "expires_at": ttl,
        }
    )


def get_history(table_name: str, thread_ts: str) -> List[Dict[str, str]]:
    table = dynamodb.Table(table_name)
    resp = table.query(
        KeyConditionExpression="thread_id = :t",
        ExpressionAttributeValues={":t": thread_ts},
        ScanIndexForward=True,
    )
    return [{"role": item.get("role"), "content": item.get("message_text")} for item in resp.get("Items", [])]
