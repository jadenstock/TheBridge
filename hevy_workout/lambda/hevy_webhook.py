import json
import os
import boto3

# Initialize Lambda client for invoking analyzer function
lambda_client = boto3.client('lambda')

def handler(event, context):
    """
    Webhook receiver for Hevy workout events.
    Validates auth header, triggers async processing, returns 200 quickly.
    """

    # Get configuration
    expected_auth = os.environ.get('HEVY_WEBHOOK_AUTH')
    analyzer_function_name = os.environ.get('ANALYZER_FUNCTION_NAME')

    # Validate auth header
    headers = event.get('headers', {})
    # API Gateway normalizes header names to lowercase
    auth_header = headers.get('authorization') or headers.get('Authorization')

    if not auth_header or auth_header != expected_auth:
        return {
            'statusCode': 401,
            'body': json.dumps({'error': 'Unauthorized'})
        }

    # Parse webhook payload
    try:
        if isinstance(event.get('body'), str):
            body = json.loads(event['body'])
        else:
            body = event.get('body', {})

        workout_id = body.get('payload', {}).get('workoutId')

        if not workout_id:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing workoutId'})
            }

        print(f"Received webhook for workout: {workout_id}")

        # Trigger analyzer function asynchronously (Event invocation type)
        lambda_client.invoke(
            FunctionName=analyzer_function_name,
            InvocationType='Event',  # Async invocation
            Payload=json.dumps({'workoutId': workout_id})
        )

        # Return 200 immediately (Hevy requires response within 5 seconds)
        return {
            'statusCode': 200,
            'body': json.dumps({'received': True, 'workoutId': workout_id})
        }

    except Exception as e:
        print(f"Error processing webhook: {str(e)}")
        # Still return 200 to acknowledge receipt (processing happens async)
        return {
            'statusCode': 200,
            'body': json.dumps({'received': True, 'note': 'Processing async'})
        }
