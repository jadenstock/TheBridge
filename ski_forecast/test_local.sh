#!/bin/bash
#
# Local test script for ski forecast Lambda
# Run this before deploying to catch issues early
#
# Usage: ./ski_forecast/test_local.sh

set -e

echo "🧪 Testing Ski Forecast Lambda..."
echo ""

# Change to project root
cd "$(dirname "$0")/.."

echo "1. Running unit tests..."
python3 -m pytest ski_forecast/test_lambda.py -v
echo "✅ Unit tests passed"
echo ""

echo "2. Testing Lambda invocation (requires AWS credentials)..."
FUNCTION_NAME=$(aws lambda list-functions --query "Functions[?contains(FunctionName, 'SkiAnalyzerFunction')].FunctionName" --output text)

if [ -z "$FUNCTION_NAME" ]; then
    echo "⚠️  Warning: Ski analyzer Lambda not found. Stack may not be deployed."
    exit 1
fi

echo "   Found function: $FUNCTION_NAME"
echo "   Invoking Lambda..."

aws lambda invoke \
    --function-name "$FUNCTION_NAME" \
    --log-type Tail \
    --query 'LogResult' \
    --output text \
    /tmp/ski-test-output.json | base64 -d

STATUS=$(cat /tmp/ski-test-output.json | python3 -c "import sys, json; print(json.load(sys.stdin)['statusCode'])")

if [ "$STATUS" == "200" ]; then
    echo "✅ Lambda invocation successful (status: $STATUS)"
else
    echo "❌ Lambda invocation failed (status: $STATUS)"
    echo "Response:"
    cat /tmp/ski-test-output.json | python3 -m json.tool
    exit 1
fi

echo ""
echo "3. Checking recent Lambda errors..."
ERROR_COUNT=$(aws logs filter-log-events \
    --log-group-name "/aws/lambda/$FUNCTION_NAME" \
    --filter-pattern "ERROR" \
    --start-time $(($(date +%s) - 86400))000 \
    --query "events[*].message" \
    --output text | wc -l)

if [ "$ERROR_COUNT" -gt 0 ]; then
    echo "⚠️  Found $ERROR_COUNT errors in last 24 hours"
    echo "   Run: aws logs tail /aws/lambda/$FUNCTION_NAME --since 24h --filter-pattern ERROR"
else
    echo "✅ No errors in last 24 hours"
fi

echo ""
echo "✅ All tests passed! Safe to deploy."
