"""
VetBot — Preparar ambiente de pruebas completo
Carga fotos de ejemplo + embeddings mock para que el bot funcione sin datos del cliente.

USO:
    python scripts\preparar_pruebas.py --profile vetbot-pamascotas

Qué hace:
    1. Crea tabla vetbot-catalogo en DynamoDB (si no existe)
    2. Genera imágenes placeholder para los 10 productos más vendidos
    3. Sube las fotos placeholder a S3
    4. Genera embeddings Titan de los productos
    5. Guarda embeddings en S3 y datos en DynamoDB
    → Al terminar el bot puede buscar y mostrar productos
"""

import boto3, json, argparse, sys, time, struct, zlib
from decimal import Decimal

REGION     = "us-east-1"
ACCOUNT_ID = "330631894163"
FOTOS_BUCKET = f"vetbot-pamascotas-fotos-{ACCOUNT_ID}"
TABLE_CAT    = "vetbot-catalogo"
EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
EMBED_DIM    = 1024

ok   = lambda m: print(f"✅  {m}")
info = lambda m: print(f"ℹ️   {m}")
err  = lambda m: print(f"❌  {m}")
step = lambda n,t: print(f"\n{'─'*55}\n🔧 Paso {n}: {t}\n{'─'*55}")

# ─── 10 PRODUCTOS DE EJEMPLO ─────────────────────────
# Usamos los primeros 10 del catálogo real de Pa'Mascotas
# Los códigos son códigos de barras reales de Siigo
PRODUCTOS_EJEMPLO = [
    {"codigo_siigo":"645095003064",
     "nombre":"Salud Dental Perros TropiClean 4oz",
     "descripcion_larga":"Solución dental para perros. Agrega al agua del bebedero. Elimina el mal aliento y reduce el sarro. Frasco 4oz.",
     "categoria":"Higiene","especie":"Perro","etapa_vida":"Todas",
     "marca":"TropiClean","palabras_clave":"dental,sarro,aliento,agua,higiene"},

    {"codigo_siigo":"645095202184",
     "nombre":"Shampoo Luxury 2 en 1 20oz",
     "descripcion_larga":"Shampoo y acondicionador 2 en 1 para perros. Pelaje suave y brillante. Frasco 20oz.",
     "categoria":"Higiene","especie":"Perro","etapa_vida":"Todas",
     "marca":"TropiClean","palabras_clave":"shampoo,baño,pelaje,acondicionador"},

    {"codigo_siigo":"7707354230321",
     "nombre":"NaturProc Jabón en Barra 100g",
     "descripcion_larga":"Jabón natural para mascotas. Ingredientes naturales. Apto para piel sensible. Barra 100g.",
     "categoria":"Higiene","especie":"Todos","etapa_vida":"Todas",
     "marca":"NaturProc","palabras_clave":"jabon,natural,piel sensible,higiene"},

    {"codigo_siigo":"7501072214492",
     "nombre":"ProPlan Pouch Adulto Active Mind 85g",
     "descripcion_larga":"Alimento húmedo para gatos adultos. Fórmula Active Mind con Omega 3. Sobre 85g.",
     "categoria":"Alimento gato","especie":"Gato","etapa_vida":"Adulto",
     "marca":"ProPlan","palabras_clave":"gato adulto,humedo,pouch,omega 3"},

    {"codigo_siigo":"7708947802840",
     "nombre":"BR Dog Hepatic 2kg",
     "descripcion_larga":"Alimento veterinario para perros con problemas hepáticos. Bajo en cobre y sodio. Bolsa 2kg.",
     "categoria":"Alimento perro","especie":"Perro","etapa_vida":"Adulto",
     "marca":"Royal Canin Vet","palabras_clave":"hepatico,veterinario,higado,dieta"},

    {"codigo_siigo":"7708574195407",
     "nombre":"BR Dog Hepatic 2kg",
     "descripcion_larga":"Alimento terapéutico para perros con enfermedades hepáticas. Fácil digestión. Bolsa 2kg.",
     "categoria":"Alimento perro","especie":"Perro","etapa_vida":"Adulto",
     "marca":"Royal Canin Vet","palabras_clave":"hepatico,veterinario,terapeutico"},

    {"codigo_siigo":"7709002399138",
     "nombre":"BR Dog Gastrointestinal 4kg",
     "descripcion_larga":"Alimento veterinario para perros con problemas digestivos. Alta digestibilidad. Bolsa 4kg.",
     "categoria":"Alimento perro","especie":"Perro","etapa_vida":"Adulto",
     "marca":"Royal Canin Vet","palabras_clave":"gastrointestinal,digestivo,veterinario,estomago"},

    {"codigo_siigo":"5701111498039",
     "nombre":"Cerdito con Sonido 20cm",
     "descripcion_larga":"Juguete de peluche con sonido para perros. Forma de cerdito. Resistente. 20cm.",
     "categoria":"Accesorios","especie":"Perro","etapa_vida":"Todas",
     "marca":"Genérica","palabras_clave":"juguete,peluche,sonido,entretenimiento"},

    {"codigo_siigo":"7506306614617",
     "nombre":"Royal Canin Medium Adult 15kg",
     "descripcion_larga":"Alimento para perros adultos de razas medianas (11-25kg). Digestión óptima. Bolsa 15kg.",
     "categoria":"Alimento perro","especie":"Perro","etapa_vida":"Adulto",
     "marca":"Royal Canin","palabras_clave":"mediana raza,adulto,15kg,mantenimiento"},

    {"codigo_siigo":"7702217370321",
     "nombre":"Purina Dog Chow Adultos 22.7kg",
     "descripcion_larga":"Alimento completo para perros adultos. Proteínas y vitaminas esenciales. Bolsa 22.7kg.",
     "categoria":"Alimento perro","especie":"Perro","etapa_vida":"Adulto",
     "marca":"Purina","palabras_clave":"economico,adulto,grande,mantenimiento"},
]


