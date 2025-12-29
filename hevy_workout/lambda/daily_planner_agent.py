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

hevy_tools = import_module("hevy_tools")

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-5.1"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_prompt() -> str:
    prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "prompts", "daily_planner_agent.txt"))
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


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


def call_openai(system: str, user: str, openai_key: str, max_tokens: int = 1200) -> str:
    import urllib.request

    body = {
        "model": MODEL,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.6,
        "max_completion_tokens": max_tokens,
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


def handler(event, context):
    print("Event:", json.dumps(event))
    openai_key = os.environ["OPENAI_API_KEY"]
    hevy_api_key = os.environ["HEVY_API_KEY"]
    slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
    channel = os.environ.get("WEEKLY_GOALS_CHANNEL", "")
    table_name = os.environ.get("CONVERSATION_TABLE_NAME")

    if not slack_token or not channel:
        return {"statusCode": 500, "body": "Slack not configured"}

    system_prompt = load_prompt()

    if event.get("is_thread_reply"):
        return handle_thread(event, system_prompt, openai_key, hevy_api_key, slack_token, channel, table_name)
    else:
        return handle_scheduled(system_prompt, openai_key, hevy_api_key, slack_token, channel, table_name)


def build_context(hevy_api_key: str, days_workouts: int = 9, days_frequency: int = 30) -> str:
    weekly_goal = hevy_tools.fetch_latest_weekly_goal_doc()
    workouts = hevy_tools.fetch_and_format_recent_workouts(api_key=hevy_api_key, days=days_workouts)
    freq = hevy_tools.fetch_recent_exercise_frequency(api_key=hevy_api_key, days=days_frequency)
    return f"Weekly goals:\n{weekly_goal}\n\nRecent workouts (last {days_workouts}d):\n{workouts}\n\nExercise frequency (last {days_frequency}d):\n{freq}"


def handle_scheduled(system_prompt, openai_key, hevy_api_key, slack_token, channel, table_name):
    context = build_context(hevy_api_key, days_workouts=9, days_frequency=30)
    user_prompt = (
        "Scheduled daily planner kickoff for today. Propose 1-3 workout options aligned to weekly goals, "
        "respecting last 2 days for recovery. Include main lifts/accessories and targets where clear. "
        "Keep concise for Slack.\n\nContext:\n" + context
    )
    draft = call_openai(system_prompt, user_prompt, openai_key, max_tokens=900)
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
    draft = call_openai(system_prompt, user_prompt, openai_key, max_tokens=900)
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
