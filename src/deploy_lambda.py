"""
VetBot — Deploy Lambda + API Gateway
Empaqueta, crea/actualiza la Lambda y configura el webhook de Meta.

USO (primera vez):
    python deploy_lambda.py --profile vetbot-pamascotas

USO (actualizar código):
    python deploy_lambda.py --profile vetbot-pamascotas --update-only

USO (forzar un layer específico):
    python deploy_lambda.py --profile vetbot-pamascotas --layer-arn arn:aws:lambda:...
"""

import boto3, json, argparse, sys, time, zipfile, os
from botocore.exceptions import ClientError
from pathlib import Path

REGION      = "us-east-1"
ACCOUNT_ID  = "330631894163"
FUNC_NAME   = "vetbot-handler"
ROLE_NAME   = "vetbot-lambda-role"
API_NAME    = "vetbot-api"
STAGE_NAME  = "prod"
LAYER_NAME  = "numpy-py312"          # layer con numpy para el RAG en memoria

# Archivos que van al ZIP (todos en la raíz del zip, sin subcarpetas)
ARCHIVOS_LAMBDA = ["handler.py", "rag_search.py"]

TAGS      = {"proyecto":"vetbot","cliente":"pamascotas","ambiente":"produccion"}
ok   = lambda m: print(f"✅  {m}")
info = lambda m: print(f"ℹ️   {m}")
err  = lambda m: print(f"❌  {m}")
step = lambda m: print(f"\n{'─'*50}\n🔧 {m}\n{'─'*50}")


# ══════════════════════════════════════════════════════
#  PASO 0 — RESOLVER EL LAYER DE NUMPY
# ══════════════════════════════════════════════════════
def resolver_layer(session: boto3.Session, layer_arn_manual: str | None) -> str:
    step("Layer numpy")

    if layer_arn_manual:
        ok(f"Layer especificado a mano: {layer_arn_manual}")
        return layer_arn_manual

    lmb = session.client("lambda", region_name=REGION)
    try:
        versiones = lmb.list_layer_versions(
            LayerName=LAYER_NAME,
            CompatibleRuntime="python3.12",
        )["LayerVersions"]
    except ClientError as e:
        err(f"Error consultando el layer: {e}")
        sys.exit(1)

    if not versiones:
        err(f"No existe el layer '{LAYER_NAME}'. Créalo primero con:")
        print("""
    pip install numpy --platform manylinux2014_x86_64 --python-version 3.12 \\
        --only-binary=:all: --target .\\layer\\python
    Compress-Archive -Path .\\layer\\python -DestinationPath .\\numpy-layer.zip -Force
    aws lambda publish-layer-version --layer-name numpy-py312 \\
        --zip-file fileb://numpy-layer.zip --compatible-runtimes python3.12 \\
        --profile vetbot-pamascotas
""")
        sys.exit(1)

    # list_layer_versions devuelve la más reciente primero
    arn = versiones[0]["LayerVersionArn"]
    ok(f"Layer encontrado: {arn}")
    return arn


# ══════════════════════════════════════════════════════
#  PASO 1 — EMPAQUETAR EL CÓDIGO EN ZIP
# ══════════════════════════════════════════════════════
def empaquetar(src_dir: Path, zip_path: Path) -> None:
    step("Empaquetando código Lambda")

    faltantes = [n for n in ARCHIVOS_LAMBDA if not (src_dir / n).exists()]
    if faltantes:
        err(f"Faltan archivos en {src_dir}: {', '.join(faltantes)}")
        sys.exit(1)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for nombre in ARCHIVOS_LAMBDA:
            zf.write(src_dir / nombre, nombre)   # arcname sin ruta = raíz del zip
            info(f"→ {nombre}")

    size_kb = zip_path.stat().st_size / 1024
    ok(f"ZIP creado: {zip_path.name} ({size_kb:.1f} KB)")


