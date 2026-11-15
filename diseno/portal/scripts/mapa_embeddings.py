"""Espacios de embeddings reales para el mapa: copia coordenadas PCA, categorías, clasificaciones y vecinos guardados.

Uso (con -I):
    python -I scripts/mapa_embeddings.py --demo <Vexplorer>/data/semantic_pipeline_demo --out public/local/mapa

No recalcula embeddings ni vecinos: los vecinos (coseno en las dimensiones originales) salen de neighbors/*.json.
Los snapshots solo traen PCA 2D, así que la PCA a 3 componentes se calcula aquí con numpy desde vectors/*.npz
(vectores L2, centrados, SVD), con el signo de PC1 y PC2 alineado con el snapshot y comprobando que coinciden. Los renders se extraen de portable-inputs.zip a renders/ con su manifiesto.
La biblioteca de la instancia (4 registros) no tiene vecinos guardados y se omite.
Salida: espacios.json (índice), espacios/<clave>.json y renders/manifest.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

import numpy as np

MODO = {"mixed": "mixto", "text": "texto", "image": "imagen"}
MODELO = {
    "google/embeddinggemma-2": "EmbeddingGemma 2",
    "facebook/dinov3-vits16-pretrain-lvd1689m": "DINOv3",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": "MiniLM",
}
# Corpus con nombre propio; el resto se nombra «modelo · modo dimensiones (n planos)».
PROPIOS = {
    "cad-eg2-logreg373": "CAD",
    "engineering-eg2-mixed-768": "Mecánicos",
    "plank-views-eg2-mixed-768": "Vistas PlankAssembly",
    "pilot-eg2-demo": "Piloto",
}
PRINCIPALES = ("eg2-mixed-768", "cad-eg2-logreg373")


def pca3(demo: Path, clave: str, pts: list[dict]) -> tuple[np.ndarray, list[float], float]:
    z = np.load(demo / "vectors" / f"{clave}.npz", allow_pickle=False)
    ids = [str(i) for i in z["ids"]]
    E = np.asarray(z["embeddings"], float)
    fila = {i: k for k, i in enumerate(ids)}
    E = E[[fila[p["id"]] for p in pts]]
    E = E / np.linalg.norm(E, axis=1, keepdims=True)
    C = E - E.mean(0)
    _, sv, vt = np.linalg.svd(C, full_matrices=False)
    Y = C @ vt[:3].T
    var = (sv**2 / (sv**2).sum())[:3]
    ref = np.array([[p["x"], p["y"]] for p in pts])
    for j in range(2):
        if np.dot(Y[:, j], ref[:, j]) < 0:
            Y[:, j] *= -1
    if Y[np.abs(Y[:, 2]).argmax(), 2] < 0:
        Y[:, 2] *= -1
    return Y, [round(float(v), 4) for v in var], float(np.abs(Y[:, :2] - ref).max())


def seguro(i: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", i)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    demo, out = Path(a.demo), Path(a.out)
    (out / "espacios").mkdir(parents=True, exist_ok=True)
    (out / "renders").mkdir(parents=True, exist_ok=True)

    # Renders: id de muestra -> PNG dentro del ZIP, comprobando que un mismo id no tenga dos imágenes distintas.
    zpath = demo / "portable-inputs.zip"
    z = zipfile.ZipFile(zpath)
    origen: dict[str, tuple[str, str]] = {}
    for nombre in z.namelist():
        if not nombre.endswith("/manifest.json"):
            continue
        corpus = nombre.split("/")[0]
        for s in json.loads(z.read(nombre))["samples"]:
            if not s.get("image_path"):
                continue
            ruta = f"{corpus}/{s['image_path']}"
            sha = hashlib.sha256(z.read(ruta)).hexdigest()
            previo = origen.get(s["id"])
            assert previo is None or previo[1] == sha, (s["id"], previo, ruta)
            if previo is None:
                origen[s["id"]] = (ruta, sha)
    renders = []
    for i, (ruta, sha) in sorted(origen.items()):
        archivo = f"{seguro(i)}.png"
        datos = z.read(ruta)
        (out / "renders" / archivo).write_bytes(datos)
        renders.append(dict(id=i, archivo=archivo, origen=ruta, sha256=sha, bytes=len(datos)))
    zsha = hashlib.sha256(zpath.read_bytes()).hexdigest()
    (out / "renders" / "manifest.json").write_text(
        json.dumps(dict(fuente="data/semantic_pipeline_demo/portable-inputs.zip", sha256_zip=zsha, renders=renders), ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    con_render = {r["id"]: r["archivo"] for r in renders}

    indice = []
    for sp in json.loads((demo / "spaces.json").read_text(encoding="utf-8"))["spaces"]:
        if sp["source"] != "corpus":
            continue
        clave = sp["id"].split(":", 1)[1]
        snap = json.loads((demo / "snapshots" / f"corpus-{clave}.json").read_text(encoding="utf-8"))
        vec = json.loads((demo / "neighbors" / f"{clave}.json").read_text(encoding="utf-8"))
        pts = snap["points"]
        pos = {p["id"]: k for k, p in enumerate(pts)}
        cats = sorted({p["category"] or "sin categoría" for p in pts})
        modelo = MODELO.get(sp["space"]["model"], sp["space"]["model"])
        modo = MODO.get(sp["space"]["mode"], sp["space"]["mode"])
        dims = sp["space"]["dimensions"]
        n = len(pts)
        assert n == sp["count"], (clave, n, sp["count"])
        nombre = f"{PROPIOS[clave]} ({n})" if clave in PROPIOS else f"{modelo} · {modo} {dims} ({n} planos)"
        Y, var, desvio = pca3(demo, clave, pts)
        puntos = []
        for k, p in enumerate(pts):
            c = p.get("classification")
            puntos.append(dict(
                id=p["id"],
                etiqueta=p["label"] if p["label"] != p["id"] else None,
                cat=cats.index(p["category"] or "sin categoría"),
                split=p["split"],
                x=round(float(Y[k, 0]), 6),
                y=round(float(Y[k, 1]), 6),
                z=round(float(Y[k, 2]), 6),
                render=con_render.get(p["id"]) if p.get("has_image") else None,
                clas=dict(etiqueta=c["label"], score=round(c["score"], 4), metodo=c["method"], calibrada=bool(c["calibrated"])) if c else None,
            ))
        vecinos = []
        for p in pts:
            lista = vec["neighbors"][p["id"]]
            vecinos.append([[pos[v["id"]], round(v["cosine"], 4)] for v in lista])
        doc = dict(
            clave=clave, nombre=nombre, modelo=sp["space"]["model"], modo=modo, dims=dims, n=n,
            metodo_vecinos=vec["method"], proyeccion=dict(metodo="pca3 desde vectors/*.npz", varianza=var, pc12_vs_snapshot=round(desvio, 6)), categorias=cats, puntos=puntos, vecinos=vecinos,
        )
        (out / "espacios" / f"{clave}.json").write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        indice.append(dict(clave=clave, nombre=nombre, n=n, principal=clave in PRINCIPALES, archivo=f"espacios/{clave}.json"))
        print(f"{nombre}: {n} puntos, {len(cats)} categorías, {sum(1 for x in puntos if x['render'])} renders, {sum(1 for x in puntos if x['clas'])} clasificaciones, varianza {var}, PC1-2 frente al snapshot {desvio:.1e}")
    indice.sort(key=lambda e: (not e["principal"], PRINCIPALES.index(e["clave"]) if e["principal"] else 0, e["nombre"]))
    (out / "espacios.json").write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    peso = sum(p.stat().st_size for p in (out / "renders").glob("*.png"))
    print(f"{len(renders)} renders, {peso / 1024:.0f} KB; {len(indice)} espacios")


if __name__ == "__main__":
    main()
