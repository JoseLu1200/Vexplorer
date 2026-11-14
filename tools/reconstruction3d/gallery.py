"""Build a local evidence gallery; missing/failed outputs stay visibly missing."""

import argparse
import html
import json
from pathlib import Path
from PIL import Image, ImageDraw


def build(root):
    manifest = json.loads((root / "public-manifest.json").read_text())
    labels = [
        "Entrada pública",
        "A · plano → Idol",
        "B · harness",
        "C · B → Idol",
        "D · control privilegiado",
        "Referencia reservada",
    ]
    sheet = Image.new("RGB", (6 * 280, len(manifest["cases"]) * 310), "white")
    draw = ImageDraw.Draw(sheet)
    rows = []
    for index, case in enumerate(manifest["cases"]):
        cid = case["id"]
        paths = [
            Path(case["input"]),
            Path(f"results/A/{cid}/seed-42/diagnostic-views/view-00.png"),
            Path(f"results/B/{cid}/artifacts/view-00.png"),
            Path(f"results/C/{cid}/seed-42/diagnostic-views/view-00.png"),
            Path(f"results/D/{cid}/seed-42/diagnostic-views/view-00.png"),
            Path(f"references/{cid}/view-00.png"),
        ]
        cells = []
        for col, (label, path) in enumerate(zip(labels, paths)):
            draw.text((col * 280 + 8, index * 310 + 8), cid + " " + label, fill="black")
            if (root / path).exists():
                im = Image.open(root / path).convert("RGB")
                im.thumbnail((275, 275))
                sheet.paste(im, (col * 280, index * 310 + 30))
                cells.append(
                    f'<td><a href="{path.as_posix()}"><img src="{path.as_posix()}" alt="{html.escape(cid + ": " + label)}"></a></td>'
                )
            else:
                draw.text(
                    (col * 280 + 15, index * 310 + 140), "Sin resultado", fill="red"
                )
                cells.append("<td>Sin resultado generado</td>")
        rows.append("<tr>" + "".join(cells) + "</tr>")
        views = Image.new("RGB", (6 * 256, 4 * 285), "white")
        vd = ImageDraw.Draw(views)
        for row, variant in enumerate(("A", "B", "C", "D")):
            base = root / "results" / variant / cid
            folder = (
                base / "artifacts"
                if variant == "B"
                else base / "seed-42" / "diagnostic-views"
            )
            for n in range(6):
                vd.text(
                    (n * 256 + 5, row * 285 + 5),
                    f"{cid} {variant} vista {n}",
                    fill="black",
                )
                path = folder / f"view-{n:02d}.png"
                if path.exists():
                    im = Image.open(path).convert("RGB")
                    im.thumbnail((256, 256))
                    views.paste(im, (n * 256, row * 285 + 25))
        views.save(root / f"all-views-{cid}.png")
        rows.append(
            f'<tr><td colspan="6"><a href="all-views-{cid}.png">{cid}: seis ángulos de cada variante</a> · <a href="results/B/{cid}/artifacts/exploded.png">Despiece B</a> · <a href="results/B/{cid}/outcome.json">Hipótesis y traza B</a></td></tr>'
        )
    sheet.save(root / "four-arm-comparison.png")
    document = (
        """<!doctype html><html lang="es"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Vexplorer · Evaluación 3D</title><style>body{font:16px system-ui;margin:28px;color:#172126;background:#fafaf7}h1{font-size:30px}p{max-width:100ch;line-height:1.6}table{width:100%;border-collapse:collapse}td,th{border:1px solid #ccd2d5;padding:8px}img{width:100%;min-width:140px}a{color:#1e46b8}.scroll{overflow:auto}</style><h1>Plano pobre → construcción 3D</h1><p>Resultados reales del diagnóstico local. A y C parten de la entrada pública; B infiere componentes. D recibe el render reservado y es un control privilegiado. La última columna es la referencia del evaluador, nunca una predicción. Los tres primeros casos son fixtures sintéticos de mobiliario plausible; los tres últimos son controles ambiguos de PlankAssembly.</p><p>Un aspecto convincente no prueba medidas, despiece ni fabricación. Ningún splat recibe puntuación de BOM. Las vistas de splats usan un renderizador diagnóstico ortográfico con covarianzas y transparencia, no una extracción de malla.</p><div class="scroll"><table><thead><tr>"""
        + "".join(f"<th>{html.escape(x)}</th>" for x in labels)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + '</tbody></table></div><p><a href="four-arm-comparison.png">Comparativa PNG</a> · <a href="public-manifest.json">Protocolo público</a> · <a href="evaluation-final.json">Métricas finales, si ya están disponibles</a></p></html>'
    )
    (root / "index.html").write_text(document, encoding="utf8")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    a = p.parse_args()
    build(a.root)
