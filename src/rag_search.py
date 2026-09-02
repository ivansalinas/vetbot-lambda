"""
VetBot — Busqueda RAG en memoria
Reemplaza la busqueda archivo-por-archivo en S3 (2.740 GET por mensaje).

Como funciona:
    _MATRIZ vive en el scope global. Se carga en el primer cold start
    (1 GET a S3 de ~10 MB) y queda cacheada mientras el contenedor viva.
    Las invocaciones siguientes buscan en RAM: ~5 ms para 2.740 x 1024.

Requiere numpy (va en el layer numpy-py312).
El indice lo genera build_vectors.py.
"""

import io
import json
import os

import boto3
import numpy as np

BUCKET = os.environ.get("BUCKET_INDICE", "vetbot-pamascotas-fotos-330631894163")
KEY_INDICE = os.environ.get("KEY_INDICE", "index/catalogo.npz")
MODELO_EMBED = os.environ.get("MODELO_EMBED", "amazon.titan-embed-text-v2:0")

_s3 = boto3.client("s3")
_bedrock = boto3.client("bedrock-runtime")

_MATRIZ = None
_METADATOS = None


def _cargar_indice():
    global _MATRIZ, _METADATOS
    if _MATRIZ is not None:
        return
    body = _s3.get_object(Bucket=BUCKET, Key=KEY_INDICE)["Body"].read()
    data = np.load(io.BytesIO(body), allow_pickle=False)
    _MATRIZ = data["matriz"]
    _METADATOS = json.loads(str(data["metadatos"]))
    print(f"[RAG] Indice cargado: {_MATRIZ.shape[0]} productos, dim {_MATRIZ.shape[1]}")


def _embed(texto: str) -> np.ndarray:
    # Mismos parametros con los que se generaron los embeddings del catalogo.
    resp = _bedrock.invoke_model(
        modelId=MODELO_EMBED,
        body=json.dumps({"inputText": texto, "dimensions": 1024, "normalize": True}),
        contentType="application/json",
        accept="application/json",
    )
    vec = json.loads(resp["body"].read())["embedding"]
    v = np.asarray(vec, dtype=np.float32)
    n = np.linalg.norm(v)
    return v / n if n else v


def buscar_productos(consulta: str, top_k: int = 5, umbral: float = 0.25):
    """Devuelve los top_k productos mas parecidos, cada uno con su 'score'.

    El contenido de cada dict es el metadato guardado en el JSON original
    del embedding (codigo_siigo, nombre, etc.), sin el vector.
    """
    _cargar_indice()
    q = _embed(consulta)

    # Ambos lados normalizados -> el producto punto ES la similitud coseno.
    scores = _MATRIZ @ q

    # argpartition evita ordenar los 2.740; solo saca los top_k.
    k = min(top_k, scores.shape[0])
    idx = np.argpartition(-scores, k - 1)[:k]
    idx = idx[np.argsort(-scores[idx])]

    resultados = []
    for i in idx:
        s = float(scores[i])
        if s < umbral:
            continue
        item = dict(_METADATOS[int(i)])
        item["score"] = round(s, 4)
        resultados.append(item)
    return resultados
