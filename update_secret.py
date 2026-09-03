import boto3, json

client = boto3.client('secretsmanager', region_name='us-east-1')

secret = {
    "SIIGO_USERNAME": "ivana@tclasesores.com",
    "SIIGO_ACCESS_KEY": "YzlkMzkzYzctODViMy00YzRiLThiM2EtYTIwYzdmMDZmNTAwOjY3aTZZKDxxSEs=",
    "SIIGO_PARTNER_ID": "vetbot",
    "META_ACCESS_TOKEN": "EAGNrkiIGBr4BSZAtakReDvmwBxBbBB98YjZAERARdfnpBzq11UsstaX75tDGzF2jk7AKrUOCZAj9aEg8PbmoxGcu1FNvTZBU6u24BoG0RbBytujxnaZBYx2JBEHQUHileRaJAGfYTVi1bFsSlIxeVOmg7VKUh5acVH3ZAavPM3zzsZAMXnC4Ex8m5w3gmpoEXAVYgZDZD",
    "META_VERIFY_TOKEN": "vetbot-pamascotas-2025",
    "META_APP_SECRET": "ace444487cf7fb697f5d349afe3080b3",
    "META_PHONE_NUMBER_ID": "1261943447009395"
}

response = client.update_secret(SecretId='vetbot/pamascotas/credentials', SecretString=json.dumps(secret))
print(f"✅ TOKEN NUEVO — Version: {response['VersionId']}")