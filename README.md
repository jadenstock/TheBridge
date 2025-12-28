# TheBridge

AWS-hosted agent workflow system with Slack interface. This project uses AWS CDK (Python) to deploy infrastructure.

## Projects

### Crystal Mountain Weekday Ski Forecast

AI-powered ski conditions analyzer for weekday-only pass holders at Crystal Mountain. The system:
- **Fetches data** from 8+ weather sources including NWS, NWAC, Mount Rainier forecasts
- **Analyzes conditions** using OpenAI to produce weekday-specific ski recommendations
- **Posts to Slack** with scored forecasts and "best day to ski" recommendations
- **Runs daily** via EventBridge scheduler

#### Data Sources

The forecaster aggregates data from:
1. **NWS/NOAA 7-Day Forecast** - Official weather.gov point forecast
2. **NWS Seattle Area Forecast Discussion (AFD)** - Technical forecast discussion with snow levels and timing
3. **Mount Rainier Recreation Forecast** - Paradise snowfall estimates (adjusted for Crystal)
4. **NWAC Mountain Weather Forecast** - Pacific Northwest mountain-specific forecast
5. **NWAC Weather Station** - Real-time observations from Crystal Mountain
6. **Snow-Forecast.com** - 6-day snow forecast by elevation
7. **OnTheSnow** - Resort weather conditions
8. **WSDOT Road Conditions** - SR 410 road status and chain requirements

### Hevy Workout Analyzer & Fitness Planning Agent

**Bidirectional fitness coaching system** that both analyzes completed workouts and helps plan future ones:

#### 1. Workout Analysis (Hevy → Slack)
- **Receives webhooks** from Hevy when workouts complete
- **Fetches workout details** including sets, reps, weights, RPE
- **Fetches exercise history** to compare performance over time
- **Analyzes with OpenAI** to provide insights, progress tracking, and recommendations
- **Posts to Slack** with personalized workout analysis

#### 2. Workout Planning (Slack → AI Agent → Hevy API)
- **Slash command `/plan`** in Slack for interactive workout planning
- **Conversational AI** powered by OpenAI with thread-based conversation history
- **Pulls recent workouts** from Hevy API (last 3 weeks) to inform recommendations
- **Considers recovery** - avoids exercises hitting recently-trained muscles (2-3 days)
- **Promotes diversity** - suggests variety based on last week's workouts
- **Equipment-aware** - recommendations based on your gym's available equipment
- **Thread-based conversations** with 7-day history stored in DynamoDB

**Example usage:**
```
/plan I'm planning upper body today. Besides seated cable rows, what would you recommend?
```

The AI will analyze your recent upper body workouts, check which muscles need recovery, and suggest exercises for balanced development using your gym's equipment.

#### Interactive thread replies (Slack back-and-forth)
- Slash commands cannot run inside threads (Slack limitation), so `/plan` must be sent as a top-level message; the bot echoes your text to the channel and replies in a thread.
- For ongoing back-and-forth, the Slack Events API handles thread replies:
  - **Request URL:** `https://<api-gateway-url>/slack/events` (from stack output `ApiGatewayUrl` + `/slack/events`). Save to trigger URL verification; you should see `url_verification` in CloudWatch.
  - **Events:** subscribe to `message.channels` (and `message.groups` if using private channels). Optionally add `app_mention` if you want mention triggers.
  - **Scopes:** `chat:write`, `channels:read`, `channels:history` (plus `groups:read`/`groups:history` if you use private channels). Add `app_mentions:read` if you subscribe to mentions. Reinstall the app after scope changes.
  - **Add bot to channel:** either mention it (e.g., `@Fitness Assistant`) and Slack will prompt to add, or Channel details → Integrations → Add apps. The bot must be in the channel to receive `message.channels` events.
  - After installing and adding, replies in the bot’s thread will trigger the planner to respond in-thread.

#### Weekly training review (scheduled)
- A scheduled Lambda (`WeeklyReviewFunction`) runs every Friday at 8:00 PM PT (EventBridge cron with `time_zone="America/Los_Angeles"`).
- It fetches the past 7 days of Hevy workouts, summarizes wins/gaps, and posts a Slack message titled “Weekly Training Review.”
- Uses the same Hevy/OpenAI/Slack webhook environment variables as the other fitness Lambdas.

## Architecture

The system uses a two-Lambda architecture:
- **Data Fetcher Lambda**: Fetches and formats weather data from multiple sources
- **Analyzer Lambda**: Uses OpenAI to analyze data and generate ski recommendations
- **EventBridge Rule**: Cron trigger that runs daily
- **Slack Integration**: Posts formatted reports to Slack via webhooks

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

### 3. Set Up Slack Integrations

#### 3a. Slack Incoming Webhook (for posting messages)

1. Go to your Slack workspace settings
2. Navigate to **Apps** → **Manage** → **Custom Integrations** → **Incoming Webhooks**
3. Click **Add to Slack**
4. Select the channel where you want messages posted
5. Copy the webhook URL (looks like: `https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXX`)

#### 3b. Slack Slash Command (for /plan command)

1. Go to https://api.slack.com/apps
2. Click **Create New App** → **From scratch**
3. App Name: `Fitness Planner` (or your preference)
4. Pick your workspace
5. Click **Create App**
6. In the left sidebar, click **Slash Commands**
7. Click **Create New Command**
8. Fill in:
   - **Command**: `/plan`
   - **Request URL**: `https://[YOUR-API-GATEWAY-URL]/slack/command` (you'll get this after deploying - see below)
   - **Short Description**: `Get AI-powered workout planning advice`
   - **Usage Hint**: `I'm doing upper body today. What should I do?`
9. Click **Save**
10. In the left sidebar, click **Basic Information**
11. Scroll to **App Credentials**
12. Copy the **Signing Secret** (you'll need this for `cdk.context.json`)
13. Scroll to **Install App** in the left sidebar
14. Click **Install to Workspace** and authorize the app

**Note**: After deploying the CDK stack, you'll get an API Gateway URL. You'll need to come back and update the Request URL in step 8.

### 4. Configure Application Secrets

Create a `cdk.context.json` file in the project root:

```bash
cp cdk.context.example.json cdk.context.json
```

Edit `cdk.context.json` and add your configuration:

```json
{
  "slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
  "hevy_api_key": "your-hevy-api-key",
  "hevy_webhook_auth": "your-secret-auth-token-for-hevy-webhook",
  "hevy_slack_webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
  "gym_openai_api_key": "your-openai-api-key",
  "slack_signing_secret": "your-slack-app-signing-secret"
}
```

**Configuration values:**
- `slack_webhook_url`: Slack incoming webhook URL (from step 3a)
- `hevy_api_key`: Your Hevy API key (get from https://api.hevyapp.com/docs/)
- `hevy_webhook_auth`: A secret token you create for authenticating Hevy webhooks (e.g., generate with `openssl rand -hex 32`)
- `hevy_slack_webhook_url`: Same as `slack_webhook_url` (for workout analysis posts)
- `gym_openai_api_key`: Your OpenAI API key (get from https://platform.openai.com/)
- `slack_signing_secret`: Your Slack app signing secret (from step 3b.12)

**Note**: The `cdk.context.json` file is gitignored to keep your secrets private.

Alternatively, you can pass these during deployment:

```bash
cdk deploy \
  -c slack_webhook_url=https://hooks.slack.com/... \
  -c hevy_api_key=your-key \
  -c hevy_webhook_auth=your-secret \
  -c hevy_slack_webhook_url=https://hooks.slack.com/... \
  -c gym_openai_api_key=sk-... \
  -c slack_signing_secret=your-signing-secret
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

After deployment, CDK will output important URLs:

```
Outputs:
HevyWorkoutStack.HevyWebhookApiEndpoint = https://abc123.execute-api.us-east-1.amazonaws.com
```

**Important**: Save this API Gateway URL! You'll need it for:
1. **Configuring the Slack slash command** - Add `/slack/command` to the URL
2. **Configuring the Hevy webhook** - Add `/webhook` to the URL

### Post-Deployment Configuration

#### Update Slack Slash Command URL

1. Go back to https://api.slack.com/apps
2. Select your app (Fitness Planner)
3. Click **Slash Commands** in the left sidebar
4. Click on your `/plan` command
5. Update the **Request URL** to: `https://[YOUR-API-GATEWAY-URL]/slack/command`
6. Click **Save**

#### Configure Hevy Webhook

1. Go to https://api.hevyapp.com/docs/
2. Log in and navigate to webhook settings
3. Set webhook URL to: `https://[YOUR-API-GATEWAY-URL]/webhook`
4. Set authorization header to the value of `hevy_webhook_auth` from your `cdk.context.json`
5. Save the webhook configuration

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

## Usage

### Using the Fitness Planning Agent

Once deployed and configured, you can use the `/plan` slash command in Slack:

```
/plan I'm planning upper body today. Besides seated cable rows, what would you recommend?
```

The AI will:
1. Fetch your recent workout history (last 3 weeks) from Hevy
2. Analyze which muscles you've trained recently
3. Consider recovery needs (recently-trained muscles)
4. Suggest exercises for variety and balanced development
5. Provide sets/reps guidance

**Thread-based conversations:**
- The agent remembers context within a thread for 7 days
- Continue the conversation by replying in the thread
- Each thread is an independent conversation

**Example conversation:**
```
You: /plan I'm doing legs today. What should I focus on?
AI: Based on your workouts, I see you did squats 2 days ago. I'd recommend focusing on...
You: What about adding some plyometrics?
AI: Given your recent volume, here's how I'd incorporate plyometrics safely...
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
