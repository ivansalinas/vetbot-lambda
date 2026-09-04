#!/usr/bin/env python3
import boto3

lambda_client = boto3.client("lambda", region_name="us-east-1")

try:
    lambda_client.update_function_configuration(
        FunctionName="vetbot-handler",
        Handler="src/handler.lambda_handler"
    )
    print("✅ vetbot-handler: Handler actualizado a src/handler.lambda_handler")
except Exception as e:
    print(f"❌ Error: {e}")