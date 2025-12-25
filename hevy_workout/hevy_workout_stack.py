from aws_cdk import (
    Stack,
    Duration,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
)
from constructs import Construct


class HevyWorkoutStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get configuration from context
        hevy_api_key = self.node.try_get_context("hevy_api_key")
        hevy_webhook_auth = self.node.try_get_context("hevy_webhook_auth")
        hevy_slack_webhook_url = self.node.try_get_context("hevy_slack_webhook_url")
        openai_api_key = self.node.try_get_context("gym_openai_api_key")

        # Lambda function to analyze workouts with AI
        hevy_analyzer_lambda = lambda_.Function(
            self,
            "HevyAnalyzerFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="hevy_analyzer.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(120),
            environment={
                "HEVY_API_KEY": hevy_api_key,
                "OPENAI_API_KEY": openai_api_key,
                "SLACK_WEBHOOK_URL": hevy_slack_webhook_url,
            },
        )

        # Lambda function to receive webhooks from Hevy
        hevy_webhook_lambda = lambda_.Function(
            self,
            "HevyWebhookFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="hevy_webhook.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(5),
            environment={
                "HEVY_WEBHOOK_AUTH": hevy_webhook_auth,
                "ANALYZER_FUNCTION_NAME": hevy_analyzer_lambda.function_name,
            },
        )

        # Grant webhook function permission to invoke analyzer
        hevy_analyzer_lambda.grant_invoke(hevy_webhook_lambda)

        # Create HTTP API Gateway
        http_api = apigwv2.HttpApi(
            self,
            "HevyWebhookApi",
            api_name="hevy-webhook-api",
            description="API Gateway for receiving Hevy workout webhooks",
        )

        # Create Lambda integration
        webhook_integration = apigwv2_integrations.HttpLambdaIntegration(
            "HevyWebhookIntegration",
            hevy_webhook_lambda,
        )

        # Add POST route for webhook
        http_api.add_routes(
            path="/webhook",
            methods=[apigwv2.HttpMethod.POST],
            integration=webhook_integration,
        )
