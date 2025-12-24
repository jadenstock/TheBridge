"""
Lambda function to analyze Crystal Mountain ski conditions using OpenAI.

Invokes the data fetcher Lambda to get forecast data, then sends to OpenAI
for expert analysis of weekday ski conditions.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any


def invoke_data_fetcher(data_fetcher_function_name: str) -> str:
    """
    Invoke the data fetcher Lambda and return the markdown forecast.

    Args:
        data_fetcher_function_name: Name of the data fetcher Lambda function

    Returns:
        Markdown string with forecast data
    """
    import boto3

    lambda_client = boto3.client('lambda')

    print(f"Invoking data fetcher Lambda: {data_fetcher_function_name}")

    response = lambda_client.invoke(
        FunctionName=data_fetcher_function_name,
        InvocationType='RequestResponse'
    )

    payload = json.loads(response['Payload'].read())

    if payload.get('statusCode') != 200:
        raise Exception(f"Data fetcher failed: {payload}")

    return payload['body']


def call_openai(forecast_markdown: str, api_key: str) -> str:
    """
    Send forecast data to OpenAI and get analysis.

    Args:
        forecast_markdown: The markdown forecast data
        api_key: OpenAI API key

    Returns:
        Analysis text from OpenAI
    """

    system_prompt = """You are an expert Pacific Northwest skier analyzing weekday-only ski conditions at Crystal Mountain.

INPUT:
- Forecast and snow data for Crystal Mountain
- Assume report is generated daily around 6 PM PST
- The skier has a WEEKDAY-ONLY pass (Mon–Fri)

TASK:
Produce a concise weekday ski conditions report covering ALL upcoming weekdays within the 7-day forecast window.

IMPORTANT: Include EVERY weekday (Mon-Fri) that appears in the forecast, starting from:
- Today if it's a weekday and there's still skiing time left (after 6 PM report time)
- Tomorrow if today is mostly over or a weekend
- Include weekdays from the current week AND next week if they fall within the 7-day forecast

For EACH weekday:
- Include the FULL DATE (e.g. Wed 12/25 or 2025-12-25)
- Provide a one-line ski-quality summary (what the day will ski like)
- Assign a score from 0–10 based on:
  recent snowfall (last 48h), snow quality (temps during + overnight low),
  wind/lift reliability, visibility, and weekday crowd advantage
- Add up to 4 relevant emojis (❄️ ☀️ ⚠️ 🔥 🚫)

At the end:
- Identify ONE "Best Weekday to Ski" if applicable
- Include a short "Cycle Summary" (2–4 sentences max) describing the
  overall weather pattern using technical ski-relevant language
  (e.g. storm cycle, refresh window, consolidation, warmup, wind loading).
- Be decisive and consistent across daily runs; this is a decision tool,
  not a weather forecast.

OUTPUT FORMAT:
- Header
- Bullet list per weekday (with dates)
- Best Bet line
- Cycle Summary"""

    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": "gpt-4o",
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"Here is the forecast data for Crystal Mountain:\n\n{forecast_markdown}"
            }
        ],
        "temperature": 0.7,
        "max_tokens": 2000
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    print("Calling OpenAI API...")

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
            else:
                raise Exception(f"Unexpected OpenAI response: {result}")

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise Exception(f"OpenAI API error {e.code}: {error_body}")


def post_to_slack(webhook_url: str, analysis: str) -> None:
    """
    Post ski analysis to Slack.

    Args:
        webhook_url: Slack webhook URL
        analysis: The ski analysis text
    """
    # Convert markdown headers to Slack formatting
    slack_text = analysis.replace('**', '*')

    message = {
        'text': f'🎿 Crystal Mountain Weekday Ski Report',
        'blocks': [
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': slack_text
                }
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
            print(f"Posted to Slack: {response.status}")
    except Exception as e:
        print(f"Failed to post to Slack: {str(e)}")
        # Don't raise - we still want to return the analysis even if Slack fails


def handler(event, context):
    """
    Lambda handler to analyze ski conditions.

    Environment variables:
    - DATA_FETCHER_FUNCTION_NAME: Name of the data fetcher Lambda
    - OPENAI_API_KEY: OpenAI API key
    - SLACK_WEBHOOK_URL: Slack webhook URL (optional)
    """
    print(f"Starting ski analysis at {datetime.utcnow().isoformat()}Z")

    # Get configuration from environment
    data_fetcher_function = os.environ.get('DATA_FETCHER_FUNCTION_NAME')
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')

    if not data_fetcher_function:
        return {
            'statusCode': 500,
            'body': 'Error: DATA_FETCHER_FUNCTION_NAME not configured'
        }

    if not openai_api_key:
        return {
            'statusCode': 500,
            'body': 'Error: OPENAI_API_KEY not configured'
        }

    try:
        # Step 1: Get forecast data
        forecast_markdown = invoke_data_fetcher(data_fetcher_function)
        print(f"Got forecast data: {len(forecast_markdown)} characters")

        # Step 2: Analyze with OpenAI
        analysis = call_openai(forecast_markdown, openai_api_key)
        print("Analysis complete")

        # Step 3: Post to Slack if webhook configured
        if slack_webhook_url and slack_webhook_url != "NOT_CONFIGURED":
            post_to_slack(slack_webhook_url, analysis)

        # Step 4: Format output
        output = f"# Crystal Mountain Weekday Ski Report\n\n"
        output += f"**Generated**: {datetime.utcnow().isoformat()}Z\n\n"
        output += "---\n\n"
        output += analysis

        return {
            'statusCode': 200,
            'body': output
        }

    except Exception as e:
        error_msg = f"# Error\n\nFailed to generate ski analysis: {str(e)}"
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': error_msg
        }
