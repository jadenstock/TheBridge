import json
import os
import urllib.request
import urllib.error
from importlib import import_module
from datetime import datetime
from typing import List

from hevy_workout.config import get_agent_config, get_openai_api_url, load_prompt_text

hevy_tools = import_module("hevy_tools")

AGENT_CONFIG = get_agent_config("weekly_review")
OPENAI_API_URL = get_openai_api_url()
PROMPT_FILE = AGENT_CONFIG["prompt_file"]
MODEL = AGENT_CONFIG["model"]
TEMPERATURE = AGENT_CONFIG["temperature"]
MAX_COMPLETION_TOKENS = AGENT_CONFIG["max_completion_tokens"]


def call_openai_summary(goal_doc: str, workouts_text: str, api_key: str) -> str:
    system_prompt = load_prompt_text(__file__, PROMPT_FILE)

    url = OPENAI_API_URL
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"Weekly goal doc (latest):\n{goal_doc}\n\nWorkouts from past week:\n{workouts_text}",
            },
        ],
        "temperature": TEMPERATURE,
        "max_completion_tokens": MAX_COMPLETION_TOKENS,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    print("Calling OpenAI for weekly review...")

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
            if "choices" in result and len(result["choices"]) > 0:
                return result["choices"][0]["message"]["content"]
            raise Exception(f"Unexpected OpenAI response: {result}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        raise Exception(f"OpenAI API error {e.code}: {error_body}")


def post_to_slack(webhook_url: str, review_text: str) -> None:
    message = {
        "text": "📅 Weekly Training Review",
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*📅 Weekly Training Review*\n\n{review_text}"},
            }
        ],
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(message).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"Posted weekly review to Slack: {response.status}")
    except Exception as e:
        print(f"Failed to post weekly review to Slack: {str(e)}")


def handler(event, context):
    print(f"Starting weekly review at {datetime.utcnow().isoformat()}Z")
    print(f"Event: {json.dumps(event)}")

    hevy_api_key = os.environ.get("HEVY_API_KEY")
    openai_api_key = os.environ.get("OPENAI_API_KEY")
    slack_webhook_url = os.environ.get("SLACK_WEBHOOK_URL")

    if not hevy_api_key or not openai_api_key or not slack_webhook_url:
        return {"statusCode": 500, "body": "Configuration error"}

    try:
        goal_doc = hevy_tools.fetch_latest_weekly_goal_doc()
        workouts_text = hevy_tools.fetch_and_format_recent_workouts(api_key=hevy_api_key, days=7)
        review = call_openai_summary(goal_doc, workouts_text, openai_api_key)
        post_to_slack(slack_webhook_url, review)

        return {
            "statusCode": 200,
            "body": json.dumps({"success": True}),
        }

    except Exception as e:
        error_msg = f"Failed to generate weekly review: {str(e)}"
        print(error_msg)
        return {
            "statusCode": 500,
            "body": json.dumps({"success": False, "error": error_msg}),
        }
