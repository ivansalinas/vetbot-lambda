"""
VetBot — Setup infraestructura AWS Fase 1
Crea todos los recursos en la sub-cuenta vetbot-pamascotas.

USO:
    python setup_infra.py --profile vetbot-pamascotas
"""

import boto3, json, argparse, time, sys
from botocore.exceptions import ClientError

APP        = "vetbot"
CLIENTE    = "pamascotas"
REGION     = "us-east-1"
ACCOUNT_ID = "330631894163"

TAGS      = [{"Key":"proyecto","Value":"vetbot"},{"Key":"cliente","Value":"pamascotas"},{"Key":"ambiente","Value":"produccion"}]
TAGS_DICT = {t["Key"]:t["Value"] for t in TAGS}

ok   = lambda m: print(f"✅  {m}")
info = lambda m: print(f"ℹ️   {m}")
err  = lambda m: print(f"❌  {m}")


def crear_tablas(s):
    ddb = s.client("dynamodb", region_name=REGION)
    print("\n📦 DynamoDB")
    for name, pk, ttl_field, desc in [
        ("vetbot-sesiones","telefono","ttl",      "Sesiones bot (TTL 30min)"),
        ("vetbot-clientes","telefono",None,        "CRM clientes Pa'Mascotas"),
        ("vetbot-pedidos", "pedido_id",None,       "Pedidos confirmados"),
    ]:
        try:
            ddb.create_table(
                TableName=name,
                AttributeDefinitions=[{"AttributeName":pk,"AttributeType":"S"}],
                KeySchema=[{"AttributeName":pk,"KeyType":"HASH"}],
                BillingMode="PAY_PER_REQUEST", Tags=TAGS)
            ok(f"{name} — {desc}")
            if ttl_field:
                time.sleep(2)
                ddb.update_time_to_live(TableName=name,
                    TimeToLiveSpecification={"Enabled":True,"AttributeName":ttl_field})
                info(f"TTL activado en {name}.{ttl_field}")
        except ClientError as e:
            if "ResourceInUse" in str(e): info(f"Ya existe: {name}")
            else: err(f"{name}: {e}")


def crear_buckets(s):
    s3 = s.client("s3", region_name=REGION)
    print("\n🪣 S3 Buckets")
    for name, desc in [
        (f"vetbot-pamascotas-fotos-{ACCOUNT_ID}",       "Fotos catálogo productos"),
        (f"vetbot-pamascotas-logs-{ACCOUNT_ID}",        "Logs conversaciones backup"),
    ]:
        try:
            s3.create_bucket(Bucket=name)
            s3.put_bucket_tagging(Bucket=name, Tagging={"TagSet":TAGS})
            s3.put_public_access_block(Bucket=name, PublicAccessBlockConfiguration={
                "BlockPublicAcls":True,"IgnorePublicAcls":True,
                "BlockPublicPolicy":True,"RestrictPublicBuckets":True})
            ok(f"{name} — {desc}")
        except ClientError as e:
            if "BucketAlreadyOwned" in str(e): info(f"Ya existe: {name}")
            else: err(f"{name}: {e}")


def crear_secreto(s):
    sm = s.client("secretsmanager", region_name=REGION)
    print("\n🔐 Secrets Manager")
    nombre = "vetbot/pamascotas/credentials"
    placeholder = {
        "META_ACCESS_TOKEN":    "PENDIENTE",
        "META_PHONE_NUMBER_ID": "PENDIENTE",
        "META_VERIFY_TOKEN":    "vetbot-pamascotas-2025",
        "META_APP_SECRET":      "PENDIENTE",
        "SIIGO_PARTNER_ID":     "PENDIENTE",
        "SIIGO_CLIENT_SECRET":  "PENDIENTE",
        "SIIGO_ACCESS_TOKEN":   "",
    }
    try:
        sm.create_secret(Name=nombre,
            Description="Credenciales VetBot Pa'Mascotas — CONFIDENCIAL",
            SecretString=json.dumps(placeholder), Tags=TAGS)
        ok(f"Secreto creado: {nombre}")
        info("Reemplaza los valores PENDIENTE cuando el cliente entregue las credenciales")
    except ClientError as e:
        if "ResourceExists" in str(e): info(f"Ya existe: {nombre}")
        else: err(str(e))


def crear_role(s):
    iam = s.client("iam")
    print("\n👤 IAM Role Lambda")
    nombre = "vetbot-lambda-role"
    trust = json.dumps({"Version":"2012-10-17","Statement":[{
        "Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},
        "Action":"sts:AssumeRole"}]})
    try:
        r = iam.create_role(RoleName=nombre, AssumeRolePolicyDocument=trust,
            Description="Role Lambda VetBot Pa'Mascotas", Tags=TAGS)
        arn = r["Role"]["Arn"]
        ok(f"Role: {nombre}")
        for p in ["arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
                  "arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess",
                  "arn:aws:iam::aws:policy/SecretsManagerReadWrite"]:
            iam.attach_role_policy(RoleName=nombre, PolicyArn=p)
            ok(f"Policy: {p.split('/')[-1]}")
        iam.put_role_policy(RoleName=nombre, PolicyName="vetbot-bedrock",
            PolicyDocument=json.dumps({"Version":"2012-10-17","Statement":[{
                "Effect":"Allow","Action":["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],
                "Resource":"*"}]}))
        iam.put_role_policy(RoleName=nombre, PolicyName="vetbot-s3",
            PolicyDocument=json.dumps({"Version":"2012-10-17","Statement":[{
                "Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:ListBucket"],
                "Resource":["arn:aws:s3:::vetbot-pamascotas-*","arn:aws:s3:::vetbot-pamascotas-*/*"]}]}))
        ok("Policies Bedrock y S3 agregadas")
        return arn
    except ClientError as e:
        if "EntityAlreadyExists" in str(e):
            arn = iam.get_role(RoleName=nombre)["Role"]["Arn"]
            info(f"Ya existe: {nombre} — {arn}"); return arn
        else: err(str(e)); return ""


def crear_logs(s):
    cw = s.client("logs", region_name=REGION)
    print("\n📊 CloudWatch Logs")
    for lg in ["/aws/lambda/vetbot-handler", "/vetbot/conversaciones"]:
        try:
            cw.create_log_group(logGroupName=lg, tags=TAGS_DICT)
            cw.put_retention_policy(logGroupName=lg, retentionInDays=30)
            ok(f"{lg} (30 días retención)")
        except ClientError as e:
            if "AlreadyExists" in str(e): info(f"Ya existe: {lg}")
            else: err(str(e))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="vetbot-pamascotas")
    parser.add_argument("--region",  default="us-east-1")
    args = parser.parse_args()

    print(f"\n{'='*50}\nVetBot — Setup Infraestructura\nProfile: {args.profile} | Cuenta: {ACCOUNT_ID}\n{'='*50}")

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cuenta  = session.client("sts").get_caller_identity()["Account"]

    if cuenta != ACCOUNT_ID:
        err(f"Cuenta incorrecta: {cuenta}. Esperada: {ACCOUNT_ID}"); sys.exit(1)
    ok(f"Cuenta verificada: {cuenta}")

    crear_tablas(session)
    crear_buckets(session)
    role_arn = crear_role(session)
    crear_secreto(session)
    crear_logs(session)

    print(f"""
{'='*50}
✅  Infraestructura lista
Role ARN: {role_arn}

Próximo paso:
  python deploy_lambda.py --profile vetbot-pamascotas --role-arn {role_arn}
{'='*50}
""")

if __name__ == "__main__":
    main()