# ══════════════════════════════════════════════════════
#  PASO 2 — CREAR O ACTUALIZAR LA LAMBDA
# ══════════════════════════════════════════════════════
def deploy_lambda(session: boto3.Session, zip_path: Path, update_only: bool,
                  layer_arn: str) -> str:
    step("Lambda Function")
    lmb = session.client("lambda", region_name=REGION)

    role_arn  = f"arn:aws:iam::{ACCOUNT_ID}:role/{ROLE_NAME}"
    zip_bytes = zip_path.read_bytes()

    env_vars = {
        "TABLE_SESIONES":      "vetbot-sesiones",
        "TABLE_CLIENTES":      "vetbot-clientes",
        "TABLE_PEDIDOS":       "vetbot-pedidos",
        "TABLE_IDEMPOTENCIA":  "vetbot-sesiones",
        "SECRET_NAME":         "vetbot/pamascotas/credentials",
        "REGION":              REGION,
        # Índice vectorial consolidado (build_vectors.py)
        "BUCKET_INDICE":       "vetbot-pamascotas-fotos-330631894163",
        "KEY_INDICE":          "index/catalogo.npz",
        "MODELO_EMBED":        "amazon.titan-embed-text-v2:0",
    }

    # Intentar actualizar primero
    try:
        lmb.update_function_code(
            FunctionName=FUNC_NAME,
            ZipFile=zip_bytes,
            Publish=True,
        )
        ok(f"Código actualizado: {FUNC_NAME}")

        # Esperar a que termine la actualización del código antes de tocar config
        info("Esperando a que la función quede lista...")
        lmb.get_waiter("function_updated_v2").wait(FunctionName=FUNC_NAME)

        lmb.update_function_configuration(
            FunctionName=FUNC_NAME,
            Timeout=29,
            MemorySize=512,
            Layers=[layer_arn],
            Environment={"Variables": env_vars},
        )
        ok("Configuración actualizada (layer + variables)")

        lmb.get_waiter("function_updated_v2").wait(FunctionName=FUNC_NAME)

        resp = lmb.get_function(FunctionName=FUNC_NAME)
        return resp["Configuration"]["FunctionArn"]

    except ClientError as e:
        if "ResourceNotFoundException" not in str(e):
            err(f"Error actualizando Lambda: {e}")
            sys.exit(1)

    if update_only:
        err("--update-only especificado pero la Lambda no existe. Corre sin --update-only primero.")
        sys.exit(1)

    # Crear nueva Lambda
    info("Lambda no existe — creando...")
    info("Esperando que el IAM role esté disponible (15s)...")
    time.sleep(15)

    try:
        resp = lmb.create_function(
            FunctionName=FUNC_NAME,
            Runtime="python3.12",
            Role=role_arn,
            Handler="handler.lambda_handler",
            Code={"ZipFile": zip_bytes},
            Timeout=29,
            MemorySize=512,
            Layers=[layer_arn],
            Environment={"Variables": env_vars},
            Tags=TAGS,
            Description="VetBot Pa'Mascotas — Asistente WhatsApp con IA",
        )
        func_arn = resp["FunctionArn"]
        ok(f"Lambda creada: {FUNC_NAME}")
        ok(f"ARN: {func_arn}")
        return func_arn

    except ClientError as e:
        err(f"Error creando Lambda: {e}")
        sys.exit(1)


