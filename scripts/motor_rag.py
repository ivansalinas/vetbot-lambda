"""
VetBot — Motor RAG + consulta Siigo en tiempo real
Busca productos por similitud semántica y consulta precio/stock a Siigo.

USO:
    python scripts\motor_rag.py --profile vetbot-pamascotas --test "shampoo para perro"
"""
import boto3, json, argparse, math, urllib.request, urllib.parse
from decimal import Decimal

REGION       = "us-east-1"
ACCOUNT_ID   = "330631894163"
FOTOS_BUCKET = f"vetbot-pamascotas-fotos-{ACCOUNT_ID}"
TABLE_CAT    = "vetbot-catalogo"
EMBED_MODEL  = "amazon.titan-embed-text-v2:0"

USERNAME   = "ivana@tclasesores.com"
ACCESS_KEY = "YzlkMzkzYzctODViMy00YzRiLThiM2EtYTIwYzdmMDZmNTAwOjY3aTZZKDxxSEs="
PARTNER_ID = "vetbot"

def coseno(v1, v2):
    dot = sum(a*b for a,b in zip(v1,v2))
    n1  = math.sqrt(sum(a*a for a in v1))
    n2  = math.sqrt(sum(b*b for b in v2))
    return dot/(n1*n2) if n1 and n2 else 0.0

def get_siigo_token():
    req = urllib.request.Request(
        "https://api.siigo.com/auth/token",
        data=json.dumps({"username":USERNAME,"access_key":ACCESS_KEY}).encode(),
        headers={"Content-Type":"application/json","Partner-Id":PARTNER_ID},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]

def consultar_siigo(token, codigo):
    """Consulta precio y stock real en Siigo."""
    url = f"https://api.siigo.com/v1/products?code={urllib.parse.quote(codigo)}"
    req = urllib.request.Request(url,
        headers={"Authorization":f"Bearer {token}","Partner-Id":PARTNER_ID})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            data    = json.loads(r.read())
        results = data.get("results", [])
        if not results: return None
        p     = results[0]
        stock = float(p.get("available_quantity", 0) or 0)
        precio= 0
        try:
            precio = int(p.get("prices",[{}])[0].get("price_list",[{}])[0].get("value",0) or 0)
        except: pass
        nombre_siigo = p.get("name","").title()  # Convertir MAYUSCULAS a Title Case
        return {
            "nombre_siigo": nombre_siigo,
            "precio":       precio,
            "stock":        int(stock),
            "disponible":   stock > 0 and p.get("active", False),
        }
    except Exception as e:
        return None

def buscar(session, consulta, especie=None, top_k=3):
    bdr = session.client("bedrock-runtime", region_name=REGION)
    s3  = session.client("s3", region_name=REGION)
    ddb = session.resource("dynamodb", region_name=REGION)

    resp = bdr.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText":consulta,"dimensions":1024,"normalize":True}),
        contentType="application/json", accept="application/json",
    )
    vq = json.loads(resp["body"].read())["embedding"]

    objs = s3.list_objects_v2(Bucket=FOTOS_BUCKET, Prefix="embeddings/").get("Contents",[])
    if not objs:
        print("❌ Sin embeddings — ejecuta recargar_catalogo.py primero")
        return []

    scores = []
    for obj in objs:
        body = s3.get_object(Bucket=FOTOS_BUCKET, Key=obj["Key"])
        data = json.loads(body["Body"].read())
        scores.append((data["codigo_siigo"], coseno(vq, data["embedding"])))
    scores.sort(key=lambda x: x[1], reverse=True)

    tabla = ddb.Table(TABLE_CAT)
    prods = []
    for codigo, score in scores[:top_k*2]:
        item = tabla.get_item(Key={"codigo_siigo": codigo}).get("Item")
        if item:
            clean = {k:(float(v) if isinstance(v,Decimal) else v) for k,v in item.items()}
            clean["_score"] = round(score, 4)
            prods.append(clean)

    if especie:
        prods = [p for p in prods if especie.lower() in p.get("especie","todos").lower()
                 or "todos" in p.get("especie","").lower()]

    score_map = {c:s for c,s in scores}
    prods.sort(key=lambda p: score_map.get(p["codigo_siigo"],0), reverse=True)
    return prods[:top_k]

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="vetbot-pamascotas")
    parser.add_argument("--test",    required=True)
    parser.add_argument("--especie", default=None)
    parser.add_argument("--top",     type=int, default=3)
    args = parser.parse_args()

    print(f"\n🔍 Búsqueda: '{args.test}'")
    print(f"{'─'*55}")

    session = boto3.Session(profile_name=args.profile, region_name=REGION)
    results = buscar(session, args.test, args.especie, args.top)

    if not results:
        print("Sin resultados")
    else:
        print("Consultando precios en Siigo...\n")
        siigo_token = get_siigo_token()

        for i, p in enumerate(results, 1):
            siigo = consultar_siigo(siigo_token, p["codigo_siigo"])

            if siigo:
                disponible = "✅ Disponible" if siigo["disponible"] else "❌ Agotado"
                precio_fmt = f"${siigo['precio']:,.0f} COP".replace(",",".")
                print(f"[{i}] Score: {p.get('_score','?')}")
                print(f"    🐾 *{siigo['nombre_siigo']}*")
                print(f"    {p['descripcion_larga']}")
                print(f"    💰 {precio_fmt}  {disponible}  (stock: {siigo['stock']} unidades)")
                print(f"    Especie: {p.get('especie','?')} | Categoría: {p.get('categoria','?')}")
                print()
            else:
                print(f"[{i}] {p['codigo_siigo']} — sin datos de Siigo")
                print()
