#!/usr/bin/env python3
import boto3, zipfile, os

lambda_client = boto3.client("lambda", region_name="us-east-1")

# Crear ZIP
repo_dir = r"C:\Users\ivanm\AWS\vetbot"
zip_path = r"C:\Users\ivanm\AWS\vetbot\vetbot-handler.zip"

if os.path.exists(zip_path):
    os.remove(zip_path)

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', 'vetbot-lambda-*']]
        for file in files:
            if file.endswith('.py') and 'src' in root:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, repo_dir)
                zf.write(file_path, arcname)

print(f"✅ ZIP: {zip_path}")

# Deploy
with open(zip_path, 'rb') as f:
    zip_content = f.read()

try:
    response = lambda_client.update_function_code(
        FunctionName="vetbot-handler",
        ZipFile=zip_content
    )
    print("✅ ACTUALIZADA: vetbot-handler")
except Exception as e:
    print(f"❌ Error: {e}")

if os.path.exists(zip_path):
    os.remove(zip_path)

print("\n🎉 DEPLOY COMPLETADO")