#!/usr/bin/env python3
import boto3

lambda_client = boto3.client("lambda", region_name="us-east-1")

LAMBDAS = [
    "webhook-receiver",
    "bedrock-processor",
    "search-engine",
    "whatsapp-sender",
    "crm-updater"
]

for func in LAMBDAS:
    try:
        lambda_client.update_function_configuration(
            FunctionName=func,
            Handler="src/handler.lambda_handler"
        )
        print(f"✅ {func}: Handler actualizado a src/handler.lambda_handler")
    except Exception as e:
        print(f"❌ {func}: {e}")

print("\n🎉 HANDLERS CONFIGURADOS")