"""
VetBot — Carga catálogo completo desde Siigo al RAG
Incluye:
  - Activos con stock → bot los ofrece
  - Activos sin stock no inventariables (stock_control=False) → siempre disponibles
  - Activos sin stock inventariables → bot los muestra como agotados
  - Inactivos → NO se cargan

Descripción, categoría y especie se infieren automáticamente del nombre.
"""
import boto3, json, time, urllib.request, urllib.parse
from decimal import Decimal

USERNAME   = "ivana@tclasesores.com"
ACCESS_KEY = "YzlkMzkzYzctODViMy00YzRiLThiM2EtYTIwYzdmMDZmNTAwOjY3aTZZKDxxSEs="  # ← Reemplazar
PARTNER_ID = "vetbot"
REGION     = "us-east-1"
ACCOUNT_ID = "330631894163"
FOTOS_BUCKET = f"vetbot-pamascotas-fotos-{ACCOUNT_ID}"
TABLE_CAT    = "vetbot-catalogo"
EMBED_MODEL  = "amazon.titan-embed-text-v2:0"
BATCH_PAUSE  = 0.3   # segundos entre embeddings (rate limit Bedrock)

ok   = lambda m: print(f"✅  {m}")
info = lambda m: print(f"ℹ️   {m}")
err  = lambda m: print(f"❌  {m}")