def crear_png_placeholder(codigo: str, nombre: str) -> bytes:
    """
    Genera un PNG placeholder de 200x200 con el código del producto.
    No necesita librerías externas — genera el PNG binario directamente.
    """
    W, H = 200, 200

    def write_chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xffffffff)

    # Encabezado PNG
    sig = b'\x89PNG\r\n\x1a\n'

    # IHDR
    ihdr_data = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    ihdr = write_chunk(b'IHDR', ihdr_data)

    # IDAT — imagen sólida color azul claro con borde
    r, g, b_val = 0x1A, 0x3A, 0x6B  # Azul Automatiza Digital
    rows = []
    for y in range(H):
        row = b'\x00'  # filtro None
        for x in range(W):
            borde = (x < 4 or x >= W-4 or y < 4 or y >= H-4)
            if borde:
                row += bytes([0x0A, 0x1A, 0x3A])  # azul oscuro borde
            else:
                row += bytes([r, g, b_val])
        rows.append(row)
    raw = b''.join(rows)
    compressed = zlib.compress(raw, 9)
    idat = write_chunk(b'IDAT', compressed)

    # IEND
    iend = write_chunk(b'IEND', b'')

    return sig + ihdr + idat + iend


def crear_tabla_catalogo(ddb_client) -> None:
    from botocore.exceptions import ClientError
    try:
        ddb_client.create_table(
            TableName=TABLE_CAT,
            AttributeDefinitions=[{"AttributeName":"codigo_siigo","AttributeType":"S"}],
            KeySchema=[{"AttributeName":"codigo_siigo","KeyType":"HASH"}],
            BillingMode="PAY_PER_REQUEST",
            Tags=[{"Key":"proyecto","Value":"vetbot"},{"Key":"cliente","Value":"pamascotas"}]
        )
        ok(f"Tabla {TABLE_CAT} creada")
        waiter = ddb_client.get_waiter("table_exists")
        waiter.wait(TableName=TABLE_CAT)
        ok("Tabla activa")
    except ClientError as e:
        if "ResourceInUseException" in str(e):
            info(f"Tabla {TABLE_CAT} ya existe")
        else: raise


def subir_foto_placeholder(s3_client, codigo: str, nombre: str) -> str:
    png_bytes = crear_png_placeholder(codigo, nombre)
    key       = f"fotos/{codigo}.jpg"  # Guardamos como jpg aunque sea PNG (placeholder)
    s3_client.put_object(
        Bucket=FOTOS_BUCKET, Key=key,
        Body=png_bytes, ContentType="image/png",
        Metadata={"codigo": codigo, "tipo": "placeholder"}
    )
    url = f"https://{FOTOS_BUCKET}.s3.{REGION}.amazonaws.com/{key}"
    return url


