"""
VetBot — Consolida los embeddings sueltos de S3 en un unico archivo .npz

Problema que resuelve:
    Hoy la Lambda hace ~2.738 GET a S3 por cada mensaje -> timeout a los 29s.
    Este script descarga TODO una sola vez (en paralelo, desde tu maquina),
    construye una matriz numpy normalizada y la sube como UN solo objeto.
    La Lambda pasa de 2.738 GET a 1 GET, y solo en cold start.

Uso:
    python build_vectors.py --profile vetbot-pamascotas

Salida:
    s3://vetbot-pamascotas-fotos-330631894163/index/catalogo.npz
"""

import argparse
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor

import boto3
import numpy as np

BUCKET = "vetbot-pamascotas-fotos-330631894163"
PREFIX_ORIGEN = "embeddings/"
KEY_DESTINO = "index/catalogo.npz"

# El script no asume el nombre del campo del vector: prueba estos en orden.
CAMPOS_VECTOR = ("embedding", "vector", "values", "embeddings")


def listar_keys(s3, bucket, prefix):
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith(".json"):
                keys.append(obj["Key"])
    return keys


def descargar(s3, bucket, key):
    try:
        body = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
        return key, json.loads(body)
    except Exception as e:
        return key, {"__error__": str(e)}


def extraer_vector(doc):
    for campo in CAMPOS_VECTOR:
        if campo in doc and isinstance(doc[campo], list):
            return doc[campo], campo
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--region", default="us-east-1")
    ap.add_argument("--workers", type=int, default=32)
    args = ap.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3 = session.client("s3")

    print(f"Listando objetos en s3://{BUCKET}/{PREFIX_ORIGEN} ...")
    keys = listar_keys(s3, BUCKET, PREFIX_ORIGEN)
    print(f"  {len(keys):,} archivos JSON encontrados")
    if not keys:
        sys.exit("No hay embeddings en ese prefijo. Revisa PREFIX_ORIGEN.")

    print(f"Descargando con {args.workers} hilos ...")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        resultados = list(pool.map(lambda k: descargar(s3, BUCKET, k), keys))

    vectores, metadatos, errores, campo_usado = [], [], 0, None

    for key, doc in resultados:
        if "__error__" in doc:
            errores += 1
            continue
        vec, campo = extraer_vector(doc)
        if vec is None:
            errores += 1
            continue
        campo_usado = campo_usado or campo
        vectores.append(vec)
        # Todo lo que no sea el vector se guarda como metadato del producto
        meta = {k: v for k, v in doc.items() if k not in CAMPOS_VECTOR}
        meta["_key"] = key
        metadatos.append(meta)

    if not vectores:
        sys.exit("No se pudo extraer ningun vector. Muestrame un JSON de ejemplo.")

    dims = {len(v) for v in vectores}
    if len(dims) > 1:
        sys.exit(f"Dimensiones inconsistentes en los vectores: {dims}")

    M = np.asarray(vectores, dtype=np.float32)

    # Normalizacion previa: en runtime la busqueda es un solo producto punto,
    # sin calcular normas. Coseno = dot cuando ambos estan normalizados.
    normas = np.linalg.norm(M, axis=1, keepdims=True)
    normas[normas == 0] = 1.0
    M = M / normas

    print(f"  Matriz: {M.shape[0]:,} x {M.shape[1]} (campo '{campo_usado}')")
    print(f"  Errores/omitidos: {errores}")

    buf = io.BytesIO()
    np.savez_compressed(
        buf,
        matriz=M,
        metadatos=np.array(json.dumps(metadatos, ensure_ascii=False)),
    )
    buf.seek(0)
    tam_mb = len(buf.getvalue()) / 1024 / 1024

    s3.put_object(Bucket=BUCKET, Key=KEY_DESTINO, Body=buf.getvalue())
    print(f"\nSubido a s3://{BUCKET}/{KEY_DESTINO}  ({tam_mb:.1f} MB)")
    print("Listo. Ahora despliega la Lambda con el nuevo modulo de busqueda.")


if __name__ == "__main__":
    main()
