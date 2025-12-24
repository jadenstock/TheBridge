#!/usr/bin/env python3
import os
import aws_cdk as cdk
from slack_bridge.slack_bridge_stack import SlackBridgeStack

app = cdk.App()

SlackBridgeStack(
    app,
    "SlackBridgeStack",
    env=cdk.Environment(
        account=os.getenv('CDK_DEFAULT_ACCOUNT'),
        region=os.getenv('CDK_DEFAULT_REGION', 'us-east-1')
    ),
)

app.synth()
