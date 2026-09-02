"""
VetBot — Lambda Handler Principal
Pa'Mascotas Medellín · Automatiza Digital
Cuenta AWS: vetbot-pamascotas (330631894163)
Región: us-east-1
"""

import json, os, time, hashlib, hmac, logging, urllib.request, urllib.parse
from datetime import datetime, timezone
from typing import Optional
import boto3
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ─── CLIENTES AWS ─────────────────────────────────────
dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
secrets  = boto3.client("secretsmanager", region_name="us-east-1")
bedrock  = boto3.client("bedrock-runtime", region_name="us-east-1")
s3       = boto3.client("s3", region_name="us-east-1")

# ─── CONSTANTES ───────────────────────────────────────
TABLE_SESIONES = os.environ.get("TABLE_SESIONES", "vetbot-sesiones")
TABLE_CLIENTES = os.environ.get("TABLE_CLIENTES", "vetbot-clientes")
TABLE_CATALOGO = os.environ.get("TABLE_CATALOGO", "vetbot-catalogo")
SECRET_NAME    = os.environ.get("SECRET_NAME",    "vetbot/pamascotas/credentials")
FOTOS_BUCKET   = os.environ.get("FOTOS_BUCKET",   "vetbot-pamascotas-fotos-330631894163")
REGION         = os.environ.get("REGION",          "us-east-1")

# ─── CACHE DE SECRETS ─────────────────────────────────
_secrets_cache: Optional[dict] = None
_secrets_ts: float = 0

def get_secrets() -> dict:
    global _secrets_cache, _secrets_ts
    # Refrescar cada 50 minutos (token Siigo expira en ~60min)
    if _secrets_cache and (time.time() - _secrets_ts) < 3000:
        return _secrets_cache
    resp = secrets.get_secret_value(SecretId=SECRET_NAME)
    _secrets_cache = json.loads(resp["SecretString"])
    _secrets_ts = time.time()
    return _secrets_cache


# ══════════════════════════════════════════════════════
#  HANDLER PRINCIPAL
# ══════════════════════════════════════════════════════
def lambda_handler(event: dict, context) -> dict:
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    if method == "GET":
        return handle_verification(event)
    elif method == "POST":
        return handle_message(event)
    return {"statusCode": 405, "body": "Method Not Allowed"}


# ══════════════════════════════════════════════════════
#  VERIFICACIÓN WEBHOOK META (GET)
# ══════════════════════════════════════════════════════
def handle_verification(event: dict) -> dict:
    params    = event.get("queryStringParameters", {}) or {}
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")
    verify    = get_secrets().get("META_VERIFY_TOKEN", "vetbot-pamascotas-2025")
    if mode == "subscribe" and token == verify:
        logger.info("Webhook verificado OK")
        return {"statusCode": 200, "body": challenge}
    logger.warning(f"Verificación fallida — token: {token}")
    return {"statusCode": 403, "body": "Forbidden"}


# ══════════════════════════════════════════════════════
#  PROCESAMIENTO MENSAJE (POST)
# ══════════════════════════════════════════════════════
def handle_message(event: dict) -> dict:
    try:
        if not validar_firma(event):
            logger.warning("Firma HMAC inválida")
            return {"statusCode": 403, "body": "Forbidden"}

        body   = json.loads(event.get("body", "{}"))
        logger.info(f"Webhook: {json.dumps(body)[:500]}")

        msg = extraer_mensaje(body)
        if not msg:
            return {"statusCode": 200, "body": "OK"}

        telefono = msg["telefono"]
        texto    = msg["texto"]
        msg_id   = msg["id"]
        nombre   = msg.get("nombre", "")

        sesion = cargar_sesion(telefono)
        respuesta, sesion_nueva = generar_respuesta(texto, sesion, nombre)
        guardar_sesion(telefono, sesion_nueva)
        registrar_cliente(telefono, nombre, texto)
        enviar_mensaje(telefono, respuesta)
        marcar_leido(msg_id)

        return {"statusCode": 200, "body": "OK"}

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return {"statusCode": 200, "body": "OK"}