# ══════════════════════════════════════════════════════
#  PASO 3 — API GATEWAY HTTP API
# ══════════════════════════════════════════════════════
def deploy_api_gateway(session: boto3.Session, func_arn: str, update_only: bool) -> str:
    step("API Gateway")
    apigw = session.client("apigatewayv2", region_name=REGION)
    lmb   = session.client("lambda", region_name=REGION)

    # Buscar si ya existe el API
    existing_api_id = None
    try:
        apis = apigw.get_apis()["Items"]
        for api in apis:
            if api["Name"] == API_NAME:
                existing_api_id = api["ApiId"]
                info(f"API Gateway existente encontrado: {existing_api_id}")
                break
    except ClientError:
        pass

    if existing_api_id and update_only:
        api_id = existing_api_id
        ok(f"API existente: {api_id}")
    else:
        if existing_api_id:
            api_id = existing_api_id
        else:
            resp = apigw.create_api(
                Name=API_NAME,
                ProtocolType="HTTP",
                Description="VetBot Pa'Mascotas — Webhook Meta WhatsApp",
                Tags=TAGS,
            )
            api_id = resp["ApiId"]
            ok(f"API Gateway creado: {api_id}")

    # Permiso para que API Gateway invoque Lambda
    try:
        lmb.add_permission(
            FunctionName=FUNC_NAME,
            StatementId="apigateway-invoke-vetbot",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:{ACCOUNT_ID}:{api_id}/*/*",
        )
        ok("Permiso Lambda ← API Gateway configurado")
    except ClientError as e:
        if "ResourceConflictException" in str(e):
            info("Permiso ya existe — omitiendo")
        else:
            err(f"Error configurando permiso: {e}")

    lambda_uri = (
        f"arn:aws:apigateway:{REGION}:lambda:path/2015-03-31"
        f"/functions/{func_arn}/invocations"
    )

    # Crear o actualizar integración
    try:
        integ = apigw.create_integration(
            ApiId=api_id,
            IntegrationType="AWS_PROXY",
            IntegrationUri=lambda_uri,
            PayloadFormatVersion="2.0",
            TimeoutInMillis=29000,
        )
        integ_id = integ["IntegrationId"]
        ok(f"Integración creada: {integ_id}")
    except ClientError:
        integs = apigw.get_integrations(ApiId=api_id)["Items"]
        integ_id = integs[0]["IntegrationId"] if integs else None
        if integ_id:
            info(f"Integración existente: {integ_id}")
        else:
            err("No se pudo crear ni encontrar la integración")
            sys.exit(1)

    # Rutas: GET /webhook (verificación) y POST /webhook (mensajes)
    for method in ["GET", "POST"]:
        route_key = f"{method} /webhook"
        try:
            apigw.create_route(
                ApiId=api_id,
                RouteKey=route_key,
                Target=f"integrations/{integ_id}",
            )
            ok(f"Ruta creada: {route_key}")
        except ClientError as e:
            if "ConflictException" in str(e) or "AlreadyExists" in str(e):
                info(f"Ruta ya existe: {route_key}")
            else:
                err(f"Error creando ruta {route_key}: {e}")

    # Stage de producción con auto-deploy
    try:
        apigw.create_stage(
            ApiId=api_id,
            StageName=STAGE_NAME,
            AutoDeploy=True,
            Tags=TAGS,
        )
        ok(f"Stage creado: {STAGE_NAME}")
    except ClientError as e:
        if "ConflictException" in str(e) or "AlreadyExists" in str(e):
            info(f"Stage ya existe: {STAGE_NAME}")
        else:
            err(f"Error creando stage: {e}")

    webhook_url = f"https://{api_id}.execute-api.{REGION}.amazonaws.com/{STAGE_NAME}/webhook"
    return webhook_url


# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="Deploy VetBot Lambda + API Gateway")
    parser.add_argument("--profile",     default="vetbot-pamascotas")
    parser.add_argument("--region",      default="us-east-1")
    parser.add_argument("--layer-arn",   default=None,
                        help="ARN del layer de numpy. Si se omite, usa la última versión de "
                             f"'{LAYER_NAME}' en la cuenta.")
    parser.add_argument("--update-only", action="store_true",
                        help="Solo actualizar código, no crear nuevos recursos")
    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════╗
║  VetBot — Deploy Lambda + API Gateway  ║
║  Profile: {args.profile:<30} ║
║  Update only: {str(args.update_only):<26} ║
╚══════════════════════════════════════════╝
""")

    script_dir = Path(__file__).parent
    src_dir    = script_dir.parent / "src"
    zip_path   = script_dir / "vetbot_lambda.zip"

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    cuenta  = session.client("sts").get_caller_identity()["Account"]
    if cuenta != ACCOUNT_ID:
        err(f"Cuenta incorrecta: {cuenta}. Esperada: {ACCOUNT_ID}")
        sys.exit(1)
    ok(f"Cuenta verificada: {cuenta}")

    layer_arn   = resolver_layer(session, args.layer_arn)
    empaquetar(src_dir, zip_path)
    func_arn    = deploy_lambda(session, zip_path, args.update_only, layer_arn)
    webhook_url = deploy_api_gateway(session, func_arn, args.update_only)

    print(f"""
╔══════════════════════════════════════════╗
║  ✅ Deploy completado                   ║
╚══════════════════════════════════════════╝

🔗 URL del webhook (pegar en Meta):
   {webhook_url}

🔑 Verify Token (configurar en Meta):
   vetbot-pamascotas-2025

🧠 Layer numpy:
   {layer_arn}

📋 Verificación rápida después del deploy:
   aws logs tail /aws/lambda/vetbot-handler --since 5m --follow \\
     --profile {args.profile}

   Busca la línea: [RAG] Indice cargado: 2740 productos
""")


if __name__ == "__main__":
    main()
