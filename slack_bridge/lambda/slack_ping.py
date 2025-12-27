"""
Lambda health check that posts a heartbeat message to Slack.

Typically triggered by a CloudWatch schedule to confirm the bridge is alive.
"""

import json
import os
import urllib.request
from datetime import datetime


def handler(event, context):
    """
    Send a scheduled heartbeat message to Slack via incoming webhook.

    Event: usually a CloudWatch scheduled trigger (payload ignored).

    Environment variables:
        SLACK_WEBHOOK_URL: Slack incoming webhook URL that receives the heartbeat
    """
    webhook_url = os.environ.get('SLACK_WEBHOOK_URL')

    if not webhook_url:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'SLACK_WEBHOOK_URL not configured'})
        }

    # Create the message
    message = {
        'text': f'🤖 Scheduled ping from TheBridge at {datetime.utcnow().isoformat()}Z',
        'blocks': [
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f'*TheBridge Health Check* :white_check_mark:\n\nScheduled ping at `{datetime.utcnow().isoformat()}Z`'
                }
            }
        ]
    }

    # Send to Slack
    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(message).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )

        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                return {
                    'statusCode': 200,
                    'body': json.dumps({'message': 'Slack notification sent successfully'})
                }
            else:
                return {
                    'statusCode': response.status,
                    'body': json.dumps({'error': f'Slack returned status {response.status}'})
                }

    except Exception as e:
        print(f'Error sending to Slack: {str(e)}')
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }
