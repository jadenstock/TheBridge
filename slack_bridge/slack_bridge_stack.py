from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct


class SlackBridgeStack(Stack):
    """
    CDK Stack for Slack Bridge application.

    Creates a Lambda function that pings Slack on a cron schedule.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get Slack webhook URL from context
        # You can pass this via: cdk deploy -c slack_webhook_url=https://hooks.slack.com/...
        slack_webhook_url = self.node.try_get_context("slack_webhook_url")

        if not slack_webhook_url:
            print("⚠️  Warning: slack_webhook_url not provided in context")
            print("   You can provide it later or pass it during deployment:")
            print("   cdk deploy -c slack_webhook_url=https://hooks.slack.com/...")
            slack_webhook_url = "NOT_CONFIGURED"

        # Lambda function that sends Slack notifications
        slack_ping_lambda = lambda_.Function(
            self,
            "SlackPingFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="slack_ping.handler",
            code=lambda_.Code.from_asset("slack_bridge/lambda"),
            timeout=Duration.seconds(30),
            environment={
                "SLACK_WEBHOOK_URL": slack_webhook_url,
            },
            description="Sends scheduled ping messages to Slack",
        )

        # EventBridge rule to trigger Lambda on a schedule
        # This runs every 5 minutes as an example - adjust as needed
        rule = events.Rule(
            self,
            "SlackPingSchedule",
            # Every 5 minutes
            schedule=events.Schedule.rate(Duration.minutes(5)),
            description="Triggers Slack ping Lambda every 5 minutes",
        )

        # Add Lambda as target for the EventBridge rule
        rule.add_target(targets.LambdaFunction(slack_ping_lambda))