# ══════════════════════════════════════════════════════
#  INFERENCIA DE CATEGORÍA Y ESPECIE
# ══════════════════════════════════════════════════════
def inferir(nombre: str) -> tuple[str, str, str, str]:
    """
    Retorna: (categoria, especie, etapa_vida, palabras_clave)
    basado en el nombre real de Siigo.
    """
    n = nombre.upper()

    # ─ ESPECIE ────────────────────────────────────────
    es_gato = any(w in n for w in [
        'CAT ','CATS','GATO','GATI','GATIT','FELIN','FELINO',
        'MIRRINGO','KITTY','KITTEN','WHISKAS','FELIX','FRISKIES',
        'CATRINA','GATOCID','MIAU', 'PURRR',' CAT'
    ])
    es_perro = any(w in n for w in [
        'DOG ','DOGS','PERRO','CANIN','PUPPY','CACHORRO',
        'PEDIGREE','DOG CHOW','DOGOURMET','RICOCAN','CHUNKY',
        'CAMPESTRE','NUPEC','LAIKA','CAN ','CANS',' DOG'
    ])
    es_ave   = any(w in n for w in ['AVE ','AVES','PAJARO','PAJÁRO','LORO','CANARIO','PERIQUITO'])
    es_pez   = any(w in n for w in ['PEZ ','PECES','ACUARIO','TORTUGA','REPTIL'])

    if es_gato and not es_perro:
        especie = "Gato"
    elif es_perro and not es_gato:
        especie = "Perro"
    elif es_gato and es_perro:
        especie = "Todos"
    elif es_ave:
        especie = "Ave"
    elif es_pez:
        especie = "Pez"
    else:
        especie = "Todos"

    # ─ ETAPA DE VIDA ──────────────────────────────────
    if any(w in n for w in ['PUPPY','CACHORRO','KITTEN','GATIT','JUNIOR','BEBÉ','BEBE','INICIO','STARTER']):
        etapa = "Cachorro"
    elif any(w in n for w in ['SENIOR','MATURE','GERIATRIC','VEJEZ','MAYOR','7+']):
        etapa = "Senior"
    elif any(w in n for w in ['ADULT','ADULTO','MANTENIMIENTO','MAINTENANCE']):
        etapa = "Adulto"
    else:
        etapa = "Todas"

    # ─ CATEGORÍA ──────────────────────────────────────
    if any(w in n for w in [
        'SHAMPOO','CHAMPÚ','CHAMPU','JABON','JABÓN','BAÑO','BANO',
        'DENTAL','DENTI','CEPILL','HIGIENE','TOALL','DESODOR',
        'COLONIA','PERFUM','TALCO','ACONDIC','OÍDO','OIDO','OID'
    ]):
        cat = "Higiene"
    elif any(w in n for w in [
        'ANTIPULG','GARRAP','PARASIT','PULGA','IVERMECT','FIPRONIL',
        'FRONTLINE','NEXGARD','BRAVECTO','SIMPARIC','ADVANTIX',
        'ANTIPAR','DESPAR','VERMIF','PIPETA','COLLAR ANTI'
    ]):
        cat = "Medicamentos"
    elif any(w in n for w in [
        'SNACK','PREMIO','TREAT','GALLETA','GOLOSINA','DENTASTIX',
        'GREENIES','HUESO','PALITO','JERKY','MASTICA'
    ]):
        cat = "Snacks"
    elif any(w in n for w in [
        'ARENA','PIEDRA','SANITARI','LITTER','SILICA','BENTONIT'
    ]):
        cat = "Arena"
    elif any(w in n for w in [
        'CORREA','COLLAR','ARNES','ARNÉS','TRAILL','PLACA','CAMA',
        'COMEDERO','BEBEDER','JUGUETE','CASA','JAULA','TRANS',
        'ROPA','ACCESORIO','CEPILLO PELO','CORTAUN'
    ]):
        cat = "Accesorios"
    elif any(w in n for w in [
        'VITAMINA','SUPLEMENTO','CALCIO','OMEGA','PROBIOT',
        'ARTICULAC','CONDROIT','GLUCOSAMINA'
    ]):
        cat = "Suplementos"
    elif any(w in n for w in [
        'LATA','POUCH','SOBRE','PATE','PATÉ','HÚMEDO','HUMEDO',
        'BARF','NATURAL FRESH','FRESH'
    ]):
        if especie == "Gato":
            cat = "Alimento gato"
        else:
            cat = "Alimento perro"
    elif any(w in n for w in [
        'ROYAL','PURINA','PROPLAN','PRO PLAN','HILLS','SCIENCE DIET',
        'EUKANUBA','ACANA','ORIJEN','TASTE','NUPEC','CHUNKY',
        'DOGOURMET','RICOCAN','CAMPESTRE','PEDIGREE','DOG CHOW',
        'WHISKAS','FELIX','FRISKIES','MIRRINGO','GATOCID','CATRINA',
        'NUTRENA','AGILITY','BRAVOS','VITALCAN','EXCELLENT'
    ]):
        if especie == "Gato":
            cat = "Alimento gato"
        elif especie == "Perro":
            cat = "Alimento perro"
        else:
            cat = "Alimento"
    else:
        cat = "General"

    # ─ PALABRAS CLAVE ─────────────────────────────────
    kw_parts = [cat.lower(), especie.lower()]
    if etapa != "Todas":
        kw_parts.append(etapa.lower())
    palabras_clave = ",".join(kw_parts)

    return cat, especie, etapa, palabras_clave


def generar_descripcion(nombre: str, categoria: str, especie: str, etapa: str) -> str:
    """Genera descripción amigable basada en el nombre de Siigo."""
    n = nombre.title()

    # Detectar presentación
    presentacion = ""
    for token in nombre.upper().split():
        if any(u in token for u in ['KG','GR','ML','LT','OZ','LB','UN','PCS']):
            presentacion = token
            break

    if categoria in ("Alimento perro", "Alimento gato", "Alimento"):
        animal = "perros" if especie == "Perro" else "gatos" if especie == "Gato" else "mascotas"
        etapa_str = f" {etapa.lower()}s" if etapa not in ("Todas","Adulto") else ""
        return f"Alimento completo para {animal}{etapa_str}. {n}{'  · '+presentacion if presentacion else ''}."
    elif categoria == "Higiene":
        return f"Producto de higiene para mascotas. {n}{'  · '+presentacion if presentacion else ''}."
    elif categoria == "Medicamentos":
        return f"Antiparasitario y control de pulgas y garrapatas. {n}."
    elif categoria == "Snacks":
        animal = "perros" if especie == "Perro" else "gatos" if especie == "Gato" else "mascotas"
        return f"Premio y snack para {animal}. {n}{'  · '+presentacion if presentacion else ''}."
    elif categoria == "Arena":
        return f"Arena sanitaria para gatos. Absorción y control de olores. {n}."
    elif categoria == "Accesorios":
        return f"Accesorio para mascotas. {n}."
    elif categoria == "Suplementos":
        return f"Suplemento vitamínico para mascotas. {n}."
    else:
        return f"{n}{'  · '+presentacion if presentacion else ''}."


