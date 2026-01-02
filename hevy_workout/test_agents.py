#!/usr/bin/env python3
"""
Test script for Hevy workout agents.

Usage:
  python test_agents.py models                    # Test OpenAI models only
  python test_agents.py agent daily_planner       # Test one specific agent
  python test_agents.py agents                    # Test all agents
  python test_agents.py all                       # Test models + all agents
"""

import json
import sys
import os
import urllib.request
import urllib.error
import boto3
from pathlib import Path

# Load config
CONFIG_PATH = Path(__file__).parent / "config.json"
with open(CONFIG_PATH) as f:
    CONFIG = json.load(f)

OPENAI_API_URL = CONFIG["openai_api_url"]
AGENTS = CONFIG["agents"]

# Get OpenAI API key from environment (only needed for model tests)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

# Lambda client
lambda_client = boto3.client('lambda')

# Lambda function names (from stack)
LAMBDA_FUNCTIONS = {
    "daily_planner": "HevyWorkoutStack-DailyPlannerFunction739130F9-iG1gj3urIXRa",
    "weekly_goals": "HevyWorkoutStack-WeeklyGoalsFunction96D7A7C7-pqYkYjTgSUfR",
    "coach_doc_refresher": "HevyWorkoutStack-CoachDocRefresherFunctionC7B6599F-XmGpWmgEX5aY",
    "weekly_review": "HevyWorkoutStack-WeeklyReviewFunctionD23AF271-O4mACQn0fYfR",
    "workout_planning": "HevyWorkoutStack-WorkoutPlanningFunction535A42C7-hVdRRtJU7rZR",
}


def test_openai_model(model_name: str) -> bool:
    """Test if an OpenAI model works with a simple request."""
    if not OPENAI_API_KEY:
        print(f"\n🧪 Testing model: {model_name}")
        print(f"  ❌ OPENAI_API_KEY environment variable not set")
        return False

    print(f"\n🧪 Testing model: {model_name}")

    body = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say 'test successful' if you can read this."}
        ],
        "max_completion_tokens": 50,
        "temperature": 1.0,
    }

    try:
        req = urllib.request.Request(
            OPENAI_API_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {OPENAI_API_KEY}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            print(f"  ✅ Model works! Response: {content[:100]}")
            return True

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            error_data = json.loads(error_body)
            error_msg = error_data.get('error', {}).get('message', error_body)
        except:
            error_msg = error_body
        print(f"  ❌ HTTP {e.code}: {error_msg}")
        return False

    except Exception as e:
        print(f"  ❌ Error: {type(e).__name__}: {e}")
        return False


def test_all_models() -> dict:
    """Test all models configured in config.json."""
    print("\n" + "="*60)
    print("🔬 TESTING OPENAI MODELS")
    print("="*60)

    results = {}
    unique_models = set(agent_config["model"] for agent_config in AGENTS.values())

    for model in sorted(unique_models):
        results[model] = test_openai_model(model)

    # Summary
    print("\n" + "="*60)
    print("📊 MODEL TEST SUMMARY")
    print("="*60)
    for model, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        agents_using = [name for name, cfg in AGENTS.items() if cfg["model"] == model]
        print(f"{status} {model:20s} (used by: {', '.join(agents_using)})")

    return results


def test_lambda_agent(agent_name: str) -> bool:
    """Test a Lambda agent by invoking it with a test payload."""
    if agent_name not in LAMBDA_FUNCTIONS:
        print(f"❌ Unknown agent: {agent_name}")
        print(f"   Available: {', '.join(LAMBDA_FUNCTIONS.keys())}")
        return False

    function_name = LAMBDA_FUNCTIONS[agent_name]
    print(f"\n🧪 Testing agent: {agent_name}")
    print(f"   Lambda: {function_name}")

    # Create test payload based on agent type
    if agent_name == "daily_planner":
        payload = {
            "channel_id": "TEST_CHANNEL",
            "user_id": "TEST_USER",
            "user_message": "Test request for workout planning",
            "is_thread_reply": False,
        }
    elif agent_name == "weekly_goals":
        payload = {
            "channel_id": "TEST_CHANNEL",
            "user_id": "TEST_USER",
            "user_message": "Test weekly goals",
            "is_thread_reply": False,
        }
    elif agent_name == "workout_planning":
        payload = {
            "channel_id": "TEST_CHANNEL",
            "user_id": "TEST_USER",
            "user_message": "Test workout planning",
            "thread_ts": "test_thread_123",
        }
    elif agent_name == "coach_doc_refresher":
        payload = {
            "test": True,
        }
    elif agent_name == "weekly_review":
        payload = {
            "test": True,
        }
    else:
        payload = {}

    try:
        print(f"   Invoking with test payload...")
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType='RequestResponse',  # Synchronous
            Payload=json.dumps(payload),
            LogType='Tail',  # Get last 4KB of logs
        )

        # Check status code
        status_code = response['StatusCode']

        # Get response payload
        response_payload = json.loads(response['Payload'].read().decode('utf-8'))

        # Check for function error
        if 'FunctionError' in response:
            print(f"  ❌ Function error: {response['FunctionError']}")
            if 'errorMessage' in response_payload:
                print(f"     Error: {response_payload['errorMessage']}")
            if 'stackTrace' in response_payload:
                print(f"     Stack trace (first 5 lines):")
                for line in response_payload.get('stackTrace', [])[:5]:
                    print(f"       {line}")
            return False

        # Decode logs if available
        if 'LogResult' in response:
            import base64
            logs = base64.b64decode(response['LogResult']).decode('utf-8')
            log_lines = logs.strip().split('\n')

            # Look for errors in logs
            error_lines = [line for line in log_lines if 'ERROR' in line or 'Error' in line]

            if error_lines:
                print(f"  ⚠️  Errors found in logs:")
                for line in error_lines[:3]:  # Show first 3 error lines
                    print(f"     {line.strip()}")
                return False

        print(f"  ✅ Agent invoked successfully (status: {status_code})")
        print(f"     Response: {json.dumps(response_payload, indent=2)[:200]}...")
        return True

    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"  ❌ Lambda function not found: {function_name}")
        print(f"     Make sure the stack is deployed")
        return False

    except Exception as e:
        print(f"  ❌ Error invoking agent: {type(e).__name__}: {e}")
        return False


