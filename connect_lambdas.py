#!/usr/bin/env python3
"""Agrega invocaciones entre lambdas"""

import re

# 1. webhook → bedrock
webhook_file = r"C:\Users\ivanm\AWS\vetbot\vetbot-lambda-webhook\src\handler.py"
with open(webhook_file, 'r', encoding='utf-8') as f:
    webhook_code = f.read()

insert_point = webhook_code.find("        marcar_procesado(msg_id)")
if insert_point > 0:
    insert_after = webhook_code.find("\n", insert_point) + 1
    invocacion = """
        # Invocar bedrock-processor
        try:
            lambda_client = boto3.client("lambda", region_name="us-east-1")
            lambda_client.invoke(
                FunctionName="bedrock-processor",
                InvocationType="Event",
                Payload=json.dumps({"evento": msg})
            )
            logger.info(f"Invocada bedrock-processor para {msg.get('id')}")
        except Exception as e:
            logger.error(f"Error invocando bedrock: {e}")
"""
    webhook_code = webhook_code[:insert_after] + invocacion + webhook_code[insert_after:]

with open(webhook_file, 'w', encoding='utf-8') as f:
    f.write(webhook_code)

print("OK webhook")

# 2. bedrock → search
bedrock_file = r"C:\Users\ivanm\AWS\vetbot\vetbot-lambda-bedrock\src\handler.py"
with open(bedrock_file, 'r', encoding='utf-8') as f:
    bedrock_code = f.read()

insert_point = bedrock_code.find("        guardar_sesion(telefono, sesion_nueva)")
if insert_point > 0:
    insert_after = bedrock_code.find("\n", insert_point) + 1
    invocacion = """
        try:
            lambda_client = boto3.client("lambda", region_name="us-east-1")
            lambda_client.invoke(
                FunctionName="search-engine",
                InvocationType="Event",
                Payload=json.dumps({"consulta": texto, "especie": "gato", "respuesta_ia": respuesta, "telefono": telefono})
            )
        except Exception as e:
            logger.error(f"Error: {e}")
"""
    bedrock_code = bedrock_code[:insert_after] + invocacion + bedrock_code[insert_after:]

with open(bedrock_file, 'w', encoding='utf-8') as f:
    f.write(bedrock_code)

print("OK bedrock")

# 3. search → whatsapp + crm
search_file = r"C:\Users\ivanm\AWS\vetbot\vetbot-lambda-search\src\handler.py"
with open(search_file, 'r', encoding='utf-8') as f:
    search_code = f.read()

if "respuesta_final = f" in search_code:
    idx = search_code.find("respuesta_final = f")
    insert_after = search_code.find("\n", idx) + 1
    invocaciones = """
        try:
            lambda_client = boto3.client("lambda", region_name="us-east-1")
            telefono = event.get("telefono", "")
            lambda_client.invoke(FunctionName="whatsapp-sender", InvocationType="Event", Payload=json.dumps({"telefono": telefono, "texto": respuesta_final}))
            lambda_client.invoke(FunctionName="crm-updater", InvocationType="Event", Payload=json.dumps({"telefono": telefono, "nombre": "Cliente", "mensaje": event.get("consulta", "")}))
        except Exception as e:
            logger.error(f"Error: {e}")
"""
    search_code = search_code[:insert_after] + invocaciones + search_code[insert_after:]

with open(search_file, 'w', encoding='utf-8') as f:
    f.write(search_code)

print("OK search")
print("LISTO!")