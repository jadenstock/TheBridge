from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
)
from constructs import Construct


class SkiForecastStack(Stack):
    """
    CDK Stack for Ski Forecast application.

    Fetches 7-day weather/snow forecast data from multiple sources for
    Crystal Mountain, analyzes with OpenAI, and generates weekday ski reports.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get OpenAI API key from context
        openai_api_key = self.node.try_get_context("ski_openai_api_key")

        if not openai_api_key:
            print("⚠️  Warning: ski_openai_api_key not provided in context")
            print("   You can provide it during deployment:")
            print("   cdk deploy -c ski_openai_api_key=sk-...")
            openai_api_key = "NOT_CONFIGURED"

        # Get Slack webhook URL for ski forecast
        ski_forecast_webhook_url = self.node.try_get_context("ski_forecast_webhook_url")

        if not ski_forecast_webhook_url:
            print("⚠️  Warning: ski_forecast_webhook_url not provided in context")
            print("   You can provide it during deployment:")
            print("   cdk deploy -c ski_forecast_webhook_url=https://hooks.slack.com/...")
            ski_forecast_webhook_url = "NOT_CONFIGURED"

        # Lambda function that fetches weather/snow data and returns markdown
        data_fetcher_lambda = lambda_.Function(
            self,
            "DataFetcherFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="data_fetcher.handler",
            code=lambda_.Code.from_asset("ski_forecast/lambda"),
            timeout=Duration.seconds(60),  # Longer timeout for multiple data sources
            description="Fetches 7-day weather/snow forecast data for Crystal Mountain",
        )

        # Lambda function that analyzes ski conditions using OpenAI
        ski_analyzer_lambda = lambda_.Function(
            self,
            "SkiAnalyzerFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="ski_analyzer.handler",
            code=lambda_.Code.from_asset("ski_forecast/lambda"),
            timeout=Duration.seconds(120),  # Longer timeout for OpenAI API call
            environment={
                "DATA_FETCHER_FUNCTION_NAME": data_fetcher_lambda.function_name,
                "OPENAI_API_KEY": openai_api_key,
                "SLACK_WEBHOOK_URL": ski_forecast_webhook_url,
            },
            description="Analyzes Crystal Mountain ski conditions using OpenAI and posts to Slack",
        )

        # Grant the analyzer Lambda permission to invoke the data fetcher
        data_fetcher_lambda.grant_invoke(ski_analyzer_lambda)

        # EventBridge rule to trigger analyzer Lambda on a schedule
        # Runs daily at 6 PM PST (2 AM UTC)
        rule = events.Rule(
            self,
            "SkiAnalysisSchedule",
            schedule=events.Schedule.cron(
                minute="0",
                hour="2",  # 2 AM UTC = 6 PM PST (UTC-8)
                month="*",
                week_day="*",
                year="*"
            ),
            description="Triggers ski analysis Lambda daily at 6 PM PST",
        )

        # Add analyzer Lambda as target for the EventBridge rule
        rule.add_target(targets.LambdaFunction(ski_analyzer_lambda))
