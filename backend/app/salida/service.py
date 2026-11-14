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


CUTLIST_FIELDS = ("id", "result_revision", "role", "quantity", "length_mm", "width_mm", "thickness_mm", "material", "finish", "grain", "edge_banding", "area_m2", "edge_banding_m", "unknown_fields")


def export_cutlist_csv(result: Result) -> str:
    """Generic cut-list CSV from confirmed pieces only; missing values stay empty and are named in unknown_fields.

    grain and edge_banding come from the human review: None is unknown, an empty edge_banding means confirmed "none".
    Derived columns (area, banded length) are filled only when every input is known.
    It is not a vendor format: importers such as panel-saw software map columns themselves.
    """
    if not result.pieces:
        raise ValueError("result_has_no_confirmed_pieces")
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=CUTLIST_FIELDS)
    writer.writeheader()
    for piece in result.pieces:
        values = {"quantity": piece.quantity, "length_mm": piece.length_mm, "width_mm": piece.width_mm, "thickness_mm": piece.thickness_mm, "material": piece.material, "finish": piece.finish, "grain": piece.grain, "edge_banding": None if piece.edge_banding is None else "|".join(piece.edge_banding)}
        unknown = [name for name, value in values.items() if value is None]
        area = round(piece.length_mm * piece.width_mm * piece.quantity / 1_000_000, 6) if None not in (piece.length_mm, piece.width_mm, piece.quantity) else None
        banded = None
        if piece.edge_banding is not None and None not in (piece.length_mm, piece.width_mm, piece.quantity):
            banded = round(sum(piece.length_mm if side.startswith("length") else piece.width_mm for side in piece.edge_banding) * piece.quantity / 1000, 6)
        row = {"id": piece.id, "result_revision": result.result_revision, "role": piece.role, **values, "area_m2": area, "edge_banding_m": banded, "unknown_fields": "|".join(unknown)}
        writer.writerow({key: _safe_csv("" if value is None else value) for key, value in row.items()})
    return stream.getvalue()


def export_csv(result: Result) -> str:
    stream = io.StringIO(newline="")
    fields = ("id", "result_revision", "state", "role", "quantity", "length_mm", "width_mm", "thickness_mm", "material", "finish", "evidence_ids")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for piece in result.pieces:
        row = {"id": piece.id, "result_revision": result.result_revision, "state": result.state, "role": piece.role, "quantity": piece.quantity, "length_mm": piece.length_mm, "width_mm": piece.width_mm, "thickness_mm": piece.thickness_mm, "material": piece.material, "finish": piece.finish, "evidence_ids": "|".join(piece.evidence_ids)}
        writer.writerow({key: _safe_csv(value) for key, value in row.items()})
    return stream.getvalue()
