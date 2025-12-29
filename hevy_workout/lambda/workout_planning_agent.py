"""
Lambda function for AI-powered workout planning using conversation history and Hevy data.

Fetches conversation history from DynamoDB, recent workouts from Hevy API,
and generates personalized workout recommendations using OpenAI.
"""

import json
import os
import urllib.request
import urllib.error
import boto3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')


def load_prompt(filename: str) -> str:
    prompt_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "prompts", filename))
    with open(prompt_path, "r", encoding="utf-8") as prompt_file:
        return prompt_file.read()


def get_conversation_history(thread_ts: str, table_name: str) -> List[Dict[str, str]]:
    """
    Fetch conversation history from DynamoDB for a given thread.

    Args:
        thread_ts: Thread timestamp/identifier
        table_name: DynamoDB table name

    Returns:
        List of messages in chronological order
    """
    table = dynamodb.Table(table_name)

    try:
        response = table.query(
            KeyConditionExpression='thread_id = :thread',
            ExpressionAttributeValues={
                ':thread': thread_ts
            },
            ScanIndexForward=True  # Sort in ascending order (oldest first)
        )

        messages = []
        for item in response.get('Items', []):
            messages.append({
                'role': item.get('role'),
                'content': item.get('message_text')
            })

        print(f"Retrieved {len(messages)} messages from conversation history")
        return messages

    except Exception as e:
        print(f"Error fetching conversation history: {str(e)}")
        return []


def store_message(thread_ts: str, user_id: str, role: str, message_text: str, table_name: str, agent: str = "planner"):
    """
    Store a message in DynamoDB with TTL.

    Args:
        thread_ts: Thread timestamp/identifier
        user_id: User ID
        role: Message role (user/assistant)
        message_text: The message content
        table_name: DynamoDB table name
    """
    table = dynamodb.Table(table_name)

    # Calculate TTL (7 days from now)
    ttl = int((datetime.utcnow() + timedelta(days=7)).timestamp())

    try:
        table.put_item(
            Item={
                'thread_id': thread_ts,
                'timestamp': datetime.utcnow().isoformat() + 'Z',
                'user_id': user_id,
                'role': role,
                'message_text': message_text,
                'agent': agent,
                'expires_at': ttl
            }
        )
        print(f"Stored {role} message in conversation history")

    except Exception as e:
        print(f"Error storing message: {str(e)}")
        # Don't fail the whole function if storage fails


