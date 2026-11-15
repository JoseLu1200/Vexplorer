"""Proyecciones alternativas del mapa, precalculadas: UMAP 2D y t-SNE 2D para cada espacio (UMAP 3D solo en embeddings).

Uso (Python con scikit-learn y umap-learn, con -I):
    python -I scripts/mapa_proyecciones.py --demo <Vexplorer>/data/semantic_pipeline_demo --out public/local/mapa

PCA 3D y PCA 2D no se calculan aquí: el portal las toma de mapa3d.* y de espacios/*.json (PC1-PC3; PCA 2D es PC1-PC2).
Entradas: vector.npy de scripts/mapa_generar.py para la geometría y vectors/*.npz del paquete de demo para los
embeddings (sin recalcular embeddings). Los vecinos siguen saliendo del espacio original; esto solo coloca puntos.
Semillas fijas. Salida: proy/geometria.json + proy/geometria.bin (uint16 por proyección) y proy/<clave>.json.
Para cada proyección se guardan dos medidas de lectura: silueta de familias o categorías en la proyección y fracción
de los k vecinos del espacio original que siguen entre los k más cercanos en la proyección.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.metrics import silhouette_score
from sklearn.neighbors import NearestNeighbors

SEMILLA = 20261114
LIMITE_TSNE_S = 600


def metricas(Y: np.ndarray, etiquetas: np.ndarray, vecinos: np.ndarray, visibles: np.ndarray | None = None) -> dict:
    idx = np.arange(len(Y)) if visibles is None else np.where(visibles)[0]
    rng = np.random.default_rng(SEMILLA)
    m = idx if len(idx) <= 5000 else rng.choice(idx, 5000, replace=False)
    sil = float(silhouette_score(Y[m], etiquetas[m])) if len(set(etiquetas[m].tolist())) > 1 else None
    k = vecinos.shape[1]
    Yv = Y[idx]
    nn = NearestNeighbors(n_neighbors=k + 1).fit(Yv)
    _, ind = nn.kneighbors(Yv)
    pos = {g: j for j, g in enumerate(idx)}
    cons = []
    for j, g in enumerate(idx):
        orig = [pos[v] for v in vecinos[g] if v in pos]
        if orig:
            cons.append(len(set(ind[j, 1:].tolist()) & set(orig)) / len(orig))
    return dict(silueta=None if sil is None else round(sil, 4), conservacion_vecinos=round(float(np.mean(cons)), 4))


def umap(X: np.ndarray, dims: int, metrica: str, n_vecinos: int = 15) -> np.ndarray:
    import umap as umap_lib

    return umap_lib.UMAP(n_components=dims, n_neighbors=min(n_vecinos, len(X) - 1), min_dist=0.1, metric=metrica, random_state=SEMILLA).fit_transform(X)


def tsne(X: np.ndarray) -> np.ndarray:
    n = len(X)
    Xp = PCA(n_components=min(50, X.shape[1], n - 1), random_state=SEMILLA).fit_transform(X) if X.shape[1] > 50 else X
    perp = float(max(2, min(30, (n - 1) // 3)))
    return TSNE(n_components=2, perplexity=perp, init="pca", random_state=SEMILLA, learning_rate="auto").fit_transform(Xp)


def geometria(out: Path) -> None:
    X = np.load(out / "vector.npy").astype(np.float64)
    meta = json.loads((out / "mapa3d.json").read_text(encoding="utf-8"))
    buf = (out / "mapa3d.bin").read_bytes()
    sec = {s["nombre"]: s for s in meta["secciones"]}
    fam = np.frombuffer(buf, np.uint8, sec["familia"]["largo"], sec["familia"]["offset"]).astype(int)
    vec = np.frombuffer(buf, np.uint16, sec["vecinos"]["largo"], sec["vecinos"]["offset"]).reshape(len(X), -1).astype(int)
    n = len(X)
    proys: list[tuple[str, str, int, np.ndarray, np.ndarray | None, float]] = []

    t0 = time.time()
    U2 = umap(X, 2, "euclidean")
    proys.append(("umap2", "UMAP 2D", 2, U2, None, time.time() - t0))
    print(f"UMAP 2D en {time.time() - t0:.0f} s")

    # t-SNE completo; si supera el límite, muestra estratificada por familia de 8.000.
    t0 = time.time()
    T = tsne(X)
    dt = time.time() - t0
    print(f"t-SNE 2D completo en {dt:.0f} s")
    if dt <= LIMITE_TSNE_S:
        proys.append(("tsne2", "t-SNE 2D", 2, T, None, dt))
    else:
        rng = np.random.default_rng(SEMILLA)
        sel = np.concatenate([rng.choice(np.where(fam == f)[0], max(1, round(8000 * (fam == f).sum() / n)), replace=False) for f in np.unique(fam)])
        vis = np.zeros(n, bool)
        vis[sel] = True
        Ts = np.zeros((n, 2))
        Ts[sel] = tsne(X[sel])
        proys.append(("tsne2", f"t-SNE 2D · muestra {vis.sum():,}".replace(",", "."), 2, Ts, vis, time.time() - t0))

    blob = bytearray()
    indice = []
    for clave, nombre, dims, Y, vis, seg in proys:
        lo, hi = Y.min(0), Y.max(0)
        ext = float((hi - lo).max()) or 1.0
        q = np.rint((Y - lo) / ext * 65535).astype("<u2")
        while len(blob) % 4:
            blob.append(0)
        e = dict(clave=clave, nombre=nombre, dims=dims, offset=len(blob), largo=int(q.size), segundos=round(seg, 1), **metricas(Y, fam, vec, vis))
        blob += q.tobytes()
        if vis is not None:
            e["visibles_offset"] = len(blob)
            blob += vis.astype(np.uint8).tobytes()
        indice.append(e)
        print(f"  {nombre}: silueta {e['silueta']}, conservación {e['conservacion_vecinos']}")
    # Referencias PCA para el informe, con las mismas medidas.
    q = np.frombuffer(buf, np.uint16, sec["pos"]["largo"], sec["pos"]["offset"]).reshape(n, 3).astype(float)
    ref = {"pca3": metricas(q, fam, vec), "pca2": metricas(q[:, :2], fam, vec)}
    print(f"  PCA 3D: {ref['pca3']} · PCA 2D: {ref['pca2']}")
    (out / "proy").mkdir(exist_ok=True)
    (out / "proy" / "geometria.bin").write_bytes(bytes(blob))
    (out / "proy" / "geometria.json").write_text(json.dumps(dict(n=n, proyecciones=indice, referencia_pca=ref), ensure_ascii=False, indent=1), encoding="utf-8")


def embeddings(demo: Path, out: Path) -> None:
    for e in json.loads((out / "espacios.json").read_text(encoding="utf-8")):
        doc = json.loads((out / e["archivo"]).read_text(encoding="utf-8"))
        ids = [p["id"] for p in doc["puntos"]]
        z = np.load(demo / "vectors" / f"{e['clave']}.npz", allow_pickle=False)
        fila = {str(i): k for k, i in enumerate(z["ids"])}
        E = np.asarray(z["embeddings"], float)[[fila[i] for i in ids]]
        E = E / np.linalg.norm(E, axis=1, keepdims=True)
        cat = np.array([p["cat"] for p in doc["puntos"]])
        vec = np.array([[j for j, _ in l] for l in doc["vecinos"]])
        lista = []
        t0 = time.time()
        for clave, nombre, dims, Y in (
            ("tsne2", "t-SNE 2D", 2, tsne(E)),
            ("umap2", "UMAP 2D", 2, umap(E, 2, "cosine")),
            ("umap3", "UMAP 3D", 3, umap(E, 3, "cosine")),
        ):
            lista.append(dict(clave=clave, nombre=nombre, dims=dims, coords=[round(float(v), 5) for v in Y.reshape(-1)], **metricas(Y, cat, vec)))
        P = np.array([[p["x"], p["y"], p["z"]] for p in doc["puntos"]])
        ref = {"pca3": metricas(P, cat, vec), "pca2": metricas(P[:, :2], cat, vec)}
        (out / "proy" / f"{e['clave']}.json").write_text(json.dumps(dict(n=len(ids), proyecciones=lista, referencia_pca=ref), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        print(f"{e['nombre']}: {time.time() - t0:.0f} s · " + " · ".join(f"{p['nombre']} sil {p['silueta']} cons {p['conservacion_vecinos']}" for p in lista) + f" · PCA3 {ref['pca3']} · PCA2 {ref['pca2']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--solo", choices=["geometria", "embeddings"], default=None)
    a = ap.parse_args()
    out = Path(a.out)
    (out / "proy").mkdir(parents=True, exist_ok=True)
    if a.solo != "geometria":
        embeddings(Path(a.demo), out)
    if a.solo != "embeddings":
        geometria(out)


if __name__ == "__main__":
    main()
