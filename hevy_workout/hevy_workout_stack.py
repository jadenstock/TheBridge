from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_dynamodb as dynamodb,
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
        slack_signing_secret = self.node.try_get_context("slack_signing_secret")
        fitness_slack_bot_token = self.node.try_get_context("fitness_slack_bot_token")

        # Lambda function to analyze workouts with AI
        hevy_analyzer_lambda = lambda_.Function(
            self,
            "HevyAnalyzerFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="hevy_analyzer.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(120),
            description="Analyzes Hevy workout details, calls OpenAI, and posts a summary to Slack",
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
            description="Receives Hevy webhook events and forwards workoutIds to the analyzer Lambda",
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

        # ============================================================
        # Slack Slash Command Integration for Workout Planning
        # ============================================================

        # DynamoDB table for conversation history with TTL
        conversation_table = dynamodb.Table(
            self,
            "ConversationHistoryTable",
            table_name="fitness-conversations",
            partition_key=dynamodb.Attribute(
                name="thread_id",
                type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="timestamp",
                type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            time_to_live_attribute="expires_at",
            removal_policy=RemovalPolicy.DESTROY,  # For dev/testing - change for production
        )

        # Lambda function for workout planning with AI
        workout_planning_lambda = lambda_.Function(
            self,
            "WorkoutPlanningFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="workout_planning_agent.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(120),
            description="Plans workouts using recent Hevy history, conversation context, and OpenAI",
            environment={
                "HEVY_API_KEY": hevy_api_key,
                "OPENAI_API_KEY": openai_api_key,
                "CONVERSATION_TABLE_NAME": conversation_table.table_name,
                "SLACK_BOT_TOKEN": fitness_slack_bot_token or "NOT_CONFIGURED",
            },
        )

        # Grant DynamoDB permissions to planning agent
        conversation_table.grant_read_write_data(workout_planning_lambda)

        # Lambda function to handle Slack slash commands
        slack_command_lambda = lambda_.Function(
            self,
            "SlackCommandFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="slack_command_handler.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(5),
            description="Handles the /plan Slack slash command and triggers the workout planner",
            environment={
                "SLACK_SIGNING_SECRET": slack_signing_secret or "NOT_CONFIGURED",
                "PLANNING_AGENT_FUNCTION_NAME": workout_planning_lambda.function_name,
                "SLACK_BOT_TOKEN": fitness_slack_bot_token or "NOT_CONFIGURED",
            },
        )

        # Grant command handler permission to invoke planning agent
        workout_planning_lambda.grant_invoke(slack_command_lambda)

        # Create Lambda integration for slash command
        slash_command_integration = apigwv2_integrations.HttpLambdaIntegration(
            "SlackCommandIntegration",
            slack_command_lambda,
        )

        # Add POST route for Slack slash command
        http_api.add_routes(
            path="/slack/command",
            methods=[apigwv2.HttpMethod.POST],
            integration=slash_command_integration,
        )

        # ============================================================
        # Slack Events API for Thread Replies
        # ============================================================

        # Lambda function to handle Slack Events API (thread messages)
        slack_events_lambda = lambda_.Function(
            self,
            "SlackEventsFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="slack_events_handler.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(5),
            description="Listens to Slack thread replies and forwards them to the workout planner",
            environment={
                "PLANNING_AGENT_FUNCTION_NAME": workout_planning_lambda.function_name,
            },
        )

        # Grant events handler permission to invoke planning agent
        workout_planning_lambda.grant_invoke(slack_events_lambda)

        # Create Lambda integration for events
        slack_events_integration = apigwv2_integrations.HttpLambdaIntegration(
            "SlackEventsIntegration",
            slack_events_lambda,
        )

        # Add POST route for Slack Events API
        http_api.add_routes(
            path="/slack/events",
            methods=[apigwv2.HttpMethod.POST],
            integration=slack_events_integration,
        )

        # Output the API Gateway URL
        CfnOutput(
            self,
            "ApiGatewayUrl",
            value=http_api.url or "Not available",
            description="API Gateway URL for Hevy webhook and Slack slash commands",
            export_name="HevyWorkoutApiUrl"
        )
