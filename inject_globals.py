#!/usr/bin/env python3
"""Inyecta variables globales en todas las lambdas"""

import os

GLOBALS = """# ═══════════════════════════════════════════════════════════════
# VARIABLES GLOBALES (del backup original)
# ═══════════════════════════════════════════════════════════════

# RAG
RAG_OK = False

# CLIENTES AWS
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
secrets = boto3.client("secretsmanager", region_name="us-east-1")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
s3 = boto3.client("s3", region_name="us-east-1")

# CONSTANTES
TABLE_SESIONES = os.environ.get("TABLE_SESIONES", "vetbot-sesiones")
TABLE_CLIENTES = os.environ.get("TABLE_CLIENTES", "vetbot-clientes")
TABLE_CATALOGO = os.environ.get("TABLE_CATALOGO", "vetbot-catalogo")
TABLE_IDEMPOTENCIA = os.environ.get("TABLE_IDEMPOTENCIA", "vetbot-sesiones")
SECRET_NAME = os.environ.get("SECRET_NAME", "vetbot/pamascotas/credentials")
FOTOS_BUCKET = os.environ.get("FOTOS_BUCKET", "vetbot-pamascotas-fotos-330631894163")
REGION = os.environ.get("REGION", "us-east-1")
SIIGO_TIMEOUT = 5
TTL_DEDUPE = 600

# CACHE DE SECRETS
_secrets_cache = None
_secrets_ts = 0

"""

LAMBDAS = [
    "vetbot-lambda-webhook",
    "vetbot-lambda-bedrock",
    "vetbot-lambda-search",
    "vetbot-lambda-whatsapp",
    "vetbot-lambda-crm"
]

for lambda_dir in LAMBDAS:
    handler_file = rf"C:\Users\ivanm\AWS\vetbot\{lambda_dir}\src\handler.py"
    
    with open(handler_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Encontrar dónde insertar (después de imports, antes de funciones)
    lines = content.split('\n')
    insert_idx = 0
    
    for i, line in enumerate(lines):
        if line.startswith('def ') and not line.startswith('def get_secrets'):
            insert_idx = i
            break
    
    # Insertar globales
    new_content = '\n'.join(lines[:insert_idx]) + '\n\n' + GLOBALS + '\n' + '\n'.join(lines[insert_idx:])
    
    with open(handler_file, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"✅ {lambda_dir}: variables globales inyectadas")

print("\n🎉 ¡¡¡TODAS LAS LAMBDAS ACTUALIZADAS!!!")