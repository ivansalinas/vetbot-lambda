#!/usr/bin/env python3
"""Extrae funciones del handler.py monolito a las 5 lambdas"""

import re
import os

# Ruta del monolito
monolito = r"C:\Users\ivanm\AWS\vetbot\src\handler.py"

# Mapeo: Lambda → funciones que necesita
LAMBDAS = {
    "vetbot-lambda-webhook": [
        "get_secrets",
        "validar_firma", 
        "extraer_mensaje",
        "ya_procesado",
        "handle_verification",
        "handle_message",
        "marcar_procesado"
    ],
    "vetbot-lambda-bedrock": [
        "get_secrets",
        "cargar_sesion",
        "guardar_sesion",
        "generar_respuesta"
    ],
    "vetbot-lambda-search": [
        "get_secrets",
        "get_siigo_token",
        "consultar_siigo",
        "consultar_siigo_lote",
        "buscar_productos_rag",
        "productos_mock",
        "formato_producto_wa"
    ],
    "vetbot-lambda-whatsapp": [
        "get_secrets",
        "enviar_mensaje",
        "marcar_leido"
    ],
    "vetbot-lambda-crm": [
        "registrar_cliente"
    ]
}

def extraer_funciones(contenido, nombres_func):
    """Extrae funciones del contenido"""
    resultado = []
    
    for nombre in nombres_func:
        # Regex para capturar la función completa
        patron = rf"^def {nombre}\(.*?\).*?:\n(.*?)(?=^def |\Z)"
        match = re.search(patron, contenido, re.MULTILINE | re.DOTALL)
        
        if match:
            # Capturar desde def hasta la siguiente función
            inicio = match.start()
            fin = match.end()
            funcion = contenido[inicio:fin].rstrip() + "\n\n"
            resultado.append(funcion)
            print(f"✅ Extraída: {nombre}")
        else:
            print(f"❌ NO ENCONTRADA: {nombre}")
    
    return "".join(resultado)

def crear_handler(lambda_name, funciones_code, imports_base):
    """Crea archivo handler.py para una lambda"""
    
    handler = f"""# -*- coding: utf-8 -*-
\"\"\"
VetBot Lambda: {lambda_name}
Auto-generada desde monolito handler.py
\"\"\"

{imports_base}

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
secrets = boto3.client("secretsmanager", region_name="us-east-1")
bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
s3 = boto3.client("s3", region_name="us-east-1")

TABLE_SESIONES = os.environ.get("TABLE_SESIONES", "vetbot-sesiones")
TABLE_CLIENTES = os.environ.get("TABLE_CLIENTES", "vetbot-clientes")
TABLE_CATALOGO = os.environ.get("TABLE_CATALOGO", "vetbot-catalogo")
SECRET_NAME = os.environ.get("SECRET_NAME", "vetbot/pamascotas/credentials")

{funciones_code}

def lambda_handler(event: dict, context) -> dict:
    \"\"\"Handler principal\"\"\"
    try:
        logger.info(f"Evento: {{json.dumps(event)[:200]}}")
        # Cada lambda tiene su lógica
        return {{"statusCode": 200, "body": "OK"}}
    except Exception as e:
        logger.error(f"Error: {{e}}", exc_info=True)
        return {{"statusCode": 200, "body": "OK"}}
"""
    
    return handler

# Leer monolito
with open(monolito, 'r', encoding='utf-8') as f:
    contenido = f.read()

# Extraer imports del monolito (primeras 50 líneas)
lineas = contenido.split('\n')
imports = []
for i, linea in enumerate(lineas[:50]):
    if linea.startswith('import ') or linea.startswith('from '):
        imports.append(linea)
    if 'TABLE_' in linea or 'SECRET_' in linea:
        break

imports_base = "\n".join(imports)

# Procesar cada lambda
for lambda_dir, funciones_necesarias in LAMBDAS.items():
    print(f"\n📦 Procesando {lambda_dir}...")
    
    ruta_handler = rf"C:\Users\ivanm\AWS\vetbot\{lambda_dir}\src\handler.py"
    
    # Extraer funciones
    funciones_code = extraer_funciones(contenido, funciones_necesarias)
    
    # Crear handler completo
    handler_completo = crear_handler(lambda_dir, funciones_code, imports_base)
    
    # Escribir archivo
    os.makedirs(os.path.dirname(ruta_handler), exist_ok=True)
    with open(ruta_handler, 'w', encoding='utf-8') as f:
        f.write(handler_completo)
    
    print(f"✅ Escrito: {ruta_handler}")

print("\n🎉 ¡¡¡TODAS LAS LAMBDAS ACTUALIZADAS!!!")