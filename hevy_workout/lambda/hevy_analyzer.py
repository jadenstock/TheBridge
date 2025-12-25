"""
Lambda function to analyze Hevy workout data using OpenAI.

Fetches workout details from Hevy API, analyzes with OpenAI,
and posts insights to Slack.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from typing import Dict, Any


def fetch_workout_from_hevy(workout_id: str, api_key: str) -> Dict[str, Any]:
    """
    Fetch workout details from Hevy API.

    Args:
        workout_id: The workout ID from the webhook
        api_key: Hevy API key

    Returns:
        Workout data as dictionary
    """
    url = f"https://api.hevyapp.com/v1/workouts/{workout_id}"

    headers = {
        'accept': 'application/json',
        'api-key': api_key
    }

    print(f"Fetching workout {workout_id} from Hevy API...")

    req = urllib.request.Request(
        url,
        headers=headers,
        method='GET'
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            workout_data = json.loads(response.read().decode('utf-8'))
            print(f"Successfully fetched workout data")
            return workout_data

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise Exception(f"Hevy API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise Exception(f"Network error fetching workout: {str(e)}")


def format_workout_for_analysis(workout: Dict[str, Any]) -> str:
    """
    Format workout data into readable text for AI analysis.

    Args:
        workout: Raw workout data from Hevy API

    Returns:
        Formatted string describing the workout
    """
    from datetime import datetime

    output = []

    # Basic workout info
    start_time = workout.get('start_time', 'Unknown')
    end_time = workout.get('end_time')

    output.append(f"**Workout Date**: {start_time}")

    # Calculate duration if both times available
    if start_time != 'Unknown' and end_time:
        try:
            start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            duration_seconds = int((end_dt - start_dt).total_seconds())
            duration_minutes = duration_seconds // 60
            output.append(f"**Duration**: {duration_minutes} minutes")
        except:
            output.append(f"**Duration**: Unknown")
    else:
        output.append(f"**Duration**: Unknown")

    output.append(f"**Title**: {workout.get('title', 'Untitled Workout')}")

    if workout.get('description'):
        output.append(f"**Description**: {workout['description']}")

    # Exercises
    exercises = workout.get('exercises', [])
    if exercises:
        output.append(f"\n**Exercises ({len(exercises)} total)**:\n")
        for i, exercise in enumerate(exercises, 1):
            exercise_name = exercise.get('title', 'Unknown Exercise')
            output.append(f"\n{i}. **{exercise_name}**")

            # Include exercise notes if present
            if exercise.get('notes'):
                output.append(f"   Notes: {exercise['notes']}")

            # Sets
            sets = exercise.get('sets', [])
            if sets:
                output.append(f"   Sets: {len(sets)}")
                for j, set_data in enumerate(sets, 1):
                    weight = set_data.get('weight_kg', set_data.get('weight_lbs'))
                    reps = set_data.get('reps')
                    distance = set_data.get('distance_meters', set_data.get('distance_miles'))
                    time = set_data.get('duration_seconds')
                    rpe = set_data.get('rpe')

                    set_info = f"   Set {j}: "
                    if weight is not None:
                        # Convert kg to lbs and round to 1 decimal place
                        weight_lbs = round(weight * 2.20462, 1)
                        set_info += f"{weight_lbs}lbs × {reps} reps" if reps else f"{weight_lbs}lbs"
                    elif distance is not None:
                        set_info += f"{distance}m"
                        if time:
                            set_info += f" in {time}s"
                    elif time is not None:
                        set_info += f"{time}s"
                        if weight:
                            weight_lbs = round(weight * 2.20462, 1)
                            set_info += f" @ {weight_lbs}lbs"
                    elif reps is not None:
                        set_info += f"{reps} reps"

                    # Add RPE if present
                    if rpe is not None:
                        set_info += f" (RPE: {rpe})"

                    output.append(set_info)

    # Notes
    if workout.get('notes'):
        output.append(f"\n**Notes**: {workout['notes']}")

    return '\n'.join(output)


def call_openai(workout_text: str, api_key: str) -> str:
    """
    Send workout data to OpenAI and get analysis.

    Args:
        workout_text: Formatted workout data
        api_key: OpenAI API key

    Returns:
        Analysis text from OpenAI
    """

    system_prompt = """You are a knowledgeable fitness coach analyzing workout data for a Slack message.