# ══════════════════════════════════════════════════════
#  VALIDACIÓN FIRMA HMAC
# ══════════════════════════════════════════════════════
def validar_firma(event: dict) -> bool:
    headers = event.get("headers", {})
    firma   = headers.get("x-hub-signature-256", "")
    if not firma:
        logger.warning("Sin firma HMAC — permitido en desarrollo")
        return True
    secret    = get_secrets().get("META_APP_SECRET", "")
    body_bytes= event.get("body", "").encode("utf-8")
    esperada  = "sha256=" + hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(firma, esperada)


# ══════════════════════════════════════════════════════
#  EXTRACCIÓN MENSAJE
# ══════════════════════════════════════════════════════
def extraer_mensaje(body: dict) -> Optional[dict]:
    try:
        value    = body["entry"][0]["changes"][0]["value"]
        if "statuses" in value:
            return None
        messages = value.get("messages", [])
        if not messages:
            return None
        msg  = messages[0]
        nombre = value.get("contacts", [{}])[0].get("profile", {}).get("name", "")
        if msg.get("type") != "text":
            return {"telefono": msg["from"], "id": msg["id"], "nombre": nombre,
                    "texto": "Por ahora solo puedo entender mensajes de texto 😊"}
        return {"telefono": msg["from"], "id": msg["id"], "nombre": nombre,
                "texto": msg["text"]["body"]}
    except (KeyError, IndexError) as e:
        logger.error(f"Error extrayendo: {e}")
        return None


# ══════════════════════════════════════════════════════
#  SESIONES (DynamoDB)
# ══════════════════════════════════════════════════════
def cargar_sesion(telefono: str) -> dict:
    tabla = dynamodb.Table(TABLE_SESIONES)
    item  = tabla.get_item(Key={"telefono": telefono}).get("Item")
    if item:
        return {"historial": item.get("historial", []),
                "estado":    item.get("estado", "inicio"),
                "mascota":   item.get("mascota", {}),
                "pedido":    item.get("pedido", {})}
    return {"historial": [], "estado": "inicio", "mascota": {}, "pedido": {}}

def guardar_sesion(telefono: str, sesion: dict) -> None:
    tabla = dynamodb.Table(TABLE_SESIONES)
    ttl   = int(time.time()) + 1800
    tabla.put_item(Item={
        "telefono":   telefono,
        "historial":  sesion["historial"][-20:],
        "estado":     sesion["estado"],
        "mascota":    sesion["mascota"],
        "pedido":     sesion["pedido"],
        "ttl":        ttl,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })


# ══════════════════════════════════════════════════════
#  SIIGO — STOCK Y PRECIO EN TIEMPO REAL
# ══════════════════════════════════════════════════════
_siigo_token: Optional[str] = None
_siigo_token_ts: float = 0

def get_siigo_token() -> str:
    global _siigo_token, _siigo_token_ts
    if _siigo_token and (time.time() - _siigo_token_ts) < 3000:
        return _siigo_token
    creds = get_secrets()
    req   = urllib.request.Request(
        "https://api.siigo.com/auth/token",
        data=json.dumps({
            "username":   creds.get("SIIGO_USERNAME", ""),
            "access_key": creds.get("SIIGO_ACCESS_KEY", ""),
        }).encode(),
        headers={"Content-Type": "application/json",
                 "Partner-Id":   creds.get("SIIGO_PARTNER_ID", "vetbot")},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read())
        _siigo_token    = data["access_token"]
        _siigo_token_ts = time.time()
        return _siigo_token

def consultar_siigo(codigo: str) -> tuple[bool, int, int, str]:
    """
    Consulta stock, precio y nombre real de un producto en Siigo.
    Returns: (disponible, precio_cop, stock, nombre_siigo)
    """
    creds = get_secrets()
    if "PENDIENTE" in creds.get("SIIGO_USERNAME", "PENDIENTE"):
        return True, 50000, 99, ""  # mock

    try:
        token = get_siigo_token()
        url   = f"https://api.siigo.com/v1/products?code={urllib.parse.quote(codigo)}"
        req   = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Partner-Id":    creds.get("SIIGO_PARTNER_ID", "vetbot"),
        })
        with urllib.request.urlopen(req, timeout=8) as r:
            data    = json.loads(r.read())
            results = data.get("results", [])
            if not results:
                return False, 0, 0, ""
            p      = results[0]
            stock  = float(p.get("available_quantity", 0) or 0)
            precio = 0
            try:
                precio = int(p.get("prices",[{}])[0].get("price_list",[{}])[0].get("value",0) or 0)
            except: pass
            activo = bool(p.get("active", False))
            nombre = p.get("name", "")
            return (activo and stock > 0), precio, int(stock), nombre
    except Exception as e:
        logger.error(f"Error Siigo para {codigo}: {e}")
        return True, 0, 0, ""


# ══════════════════════════════════════════════════════
#  RAG — BÚSQUEDA DE PRODUCTOS
# ══════════════════════════════════════════════════════
import math

def generar_embedding_consulta(texto: str) -> list:
    resp = bedrock.invoke_model(
        modelId="amazon.titan-embed-text-v2:0",
        body=json.dumps({"inputText": texto, "dimensions": 1024, "normalize": True}),
        contentType="application/json", accept="application/json",
    )
    return json.loads(resp["body"].read())["embedding"]

def coseno(v1: list, v2: list) -> float:
    dot   = sum(a*b for a,b in zip(v1,v2))
    n1    = math.sqrt(sum(a*a for a in v1))
    n2    = math.sqrt(sum(b*b for b in v2))
    return dot / (n1*n2) if n1 and n2 else 0.0

def buscar_productos_rag(consulta: str, especie: str = None, top_k: int = 3) -> list[dict]:
    """
    Busca productos semánticamente en S3 + DynamoDB.
    Filtra por especie si se especifica.
    """
    try:
        vector_consulta = generar_embedding_consulta(consulta)

        # Cargar embeddings del S3
        objs = s3.list_objects_v2(
            Bucket=FOTOS_BUCKET, Prefix="embeddings/"
        ).get("Contents", [])

        if not objs:
            logger.warning("Sin embeddings en S3 — usando catálogo mock")
            return productos_mock(especie, top_k)

        scores = []
        for obj in objs:
            body = s3.get_object(Bucket=FOTOS_BUCKET, Key=obj["Key"])
            data = json.loads(body["Body"].read())
            sim  = coseno(vector_consulta, data["embedding"])
            scores.append((data["codigo_siigo"], sim))

        scores.sort(key=lambda x: x[1], reverse=True)
        top_codigos = [c for c, _ in scores[:top_k*2]]

        # Obtener datos de DynamoDB
        tabla = dynamodb.Table(TABLE_CATALOGO)
        prods = []
        for codigo in top_codigos:
            item = tabla.get_item(Key={"codigo_siigo": codigo}).get("Item")
            if item:
                clean = {}
                for k, v in item.items():
                    clean[k] = int(v) if isinstance(v, Decimal) and v==int(v) \
                               else float(v) if isinstance(v, Decimal) else v
                prods.append(clean)

        # Filtrar por especie
        if especie:
            prods = [p for p in prods if especie.lower() in
                     p.get("especie","todos").lower() or
                     "todos" in p.get("especie","").lower()]

        score_map = {c: s for c, s in scores}
        prods.sort(key=lambda p: score_map.get(p["codigo_siigo"], 0), reverse=True)
        return prods[:top_k]

    except Exception as e:
        logger.error(f"Error RAG: {e}")
        return productos_mock(especie, top_k)

