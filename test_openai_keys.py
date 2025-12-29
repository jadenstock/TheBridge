#!/usr/bin/env python3
"""
Health check script for OpenAI API keys.
Tests multiple models with both ski and gym OpenAI keys.
"""

import json
import urllib.request
import urllib.error
import sys

def load_keys():
    """Load API keys from cdk.context.json"""
    try:
        with open('cdk.context.json', 'r') as f:
            context = json.load(f)
        return {
            'ski_openai_api_key': context.get('ski_openai_api_key'),
            'gym_openai_api_key': context.get('gym_openai_api_key'),
        }
    except Exception as e:
        print(f"Error loading keys: {e}")
        sys.exit(1)

def test_openai_key(api_key, key_name, model):
    """Test an OpenAI API key with a specific model"""
    url = "https://api.openai.com/v1/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Say 'OK' if you can read this."}
        ],
        "max_tokens": 10
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {api_key}'
    }

    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode('utf-8'),
            headers=headers,
            method='POST'
        )

        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            response_text = result['choices'][0]['message']['content']
            print(f"✅ {key_name} + {model:20s} -> SUCCESS (response: {response_text.strip()})")
            return True

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get('error', {}).get('message', error_body)
        except:
            error_msg = error_body
        print(f"❌ {key_name} + {model:20s} -> HTTP {e.code}: {error_msg}")
        return False

    except Exception as e:
        print(f"❌ {key_name} + {model:20s} -> ERROR: {str(e)}")
        return False

def main():
    print("=" * 80)
    print("OpenAI API Keys Health Check")
    print("=" * 80)

    keys = load_keys()

    # Models to test
    models = [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ]

    print(f"\nTesting {len(models)} models with 2 API keys...\n")

    results = {}

    # Test ski key
    print("Testing ski_openai_api_key:")
    print("-" * 80)
    ski_key = keys['ski_openai_api_key']
    if ski_key:
        results['ski'] = {}
        for model in models:
            results['ski'][model] = test_openai_key(ski_key, "ski_key", model)
    else:
        print("⚠️  ski_openai_api_key not found in cdk.context.json")

    print()

    # Test gym key
    print("Testing gym_openai_api_key:")
    print("-" * 80)
    gym_key = keys['gym_openai_api_key']
    if gym_key:
        results['gym'] = {}
        for model in models:
            results['gym'][model] = test_openai_key(gym_key, "gym_key", model)
    else:
        print("⚠️  gym_openai_api_key not found in cdk.context.json")

    # Summary
    print("\n" + "=" * 80)
    print("Summary:")
    print("=" * 80)

    for key_name, model_results in results.items():
        success_count = sum(1 for v in model_results.values() if v)
        total_count = len(model_results)
        print(f"{key_name}_openai_api_key: {success_count}/{total_count} models working")

    print("=" * 80)

if __name__ == "__main__":
    main()
