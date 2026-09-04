#!/usr/bin/env python3
"""Deploy todas las 5 lambdas a AWS"""

import boto3
import zipfile
import os
import shutil
import json

lambda_client = boto3.client("lambda", region_name="us-east-1")
iam_client = boto3.client("iam", region_name="us-east-1")

LAMBDAS = [
    ("vetbot-lambda-webhook", "webhook-receiver", "src/handler.lambda_handler"),
    ("vetbot-lambda-bedrock", "bedrock-processor", "src/handler.lambda_handler"),
    ("vetbot-lambda-search", "search-engine", "src/handler.lambda_handler"),
    ("vetbot-lambda-whatsapp", "whatsapp-sender", "src/handler.lambda_handler"),
    ("vetbot-lambda-crm", "crm-updater", "src/handler.lambda_handler"),
]

def crear_zip(repo_dir, zip_path):
    """Crea ZIP de la lambda"""
    if os.path.exists(zip_path):
        os.remove(zip_path)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(repo_dir):
            # Ignorar .git y __pycache__
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', '.venv']]
            
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, repo_dir)
                zf.write(file_path, arcname)
    
    print(f"✅ ZIP creado: {zip_path}")

def deploy_lambda(func_name, handler, zip_path):
    """Deploy lambda a AWS"""
    try:
        # Leer ZIP
        with open(zip_path, 'rb') as f:
            zip_content = f.read()
        
        # Intentar actualizar si existe
        try:
            response = lambda_client.update_function_code(
                FunctionName=func_name,
                ZipFile=zip_content
            )
            print(f"✅ ACTUALIZADA: {func_name}")
            return response
        except lambda_client.exceptions.ResourceNotFoundException:
            # Crear nueva
            response = lambda_client.create_function(
                FunctionName=func_name,
                Runtime="python3.12",
                Role="arn:aws:iam::330631894163:role/vetbot-lambda-role",
                Handler=handler,
                Code={"ZipFile": zip_content},
                Timeout=60,
                MemorySize=512,
                Environment={
                    "Variables": {
                        "TABLE_SESIONES": "vetbot-sesiones",
                        "TABLE_CLIENTES": "vetbot-clientes",
                        "TABLE_CATALOGO": "vetbot-catalogo"
                    }
                }
            )
            print(f"✅ CREADA: {func_name}")
            return response
    
    except Exception as e:
        print(f"❌ ERROR en {func_name}: {e}")
        return None

# DEPLOY
print("🚀 INICIANDO DEPLOY A AWS...\n")

for repo_name, func_name, handler in LAMBDAS:
    repo_dir = rf"C:\Users\ivanm\AWS\vetbot\{repo_name}"
    zip_path = rf"C:\Users\ivanm\AWS\vetbot\{func_name}.zip"
    
    print(f"\n📦 Procesando {func_name}...")
    crear_zip(repo_dir, zip_path)
    deploy_lambda(func_name, handler, zip_path)
    
    # Limpiar ZIP
    if os.path.exists(zip_path):
        os.remove(zip_path)

print("\n🎉 ¡¡¡TODAS LAS LAMBDAS DESPLEGADAS A AWS!!!")