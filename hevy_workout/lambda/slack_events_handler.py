"""
Lambda function to handle Slack Events API for thread messages.

Receives message events from Slack when users reply in threads,
and triggers the workout planning agent to respond.
"""

import json
import os
import boto3
from datetime import datetime, timedelta

# Initialize Lambda client for invoking planning agent
lambda_client = boto3.client('lambda')
dynamodb = boto3.resource('dynamodb')


def handler(event, context):
    """
    Handle Slack Events API requests.

    Handles:
    - URL verification (one-time challenge during setup)
    - Message events in threads

    Environment variables:
        PLANNING_AGENT_FUNCTION_NAME: Name of the workout planning agent Lambda
    """

    print(f"Received Slack event: {json.dumps(event)}")

    # Parse request body
    try:
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})

        event_type = body.get('type')

        # Handle URL verification challenge (one-time setup)
        if event_type == 'url_verification':
            challenge = body.get('challenge')
            print(f"Responding to URL verification challenge: {challenge}")
            return {
                'statusCode': 200,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'challenge': challenge})
            }

        # Handle event callbacks (actual messages)
        if event_type == 'event_callback':
            slack_event = body.get('event', {})
            event_subtype = slack_event.get('type')

            print(f"Event subtype: {event_subtype}")

            # Only handle message events
            if event_subtype == 'message':
                # Ignore bot messages and message changes/deletions
                if slack_event.get('subtype') in ['bot_message', 'message_changed', 'message_deleted']:
                    print("Ignoring bot message or message change")
                    return {'statusCode': 200, 'body': json.dumps({'ok': True})}

                if 'bot_id' in slack_event:
                    print("Ignoring message from bot")
                    return {'statusCode': 200, 'body': json.dumps({'ok': True})}

                # Extract message details
                user_id = slack_event.get('user')
                channel_id = slack_event.get('channel')
                text = slack_event.get('text', '')
                thread_ts = slack_event.get('thread_ts')  # Present if this is a thread reply
                message_ts = slack_event.get('ts')

                print(f"Message from user {user_id} in channel {channel_id}")
                print(f"Thread TS: {thread_ts}, Message TS: {message_ts}")
                print(f"Text: {text}")

                # Only respond to messages in threads (not top-level messages)
                if not thread_ts:
                    print("Not a thread message, ignoring")
                    return {'statusCode': 200, 'body': json.dumps({'ok': True})}

                # Ignore empty messages
                if not text or not text.strip():
                    print("Empty message, ignoring")
                    return {'statusCode': 200, 'body': json.dumps({'ok': True})}

                planning_agent_function = os.environ.get('PLANNING_AGENT_FUNCTION_NAME')
                weekly_goals_function = os.environ.get('WEEKLY_GOALS_FUNCTION_NAME')
                daily_planner_function = os.environ.get('DAILY_PLANNER_FUNCTION_NAME')
                conversation_table = os.environ.get('CONVERSATION_TABLE_NAME')

                target_function = planning_agent_function

                # Look up agent by thread (if present)
                if conversation_table and thread_ts:
                    table = dynamodb.Table(conversation_table)
                    resp = table.query(
                        KeyConditionExpression='thread_id = :thread',
                        ExpressionAttributeValues={':thread': thread_ts},
                        ScanIndexForward=False,
                        Limit=1,
                    )
                    items = resp.get('Items', [])
                    if items:
                        agent = items[0].get('agent')
                        if agent == 'weekly_goals' and weekly_goals_function:
                            target_function = weekly_goals_function
                        elif agent == 'daily_planner' and daily_planner_function:
                            target_function = daily_planner_function

                if not target_function:
                    print("Error: no target function configured")
                    return {'statusCode': 500, 'body': json.dumps({'ok': False})}

                agent_payload = {
                    'user_id': user_id,
                    'user_name': 'user',
                    'channel_id': channel_id,
                    'thread_ts': thread_ts,
                    'user_message': text,
                    'response_url': None,
                    'is_thread_reply': True
                }

                # Record user message for routing/history
                if conversation_table:
                    table = dynamodb.Table(conversation_table)
                    ttl = int((datetime.utcnow() + timedelta(days=14)).timestamp())
                    table.put_item(
                        Item={
                            'thread_id': thread_ts,
                            'timestamp': datetime.utcnow().isoformat() + 'Z',
                            'user_id': user_id,
                            'role': 'user',
                            'message_text': text,
                            'agent': 'weekly_goals' if target_function == weekly_goals_function else 'planner',
                            'expires_at': ttl,
                        }
                    )

                # Invoke planning agent asynchronously
                print(f"Invoking agent: {target_function}")
                lambda_client.invoke(
                    FunctionName=target_function,
                    InvocationType='Event',  # Async invocation
                    Payload=json.dumps(agent_payload)
                )

                # Return 200 immediately to Slack
                return {
                    'statusCode': 200,
                    'headers': {'Content-Type': 'application/json'},
                    'body': json.dumps({'ok': True})
                }

            # Handle app_mention events (when someone @mentions the bot)
            if event_subtype == 'app_mention':
                print("App mention event received")
                # Similar handling as message events
                # (We'll primarily use message events in threads)
                return {'statusCode': 200, 'body': json.dumps({'ok': True})}

        # Unknown event type
        print(f"Unknown event type: {event_type}")
        return {
            'statusCode': 200,
            'body': json.dumps({'ok': True})
        }

    except Exception as e:
        print(f"Error processing Slack event: {str(e)}")
        import traceback
        traceback.print_exc()

        # Always return 200 to Slack to avoid retries
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'ok': True})
        }
