"""
Verifica que los 10 productos de prueba existen en Siigo
y muestra precio y stock real de cada uno.
"""
import urllib.request, json

USERNAME   = "ivana@tclasesores.com"
ACCESS_KEY = "YzlkMzkzYzctODViMy00YzRiLThiM2EtYTIwYzdmMDZmNTAwOjY3aTZZKDxxSEs="
PARTNER_ID = "vetbot"

CODIGOS = [
    "645095003064",
    "645095202184",
    "7707354230321",
    "7501072214492",
    "7708947802840",
    "7708574195407",
    "7709002399138",
    "5701111498039",
    "7506306614617",
    "7702217370321",
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

def consultar_producto(token, codigo):
    import urllib.parse
    url = f"https://api.siigo.com/v1/products?code={urllib.parse.quote(codigo)}"
    req = urllib.request.Request(url,
        headers={"Authorization":f"Bearer {token}","Partner-Id":PARTNER_ID})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        results = data.get("results", [])
        if not results:
            return None
        p = results[0]
        stock = float(p.get("available_quantity", 0) or 0)
        precio = 0
        try:
            precio = int(p.get("prices",[{}])[0].get("price_list",[{}])[0].get("value",0) or 0)
        except: pass
        return {
            "nombre": p.get("name",""),
            "stock":  stock,
            "precio": precio,
            "activo": p.get("active", False),
        }
    except Exception as e:
        return {"error": str(e)}

print("Verificando productos en Siigo...\n")
token = get_token()
print(f"{'Código':<18} {'Stock':>6} {'Precio':>12}  {'Nombre'}")
print("─" * 80)

for codigo in CODIGOS:
    p = consultar_producto(token, codigo)
    if not p:
        print(f"{codigo:<18} {'❌ NO EXISTE':>6}")
    elif "error" in p:
        print(f"{codigo:<18} {'❌ ERROR':>6}  {p['error'][:40]}")
    else:
        estado = "✅" if p["activo"] and p["stock"] > 0 else "⏳" if p["activo"] else "❌"
        print(f"{codigo:<18} {int(p['stock']):>5}u  ${p['precio']:>10,}  {estado} {p['nombre'][:40]}")
