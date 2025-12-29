from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    aws_lambda as lambda_,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_integrations as apigwv2_integrations,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_s3 as s3,
)
from constructs import Construct


class HevyWorkoutStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Get configuration from context
        hevy_api_key = self.node.try_get_context("hevy_api_key")
        hevy_slack_webhook_url = self.node.try_get_context("hevy_slack_webhook_url")
        openai_api_key = self.node.try_get_context("gym_openai_api_key")
        slack_signing_secret = self.node.try_get_context("slack_signing_secret")
        fitness_slack_bot_token = self.node.try_get_context("fitness_slack_bot_token")
        coach_docs_bucket_name = self.node.try_get_context("coach_docs_bucket_name")
        coach_docs_prefix = self.node.try_get_context("coach_docs_prefix") or "coach_docs/"

        # S3 bucket for coach docs (versioned, retained)
        coach_docs_bucket = s3.Bucket(
            self,
            "CoachDocsBucket",
            bucket_name=coach_docs_bucket_name,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # Lambda function for weekly training review
        weekly_review_lambda = lambda_.Function(
            self,
            "WeeklyReviewFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="weekly_review.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(120),
            description="Creates a weekly training review using Hevy data and posts to Slack",
            environment={
                "HEVY_API_KEY": hevy_api_key,
                "OPENAI_API_KEY": openai_api_key,
                "SLACK_WEBHOOK_URL": hevy_slack_webhook_url,
                "COACH_DOC_S3_BUCKET": coach_docs_bucket.bucket_name,
                "COACH_DOC_S3_PREFIX": coach_docs_prefix,
                "WEEKLY_GOALS_S3_PREFIX": self.node.try_get_context("weekly_goals_prefix") or "weekly_goals/",
            },
        )

        # Weekly EventBridge schedule (Saturday 12pm PT / 20:00 UTC)
        events.Rule(
            self,
            "WeeklyReviewSchedule",
            description="Runs the weekly training review every Saturday at noon PT",
            schedule=events.Schedule.cron(
                minute="0",
                hour="20",
                week_day="SAT",
            ),
            targets=[targets.LambdaFunction(weekly_review_lambda)],
        )

        # ============================================================
        # Slack Slash Command Integration for Workout Planning
        # ============================================================

        # HTTP API Gateway for Slack endpoints
        http_api = apigwv2.HttpApi(
            self,
            "FitnessApi",
            api_name="fitness-api",
            description="API Gateway for Slack command/events",
        )

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
                "COACH_DOC_S3_BUCKET": coach_docs_bucket.bucket_name,
                "COACH_DOC_S3_PREFIX": coach_docs_prefix,
            },
        )

        # Grant DynamoDB permissions to planning agent
        conversation_table.grant_read_write_data(workout_planning_lambda)

        # Weekly goals agent (scheduled + thread replies)
        weekly_goals_lambda = lambda_.Function(
            self,
            "WeeklyGoalsFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="weekly_goals_agent.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(180),
            description="Generates weekly goals, posts options to Slack, and writes weekly goal docs",
            environment={
                "HEVY_API_KEY": hevy_api_key,
                "OPENAI_API_KEY": openai_api_key,
                "SLACK_BOT_TOKEN": fitness_slack_bot_token or "NOT_CONFIGURED",
                "WEEKLY_GOALS_CHANNEL": self.node.try_get_context("weekly_goals_channel") or "",
                "CONVERSATION_TABLE_NAME": conversation_table.table_name,
                "COACH_DOC_S3_BUCKET": coach_docs_bucket.bucket_name,
                "COACH_DOC_S3_PREFIX": coach_docs_prefix,
                "WEEKLY_GOALS_S3_PREFIX": self.node.try_get_context("weekly_goals_prefix") or "weekly_goals/",
            },
        )

        # Allow weekly goals to write/read coach docs + weekly goal docs
        coach_docs_bucket.grant_read_write(weekly_goals_lambda)
        conversation_table.grant_read_write_data(weekly_goals_lambda)

        # Daily planner agent (Mon/Wed/Fri)
        daily_planner_lambda = lambda_.Function(
            self,
            "DailyPlannerFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="daily_planner_agent.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(120),
            description="Plans daily workouts to satisfy weekly goals and responds in Slack threads",
            environment={
                "HEVY_API_KEY": hevy_api_key,
                "OPENAI_API_KEY": openai_api_key,
                "SLACK_BOT_TOKEN": fitness_slack_bot_token or "NOT_CONFIGURED",
                "WEEKLY_GOALS_CHANNEL": self.node.try_get_context("weekly_goals_channel") or "",
                "CONVERSATION_TABLE_NAME": conversation_table.table_name,
                "COACH_DOC_S3_BUCKET": coach_docs_bucket.bucket_name,
                "COACH_DOC_S3_PREFIX": coach_docs_prefix,
                "WEEKLY_GOALS_S3_PREFIX": self.node.try_get_context("weekly_goals_prefix") or "weekly_goals/",
            },
        )

        coach_docs_bucket.grant_read(daily_planner_lambda)
        conversation_table.grant_read_write_data(daily_planner_lambda)

        # Biweekly coach doc refresher
        coach_doc_refresher_lambda = lambda_.Function(
            self,
            "CoachDocRefresherFunction",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="coach_doc_refresher.handler",
            code=lambda_.Code.from_asset("hevy_workout/lambda"),
            timeout=Duration.seconds(120),
            description="Biweekly minimal coach doc updater",
            environment={
                "HEVY_API_KEY": hevy_api_key,
                "OPENAI_API_KEY": openai_api_key,
                "SLACK_BOT_TOKEN": fitness_slack_bot_token or "NOT_CONFIGURED",
                "WEEKLY_GOALS_CHANNEL": self.node.try_get_context("weekly_goals_channel") or "",
                "COACH_DOC_S3_BUCKET": coach_docs_bucket.bucket_name,
                "COACH_DOC_S3_PREFIX": coach_docs_prefix,
                "WEEKLY_GOALS_S3_PREFIX": self.node.try_get_context("weekly_goals_prefix") or "weekly_goals/",
            },
        )
        coach_docs_bucket.grant_read_write(coach_doc_refresher_lambda)

        events.Rule(
            self,
            "CoachDocRefresherSchedule",
            description="Runs coach doc refresher every other Sunday at noon PT",
            schedule=events.Schedule.cron(
                minute="0",
                hour="20",
                week_day="SUN",
                month="*/1"  # every month; biweekly cadence approximate via code if needed
            ),
            targets=[targets.LambdaFunction(coach_doc_refresher_lambda)],
        )
        events.Rule(
            self,
            "DailyPlannerSchedule",
            description="Runs the daily workout planner Mon/Wed/Fri at noon PT",
            schedule=events.Schedule.cron(
                minute="0",
                hour="20",
                week_day="MON,WED,FRI",
            ),
            targets=[targets.LambdaFunction(daily_planner_lambda)],
        )

        # Sunday midday PT trigger (20:00 UTC Sunday ~= 12pm PT)
        events.Rule(
            self,
            "WeeklyGoalsSchedule",
            description="Runs weekly goal setter every Sunday at noon PT",
            schedule=events.Schedule.cron(
                minute="0",
                hour="20",
                week_day="SUN",
            ),
            targets=[targets.LambdaFunction(weekly_goals_lambda)],
        )

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
                "WEEKLY_GOALS_FUNCTION_NAME": weekly_goals_lambda.function_name,
                "DAILY_PLANNER_FUNCTION_NAME": daily_planner_lambda.function_name,
                "COACH_DOC_REFRESHER_FUNCTION_NAME": coach_doc_refresher_lambda.function_name,
                "CONVERSATION_TABLE_NAME": conversation_table.table_name,
            },
        )

        # Grant events handler permission to invoke all agents
        workout_planning_lambda.grant_invoke(slack_events_lambda)
        weekly_goals_lambda.grant_invoke(slack_events_lambda)
        daily_planner_lambda.grant_invoke(slack_events_lambda)
        # Allow events handler to read conversation table for routing
        conversation_table.grant_read_write_data(slack_events_lambda)

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

        # S3 read permissions for coach docs
        coach_docs_bucket.grant_read(weekly_review_lambda)
        coach_docs_bucket.grant_read(workout_planning_lambda)
        coach_docs_bucket.grant_read(slack_events_lambda)
        coach_docs_bucket.grant_read(daily_planner_lambda)

        # Output the API Gateway URL
        CfnOutput(
            self,
            "ApiGatewayUrl",
            value=http_api.url or "Not available",
            description="API Gateway URL for Hevy webhook and Slack slash commands",
            export_name="HevyWorkoutApiUrl"
        )

        CfnOutput(
            self,
            "CoachDocsBucketName",
            value=coach_docs_bucket.bucket_name,
            description="S3 bucket for coach docs and related fitness artifacts",
        )
