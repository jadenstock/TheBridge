# Ski Forecast Troubleshooting Guide

## Quick Health Check

Run the automated test script:
```bash
./ski_forecast/test_local.sh
```

This will:
- ✅ Run unit tests for imports
- ✅ Invoke the Lambda function
- ✅ Check for recent errors

## Common Issues

### 1. Import Errors (`No module named 'X'`)

**Symptoms**: Lambda fails with `ImportModuleError` in CloudWatch logs

**Cause**: Missing dependencies in the Lambda deployment package

**Fix**:
1. Ensure all required files are in `ski_forecast/lambda/`:
   - `config.py`
   - `config.json`
   - `prompts/ski_analyzer_system.txt`
   - All dependencies (bs4, soupsieve, etc.)

2. Check imports in `ski_analyzer.py` use relative imports:
   ```python
   from config import ...  # ✅ Correct
   from ski_forecast.config import ...  # ❌ Wrong
   ```

3. Run unit tests before deploying:
   ```bash
   python3 -m pytest ski_forecast/test_lambda.py -v
   ```

### 2. Lambda Not Running (Scheduled Execution)

**Symptoms**: No recent invocations in CloudWatch logs

**Check**:
1. Verify EventBridge rule is enabled:
   ```bash
   aws events list-rules --name-prefix SkiForecastStack
   ```

2. Check CloudWatch alarm (if configured):
   ```bash
   aws cloudwatch describe-alarms --alarm-names SkiForecast-No-Invocations
   ```

3. Manually invoke to test:
   ```bash
   aws lambda invoke \
     --function-name $(aws lambda list-functions --query "Functions[?contains(FunctionName, 'SkiAnalyzerFunction')].FunctionName" --output text) \
     /tmp/test-output.json
   cat /tmp/test-output.json
   ```

### 3. OpenAI API Errors

**Symptoms**: Lambda runs but fails during OpenAI call

**Check**:
1. Verify API key is set:
   ```bash
   aws lambda get-function-configuration \
     --function-name $(aws lambda list-functions --query "Functions[?contains(FunctionName, 'SkiAnalyzerFunction')].FunctionName" --output text) \
     --query "Environment.Variables.OPENAI_API_KEY"
   ```

2. Check CloudWatch logs for specific error:
   ```bash
   aws logs tail /aws/lambda/SkiForecastStack-SkiAnalyzerFunction* --since 24h --filter-pattern "ERROR"
   ```

3. Test API key manually:
   ```bash
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer YOUR_API_KEY"
   ```

### 4. Slack Posting Fails

**Symptoms**: Lambda completes but no Slack message appears

**Check**:
1. Verify webhook URL is configured:
   ```bash
   aws lambda get-function-configuration \
     --function-name $(aws lambda list-functions --query "Functions[?contains(FunctionName, 'SkiAnalyzerFunction')].FunctionName" --output text) \
     --query "Environment.Variables.SLACK_WEBHOOK_URL"
   ```

2. Test webhook manually:
   ```bash
   curl -X POST YOUR_WEBHOOK_URL \
     -H 'Content-Type: application/json' \
     -d '{"text": "Test message"}'
   ```

**Note**: Slack failures don't cause the Lambda to fail (statusCode 200)

## Debugging Commands

### View Recent Logs
```bash
# All logs from last 24 hours
aws logs tail /aws/lambda/SkiForecastStack-SkiAnalyzerFunction* --since 24h --format short

# Only errors
aws logs tail /aws/lambda/SkiForecastStack-SkiAnalyzerFunction* --since 24h --filter-pattern "ERROR"

# Follow live logs
aws logs tail /aws/lambda/SkiForecastStack-SkiAnalyzerFunction* --follow
```

### Check Lambda Status
```bash
# List all ski forecast functions
aws lambda list-functions --query "Functions[?contains(FunctionName, 'SkiForecast')]"

# Get function configuration
aws lambda get-function-configuration \
  --function-name SkiForecastStack-SkiAnalyzerFunction*
```

### Check EventBridge Schedule
```bash
# View schedule rule
aws events describe-rule --name SkiForecastStack-SkiAnalysisSchedule*

# View recent invocations
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Invocations \
  --dimensions Name=FunctionName,Value=SkiForecastStack-SkiAnalyzerFunction* \
  --start-time $(date -u -d '7 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum
```

### Check CloudWatch Alarms
```bash
# List all alarms
aws cloudwatch describe-alarms --alarm-name-prefix SkiForecast

# View alarm history
aws cloudwatch describe-alarm-history \
  --alarm-name SkiForecast-Lambda-Errors \
  --max-records 10
```

## Deployment

### Standard Deployment
```bash
cdk deploy SkiForecastStack --require-approval never
```

### Deployment with Alarms
```bash
cdk deploy SkiForecastStack \
  -c ski_alarm_email=your@email.com \
  --require-approval never
```

**Note**: You'll receive an SNS subscription confirmation email on first deployment

### Update Configuration Only
If you only need to update environment variables:
```bash
aws lambda update-function-configuration \
  --function-name SkiForecastStack-SkiAnalyzerFunction* \
  --environment "Variables={OPENAI_API_KEY=sk-...,SLACK_WEBHOOK_URL=https://...}"
```

## Testing Before Deployment

### 1. Run Unit Tests
```bash
python3 -m pytest ski_forecast/test_lambda.py -v
```

### 2. Run Full Test Suite
```bash
./ski_forecast/test_local.sh
```

### 3. Manual Lambda Test
```bash
# Invoke the function
aws lambda invoke \
  --function-name SkiForecastStack-SkiAnalyzerFunction* \
  --log-type Tail \
  /tmp/output.json

# Check output
cat /tmp/output.json | python3 -m json.tool
```

## Monitoring

### CloudWatch Alarms (Recommended)

Two alarms are available if you deploy with `-c ski_alarm_email=your@email.com`:

1. **SkiForecast-Lambda-Errors**: Alerts on any Lambda errors
2. **SkiForecast-No-Invocations**: Alerts if Lambda hasn't run in 25 hours

### Manual Monitoring

Check for errors in the last 24 hours:
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/SkiForecastStack-SkiAnalyzerFunction* \
  --filter-pattern "ERROR" \
  --start-time $(($(date +%s) - 86400))000 \
  --query "events[*].[timestamp,message]" \
  --output text
```

Check last successful run:
```bash
aws logs filter-log-events \
  --log-group-name /aws/lambda/SkiForecastStack-SkiAnalyzerFunction* \
  --filter-pattern "Analysis complete" \
  --max-items 1 \
  --query "events[-1].timestamp" \
  --output text
```

## Architecture

```
EventBridge Rule (daily at 6 PM PST)
  └─> SkiAnalyzerFunction
       ├─> invokes DataFetcherFunction
       ├─> calls OpenAI API
       └─> posts to Slack
```

## Files to Check

- `ski_forecast/lambda/ski_analyzer.py` - Main Lambda handler
- `ski_forecast/lambda/data_fetcher.py` - Data fetcher Lambda
- `ski_forecast/lambda/config.py` - Configuration loader
- `ski_forecast/lambda/config.json` - Agent configuration
- `ski_forecast/lambda/prompts/ski_analyzer_system.txt` - System prompt
- `ski_forecast/ski_forecast_stack.py` - CDK infrastructure

## Getting Help

If you're still stuck:

1. Check the [CDK Stack logs](https://console.aws.amazon.com/cloudformation)
2. Review [Lambda logs](https://console.aws.amazon.com/cloudwatch/home#logsV2:log-groups/log-group/$252Faws$252Flambda$252FSkiForecastStack)
3. Check EventBridge rule status in AWS Console
