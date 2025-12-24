# TheBridge

AWS-hosted agent workflow system with Slack interface. This project uses AWS CDK (Python) to deploy infrastructure.

## Architecture

The initial setup includes:
- **Lambda Function**: Python-based function that sends messages to Slack
- **EventBridge Rule**: Cron trigger that runs the Lambda every 5 minutes
- **Slack Integration**: Uses Slack Incoming Webhooks for posting messages

## Prerequisites

1. **AWS Account** with configured credentials
2. **Slack Workspace** with admin access
3. **AWS CDK CLI** (install with: `npm install -g aws-cdk`)
4. **uv** (Python package manager: https://docs.astral.sh/uv/)
5. **Node.js** (for CDK CLI)

## Setup

### 1. Install Dependencies

```bash
# Install Python dependencies
uv sync

# Install CDK CLI (if not already installed)
npm install -g aws-cdk
```

### 2. Set Up Slack Webhook

1. Go to your Slack workspace settings
2. Navigate to **Apps** → **Manage** → **Custom Integrations** → **Incoming Webhooks**
3. Click **Add to Slack**
4. Select the channel where you want messages posted
5. Copy the webhook URL (looks like: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXX`)

### 3. Configure Slack Webhook URL

Create a `cdk.context.json` file in the project root:

```bash
cp cdk.context.example.json cdk.context.json
```

Edit `cdk.context.json` and add your Slack webhook URL:

```json
{
  "slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
}
```

**Note**: The `cdk.context.json` file is gitignored to keep your webhook URL private.

Alternatively, you can pass the webhook URL during deployment:

```bash
cdk deploy -c slack_webhook_url=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
```

### 4. Bootstrap CDK (First Time Only)

If this is your first time using CDK in your AWS account/region:

```bash
cdk bootstrap aws://ACCOUNT-ID/REGION
```

Or let CDK detect your account/region automatically:

```bash
cdk bootstrap
```

## Deployment

### Deploy to AWS

```bash
# Activate the virtual environment
source .venv/bin/activate

# Synthesize CloudFormation template (optional, for review)
cdk synth

# Deploy the stack
cdk deploy
```

### View Deployed Resources

```bash
# List all CDK stacks
cdk list

# View differences between deployed and local
cdk diff
```

### Update Schedule

The Lambda currently runs every 5 minutes. To change this, edit `slack_bridge/slack_bridge_stack.py`:

```python
# Current: Every 5 minutes
schedule=events.Schedule.rate(Duration.minutes(5))

# Examples:
# Every hour
schedule=events.Schedule.rate(Duration.hours(1))

# Every day at 9 AM UTC
schedule=events.Schedule.cron(hour="9", minute="0")

# Every weekday at 9 AM UTC
schedule=events.Schedule.cron(hour="9", minute="0", week_day="MON-FRI")
```

After making changes, redeploy:

```bash
cdk deploy
```

## Testing

### Test Lambda Locally

You can test the Lambda function locally:

```bash
# Set the webhook URL
export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL"

# Run the function
python -c "from slack_bridge.lambda.slack_ping import handler; handler({}, None)"
```

### Invoke Deployed Lambda

```bash
aws lambda invoke \
  --function-name SlackBridgeStack-SlackPingFunction-XXXXX \
  --region us-east-1 \
  response.json

cat response.json
```

## Project Structure

```
TheBridge/
├── app.py                          # CDK app entry point
├── cdk.json                        # CDK configuration
├── pyproject.toml                  # Python dependencies (uv)
├── slack_bridge/
│   ├── __init__.py
│   ├── slack_bridge_stack.py      # CDK stack definition
│   └── lambda/
│       └── slack_ping.py          # Lambda function code
└── README.md
```

## Cleanup

To remove all deployed resources:

```bash
cdk destroy
```

## Next Steps

- Add more sophisticated agent workflows
- Implement Slack slash commands or interactive components
- Add DynamoDB for state management
- Set up Step Functions for multi-step workflows
- Add API Gateway for webhook receivers
- Implement proper monitoring and alerting

## Useful CDK Commands

- `cdk ls` - List all stacks
- `cdk synth` - Synthesize CloudFormation template
- `cdk deploy` - Deploy stack to AWS
- `cdk diff` - Compare deployed stack with current state
- `cdk destroy` - Remove stack from AWS
- `cdk docs` - Open CDK documentation

## Troubleshooting

### Lambda can't reach Slack

- Verify the webhook URL is correct in `cdk.context.json`
- Check Lambda CloudWatch logs: AWS Console → Lambda → SlackPingFunction → Monitor → View logs in CloudWatch

### CDK bootstrap fails

- Ensure your AWS credentials are configured: `aws configure`
- Verify you have sufficient permissions to create CloudFormation stacks

### Deployment fails

- Check CloudFormation console for detailed error messages
- Ensure you're not hitting AWS service quotas