# ══════════════════════════════════════════════════════
#  SIIGO — AUTENTICACIÓN Y DESCARGA
# ══════════════════════════════════════════════════════
def get_token():
    req = urllib.request.Request(
        "https://api.siigo.com/auth/token",
        data=json.dumps({"username":USERNAME,"access_key":ACCESS_KEY}).encode(),
        headers={"Content-Type":"application/json","Partner-Id":PARTNER_ID},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())["access_token"]

def descargar_productos(token):
    todos = []; page = 1; total_esperado = None
    while True:
        url = f"https://api.siigo.com/v1/products?page={page}&page_size=100"
        req = urllib.request.Request(url,
            headers={"Authorization":f"Bearer {token}","Partner-Id":PARTNER_ID})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
            resultados = data.get("results", [])
            if total_esperado is None:
                total_esperado = data.get("pagination",{}).get("total_results",0)
                print(f"   Total en Siigo: {total_esperado}")
            if not resultados: break
            todos.extend(resultados)
            print(f"   Página {page} — {len(todos)}/{total_esperado}", end="\r")
            if len(resultados) < 100: break
            page += 1; time.sleep(0.4)
        except urllib.error.HTTPError as e:
            if e.code == 401:
                print(f"\n   Token expirado — renovando...")
                token = get_token()
            else:
                print(f"\n   HTTP {e.code} — reintentando..."); time.sleep(3)
        except Exception as e:
            print(f"\n   Error: {e}"); time.sleep(3)
    print(f"\n   Descarga completa: {len(todos)} productos")
    return todos


# ══════════════════════════════════════════════════════
#  CARGA AL RAG
# ══════════════════════════════════════════════════════
def generar_embedding(bedrock, texto):
    resp = bedrock.invoke_model(
        modelId=EMBED_MODEL,
        body=json.dumps({"inputText":texto,"dimensions":1024,"normalize":True}),
        contentType="application/json", accept="application/json",
    )
    return json.loads(resp["body"].read())["embedding"]

def cargar_producto(producto_raw, bedrock, s3_client, tabla):
    codigo        = producto_raw.get("code","")
    nombre        = producto_raw.get("name","")
    stock         = float(producto_raw.get("available_quantity",0) or 0)
    activo        = bool(producto_raw.get("active",False))
    stock_control = bool(producto_raw.get("stock_control",False))

    if not activo:
        return False, "inactivo"

    # Precio
    precio = 0
    try:
        precio = int(producto_raw.get("prices",[{}])[0].get("price_list",[{}])[0].get("value",0) or 0)
    except: pass

    categoria, especie, etapa, palabras_clave = inferir(nombre)
    descripcion = generar_descripcion(nombre, categoria, especie, etapa)

    texto_embedding = (
        f"{nombre} | {descripcion} | "
        f"Categoría: {categoria} | Especie: {especie} | {palabras_clave}"
    )

    # Generar embedding
    vector = generar_embedding(bedrock, texto_embedding)

    # Guardar en S3
    s3_client.put_object(
        Bucket=FOTOS_BUCKET,
        Key=f"embeddings/{codigo}.json",
        Body=json.dumps({
            "codigo_siigo": codigo,
            "embedding":    vector,
            "texto_fuente": texto_embedding,
        }),
        ContentType="application/json",
    )

    # Guardar en DynamoDB — SIN precio ni stock
    tabla.put_item(Item={
        "codigo_siigo":     codigo,
        "nombre":           nombre,
        "descripcion_larga":descripcion,
        "categoria":        categoria,
        "especie":          especie,
        "etapa_vida":       etapa,
        "palabras_clave":   palabras_clave,
        "nombre_foto":      codigo + ".jpg",
        "stock_control":    stock_control,
        # precio y stock NO se guardan — se consultan a Siigo en tiempo real
    })
    return True, "ok"


