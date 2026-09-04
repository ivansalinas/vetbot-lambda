import logging
import json
import boto3
# ... resto de imports
def lambda_handler(event: dict, context):
    """Router que invoca webhook-receiver"""
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    try:
        method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
        
        if method == "GET":
            return handle_verification(event)
        
        elif method == "POST":
            lambda_client = boto3.client("lambda", region_name="us-east-1")
            try:
                response = lambda_client.invoke(
                    FunctionName="webhook-receiver",
                    InvocationType="Event",
                    Payload=json.dumps(event)
                )
                logger.info("✅ webhook-receiver invocada")
            except Exception as e:
                logger.error(f"Error invocando webhook-receiver: {e}")
            
            return {"statusCode": 200, "body": json.dumps({"status": "ok"})}
        
        return {"statusCode": 405, "body": "Method Not Allowed"}
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"statusCode": 200, "body": "OK"}
