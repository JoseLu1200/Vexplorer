from __future__ import annotations

import csv
import io

from backend.app.contratos.modelos import Result


def _safe_csv(value: object) -> object:
    if isinstance(value, str) and (value[:1] in ("=", "+", "-", "@") or value[:1] in ("\t", "\r", "\n")):
        return "'" + value
    return value


def export_json(result: Result) -> str:
    return result.model_dump_json(indent=2)


def export_csv(result: Result) -> str:
    stream = io.StringIO(newline="")
    fields = ("id", "result_revision", "state", "role", "quantity", "length_mm", "width_mm", "thickness_mm", "material", "finish", "evidence_ids")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for piece in result.pieces:
        row = {"id": piece.id, "result_revision": result.result_revision, "state": result.state, "role": piece.role, "quantity": piece.quantity, "length_mm": piece.length_mm, "width_mm": piece.width_mm, "thickness_mm": piece.thickness_mm, "material": piece.material, "finish": piece.finish, "evidence_ids": "|".join(piece.evidence_ids)}
        writer.writerow({key: _safe_csv(value) for key, value in row.items()})
    return stream.getvalue()
