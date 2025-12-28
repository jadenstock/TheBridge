"""
Weekly training review Lambda.

Fetches the past week's Hevy workouts, summarizes strengths/gaps with OpenAI,
and posts a concise review to Slack.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from typing import Any, Dict, List


def load_prompt(filename: str) -> str:
    prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "prompts", filename))
    with open(prompt_path, "r", encoding="utf-8") as prompt_file:
        return prompt_file.read()


def fetch_recent_workouts(api_key: str, days: int = 7) -> List[Dict[str, Any]]:
    """
    Fetch recent workouts from Hevy API.
    """
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    start_date_str = start_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_date_str = end_date.strftime('%Y-%m-%dT%H:%M:%SZ')

    from urllib.parse import quote
    url = f"https://api.hevyapp.com/v1/workouts?start_date={quote(start_date_str)}&end_date={quote(end_date_str)}&page_size=50"

    headers = {
        'accept': 'application/json',
        'api-key': api_key
    }

    print(f"Fetching workouts from {start_date_str} to {end_date_str}")

    req = urllib.request.Request(url, headers=headers, method='GET')

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            data = json.loads(response.read().decode('utf-8'))
            workouts = data.get('workouts', [])
            print(f"Fetched {len(workouts)} recent workouts")
            return workouts

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"Warning: Failed to fetch workouts {e.code}: {error_body}")
        return []
    except urllib.error.URLError as e:
        print(f"Warning: Network error fetching workouts: {str(e)}")
        return []


def format_workouts_for_context(workouts: List[Dict[str, Any]]) -> str:
    """
    Format workouts into a concise text block for OpenAI context.
    """
    if not workouts:
        return "No workouts logged in the last 7 days."

    output = ["**Workouts (last 7 days)**"]

    # Most recent first
    sorted_workouts = sorted(workouts, key=lambda w: w.get('start_time', ''), reverse=True)
    for i, workout in enumerate(sorted_workouts, 1):
        start_time = workout.get('start_time', '')
        title = workout.get('title', 'Untitled Workout')
        date_str = start_time[:10] if start_time else "Unknown date"
        exercises = workout.get('exercises', [])
        exercise_names = [ex.get('title', 'Unknown') for ex in exercises]
        output.append(f"{i}. {date_str} - {title}")
        if exercise_names:
            output.append(f"   Exercises: {', '.join(exercise_names[:8])}" + (" ..." if len(exercise_names) > 8 else ""))
        if workout.get('notes'):
            output.append(f"   Notes: {workout['notes']}")

    return "\n".join(output)


def call_openai_summary(workout_context: str, api_key: str) -> str:
    """
    Generate a weekly review via OpenAI.
    """
    system_prompt = load_prompt("weekly_review_system.txt")

    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": "gpt-5.1",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Here are the workouts from the past week:\n\n{workout_context}"}
        ],
        "temperature": 0.7,
        "max_completion_tokens": 1500
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    print("Calling OpenAI for weekly review...")

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            result = json.loads(response.read().decode('utf-8'))
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            raise Exception(f"Unexpected OpenAI response: {result}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise Exception(f"OpenAI API error {e.code}: {error_body}")


def post_to_slack(webhook_url: str, review_text: str) -> None:
    """
    Post the weekly review to Slack via webhook.
    """
    message = {
        'text': '📅 Weekly Training Review',
        'blocks': [
            {
                'type': 'section',
                'text': {'type': 'mrkdwn', 'text': f"*📅 Weekly Training Review*\n\n{review_text}"}
            }
        ]
    }

    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(message).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"Posted weekly review to Slack: {response.status}")
    except Exception as e:
        print(f"Failed to post weekly review to Slack: {str(e)}")


def handler(event, context):
    """
    Entry point for scheduled weekly review.
    """
    print(f"Starting weekly review at {datetime.utcnow().isoformat()}Z")
    print(f"Event: {json.dumps(event)}")

    hevy_api_key = os.environ.get('HEVY_API_KEY')
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')

    if not hevy_api_key or not openai_api_key or not slack_webhook_url:
        return {'statusCode': 500, 'body': 'Configuration error'}

    try:
        workouts = fetch_recent_workouts(hevy_api_key, days=7)
        workout_context = format_workouts_for_context(workouts)
        review = call_openai_summary(workout_context, openai_api_key)
        post_to_slack(slack_webhook_url, review)

        return {
            'statusCode': 200,
            'body': json.dumps({'success': True})
        }

    except Exception as e:
        error_msg = f"Failed to generate weekly review: {str(e)}"
        print(error_msg)
        return {
            'statusCode': 500,
            'body': json.dumps({'success': False, 'error': error_msg})
        }
