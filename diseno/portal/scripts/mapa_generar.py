"""Mapa de muebles: vector geométrico, vecinos, PCA a 3 componentes y familias de los 26.707 modelos de PlankAssembly.

Uso (fuera de la carpeta del ZIP, con -I):
    python -I scripts/mapa_generar.py --zip <plankassembly-original.zip> --raros <seleccion.json> --out public/local/mapa

Sin modelos ni API: todo sale de las cajas `planks` ([xmin, ymin, zmin, xmax, ymax, zmax] en mm, la fila 0 es la envolvente).
Ejes: x = ancho, y = fondo (-y es el frente: los paneles de 9 mm se concentran en +y), z = alto. La silueta es la vista frontal x/z.
Mismas definiciones de `tipos` y `asim` que la selección de raros, y los pesos de bloque del `geometric_match` del producto
(0,60 medidas, 0,25 estructura, 0,15 grosor).
Salida: mapa3d.json (metadatos y familias), mapa3d.bin (columnas little-endian), ids.txt y sil/NNN.bin (siluetas por lotes de 1024).
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import struct
import time
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np

ROLES = ("laterales", "divisores", "tapas", "bases", "baldas", "traseras", "puertas", "cajones", "patas", "otras")
ROL_IDX = {r: i for i, r in enumerate(ROLES)}
K_VECINOS = 12
LOTE = 1024
SEMILLA = 20261114


def leer_ids(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    ids: list[tuple[str, str]] = []
    for split in ("train", "valid", "test"):
        for linea in z.read(f"data/splits/{split}.txt").decode().split():
            ids.append((linea.strip().removesuffix(".json"), split))
    ids.sort()
    assert len(ids) == 26707 and len({i for i, _ in ids}) == 26707, len(ids)
    return ids


def describir(planks: np.ndarray) -> tuple[dict, np.ndarray]:
    """Características de un mueble y sus rectángulos frontales (x0, z0, x1, z1, rol) en mm, de atrás adelante."""
    P = planks[1:]
    lo, hi = P[:, :3].min(0), P[:, 3:].max(0)
    W, D, H = (hi - lo).tolist()
    sz = P[:, 3:] - P[:, :3]
    eje = sz.argmin(1)
    gros = sz.min(1)
    ordenadas = np.sort(sz, 1)
    roles = np.zeros(len(P), dtype=np.int64)
    horiz = np.where(eje == 2)[0]
    zbase = P[horiz, 2].min() if len(horiz) else None
    for k, (p, a, t) in enumerate(zip(P, eje, gros)):
        if t >= 35 and ordenadas[k, 1] < 3 * t:  # barra de sección gruesa: pata o listón
            r = "patas"
        elif a == 0:  # vertical de canto lateral
            borde = min(p[0] - lo[0], hi[0] - p[3])
            r = "laterales" if borde <= 0.08 * W + 5 else "divisores"
        elif a == 2:  # horizontal
            if hi[2] - p[5] <= 5:
                r = "tapas"
            elif zbase is not None and p[2] - zbase <= 1 and p[2] - lo[2] <= 0.2 * H:
                r = "bases"
            else:
                r = "baldas"
        else:  # plano frontal (normal en y)
            cy = (p[1] + p[4]) / 2 - lo[1]
            if cy >= 0.75 * D:
                r = "traseras"
            elif cy <= 0.25 * D:
                r = "puertas" if sz[k, 2] >= 0.9 * sz[k, 0] else "cajones"
            else:
                r = "otras"
        roles[k] = ROL_IDX[r]
    cuenta = np.bincount(roles, minlength=len(ROLES))
    paneles = gros[gros < 35]
    tdom = Counter(np.rint(paneles).astype(int).tolist()).most_common(1)[0][0] if len(paneles) else int(round(gros.min()))
    cx = ((P[:, 0] + P[:, 3]) / 2).mean()
    asim = abs(cx - (lo[0] + hi[0]) / 2) / W
    tipos = len({tuple(sorted(round(float(v)) for v in s)) for s in sz})
    rasgos = dict(
        W=W, D=D, H=H, n=len(P), cuenta=cuenta, tdom=tdom, fino=float((gros <= 12).mean()),
        asim=float(asim), tipos=tipos, densidad=len(P) / max(W * D * H / 1e9, 1e-3),
    )
    orden = np.argsort(-((P[:, 1] + P[:, 4]) / 2), kind="stable")  # fondo primero, frente al final
    rect = np.column_stack([P[orden, 0] - lo[0], P[orden, 2] - lo[2], P[orden, 3] - lo[0], P[orden, 5] - lo[2], roles[orden]])
    return rasgos, rect


def vector(R: list[dict]) -> tuple[np.ndarray, list[str]]:
    cols: dict[str, tuple[np.ndarray, str]] = {}
    for c in ("W", "D", "H"):
        cols[f"log_{c}"] = (np.log([r[c] for r in R]), "medidas")
    cols["log_piezas"] = (np.log1p([r["n"] for r in R]), "estructura")
    for i, rol in enumerate(ROLES):
        cols[f"n_{rol}"] = (np.log1p([r["cuenta"][i] for r in R]), "estructura")
    cols["log_tipos"] = (np.log1p([r["tipos"] for r in R]), "estructura")
    cols["asim"] = (np.array([r["asim"] for r in R]), "estructura")
    cols["log_densidad"] = (np.log([r["densidad"] for r in R]), "estructura")
    cols["grosor"] = (np.array([r["tdom"] for r in R], float), "grosor")
    cols["fino"] = (np.array([r["fino"] for r in R]), "grosor")
    pesos = {"medidas": 0.60, "estructura": 0.25, "grosor": 0.15}
    por_bloque = Counter(b for _, b in cols.values())
    X = []
    for v, b in cols.values():
        sd = v.std()
        z = (v - v.mean()) / (sd if sd > 0 else 1.0)
        X.append(z * np.sqrt(pesos[b] / por_bloque[b]))
    return np.column_stack(X).astype(np.float64), list(cols)


def vecinos(X: np.ndarray, k: int, bloque: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    n = len(X)
    sq = (X * X).sum(1)
    idx = np.empty((n, k), np.int64)
    dist = np.empty((n, k), np.float64)
    todos = np.arange(n)
    for a in range(0, n, bloque):
        b = min(n, a + bloque)
        d2 = sq[a:b, None] + sq[None, :] - 2 * X[a:b] @ X.T
        np.maximum(d2, 0, out=d2)
        d2 = np.round(d2, 9)  # desempate estable por índice entre distancias iguales
        d2[np.arange(b - a), todos[a:b]] = np.inf
        cand = np.argpartition(d2, k + 8, axis=1)[:, : k + 8]
        for f in range(b - a):
            c = cand[f]
            o = np.lexsort((c, d2[f, c]))[:k]
            idx[a + f] = c[o]
            dist[a + f] = np.sqrt(d2[f, c[o]])
    return idx, dist


def pca(X: np.ndarray, k: int = 3) -> tuple[np.ndarray, np.ndarray]:
    """Componentes principales centradas por SVD con signo determinista; devuelve coordenadas y varianza explicada."""
    C = X - X.mean(0)
    _, sv, vt = np.linalg.svd(C, full_matrices=False)
    Y = C @ vt[:k].T
    for j in range(k):
        if Y[np.abs(Y[:, j]).argmax(), j] < 0:
            Y[:, j] *= -1
    return Y, (sv**2 / (sv**2).sum())[:k]


def conservacion(Y: np.ndarray, nbr: np.ndarray) -> float:
    """Fracción de los 12 vecinos del espacio completo que siguen entre los 12 más cercanos en la proyección."""
    i2, _ = vecinos(Y, nbr.shape[1], 2048)
    return float(np.mean([len(set(i2[i]) & set(nbr[i])) for i in range(len(Y))]) / nbr.shape[1])


def kmeans(X: np.ndarray, k: int, iters: int = 60) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(SEMILLA + k)
    C = [X[rng.integers(len(X))]]
    d2 = ((X - C[0]) ** 2).sum(1)
    for _ in range(1, k):
        C.append(X[rng.choice(len(X), p=d2 / d2.sum())])
        d2 = np.minimum(d2, ((X - C[-1]) ** 2).sum(1))
    C = np.array(C)
    lab = np.zeros(len(X), int)
    for _ in range(iters):
        dd = ((X[:, None, :] - C[None]) ** 2).sum(2)
        nuevo = dd.argmin(1)
        if (nuevo == lab).all() and _ > 0:
            break
        lab = nuevo
        C = np.array([X[lab == j].mean(0) if (lab == j).any() else C[j] for j in range(k)])
    return lab, C


def silueta(X: np.ndarray, lab: np.ndarray, m: int = 4000) -> float:
    rng = np.random.default_rng(SEMILLA)
    s = rng.choice(len(X), m, replace=False)
    Xs, ls = X[s], lab[s]
    sq = (Xs * Xs).sum(1)
    D = np.sqrt(np.maximum(sq[:, None] + sq[None] - 2 * Xs @ Xs.T, 0))
    out = []
    for i in range(m):
        same = ls == ls[i]
        same[i] = False
        if not same.any():
            continue
        a = D[i, same].mean()
        b = min(D[i, ls == j].mean() for j in set(ls.tolist()) if j != ls[i])
        out.append((b - a) / max(a, b))
    return float(np.mean(out))


def nombrar(R: list[dict], lab: np.ndarray, k: int) -> list[dict]:
    """Nombre de cada familia por reglas sobre sus medianas en mm y piezas. Nada inventado: cada palabra sale de una cifra."""
    fams = []
    for j in range(k):
        m = [R[i] for i in np.where(lab == j)[0]]
        med = lambda key: float(np.median([r[key] for r in m]))  # noqa: E731
        cnt = lambda rol: float(np.median([r["cuenta"][ROL_IDX[rol]] for r in m]))  # noqa: E731
        W, D, H = med("W"), med("D"), med("H")
        f = dict(W=W, D=D, H=H, n=med("n"), **{rol: cnt(rol) for rol in ROLES}, tdom=med("tdom"))
        f["frentes"] = f["puertas"] + f["cajones"]
        fams.append(f)
    for f in fams:
        alto = "altos" if f["H"] >= 1600 else ("bajos" if f["H"] < 1000 else "medios")
        if f["W"] >= 2.2 * f["H"]:
            ancho = "muy anchos"
        elif f["W"] >= 1400 or (alto == "bajos" and f["W"] >= 1.3 * f["H"]):
            ancho = "anchos"
        elif f["W"] <= 650 or f["W"] <= 0.42 * f["H"]:
            ancho = "estrechos"
        else:
            ancho = ""
        if f["patas"] >= 2 and f["H"] < 1000 and f["frentes"] == 0:
            sust = "Mesas"
        elif alto == "altos" and ancho == "estrechos":
            sust, alto, ancho = "Columnas", "altas", "estrechas"
        elif f["cajones"] >= 2 and f["cajones"] >= f["puertas"]:
            sust = "Cajoneras"
        elif f["puertas"] >= 1:
            sust = "Armarios" if alto == "altos" else "Muebles"
        elif f["baldas"] >= 2:
            sust, alto, ancho = "Estanterías", alto.replace("os", "as"), ancho.replace("chos", "chas")
        else:
            sust = "Módulos"
        partes = [sust, alto, ancho]
        if f["puertas"] >= 1 and sust != "Cajoneras":
            p = int(round(f["puertas"]))
            partes.append(f"de {p} puerta{'s' if p != 1 else ''}")
        elif f["cajones"] >= 1 and sust != "Cajoneras":
            partes.append("con cajones")
        elif f["baldas"] >= 1 and sust != "Mesas":
            b = int(round(f["baldas"]))
            partes.append(f"con {b} balda{'s' if b != 1 else ''}")
        elif f["patas"] >= 2 and sust != "Mesas":
            partes.append("con patas")
        elif f["frentes"] == 0 and sust != "Mesas":
            partes.append("abiertas" if sust in ("Columnas", "Estanterías") else "abiertos")
        f["nombre"] = " ".join(p for p in partes if p)
    # Desempate determinista: si dos familias se llaman igual, se añade la medida que más las separa.
    for _ in range(3):
        rep = Counter(f["nombre"] for f in fams)
        for nombre, c in rep.items():
            if c < 2:
                continue
            grupo = [f for f in fams if f["nombre"] == nombre]
            ratio = lambda key: max(g[key] for g in grupo) / max(min(g[key] for g in grupo), 1)  # noqa: E731
            clave = max(("D", "W", "H", "n", "tdom"), key=ratio)
            for g in grupo:
                v = int(round(g[clave] / 50) * 50) if clave in ("D", "W", "H") else int(round(g[clave]))
                g["nombre"] += {"D": f", {v} mm de fondo", "W": f", {v} mm de ancho", "H": f", {v} mm de alto", "n": f", {v} piezas", "tdom": f", tablero de {v} mm"}[clave]
    nombres = [f["nombre"] for f in fams]
    assert len(set(nombres)) == len(nombres), nombres
    return fams


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", required=True)
    ap.add_argument("--raros", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--k", type=int, default=0, help="familias; 0 elige entre 8 y 12 por silueta")
    args = ap.parse_args()
    t0 = time.time()
    out = Path(args.out)
    (out / "sil").mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(args.zip)
    ids = leer_ids(z)
    R, RECT = [], []
    for i, _ in ids:
        planks = np.array(json.loads(z.read(f"data/model/{i}.json"))["planks"], float)
        r, rect = describir(planks)
        R.append(r)
        RECT.append(rect)
    n = len(R)
    print(f"leídos {n} en {time.time() - t0:.1f} s")

    X, nombres_cols = vector(R)
    np.save(out / "vector.npy", X.astype(np.float32))  # para scripts/mapa_proyecciones.py; no lo carga el portal
    nbr, nd = vecinos(X, K_VECINOS)
    dup = int((nd[:, 0] == 0).sum())
    print(f"vecinos en {time.time() - t0:.1f} s; {dup} muebles con un gemelo a distancia 0")

    Y, var = pca(X, 3)
    c3 = conservacion(Y, nbr)
    print(f"PCA 3D: varianza {', '.join(f'{v:.3f}' for v in var)}; conservación de los 12 vecinos {c3:.3f}")

    if args.k:
        ks = {args.k: None}
    else:
        ks = {}
        for k in range(8, 13):
            lab, _ = kmeans(X, k)
            ks[k] = silueta(X, lab)
            print(f"k={k} silueta {ks[k]:.3f}, familia mínima {np.bincount(lab).min()}")
    # Se descartan los k que dejan una familia con menos del 1 % de los muebles: la silueta premia grupos diminutos de atípicos.
    validos = [kk for kk in ks if args.k or min(np.bincount(kmeans(X, kk)[0], minlength=kk)) >= 0.01 * n] or list(ks)
    k = args.k or max(validos, key=lambda kk: (round(ks[kk], 3), -kk))
    lab, C = kmeans(X, k)
    # Orden estable de familias: por alto mediano y luego ancho, para que el color siga a la familia y no al azar del k-means.
    med = [(float(np.median([R[i]["H"] for i in np.where(lab == j)[0]])), float(np.median([R[i]["W"] for i in np.where(lab == j)[0]])), j) for j in range(k)]
    orden = [j for _, _, j in sorted(med)]
    remap = np.empty(k, int)
    remap[orden] = np.arange(k)
    lab = remap[lab]
    fams = nombrar(R, lab, k)

    raros_sel = json.loads(Path(args.raros).read_text(encoding="utf-8"))
    pos_id = {i: p for p, (i, _) in enumerate(ids)}
    raros = [pos_id[r["id"]] for r in raros_sel]
    for r in raros_sel:  # mismas definiciones que la selección
        q = R[pos_id[r["id"]]]
        assert q["n"] == r["piezas"] and q["tipos"] == r["tipos"] and abs(q["asim"] - r["asim"]) < 1e-3, (r["id"], q["n"], q["tipos"], q["asim"])

    # Cuantización.
    lo, hi = Y.min(0), Y.max(0)
    ext = float((hi - lo).max())
    Q = np.rint((Y - lo) / ext * 65535).astype(np.uint16)  # x, y, z intercalados; misma escala en los tres ejes
    cols: list[tuple[str, np.ndarray]] = [
        ("pos", Q.reshape(-1)),
        ("medidas", np.rint([[r["W"], r["D"], r["H"]] for r in R]).astype(np.uint16).reshape(-1)),
        ("vecinos", nbr.astype(np.uint16).reshape(-1)),
        ("piezas", np.array([r["n"] for r in R], np.uint8)),
        ("split", np.array([{"train": 0, "valid": 1, "test": 2}[s] for _, s in ids], np.uint8)),
        ("familia", lab.astype(np.uint8)),
        ("roles", np.array([r["cuenta"] for r in R], np.uint8).reshape(-1)),
        ("tipos", np.array([r["tipos"] for r in R], np.uint8)),
        ("grosor", np.array([r["tdom"] for r in R], np.uint8)),
        ("asim", np.rint(np.array([r["asim"] for r in R]) * 1000).astype(np.uint16)),
    ]
    assert max(r["W"] for r in R) < 65535 and max(max(r["D"], r["H"]) for r in R) < 65535
    assert max(r["n"] for r in R) < 256 and max(r["tipos"] for r in R) < 256 and max(r["tdom"] for r in R) < 256
    assert int(nbr.max()) < 65535
    secciones, blob = [], bytearray()
    for nombre, arr in cols:
        while len(blob) % 4:
            blob.append(0)
        a = arr.astype(arr.dtype.newbyteorder("<"))
        secciones.append(dict(nombre=nombre, tipo=str(a.dtype.name), offset=len(blob), largo=int(a.size)))
        blob += a.tobytes()
    (out / "mapa3d.bin").write_bytes(bytes(blob))
    (out / "ids.txt").write_bytes("\n".join(i for i, _ in ids).encode("ascii"))  # sin CRLF en Windows

    # Siluetas: 5 bytes por pieza (x0, z0, x1, z1 en 0..255 sobre el ancho y el alto del mueble, rol), por lotes de 1024 muebles.
    lotes = 0
    for a in range(0, n, LOTE):
        buf = bytearray()
        for i in range(a, min(n, a + LOTE)):
            rect, r = RECT[i], R[i]
            q = np.empty((len(rect), 5), np.uint8)
            q[:, 0] = np.clip(np.floor(rect[:, 0] / r["W"] * 255), 0, 255)
            q[:, 1] = np.clip(np.floor(rect[:, 1] / r["H"] * 255), 0, 255)
            q[:, 2] = np.clip(np.ceil(rect[:, 2] / r["W"] * 255), 0, 255)
            q[:, 3] = np.clip(np.ceil(rect[:, 3] / r["H"] * 255), 0, 255)
            q[:, 4] = rect[:, 4]
            buf += q.tobytes()
        (out / "sil" / f"{a // LOTE:03d}.bin").write_bytes(bytes(buf))
        lotes += 1

    meta = dict(
        version=1,
        fuente="PlankAssembly, manycore-research, CC BY-NC-ND 4.0",
        n=n,
        k_vecinos=K_VECINOS,
        lote_siluetas=LOTE,
        lotes_siluetas=lotes,
        roles=list(ROLES),
        secciones=secciones,
        proyeccion=dict(metodo="pca3", varianza=[round(float(v), 4) for v in var], conservacion_12nn=round(c3, 4), origen=[round(float(v), 6) for v in lo], escala=ext),
        vector=dict(columnas=nombres_cols, pesos={"medidas": 0.6, "estructura": 0.25, "grosor": 0.15}),
        familias=[dict(nombre=f["nombre"], n=int((lab == j).sum()), W=round(f["W"]), D=round(f["D"]), H=round(f["H"]), piezas=round(f["n"])) for j, f in enumerate(fams)],
        silueta_k={str(kk): (round(v, 4) if v is not None else None) for kk, v in ks.items()},
        raros=raros,
        gemelos_distancia_cero=dup,
    )
    (out / "mapa3d.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    tam = {}
    for p in sorted(out.rglob("*")):
        if p.is_file() and p.name != "ping.json":
            b = p.read_bytes()
            tam[str(p.relative_to(out)).replace("\\", "/")] = (len(b), len(gzip.compress(b, 9)))
    sil = [v for kk, v in tam.items() if kk.startswith("sil/")]
    print("familias:")
    for j, f in enumerate(fams):
        print(f"  {j} {f['nombre']}: {(lab == j).sum()} · {f['W']:.0f}x{f['D']:.0f}x{f['H']:.0f} · {f['n']:.0f} piezas · " + " ".join(f"{r}={f[r]:.0f}" for r in ROLES if f[r]))
    for kk in ("mapa3d.bin", "ids.txt", "mapa3d.json"):
        print(f"{kk}: {tam[kk][0] / 1024:.0f} KB, gzip {tam[kk][1] / 1024:.0f} KB")
    print(f"sil/: {len(sil)} lotes, {sum(s for s, _ in sil) / 1024:.0f} KB, gzip {sum(g for _, g in sil) / 1024:.0f} KB")
    print("sha256 mapa3d.bin", hashlib.sha256((out / "mapa3d.bin").read_bytes()).hexdigest()[:16])
    print(f"total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
