# TheBridge

AWS-hosted agent workflow system with Slack interface. This project uses AWS CDK (Python) to deploy infrastructure.

## Architecture

The initial setup includes:
- **Lambda Function**: Python-based function that sends messages to Slack
- **EventBridge Rule**: Cron trigger that runs the Lambda every 5 minutes
- **Slack Integration**: Uses Slack Incoming Webhooks for posting messages

## Prerequisites

1. **AWS Account**
2. **Slack Workspace** with admin access
3. **AWS CDK CLI** (install with: `npm install -g aws-cdk`)
4. **AWS CLI** (for credential management)
5. **uv** (Python package manager: https://docs.astral.sh/uv/)
6. **Node.js** (for CDK CLI)

## Setup

### 1. Install Dependencies

```bash
# Install Python dependencies
uv sync

# Install AWS CLI (if not already installed)
# On Linux:
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install
rm -rf aws awscliv2.zip

# On macOS:
brew install awscli

# Install CDK CLI (if not already installed)
npm install -g aws-cdk
```

### 2. Configure AWS Credentials

**For Local Development:**

1. **Create an IAM user** (if you don't have one):
   - Go to AWS Console → IAM → Users → Create user
   - User name: `cdk-admin` (or your preference)
   - Attach policy: `AdministratorAccess` (for personal dev account)

2. **Create access keys**:
   - IAM → Users → `cdk-admin` → Security credentials
   - Click "Create access key"
   - Choose "Command Line Interface (CLI)"
   - Download/copy the Access Key ID and Secret Access Key

3. **Configure AWS CLI**:
   ```bash
   aws configure
   ```

   Provide when prompted:
   - AWS Access Key ID: `[your access key]`
   - AWS Secret Access Key: `[your secret key]`
   - Default region name: `us-east-1` (or your preferred region)
   - Default output format: `json` (or press Enter)

   This stores credentials in `~/.aws/credentials` (outside your git repo, so they won't leak).

4. **Verify it works**:
   ```bash
   aws sts get-caller-identity
   ```

**For GitHub Actions (CI/CD):**

See the [GitHub Actions Deployment](#github-actions-deployment) section below for OIDC setup (no long-lived credentials needed).

### 3. Set Up Slack Webhook

1. Go to your Slack workspace settings
2. Navigate to **Apps** → **Manage** → **Custom Integrations** → **Incoming Webhooks**
3. Click **Add to Slack**
4. Select the channel where you want messages posted
5. Copy the webhook URL (looks like: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXX`)

### 4. Configure Slack Webhook URL

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

### 5. Bootstrap CDK (First Time Only)

Bootstrap CDK in your AWS account/region (only needs to be done once per account/region):

```bash
source .venv/bin/activate
cdk bootstrap
```

This creates the necessary S3 buckets and IAM roles for CDK deployments.

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

## GitHub Actions Deployment

To deploy automatically from GitHub Actions using OIDC (no stored credentials):

### 1. Create OIDC Provider in AWS

1. Go to AWS Console → IAM → Identity providers
2. Click "Add provider"
3. Provider type: `OpenID Connect`
4. Provider URL: `https://token.actions.githubusercontent.com`
5. Audience: `sts.amazonaws.com`
6. Click "Add provider"

### 2. Create IAM Role for GitHub Actions

1. Go to IAM → Roles → Create role
2. Select "Web identity"
3. Identity provider: `token.actions.githubusercontent.com`
4. Audience: `sts.amazonaws.com`
5. GitHub organization: `[your-github-username]`
6. GitHub repository: `TheBridge` (or your repo name)
7. Click "Next"
8. Attach policy: `AdministratorAccess` (or create a custom policy with only CDK permissions)
9. Role name: `GitHubActionsDeployRole`
10. Click "Create role"
11. **Copy the Role ARN** (looks like: `arn:aws:iam::296674252477:role/GitHubActionsDeployRole`)

### 3. Add GitHub Secrets

Go to your GitHub repo → Settings → Secrets and variables → Actions → New repository secret:

1. `AWS_ROLE_ARN`: The role ARN from step 2
2. `AWS_REGION`: `us-east-1` (or your region)
3. `SLACK_WEBHOOK_URL`: Your Slack webhook URL

### 4. Create GitHub Actions Workflow

Create `.github/workflows/deploy.yml`:

```yaml
name: Deploy to AWS

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  id-token: write
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install uv
        run: pip install uv

      - name: Install dependencies
        run: uv sync

      - name: Set up Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Install AWS CDK
        run: npm install -g aws-cdk

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: ${{ secrets.AWS_ROLE_ARN }}
          aws-region: ${{ secrets.AWS_REGION }}

      - name: Deploy CDK stack
        run: |
          source .venv/bin/activate
          cdk deploy --require-approval never -c slack_webhook_url=${{ secrets.SLACK_WEBHOOK_URL }}
```

Now every push to `main` will automatically deploy your infrastructure.

### Manual Trigger

You can also manually trigger deployments from GitHub:
- Go to Actions → Deploy to AWS → Run workflow