def generar_y_guardar_embedding(producto: dict, bedrock_client, s3_client, ddb_resource) -> bool:
    codigo = producto["codigo_siigo"]
    texto  = (
        f"{producto['nombre']} | {producto['descripcion_larga']} | "
        f"Categoría: {producto['categoria']} | Especie: {producto['especie']} | "
        f"{producto.get('palabras_clave','')}"
    )

    try:
        # Generar embedding
        resp   = bedrock_client.invoke_model(
            modelId=EMBED_MODEL,
            body=json.dumps({"inputText": texto, "dimensions": EMBED_DIM, "normalize": True}),
            contentType="application/json", accept="application/json",
        )
        vector = json.loads(resp["body"].read())["embedding"]

        # Guardar embedding en S3
        s3_client.put_object(
            Bucket=FOTOS_BUCKET,
            Key=f"embeddings/{codigo}.json",
            Body=json.dumps({"codigo_siigo": codigo, "embedding": vector, "texto_fuente": texto}),
            ContentType="application/json",
        )

        # Guardar datos en DynamoDB
        tabla = ddb_resource.Table(TABLE_CAT)
        item  = {k: (Decimal(str(v)) if isinstance(v, (int, float)) else v)
                 for k, v in producto.items()}
        tabla.put_item(Item=item)

        ok(f"{codigo} — embedding OK")
        return True

    except Exception as e:
        err(f"{codigo}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Preparar ambiente de pruebas VetBot")
    parser.add_argument("--profile", default="vetbot-pamascotas")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"""
{'='*55}
VetBot — Preparar ambiente de pruebas
Profile: {args.profile}
{'='*55}
""")

    session   = boto3.Session(profile_name=args.profile, region_name=REGION)
    cuenta    = session.client("sts").get_caller_identity()["Account"]
    if cuenta != ACCOUNT_ID:
        err(f"Cuenta incorrecta: {cuenta}"); sys.exit(1)
    ok(f"Cuenta: {cuenta}")

    if args.dry_run:
        info("DRY RUN — no se crea nada")
        for p in PRODUCTOS_EJEMPLO:
            print(f"  {p['codigo_siigo']} | {p['nombre']}")
        return

    ddb     = session.client("dynamodb", region_name=REGION)
    ddb_res = session.resource("dynamodb", region_name=REGION)
    s3_cli  = session.client("s3", region_name=REGION)
    bdr     = session.client("bedrock-runtime", region_name=REGION)

    step(1, "Crear tabla DynamoDB del catálogo")
    crear_tabla_catalogo(ddb)

    step(2, f"Subir {len(PRODUCTOS_EJEMPLO)} fotos placeholder a S3")
    for p in PRODUCTOS_EJEMPLO:
        url = subir_foto_placeholder(s3_cli, p["codigo_siigo"], p["nombre"])
        ok(f"Foto: {p['codigo_siigo']}.jpg → {url[:60]}...")

    step(3, f"Generar embeddings Titan y cargar en S3 + DynamoDB")
    ok_count = 0
    for i, p in enumerate(PRODUCTOS_EJEMPLO, 1):
        print(f"  [{i:02d}/{len(PRODUCTOS_EJEMPLO)}] ", end="", flush=True)
        if generar_y_guardar_embedding(p, bdr, s3_cli, ddb_res):
            ok_count += 1
        time.sleep(0.3)

    print(f"""
{'='*55}
✅  Ambiente de pruebas listo

   Fotos placeholder:    {len(PRODUCTOS_EJEMPLO)} subidas a S3
   Embeddings generados: {ok_count}/{len(PRODUCTOS_EJEMPLO)}
   Tabla DynamoDB:       {TABLE_CAT}

Próximos pasos:
   1. Probar búsqueda RAG:
      python scripts\\motor_rag.py --profile vetbot-pamascotas --test "comida para perro"

   2. Conectar Meta sandbox:
      → developers.facebook.com → Tu App → WhatsApp → Webhooks
      → URL: https://vuc7a3fiak.execute-api.us-east-1.amazonaws.com/prod/webhook
      → Token: vetbot-pamascotas-2025

   3. Actualizar Lambda con el nuevo handler:
      python deploy\\deploy_lambda.py --profile vetbot-pamascotas --update-only

   4. Enviar mensaje de prueba desde WhatsApp sandbox
{'='*55}
""")

if __name__ == "__main__":
    main()