def productos_mock(especie: str = None, top_k: int = 3) -> list[dict]:
    """Fallback cuando no hay embeddings cargados."""
    mock = [
        {"codigo_siigo":"RC-MAXI-15","nombre":"Royal Canin Maxi Adult 15kg",
         "descripcion_larga":"Alimento para perros adultos de razas grandes. Articulaciones y digestión.","especie":"Perro","precio_mock":189000,"stock_mock":45},
        {"codigo_siigo":"RC-CAT-4","nombre":"Royal Canin Feline Health 4kg",
         "descripcion_larga":"Alimento para gatos adultos en interiores. Control de bolas de pelo.","especie":"Gato","precio_mock":68000,"stock_mock":40},
        {"codigo_siigo":"DENTASTIX-L","nombre":"DentaStix Large x28",
         "descripcion_larga":"Snack dental para perros grandes. Reduce el sarro hasta un 80%.","especie":"Perro","precio_mock":28000,"stock_mock":80},
    ]
    if especie:
        mock = [p for p in mock if especie.lower() in p.get("especie","").lower()]
    return mock[:top_k]

def formato_producto_wa(producto: dict, precio: int = None, stock: int = None, nombre_siigo: str = None) -> str:
    """Formatea un producto para WhatsApp."""
    p    = precio or 0
    s    = stock if stock is not None else 0
    disp = "✅ Disponible" if s > 0 else "❌ Agotado"
    pfmt = f"${p:,.0f} COP".replace(",",".")
    nombre = nombre_siigo.title() if nombre_siigo else producto.get("nombre", "")
    return f"🐾 *{nombre}*\n{producto['descripcion_larga']}\n💰 {pfmt}  {disp}  (stock: {s}u)"


# ══════════════════════════════════════════════════════
#  GENERACIÓN DE RESPUESTA (Bedrock Claude Haiku 3)
# ══════════════════════════════════════════════════════
SYSTEM_PROMPT = """Eres VetBot, el asistente virtual de Pa'Mascotas Medellín.
Eres un experto en productos para mascotas y tu misión es ayudar a los clientes
a encontrar el producto ideal y concretar la venta.

PERSONALIDAD:
- Amable, cálido y cercano. Tuteas al cliente.
- Apasionado por las mascotas. Pregunta el nombre de la mascota.
- Usa emojis con moderación (máximo 2-3 por mensaje).
- Respuestas cortas y directas. Máximo 5 líneas por mensaje.

REGLAS CRÍTICAS:
- NUNCA ofrezcas un producto agotado.
- SIEMPRE muestra el precio en COP.
- Recomienda máximo 3 productos por respuesta.
- Sugiere UN producto complementario por conversación.
- Si no sabes algo, dilo y ofrece conectar con un asesor humano.
- NUNCA inventes productos, precios ni información.
- Si el cliente quiere hablar con una persona, ofrécelo de inmediato.

FLUJO DE VENTA:
1. Saluda y pregunta qué necesita.
2. Identifica la mascota (especie, tamaño, edad si aplica).
3. Recomienda 2-3 productos con precio y disponibilidad.
4. Sugiere un producto complementario.
5. Cierra el pedido: confirma productos y pide dirección de entrega.

INFORMACIÓN DEL NEGOCIO:
- Nombre: Pa'Mascotas Medellín
- Horario tienda: lunes a sábado 8am-6pm
- Bot disponible 24/7
- Domicilios en Medellín y área metropolitana
- Tiempo de entrega: 1-3 horas en horario comercial
- Medios de pago: efectivo, Nequi o Bancolombia"""

