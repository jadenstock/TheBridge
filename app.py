#!/usr/bin/env python3
import os
import aws_cdk as cdk
from slack_bridge.slack_bridge_stack import SlackBridgeStack
from ski_forecast.ski_forecast_stack import SkiForecastStack
from hevy_workout.hevy_workout_stack import HevyWorkoutStack

app = cdk.App()

# Common environment configuration
env = cdk.Environment(
    account=os.getenv('CDK_DEFAULT_ACCOUNT'),
    region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
)

# Slack Bridge Stack - simple ping application
SlackBridgeStack(app, "SlackBridgeStack", env=env)

# Ski Forecast Stack - weather/snow data fetcher
SkiForecastStack(app, "SkiForecastStack", env=env)

# Hevy Workout Stack - workout tracking and AI analysis
HevyWorkoutStack(app, "HevyWorkoutStack", env=env)

app.synth()
