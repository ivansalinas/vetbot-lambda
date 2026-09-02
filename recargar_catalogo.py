"""
VetBot — Recarga catálogo con datos correctos
DynamoDB guarda: nombre, descripción, categoría, especie, embedding
Precio y stock: SIEMPRE se consultan a Siigo en tiempo real (NO se guardan)
"""
import boto3, json, time, urllib.request, urllib.parse
from decimal import Decimal

USERNAME   = "ivana@tclasesores.com"
ACCESS_KEY = "YzlkMzkzYzctODViMy00YzRiLThiM2EtYTIwYzdmMDZmNTAwOjY3aTZZKDxxSEs="
PARTNER_ID = "vetbot"
REGION     = "us-east-1"
ACCOUNT_ID = "330631894163"
FOTOS_BUCKET = f"vetbot-pamascotas-fotos-{ACCOUNT_ID}"
TABLE_CAT  = "vetbot-catalogo"
EMBED_MODEL= "amazon.titan-embed-text-v2:0"

ok  = lambda m: print(f"✅  {m}")
err = lambda m: print(f"❌  {m}")

# ─── CATÁLOGO — solo datos estáticos ─────────────────
# Precio y stock NO están aquí — se consultan a Siigo en tiempo real
PRODUCTOS = [
    {
        "codigo_siigo":     "645095003064",
        "nombre":           "SALUD DENTAL PERROS FCO X 4 OZ (TROPICLEAN)",
        "descripcion_larga":"Solución dental para perros. Se agrega al agua del bebedero. Elimina el mal aliento y reduce el sarro. Frasco 4oz.",
        "categoria":        "Higiene",
        "especie":          "Perro",
        "etapa_vida":       "Todas",
        "marca":            "TropiClean",
        "palabras_clave":   "dental,sarro,aliento,agua,higiene,dientes",
    },
    {
        "codigo_siigo":     "645095202184",
        "nombre":           "SHAMPOO LUXURY 2 EN 1 20 OZ",
        "descripcion_larga":"Shampoo y acondicionador 2 en 1 para perros. Deja el pelaje suave y brillante. Frasco 20oz.",
        "categoria":        "Higiene",
        "especie":          "Perro",
        "etapa_vida":       "Todas",
        "marca":            "TropiClean",
        "palabras_clave":   "shampoo,baño,pelaje,acondicionador,brillo",
    },
    {
        "codigo_siigo":     "7707354230321",
        "nombre":           "NATURPROC JABON EN BARRA 100GR",
        "descripcion_larga":"Jabón natural para mascotas. Ingredientes naturales, apto para piel sensible. Barra 100g.",
        "categoria":        "Higiene",
        "especie":          "Todos",
        "etapa_vida":       "Todas",
        "marca":            "NaturProc",
        "palabras_clave":   "jabon,natural,piel sensible,baño,higiene",
    },
    {
        "codigo_siigo":     "7501072214492",
        "nombre":           "PROPLAN POUCH ADULTO ACTIVE MIND 85GR",
        "descripcion_larga":"Alimento húmedo para gatos adultos. Fórmula Active Mind con Omega 3 para salud cerebral. Sobre 85g.",
        "categoria":        "Alimento gato",
        "especie":          "Gato",
        "etapa_vida":       "Adulto",
        "marca":            "ProPlan",
        "palabras_clave":   "gato adulto,humedo,pouch,omega 3,sobre",
    },
    {
        "codigo_siigo":     "7708574195407",
        "nombre":           "BR DOG HEPATIC 2KG",
        "descripcion_larga":"Alimento veterinario para perros con enfermedad hepática. Bajo en cobre y sodio. Bolsa 2kg.",
        "categoria":        "Alimento perro",
        "especie":          "Perro",
        "etapa_vida":       "Adulto",
        "marca":            "Royal Canin Vet",
        "palabras_clave":   "hepatico,veterinario,higado,dieta,terapeutico",
    },
]

def get_token():
    req = urllib.request.Request(
        "https://api.siigo.com/auth/token",
        data=json.dumps({"username":USERNAME,"access_key":ACCESS_KEY}).encode(),
        headers={"Content-Type":"application/json","Partner-Id":PARTNER_ID},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]

