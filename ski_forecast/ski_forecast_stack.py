from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_events as events,
    aws_events_targets as targets,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
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

        # Get email from context for alarm notifications
        alarm_email = self.node.try_get_context("ski_alarm_email")

        if alarm_email and alarm_email != "NOT_CONFIGURED":
            # Create SNS topic for alarm notifications
            alarm_topic = sns.Topic(
                self,
                "SkiForecastAlarmTopic",
                display_name="Ski Forecast Lambda Failures",
                topic_name="SkiForecastAlarms"
            )

            # Subscribe email to topic
            sns.Subscription(
                self,
                "EmailSubscription",
                topic=alarm_topic,
                endpoint=alarm_email,
                protocol=sns.SubscriptionProtocol.EMAIL
            )

            # Create CloudWatch alarm for Lambda errors
            error_alarm = cloudwatch.Alarm(
                self,
                "SkiAnalyzerErrorAlarm",
                metric=ski_analyzer_lambda.metric_errors(
                    period=Duration.hours(1),
                    statistic="Sum"
                ),
                threshold=1,
                evaluation_periods=1,
                datapoints_to_alarm=1,
                alarm_description="Alert when ski analyzer Lambda has errors",
                alarm_name="SkiForecast-Lambda-Errors",
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
            )

            # Add SNS action to alarm
            error_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))

            # Create CloudWatch alarm for no successful invocations
            no_invocations_alarm = cloudwatch.Alarm(
                self,
                "SkiAnalyzerNoInvocationsAlarm",
                metric=ski_analyzer_lambda.metric_invocations(
                    period=Duration.hours(25),
                    statistic="Sum"
                ),
                threshold=1,
                comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
                evaluation_periods=1,
                datapoints_to_alarm=1,
                alarm_description="Alert when ski analyzer Lambda hasn't run in 25 hours",
                alarm_name="SkiForecast-No-Invocations",
                treat_missing_data=cloudwatch.TreatMissingData.BREACHING
            )

            # Add SNS action to alarm
            no_invocations_alarm.add_alarm_action(cw_actions.SnsAction(alarm_topic))

            print(f"✅ CloudWatch alarms configured with notifications to {alarm_email}")
            print("   You'll need to confirm the SNS subscription via email after deployment")
        else:
            print("⚠️  Warning: ski_alarm_email not provided in context")
            print("   CloudWatch alarms will not be created")
            print("   You can provide it during deployment:")
            print("   cdk deploy -c ski_alarm_email=your@email.com")
