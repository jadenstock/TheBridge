
"""
Lambda function to handle Slack slash commands for fitness planning.

Receives /plan commands from Slack, validates the request,
and triggers the workout planning agent asynchronously.
"""

import json
import os
import hmac
import hashlib
import time
import base64
import boto3
from urllib.parse import parse_qs
import urllib.request

# Initialize Lambda client for invoking planning agent
lambda_client = boto3.client('lambda')


def post_user_message(slack_bot_token: str, channel_id: str, user_id: str, text: str) -> str:
    """
    Post the user's /plan text to the channel so the conversation has a visible root.
    Returns the message timestamp for threading.
    """
    url = "https://slack.com/api/chat.postMessage"
    payload = {
        "channel": channel_id,
        "text": f"<@{user_id}>: {text}" if user_id else text,
    }
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Authorization": f"Bearer {slack_bot_token}",
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=10) as response:
        result = json.loads(response.read().decode('utf-8'))
        if not result.get('ok'):
            raise Exception(f"Slack API error posting user message: {result.get('error')}")
        return result.get('ts')


def verify_slack_request(event):
    """
    Verify that the request actually came from Slack using request signing.

    TEMPORARILY DISABLED FOR DEBUGGING

    Args:
        event: API Gateway event

    Returns:
        True if valid, False otherwise
    """
    print("Signature verification DISABLED for debugging")
    return True

    # TODO: Re-enable signature verification after debugging
    # try:
    #     signing_secret = os.environ.get('SLACK_SIGNING_SECRET')
    #     if not signing_secret or signing_secret == 'NOT_CONFIGURED':
    #         print("Warning: SLACK_SIGNING_SECRET not configured, skipping verification")
    #         return True
    #
    #     # Get headers (API Gateway normalizes to lowercase)
    #     headers = event.get('headers', {})
    #     slack_signature = headers.get('x-slack-signature', '')
    #     slack_request_timestamp = headers.get('x-slack-request-timestamp', '')
    #
    #     # Check if request is too old (replay attack protection)
    #     if abs(time.time() - float(slack_request_timestamp)) > 60 * 5:
    #         print("Request timestamp too old")
    #         return False
    #
    #     # Get request body (decode base64 if needed for signature verification)
    #     body = event.get('body', '')
    #     if event.get('isBase64Encoded', False):
    #         body = base64.b64decode(body).decode('utf-8')
    #
    #     # Compute expected signature
    #     sig_basestring = f"v0:{slack_request_timestamp}:{body}"
    #     expected_signature = 'v0=' + hmac.new(
    #         signing_secret.encode(),
    #         sig_basestring.encode(),
    #         hashlib.sha256
    #     ).hexdigest()
    #
    #     # Compare signatures
    #     result = hmac.compare_digest(expected_signature, slack_signature)
    #     return result
    #
    # except Exception as e:
    #     print(f"Error in verify_slack_request: {str(e)}")
    #     import traceback
    #     traceback.print_exc()
    #     return False


def handler(event, context):
    """
    Handle Slack slash command requests.

    Expected slash command: /plan [text]
    Example: /plan I'm planning upper body today. Besides seated cable rows, what would you recommend?

    Environment variables:
        SLACK_SIGNING_SECRET: Slack app signing secret for request verification
        DAILY_PLANNER_FUNCTION_NAME: Name of the daily workout planner Lambda
        SLACK_BOT_TOKEN: Bot token used to echo the user message to the channel
    """

    print(f"Received slash command event: {json.dumps(event)}")

    # Verify request came from Slack
    print("Starting signature verification...")
    is_valid = verify_slack_request(event)
    print(f"Signature verification result: {is_valid}")

    if not is_valid:
        print("Signature verification failed, returning 401")
        return {
            'statusCode': 401,
            'body': json.dumps({'error': 'Invalid Slack signature'})
        }

    print("Signature verified, proceeding with request...")

    # Parse the form-encoded body from Slack
    try:
        print("Starting to parse request body...")
        # Decode base64 if needed (API Gateway may encode the body)
        body = event.get('body', '')
        if event.get('isBase64Encoded', False):
            print("Decoding base64 body...")
            body = base64.b64decode(body).decode('utf-8')

        print(f"Body to parse: {body[:200]}...")  # Print first 200 chars

        if isinstance(body, str):
            print("Parsing URL-encoded parameters...")
            body_params = parse_qs(body)
            # parse_qs returns lists for each value, get first item
            payload = {k: v[0] if v else '' for k, v in body_params.items()}
        else:
            payload = body if isinstance(body, dict) else {}

        print(f"Parsed payload keys: {list(payload.keys())}")

        # Extract important fields
        command = payload.get('command', '')
        text = payload.get('text', '')
        user_id = payload.get('user_id', '')
        user_name = payload.get('user_name', '')
        channel_id = payload.get('channel_id', '')
        thread_ts = payload.get('thread_ts', '')  # Only present if in a thread
        response_url = payload.get('response_url', '')
        trigger_id = payload.get('trigger_id', '')

        print(f"Extracted - Command: {command}, Text: {text}, User: {user_name}")

        # If not in a thread, we'll use the response_url timestamp as thread identifier
        # (In practice, Slack will create a thread when we post the first response)
        if not thread_ts:
            # Generate a pseudo thread_ts - we'll update this when we post to Slack
            thread_ts = f"new_{user_id}_{int(time.time())}"

        print(f"Command: {command}, User: {user_name}, Channel: {channel_id}, Thread: {thread_ts}")
        print(f"Text: {text}")

        if not text:
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'response_type': 'ephemeral',
                    'text': 'Please provide a question or description. Example: `/plan I\'m doing upper body today. What exercises should I do?`'
                })
            }

        daily_planner_function = os.environ.get('DAILY_PLANNER_FUNCTION_NAME')
        if not daily_planner_function:
            return {
                'statusCode': 500,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({
                    'response_type': 'ephemeral',
                    'text': 'Configuration error: Daily planner not configured'
                })
            }

        slack_bot_token = os.environ.get('SLACK_BOT_TOKEN')
        user_message_ts = None
        if slack_bot_token and slack_bot_token != 'NOT_CONFIGURED' and channel_id:
            try:
                user_message_ts = post_user_message(slack_bot_token, channel_id, user_id, text)
                print(f"Posted user message to channel, ts={user_message_ts}")
            except Exception as post_err:
                print(f"Failed to post user message to Slack: {post_err}")

        # Prepare payload for planning agent
        agent_payload = {
            'user_id': user_id,
            'user_name': user_name,
            'channel_id': channel_id,
            'thread_ts': user_message_ts or thread_ts,
            'user_message': text,
            'response_url': response_url
        }

        # Invoke planning agent asynchronously
        print(f"Invoking daily planner: {daily_planner_function}")
        lambda_client.invoke(
            FunctionName=daily_planner_function,
            InvocationType='Event',  # Async invocation
            Payload=json.dumps(agent_payload)
        )

        # Return empty 200; the bot has already posted the user's message and will reply via Web API
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': ''
        }

    except Exception as e:
        print(f"Error processing slash command: {str(e)}")
        import traceback
        traceback.print_exc()

        # Still return 200 to Slack with error message
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'response_type': 'ephemeral',
                'text': f'Sorry, something went wrong processing your request. Please try again.'
            })
        }