def generar_respuesta(texto: str, sesion: dict, nombre: str) -> tuple[str, dict]:
    mensajes = list(sesion["historial"])
    mensajes.append({"role": "user", "content": texto})

    # Detectar si hay búsqueda de productos
    palabras_busqueda = ["necesito","quiero","busco","tienen","comida","alimento",
                         "producto","snack","premio","antipulgas","shampoo","arena"]
    if any(p in texto.lower() for p in palabras_busqueda):
        especie = None
        if any(w in texto.lower() for w in ["perro","can","cachorro","mascota"]):
            especie = "Perro"
        elif any(w in texto.lower() for w in ["gato","felino","gatito","michi"]):
            especie = "Gato"

        try:
            prods = buscar_productos_rag(texto, especie=especie, top_k=3)
            if prods:
                lineas = []
                for p in prods:
                    disponible, precio, stock, nombre_siigo = consultar_siigo(p["codigo_siigo"])
                    if disponible:
                        lineas.append(formato_producto_wa(p, precio, stock, nombre_siigo))
                if lineas:
                    ctx = "\n\n".join(lineas)
                    mensajes[-1]["content"] = (
                        f"{texto}\n\n[Productos disponibles en inventario — úsalos para tu respuesta]:\n{ctx}"
                    )
        except Exception as e:
            logger.error(f"Error enriqueciendo contexto RAG: {e}")

    try:
        resp = bedrock.invoke_model(
            modelId="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "system":     SYSTEM_PROMPT,
                "messages":   mensajes[-10:],
            }),
            contentType="application/json", accept="application/json",
        )
        texto_resp = json.loads(resp["body"].read())["content"][0]["text"]
        mensajes.append({"role": "assistant", "content": texto_resp})
        return texto_resp, {**sesion, "historial": mensajes}

    except Exception as e:
        logger.error(f"Error Bedrock: {e}")
        return ("Lo siento, tuve un problema técnico 😔 ¿Puedes repetir tu pregunta?", sesion)


# ══════════════════════════════════════════════════════
#  CRM
# ══════════════════════════════════════════════════════
def registrar_cliente(telefono: str, nombre: str, mensaje: str) -> None:
    try:
        tabla = dynamodb.Table(TABLE_CLIENTES)
        ahora = datetime.now(timezone.utc).isoformat()
        tabla.update_item(
            Key={"telefono": telefono},
            UpdateExpression=(
                "SET nombre = if_not_exists(nombre, :n), "
                "primera_interaccion = if_not_exists(primera_interaccion, :t), "
                "ultima_interaccion = :t, ultimo_mensaje = :m, "
                "interacciones = if_not_exists(interacciones, :z) + :o"
            ),
            ExpressionAttributeValues={
                ":n": nombre or "Sin nombre", ":t": ahora,
                ":m": mensaje[:200], ":z": 0, ":o": 1,
            }
        )
    except Exception as e:
        logger.error(f"Error CRM: {e}")


# ══════════════════════════════════════════════════════
#  ENVÍO MENSAJES META
# ══════════════════════════════════════════════════════
def enviar_mensaje(telefono: str, texto: str) -> None:
    creds    = get_secrets()
    token    = creds.get("META_ACCESS_TOKEN", "")
    phone_id = creds.get("META_PHONE_NUMBER_ID", "")
    if not token or token == "PENDIENTE":
        logger.info(f"[MOCK] → {telefono}: {texto[:80]}")
        return
    url     = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                telefono,
        "type":              "text",
        "text":              {"preview_url": False, "body": texto},
    }).encode()
    req = urllib.request.Request(url, data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            logger.info(f"Mensaje enviado a {telefono}: {r.read()[:100]}")
    except Exception as e:
        logger.error(f"Error enviando a {telefono}: {e}")

def marcar_leido(msg_id: str) -> None:
    creds    = get_secrets()
    token    = creds.get("META_ACCESS_TOKEN", "")
    phone_id = creds.get("META_PHONE_NUMBER_ID", "")
    if not token or token == "PENDIENTE":
        return
    url     = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "status":            "read",
        "message_id":        msg_id,
    }).encode()
    req = urllib.request.Request(url, data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            pass
    except Exception as e:
        logger.error(f"Error marcando leído {msg_id}: {e}")