# ══════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════
def main():
    print("="*60)
    print("VetBot — Carga catálogo completo Siigo → RAG")
    print("Criterio: todos los activos (con stock, sin stock,")
    print("          y no inventariables)")
    print("="*60)

    session  = boto3.Session(profile_name="vetbot-pamascotas", region_name=REGION)
    cuenta   = session.client("sts").get_caller_identity()["Account"]
    if cuenta != ACCOUNT_ID:
        err(f"Cuenta incorrecta: {cuenta}"); return
    ok(f"Cuenta: {cuenta}")

    bedrock = session.client("bedrock-runtime", region_name=REGION)
    s3      = session.client("s3", region_name=REGION)
    tabla   = session.resource("dynamodb", region_name=REGION).Table(TABLE_CAT)

    print("\n1. Autenticando en Siigo...")
    token = get_token(); ok("Token Siigo OK")

    print("\n2. Descargando catálogo completo...")
    productos = descargar_productos(token)

    # Filtrar: solo activos
    activos = [p for p in productos if bool(p.get("active",False))]
    inactivos = len(productos) - len(activos)

    con_stock     = sum(1 for p in activos if float(p.get("available_quantity",0) or 0) > 0)
    sin_stock_inv = sum(1 for p in activos if float(p.get("available_quantity",0) or 0) == 0
                        and bool(p.get("stock_control",False)))
    no_inv        = sum(1 for p in activos if not bool(p.get("stock_control",False)))

    print(f"""
   Resumen:
   ✅ Activos con stock:              {con_stock:,}
   ⏳ Activos sin stock (inventariab): {sin_stock_inv:,}
   🔄 Activos no inventariables:      {no_inv:,}
   ❌ Inactivos (excluidos):          {inactivos:,}
   ─────────────────────────────────
   Total a cargar al RAG:             {len(activos):,}
""")

    respuesta = input("¿Cargar todos al RAG? (s/n): ").strip().lower()
    if respuesta != 's':
        print("Cancelado."); return

    print(f"\n3. Generando embeddings y cargando {len(activos)} productos...")
    print("   (Puede tomar 15-20 minutos para el catálogo completo)\n")

    ok_count = 0; err_count = 0
    for i, p in enumerate(activos, 1):
        codigo = p.get("code","")
        nombre = p.get("name","")[:35]
        print(f"  [{i:04d}/{len(activos)}] {codigo:<18} {nombre:<35}", end=" ", flush=True)
        try:
            exito, motivo = cargar_producto(p, bedrock, s3, tabla)
            if exito:
                ok_count += 1
                print("✅")
            else:
                print(f"⏭️  {motivo}")
        except Exception as e:
            err_count += 1
            print(f"❌ {str(e)[:50]}")
        time.sleep(BATCH_PAUSE)

        # Renovar token cada 200 productos
        if i % 200 == 0:
            info("Renovando token Siigo...")
            token = get_token()

    print(f"""
{'='*60}
✅ Carga completada

   Cargados:  {ok_count:,}
   Errores:   {err_count:,}
   Total:     {len(activos):,}

El bot ahora tiene acceso al catálogo completo de Pa'Mascotas.
Prueba escribiéndole: "Tienen comida para perro adulto mediano?"
{'='*60}
""")

if __name__ == "__main__":
    main()