def verificar_en_siigo(token, codigo):
    """Solo verifica que el producto existe — precio/stock se consultan en tiempo real."""
    url = f"https://api.siigo.com/v1/products?code={urllib.parse.quote(codigo)}"
    req = urllib.request.Request(url,
        headers={"Authorization":f"Bearer {token}","Partner-Id":PARTNER_ID})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        results = data.get("results", [])
        if not results: return False, 0, 0
        p = results[0]
        stock = float(p.get("available_quantity", 0) or 0)
        precio = 0
        try:
            precio = int(p.get("prices",[{}])[0].get("price_list",[{}])[0].get("value",0) or 0)
        except: pass
        return p.get("active", False), stock, precio
    except:
        return False, 0, 0

def generar_embedding(bedrock, texto):
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText":texto,"dimensions":1024,"normalize":True}),
        contentType="application/json", accept="application/json",
    )
    return json.loads(resp["body"].read())["embedding"]

def main():
    print("="*60)
    print("VetBot — Recarga catálogo")
    print("DynamoDB: nombre + descripción + categoría (sin precio/stock)")
    print("Precio/stock: Siigo en tiempo real por el handler")
    print("="*60)

    session = boto3.Session(profile_name="vetbot-pamascotas", region_name=REGION)
    bedrock = session.client("bedrock-runtime", region_name=REGION)
    s3      = session.client("s3", region_name=REGION)
    tabla   = session.resource("dynamodb", region_name=REGION).Table(TABLE_CAT)

    print("\n1. Verificando existencia en Siigo (precio/stock solo referencial)...")
    token = get_token()
    print(f"\n{'Código':<18} {'Stock':>6} {'Precio':>12}  Estado")
    print("─"*55)
    for p in PRODUCTOS:
        activo, stock, precio = verificar_en_siigo(token, p["codigo_siigo"])
        estado = "✅ Con stock" if activo and stock > 0 else "⏳ Sin stock" if activo else "❌ Inactivo"
        print(f"{p['codigo_siigo']:<18} {int(stock):>5}u  ${precio:>10,}  {estado}")

    print(f"\n2. Cargando {len(PRODUCTOS)} productos en DynamoDB + S3 (SIN precio/stock)...")
    ok_count = 0
    for i, p in enumerate(PRODUCTOS, 1):
        print(f"  [{i:02d}/{len(PRODUCTOS)}] ", end="", flush=True)
        try:
            texto = (
                f"{p['nombre']} | {p['descripcion_larga']} | "
                f"Categoría: {p['categoria']} | Especie: {p['especie']} | "
                f"{p.get('palabras_clave','')}"
            )
            vector = generar_embedding(bedrock, texto)

            # S3 — solo el embedding
            s3.put_object(
                Bucket=FOTOS_BUCKET,
                Key=f"embeddings/{p['codigo_siigo']}.json",
                Body=json.dumps({
                    "codigo_siigo": p["codigo_siigo"],
                    "embedding":    vector,
                    "texto_fuente": texto,
                }),
                ContentType="application/json",
            )

            # DynamoDB — SOLO datos estáticos, SIN precio ni stock
            tabla.put_item(Item={
                "codigo_siigo":     p["codigo_siigo"],
                "nombre":           p["nombre"],
                "descripcion_larga":p["descripcion_larga"],
                "categoria":        p["categoria"],
                "especie":          p["especie"],
                "etapa_vida":       p.get("etapa_vida","Todas"),
                "marca":            p.get("marca",""),
                "palabras_clave":   p.get("palabras_clave",""),
                "nombre_foto":      p["codigo_siigo"] + ".jpg",
                # ⚠️ Sin precio_mock ni stock_mock — el handler consulta Siigo en tiempo real
            })
            ok(f"{p['codigo_siigo']} — embedding + DynamoDB OK")
            ok_count += 1
            time.sleep(0.3)

        except Exception as e:
            err(f"{p['codigo_siigo']}: {e}")

    print(f"""
{'='*60}
✅ {ok_count}/{len(PRODUCTOS)} productos cargados correctamente

Flujo en producción:
  Cliente escribe → RAG encuentra código → handler consulta
  Siigo en tiempo real → muestra precio y stock actualizados

Prueba el RAG:
  python scripts\\motor_rag.py --profile vetbot-pamascotas --test "shampoo para perro"
  python scripts\\motor_rag.py --profile vetbot-pamascotas --test "alimento para gato"
  python scripts\\motor_rag.py --profile vetbot-pamascotas --test "dental para perro"
{'='*60}
""")

if __name__ == "__main__":
    main()