def test_all_agents() -> dict:
    """Test all Lambda agents."""
    print("\n" + "="*60)
    print("🤖 TESTING LAMBDA AGENTS")
    print("="*60)

    results = {}
    for agent_name in LAMBDA_FUNCTIONS.keys():
        results[agent_name] = test_lambda_agent(agent_name)

    # Summary
    print("\n" + "="*60)
    print("📊 AGENT TEST SUMMARY")
    print("="*60)
    for agent_name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        model = AGENTS.get(agent_name, {}).get("model", "unknown")
        print(f"{status} {agent_name:25s} (model: {model})")

    return results


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    command = sys.argv[1]

    if command == "models":
        results = test_all_models()
        all_passed = all(results.values())
        sys.exit(0 if all_passed else 1)

    elif command == "agent":
        if len(sys.argv) < 3:
            print("❌ Please specify an agent name")
            print(f"   Available: {', '.join(LAMBDA_FUNCTIONS.keys())}")
            sys.exit(1)
        agent_name = sys.argv[2]
        success = test_lambda_agent(agent_name)
        sys.exit(0 if success else 1)

    elif command == "agents":
        results = test_all_agents()
        all_passed = all(results.values())
        sys.exit(0 if all_passed else 1)

    elif command == "all":
        model_results = test_all_models()
        agent_results = test_all_agents()
        all_passed = all(model_results.values()) and all(agent_results.values())

        print("\n" + "="*60)
        print("🎯 OVERALL SUMMARY")
        print("="*60)
        print(f"Models: {sum(model_results.values())}/{len(model_results)} passed")
        print(f"Agents: {sum(agent_results.values())}/{len(agent_results)} passed")
        print("="*60)

        sys.exit(0 if all_passed else 1)

    else:
        print(f"❌ Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
