def lambda_handler(event: dict, context):
    """
    Router que invoca webhook-receiver
    Mantiene compatibilidad con Meta webhook
    """
    try:
        method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
        
        # GET → verificación Meta
        if method == "GET":
            return handle_verification(event)
        
        # POST → invocar webhook-receiver
        elif method == "POST":
            lambda_client = boto3.client("lambda", region_name="us-east-1")
            try:
                response = lambda_client.invoke(
                    FunctionName="webhook-receiver",
                    InvocationType="Event",  # Async
                    Payload=json.dumps(event)
                )
                logger.info("✅ webhook-receiver invocada")
            except Exception as e:
                logger.error(f"Error invocando webhook-receiver: {e}")
            
            # Responder inmediatamente a Meta (200 OK)
            return {"statusCode": 200, "body": json.dumps({"status": "ok"})}
        
        return {"statusCode": 405, "body": "Method Not Allowed"}
    
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"statusCode": 200, "body": "OK"}