def fetch_recent_workouts(api_key: str, days: int = 21) -> List[Dict[str, Any]]:
    """
    Fetch recent workouts from Hevy API.

    Args:
        api_key: Hevy API key
        days: Number of days to look back (default 21 for 3 weeks)

    Returns:
        List of workout data
    """
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Format dates for Hevy API (ISO 8601)
    start_date_str = start_date.strftime('%Y-%m-%dT%H:%M:%SZ')
    end_date_str = end_date.strftime('%Y-%m-%dT%H:%M:%SZ')

    from urllib.parse import quote
    url = f"https://api.hevyapp.com/v1/workouts?start_date={quote(start_date_str)}&end_date={quote(end_date_str)}&page_size=20"

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
    Format recent workouts into readable text for AI context.

    Emphasizes most recent workout (might be sore) and last week (for diversity).

    Args:
        workouts: List of workout data from Hevy API

    Returns:
        Formatted string describing recent workouts
    """
    if not workouts:
        return "No recent workout data available."

    output = ["**Recent Workout History (Last 3 Weeks)**\n"]

    # Sort by date (most recent first)
    sorted_workouts = sorted(
        workouts,
        key=lambda w: w.get('start_time', ''),
        reverse=True
    )

    now = datetime.utcnow()

    for i, workout in enumerate(sorted_workouts):
        start_time = workout.get('start_time', 'Unknown')
        title = workout.get('title', 'Untitled Workout')

        # Calculate days ago
        try:
            workout_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            days_ago = (now - workout_dt).days

            if days_ago == 0:
                recency = "Today"
            elif days_ago == 1:
                recency = "Yesterday"
            elif days_ago <= 3:
                recency = f"{days_ago} days ago (RECENT - muscles may still be recovering)"
            elif days_ago <= 7:
                recency = f"{days_ago} days ago (within last week)"
            else:
                recency = f"{days_ago} days ago"
        except:
            recency = "Unknown date"

        output.append(f"\n**Workout {i+1}: {title}** - {recency}")
        output.append(f"Date: {start_time[:10]}")

        # Exercise list
        exercises = workout.get('exercises', [])
        if exercises:
            output.append(f"Exercises ({len(exercises)} total):")
            for exercise in exercises:
                exercise_name = exercise.get('title', 'Unknown')
                sets = exercise.get('sets', [])

                # Get max weight from sets
                max_weight_kg = 0
                max_reps = 0
                for s in sets:
                    weight = s.get('weight_kg', 0) or 0
                    reps = s.get('reps', 0) or 0
                    if weight > max_weight_kg:
                        max_weight_kg = weight
                        max_reps = reps

                if max_weight_kg > 0:
                    max_weight_lbs = round(max_weight_kg * 2.20462, 1)
                    output.append(f"  - {exercise_name}: {len(sets)} sets (max: {max_weight_lbs}lbs × {max_reps} reps)")
                else:
                    output.append(f"  - {exercise_name}: {len(sets)} sets")

    return '\n'.join(output)


def call_openai_for_planning(
    user_message: str,
    conversation_history: List[Dict[str, str]],
    workout_context: str,
    api_key: str
) -> str:
    """
    Call OpenAI to generate workout planning advice.

    Args:
        user_message: The user's current question/request
        conversation_history: Previous messages in the thread
        workout_context: Formatted workout history
        api_key: OpenAI API key

    Returns:
        AI-generated workout plan/advice
    """

    system_prompt = load_prompt("workout_planning_system.txt")

    # Build conversation context
    messages = [{'role': 'system', 'content': system_prompt}]

    # Add workout context as a system message
    messages.append({
        'role': 'system',
        'content': f"Here is the user's recent workout history:\n\n{workout_context}"
    })

    # Add conversation history
    for msg in conversation_history:
        messages.append(msg)

    # Add current user message
    messages.append({
        'role': 'user',
        'content': user_message
    })

    # Call OpenAI
    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": "gpt-5.1",
        "messages": messages,
        "temperature": 0.7,
        "max_completion_tokens": 2000
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    print("Calling OpenAI API for workout planning...")

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


def post_to_slack_response_url(response_url: str, message: str, thread_ts: str = None):
    """
    Post message to Slack using response_url from slash command.

    Args:
        response_url: The response URL from Slack
        message: Message to post
        thread_ts: Thread timestamp (optional, for threading)
    """
    payload = {
        'response_type': 'in_channel',
        'text': message,
    }

    # If we have a thread_ts, include it
    if thread_ts and not thread_ts.startswith('new_'):
        payload['thread_ts'] = thread_ts

    try:
        req = urllib.request.Request(
            response_url,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"Posted to Slack via response_url: {response.status}")
    except Exception as e:
        print(f"Failed to post to Slack: {str(e)}")
        raise


def post_to_slack_web_api(bot_token: str, channel_id: str, message: str, thread_ts: str = None):
    """
    Post message to Slack using Web API.

    Args:
        bot_token: Slack bot OAuth token
        channel_id: Channel ID to post to
        message: Message to post
        thread_ts: Thread timestamp to reply in (optional, creates new thread if None)

    Returns:
        The message timestamp (ts) from Slack's response
    """
    url = "https://slack.com/api/chat.postMessage"

    payload = {
        'channel': channel_id,
        'text': message
    }

    # If thread_ts is provided, post as a reply in that thread
    if thread_ts:
        payload['thread_ts'] = thread_ts

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {bot_token}'
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            result = json.loads(response.read().decode('utf-8'))
            if result.get('ok'):
                message_ts = result.get('ts')
                print(f"Posted to Slack via Web API, message ts: {message_ts}")
                return message_ts
            else:
                error = result.get('error')
                print(f"Slack API error: {error}")
                raise Exception(f"Slack API error: {error}")
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"HTTP error posting to Slack: {e.code} - {error_body}")
        raise
    except Exception as e:
        print(f"Failed to post to Slack: {str(e)}")
        raise


def handler(event, context):
    """
    Lambda handler for workout planning agent.

    Event should contain:
    - user_id: Slack user ID
    - user_name: Slack username
    - channel_id: Slack channel ID
    - thread_ts: Thread timestamp
    - user_message: The user's question/request
    - response_url: Slack response URL for posting back

    Environment variables:
    - HEVY_API_KEY: Hevy API key
    - OPENAI_API_KEY: OpenAI API key
    - CONVERSATION_TABLE_NAME: DynamoDB table for conversation history
    """
    print(f"Starting workout planning agent at {datetime.utcnow().isoformat()}Z")
    print(f"Event: {json.dumps(event)}")

    # Get configuration
    hevy_api_key = os.environ.get('HEVY_API_KEY')
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    conversation_table = os.environ.get('CONVERSATION_TABLE_NAME')
    slack_bot_token = os.environ.get('SLACK_BOT_TOKEN')

    if not hevy_api_key:
        print("Error: HEVY_API_KEY not configured")
        return {'statusCode': 500, 'body': 'Configuration error'}

    if not openai_api_key:
        print("Error: OPENAI_API_KEY not configured")
        return {'statusCode': 500, 'body': 'Configuration error'}

    if not conversation_table:
        print("Error: CONVERSATION_TABLE_NAME not configured")
        return {'statusCode': 500, 'body': 'Configuration error'}

    # Extract event data
    user_id = event.get('user_id')
    channel_id = event.get('channel_id')
    thread_ts = event.get('thread_ts')
    user_message = event.get('user_message')
    response_url = event.get('response_url')
    is_thread_reply = event.get('is_thread_reply', False)

    try:
        # Check if bot token is configured (required for Web API posting)
        if not slack_bot_token or slack_bot_token == 'NOT_CONFIGURED':
            print("Error: SLACK_BOT_TOKEN not configured")
            return {'statusCode': 500, 'body': 'Configuration error'}

        # Determine the actual thread_ts to use
        # If we already have a real thread timestamp (e.g., initial /plan message posted to channel), reuse it
        actual_thread_ts = thread_ts if thread_ts and not thread_ts.startswith('new_') else None

        # Step 1: Fetch conversation history
        if actual_thread_ts:
            conversation_history = get_conversation_history(actual_thread_ts, conversation_table)
        else:
            conversation_history = []

        # Step 2: Fetch recent workouts from Hevy
        recent_workouts = fetch_recent_workouts(hevy_api_key, days=21)

        # Step 3: Format workout context
        workout_context = format_workouts_for_context(recent_workouts)

        # Step 4: Call OpenAI for planning advice
        ai_response = call_openai_for_planning(
            user_message,
            conversation_history,
            workout_context,
            openai_api_key
        )

        # Step 5: Post response to Slack using Web API
        # For slash commands: Post as new message (will become the thread parent)
        # For thread replies: Post in the existing thread
        print(f"Posting to Slack - is_thread_reply: {is_thread_reply}, thread_ts: {actual_thread_ts}")
        message_ts = post_to_slack_web_api(slack_bot_token, channel_id, ai_response, actual_thread_ts)

        # Step 6: Use the message timestamp as the thread_ts for conversation history
        # For new threads, the message_ts is the parent message
        # For existing threads, we use the provided thread_ts
        final_thread_ts = actual_thread_ts if actual_thread_ts else message_ts

        print(f"Final thread_ts for storage: {final_thread_ts}")

        # Step 7: Store messages in conversation history with the actual thread_ts
        store_message(final_thread_ts, user_id, 'user', user_message, conversation_table, agent="planner")
        store_message(final_thread_ts, user_id, 'assistant', ai_response, conversation_table, agent="planner")

        return {
            'statusCode': 200,
            'body': json.dumps({'success': True})
        }

    except Exception as e:
        error_msg = f"Failed to generate workout plan: {str(e)}"
        print(f"Error: {error_msg}")
        import traceback
        traceback.print_exc()

        # Try to post error to Slack
        try:
            error_message = "Sorry, I encountered an error while planning your workout. Please try again."
            if slack_bot_token and slack_bot_token != 'NOT_CONFIGURED' and channel_id:
                # Try to determine thread_ts for error message
                error_thread_ts = thread_ts if (is_thread_reply and thread_ts and not thread_ts.startswith('new_')) else None
                post_to_slack_web_api(slack_bot_token, channel_id, error_message, error_thread_ts)
        except Exception as e2:
            print(f"Failed to post error message to Slack: {str(e2)}")

        return {
            'statusCode': 500,
            'body': json.dumps({'success': False, 'error': error_msg})
        }
