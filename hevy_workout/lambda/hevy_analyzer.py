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


def load_prompt(filename: str) -> str:
    prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "prompts", filename))
    with open(prompt_path, "r", encoding="utf-8") as prompt_file:
        return prompt_file.read()


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


def fetch_exercise_history(exercise_id: str, api_key: str, start_date: str, end_date: str) -> Dict[str, Any]:
    """
    Fetch exercise history from Hevy API.

    Args:
        exercise_id: The exercise ID from the workout
        api_key: Hevy API key
        start_date: Start date in ISO format (e.g., '2025-09-01T00:00:00Z')
        end_date: End date in ISO format (e.g., '2025-12-31T23:59:59Z')

    Returns:
        Exercise history data as dictionary
    """
    # URL encode the dates
    from urllib.parse import quote

    url = f"https://api.hevyapp.com/v1/exercise_history/{exercise_id}?start_date={quote(start_date)}&end_date={quote(end_date)}"

    headers = {
        'accept': 'application/json',
        'api-key': api_key
    }

    print(f"Fetching history for exercise {exercise_id}...")

    req = urllib.request.Request(
        url,
        headers=headers,
        method='GET'
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            history_data = json.loads(response.read().decode('utf-8'))
            print(f"Successfully fetched exercise history")
            return history_data

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"Warning: Failed to fetch exercise history {e.code}: {error_body}")
        # Return empty history rather than failing the whole analysis
        return {}
    except urllib.error.URLError as e:
        print(f"Warning: Network error fetching exercise history: {str(e)}")
        return {}


def format_workout_for_analysis(workout: Dict[str, Any], exercise_histories: Dict[str, Dict[str, Any]] = None) -> str:
    """
    Format workout data into readable text for AI analysis.

    Args:
        workout: Raw workout data from Hevy API
        exercise_histories: Dictionary mapping exercise IDs to their history data

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
            exercise_id = exercise.get('exercise_template_id')
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

            # Add exercise history if available
            if exercise_histories and exercise_id and exercise_id in exercise_histories:
                history = exercise_histories[exercise_id]
                output.append(f"\n   **Historical Context**:")

                # Format history data - API returns flat list of sets grouped by workout
                history_sets = history.get('exercise_history', [])
                if history_sets:
                    # Group sets by workout
                    workouts_dict = {}
                    for set_data in history_sets:
                        workout_id = set_data.get('workout_id')
                        if workout_id not in workouts_dict:
                            workouts_dict[workout_id] = {
                                'start_time': set_data.get('workout_start_time', 'Unknown'),
                                'title': set_data.get('workout_title', ''),
                                'sets': []
                            }
                        workouts_dict[workout_id]['sets'].append(set_data)

                    # Get last 5 workouts (excluding current workout)
                    workouts = sorted(workouts_dict.values(), key=lambda w: w['start_time'])
                    recent_workouts = [w for w in workouts if w['start_time'] < workout.get('start_time', '')][-5:]

                    if recent_workouts:
                        output.append(f"   Previous performances (last {len(recent_workouts)} workouts):")
                        for hw in recent_workouts:
                            hw_date = hw['start_time']
                            hw_sets = hw['sets']
                            if hw_sets:
                                # Get max weight and reps from this historical workout
                                max_weight = max((s.get('weight_kg', 0) for s in hw_sets if s.get('weight_kg')), default=0)
                                max_reps = max((s.get('reps', 0) for s in hw_sets if s.get('reps')), default=0)
                                if max_weight > 0:
                                    max_weight_lbs = round(max_weight * 2.20462, 1)
                                    output.append(f"   - {hw_date[:10]}: {max_weight_lbs}lbs × {max_reps} reps")

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

    system_prompt = load_prompt("hevy_analyzer_system.txt")

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
        "max_completion_tokens": 2000
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
        workout_text: Formatted workout data (not used in message, kept for backwards compatibility)
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

        # Step 2: Fetch exercise histories
        exercise_histories = {}
        exercises = workout_data.get('exercises', [])

        # Calculate date range for history (last 6 months)
        from datetime import timedelta
        workout_date = workout_data.get('start_time', datetime.utcnow().isoformat() + 'Z')
        try:
            workout_dt = datetime.fromisoformat(workout_date.replace('Z', '+00:00'))
            end_date = workout_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
            start_date = (workout_dt - timedelta(days=180)).strftime('%Y-%m-%dT%H:%M:%SZ')
        except:
            # Fallback to current date if parsing fails
            end_date = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            start_date = (datetime.utcnow() - timedelta(days=180)).strftime('%Y-%m-%dT%H:%M:%SZ')

        print(f"Fetching exercise histories from {start_date} to {end_date}")

        for exercise in exercises:
            exercise_id = exercise.get('exercise_template_id')
            if exercise_id:
                history = fetch_exercise_history(exercise_id, hevy_api_key, start_date, end_date)
                if history:
                    exercise_histories[exercise_id] = history

        print(f"Fetched history for {len(exercise_histories)} exercises")

        # Step 3: Format for analysis
        workout_text = format_workout_for_analysis(workout_data, exercise_histories)
        print(f"Formatted workout: {len(workout_text)} characters")

        # Step 4: Analyze with OpenAI
        analysis = call_openai(workout_text, openai_api_key)
        print("Analysis complete")

        # Step 5: Post to Slack if webhook configured
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
