#!/usr/bin/env python3
"""Configura permisos IAM para que lambdas se invoquen entre sí"""

import boto3

iam = boto3.client("iam")
lambda_client = boto3.client("lambda", region_name="us-east-1")

# Rol que usan todas las lambdas
ROLE_NAME = "vetbot-lambda-role"

# Política para que las lambdas se invoquen entre sí
policy_doc = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "lambda:InvokeFunction"
            ],
            "Resource": [
                "arn:aws:lambda:us-east-1:330631894163:function:webhook-receiver",
                "arn:aws:lambda:us-east-1:330631894163:function:bedrock-processor",
                "arn:aws:lambda:us-east-1:330631894163:function:search-engine",
                "arn:aws:lambda:us-east-1:330631894163:function:whatsapp-sender",
                "arn:aws:lambda:us-east-1:330631894163:function:crm-updater"
            ]
        }
    ]
}

try:
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName="vetbot-lambda-invoke",
        PolicyDocument=__import__('json').dumps(policy_doc)
    )
    print(f"✅ Permisos IAM configurados para {ROLE_NAME}")
except Exception as e:
    print(f"❌ Error: {e}")