IMPORTANT NOTES:
- All weights are in POUNDS (lbs), not kilograms
- This will be posted to Slack, so use Slack markdown formatting
- Exercise names, sets, reps, RPE values, and notes are all provided - use them!

TASK:
Provide a brief, encouraging analysis of the workout with actionable insights.

ANALYSIS SHOULD INCLUDE:
- Overall workout quality assessment (reference specific exercises by name)
- Notable achievements or impressive sets (mention specific weights/reps/RPE)
- Exercise selection and programming observations
- Volume and intensity analysis (use the RPE values when discussing intensity)
- Suggestions for progression or areas to focus on
- Recovery considerations

TONE:
- Supportive and motivating
- Specific and technical where appropriate (mention actual exercises, weights, and reps)
- Brief and actionable (keep it under 300 words)
- Use emojis sparingly but effectively (💪 🔥 ⚡ 🎯 ✅)

OUTPUT FORMAT (using Slack markdown):
- Short headline summarizing the workout (use *bold* not **bold**)
- 3-5 key observations (be specific - mention exercise names, weights, RPE)
- 1-2 actionable recommendations
- Remember: Use single asterisks (*text*) for bold in Slack, not double asterisks"""

    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": "gpt-5.1",
        "messages": [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": f"Here is the workout data:\n\n{workout_text}"
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1000
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


def post_to_slack(webhook_url: str, workout_text: str, analysis: str) -> None:
    """
    Post workout analysis to Slack.

    Args:
        webhook_url: Slack webhook URL
        workout_text: Formatted workout data
        analysis: The AI analysis text (already in Slack markdown format)
    """
    # Analysis is already formatted for Slack
    slack_text = analysis

    message = {
        'text': '💪 Hevy Workout Analysis',
        'blocks': [
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': slack_text
                }
            },
            {
                'type': 'divider'
            },
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f"```{workout_text[:500]}{'...' if len(workout_text) > 500 else ''}```"
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
        # Don't raise - we still want to complete even if Slack fails


def handler(event, context):
    """
    Lambda handler to analyze Hevy workout.

    Event should contain:
    - workoutId: The workout ID from Hevy webhook

    Environment variables:
    - HEVY_API_KEY: Hevy API key
    - OPENAI_API_KEY: OpenAI API key
    - SLACK_WEBHOOK_URL: Slack webhook URL
    """
    print(f"Starting workout analysis at {datetime.utcnow().isoformat()}Z")
    print(f"Event: {json.dumps(event)}")

    # Get configuration from environment
    hevy_api_key = os.environ.get('HEVY_API_KEY')
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')

    if not hevy_api_key:
        return {
            'statusCode': 500,
            'body': 'Error: HEVY_API_KEY not configured'
        }

    if not openai_api_key:
        return {
            'statusCode': 500,
            'body': 'Error: OPENAI_API_KEY not configured'
        }

    # Get workout ID from event
    workout_id = event.get('workoutId')
    if not workout_id:
        return {
            'statusCode': 400,
            'body': 'Error: workoutId not provided in event'
        }

    try:
        # Step 1: Fetch workout from Hevy API
        workout_data = fetch_workout_from_hevy(workout_id, hevy_api_key)
        print(f"Got workout data")

        # Step 2: Format for analysis
        workout_text = format_workout_for_analysis(workout_data)
        print(f"Formatted workout: {len(workout_text)} characters")

        # Step 3: Analyze with OpenAI
        analysis = call_openai(workout_text, openai_api_key)
        print("Analysis complete")

        # Step 4: Post to Slack if webhook configured
        if slack_webhook_url:
            post_to_slack(slack_webhook_url, workout_text, analysis)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'workoutId': workout_id,
                'analysis': analysis
            })
        }

    except Exception as e:
        error_msg = f"Failed to analyze workout: {str(e)}"
        print(f"Error: {error_msg}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': error_msg
            })
        }
