"""
Weekly goals agent.

Behaviors:
- Scheduled every Sunday: fetch latest coach doc + last week of workouts, generate 1-3 themed options, post to Slack thread, and record the thread for follow-ups.
- Thread replies: refine the plan using conversation context, exercise trends/frequency, and lock in a weekly goals doc on "lock it in".
"""

import json
import os
import boto3
from importlib import import_module
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
import traceback

hevy_tools = import_module("hevy_tools")

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
MODEL = "gpt-5.1"

dynamodb = boto3.resource("dynamodb")
s3_client = boto3.client("s3")
http = boto3.client("lambda")  # unused but kept for parity if needed
slack_client = boto3.client("lambda")  # placeholder; using urllib to call slack api below


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_prompt() -> str:
    prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "prompts", "weekly_goals_agent.txt"))
    with open(prompt_path, "r", encoding="utf-8") as f:
        return f.read()


def post_slack_message(token: str, channel: str, text: str, thread_ts: str = None) -> Dict[str, Any]:
    import urllib.request

    payload = {
        "channel": channel,
        "text": text,
    }
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
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
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


def store_message(table_name: str, thread_ts: str, role: str, message_text: str, agent: str = "weekly_goals"):
    table = dynamodb.Table(table_name)
    ttl = int((datetime.utcnow() + timedelta(days=14)).timestamp())
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
    return [
        {"role": item.get("role"), "content": item.get("message_text")}
        for item in resp.get("Items", [])
    ]


def handler(event, context):
    try:
        print("Event:", json.dumps(event))
        openai_key = os.environ["OPENAI_API_KEY"]
        hevy_api_key = os.environ["HEVY_API_KEY"]
        slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
        channel = os.environ.get("WEEKLY_GOALS_CHANNEL", "")
        table_name = os.environ.get("CONVERSATION_TABLE_NAME")

        if not slack_token or not channel:
            return {"statusCode": 500, "body": "Slack not configured"}

        system_prompt = load_prompt()

        # Detect invocation type
        is_thread_reply = event.get("is_thread_reply")
        if is_thread_reply:
            return handle_thread_reply(event, system_prompt, openai_key, hevy_api_key, slack_token, channel, table_name)
        else:
            return handle_scheduled_kickoff(system_prompt, openai_key, hevy_api_key, slack_token, channel, table_name)
    except Exception as e:
        err = f"Weekly goals agent failed: {str(e)}"
        print(err)
        traceback.print_exc()
        # Attempt to notify in Slack if possible
        slack_token = os.environ.get("SLACK_BOT_TOKEN", "")
        channel = os.environ.get("WEEKLY_GOALS_CHANNEL", "")
        if slack_token and channel:
            try:
                post_slack_message(slack_token, channel, f"Weekly goals agent error: {err}")
            except Exception as e2:
                print(f"Failed to post error to Slack: {e2}")
        return {"statusCode": 500, "body": err}


def build_data_pack(hevy_api_key: str, days_workouts: int = 7, days_frequency: int = 30) -> str:
    coach_doc = hevy_tools.fetch_latest_coach_doc()
    workouts = hevy_tools.fetch_and_format_recent_workouts(api_key=hevy_api_key, days=days_workouts)
    frequency = hevy_tools.fetch_recent_exercise_frequency(api_key=hevy_api_key, days=days_frequency)
    return f"Latest coach doc:\n{coach_doc}\n\nRecent workouts (last {days_workouts}d):\n{workouts}\n\nExercise frequency (last {days_frequency}d):\n{frequency}"


def handle_scheduled_kickoff(system_prompt: str, openai_key: str, hevy_api_key: str, slack_token: str, channel: str, table_name: str):
    data_pack = build_data_pack(hevy_api_key, days_workouts=7, days_frequency=30)
    user_prompt = f"PHASE 1 kickoff. Generate 1-3 weekly goal options for the coming week.\n\nContext:\n{data_pack}"
    draft = call_openai(system_prompt, user_prompt, openai_key, max_tokens=1400)
    if not draft or not draft.strip():
        print("Empty OpenAI response on kickoff; logging context for debugging.")
        draft = "Weekly goals agent did not get a usable response. Please rerun or check logs."

    # Post to Slack (new thread)
    resp = post_slack_message(slack_token, channel, draft)
    thread_ts = resp.get("ts")
    if table_name and thread_ts:
        store_message(table_name, thread_ts, "assistant", draft, agent="weekly_goals")
    return {"statusCode": 200, "body": json.dumps({"thread_ts": thread_ts, "posted": True})}


def handle_thread_reply(event, system_prompt: str, openai_key: str, hevy_api_key: str, slack_token: str, channel: str, table_name: str):
    thread_ts = event.get("thread_ts")
    user_text = event.get("user_message", "")

    if not thread_ts:
        return {"statusCode": 400, "body": "Missing thread_ts"}

    history = get_history(table_name, thread_ts) if table_name else []
    history_text = "\n".join([f"{m['role']}: {m['content']}" for m in history])

    # Gather additional context: frequency and a couple of trends (last 30d) for relevant exercises from user text?
    # For simplicity, include frequency + last 4 months history summary.
    data_pack = build_data_pack(hevy_api_key, days_workouts=21, days_frequency=60)

    lock_it = "lock it in" in user_text.lower()
    action = "Produce a refined plan and wait" if not lock_it else "Produce final weekly goals doc now"

    user_prompt = (
        f"PHASE 2 refinement.\nUser said: {user_text}\n\n"
        f"Prior thread:\n{history_text}\n\n"
        f"Context:\n{data_pack}\n\n"
        f"Instruction: {action}. If locking, provide a final weekly goal doc (title + body) concisely."
    )

    draft = call_openai(system_prompt, user_prompt, openai_key, max_tokens=1400)
    if not draft or not draft.strip():
        print("Empty OpenAI response on refinement; logging context for debugging.")
        draft = "Weekly goals agent did not get a usable response. Please rerun or check logs."

    # If lock, write doc to S3
    lock_info = None
    if lock_it:
        title_line = draft.splitlines()[0].strip() if draft else "Weekly Goals"
        key = hevy_tools.write_weekly_goal_doc(draft, title_line)
        lock_info = f"Saved weekly goals to s3://{key}"
        draft = draft + f"\n\n{lock_info}"

    resp = post_slack_message(slack_token, channel, draft, thread_ts=thread_ts)
    if table_name:
        store_message(table_name, thread_ts, "user", user_text, agent="weekly_goals")
        store_message(table_name, thread_ts, "assistant", draft, agent="weekly_goals")
    return {
        "statusCode": 200,
        "body": json.dumps({"thread_ts": thread_ts, "posted": True, "lock_info": lock_info}),
    }
