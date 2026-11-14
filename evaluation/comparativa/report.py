"""JSON and Markdown report.  Per variant, family and split; never one global score."""

from __future__ import annotations

from typing import Any

REPORT_SCHEMA = "comparativa-report-1"

LIMITATIONS = (
    "No global score is computed; read each variant, family and split separately.",
    "Components are matched by dimension values alone (greedy, one-to-one, documented tolerance); ambiguous equal-size components pair arbitrarily but deterministically.",
    "Missing or abstained fields reduce coverage and are never imputed as zero error.",
    "Rows with reference=None (no reference) are counted in the sample but never scored.",
    "Cost is reported only when the adapter observed it; it is never estimated from a tariff.",
    "A2 (rectangle hypotheses of assembled views) is a rule added by this harness; the app's geometry_only run for general furniture does not execute it.",
    "Time limits are checked after a method returns, not enforced preventively; call limits are checked on the usage the adapter reports.",
    "Development cases were inspected while building rules and prompts: they show mechanics, not generalisation.",
)


def build_report(
    scores: dict[str, dict[str, dict[str, dict[str, Any]]]],
    *,
    freeze: dict[str, Any],
    settings: dict[str, Any],
) -> dict[str, Any]:
    requested = list(freeze.get("variants_requested", []))
    not_run = sorted(set(requested) - set(scores))
    return {
        "schema": REPORT_SCHEMA,
        "corpus": freeze.get("corpus"),
        "freeze": {
            "frozen_at": freeze.get("frozen_at"),
            "outputs_digest": freeze.get("outputs_digest"),
            "outputs": len(freeze.get("outputs", [])),
            "inputs": freeze.get("inputs"),
            "methods": freeze.get("methods"),
            "limits": freeze.get("limits"),
        },
        "settings": settings,
        "variants": {variant: {"families": families} for variant, families in scores.items()},
        "variants_without_outputs": not_run,
        "limitations": list(LIMITATIONS),
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_markdown(report: dict[str, Any]) -> str:
    corpus = report.get("corpus") or {}
    lines = [
        "# Comparativa de metodos A/B/C/D",
        "",
        f"Corpus: `{corpus.get('id')}` ({corpus.get('kind')}). Digest de salidas congeladas: `{report['freeze']['outputs_digest']}`.",
        f"Tolerancia de medida: {report['settings']['tolerance_mm']} mm; tolerancia de emparejamiento: {report['settings']['match_tolerance_mm']} mm.",
        "",
        "Sin puntuacion global: cada variante, familia y particion se lee por separado.",
        "",
    ]
    if report["variants_without_outputs"]:
        lines += ["Variantes sin salidas: " + ", ".join(report["variants_without_outputs"]) + ".", ""]
    for variant, body in report["variants"].items():
        lines += [f"## Variante {variant}", ""]
        for family, splits in body["families"].items():
            for split, m in splits.items():
                sample, dims, ident = m["sample"], m["dimensions"], m["identity"]
                qty, abst, res = ident["quantity"], m["abstention"], m["resources"]
                cost = res["cost_eur_reported_total"]
                reasons = f"; motivos {sample['reason_counts']}" if sample["reason_counts"] else ""
                bullets = [
                    (
                        f"- Muestra: {sample['cases']} casos, {sample['observations']} observaciones, "
                        f"{sample['observations_scored']} puntuadas; con referencia {sample['cases_with_reference']}, "
                        f"sin referencia {sample['cases_without_reference']}; estados {sample['status_counts']}{reasons}"
                    ),
                    (
                        f"- Dimensiones: cobertura {_pct(dims['coverage'])} ({dims['predicted_fields']}/{dims['eligible_fields']}), "
                        f"MAE {_num(dims['mae_mm'])} mm, dentro de tolerancia {_pct(dims['within_tolerance_rate'])}, "
                        f"etiquetas de rol discordantes {dims['role_label_mismatches']}"
                    ),
                    (
                        f"- Despiece: emparejadas {ident['matched']}, falsos positivos {ident['false_positives']}, "
                        f"omisiones {ident['omissions']}, precision {_pct(ident['precision'])}, recall {_pct(ident['recall'])}; "
                        f"parciales (fuera de precision/recall) {ident['matched_partial']}, "
                        f"pares en clases ambiguas {ident['ambiguous_class_pairs']}"
                    ),
                    (
                        f"- Cantidades: comparadas {qty['compared_components']}, exactas {_pct(qty['exact_rate'])}, "
                        f"precision {_pct(qty['precision'])}, recall {_pct(qty['recall'])}"
                    ),
                    (
                        f"- Abstencion: correcta {_pct(abst['correct_abstention_rate'])} "
                        f"({abst['correct_abstentions']}/{abst['unidentifiable_fields']}), afirmados no identificables "
                        f"{abst['asserted_unidentifiable']}, sobre-abstencion {_pct(abst['over_abstention_rate'])}; "
                        f"cota inferior (asignacion menos favorable) correcta {_pct(abst['lower_bound']['correct_abstention_rate'])}, "
                        f"afirmados {abst['lower_bound']['asserted_unidentifiable']}"
                    ),
                    f"- Campos sin referencia anotada: {m['fields_without_reference']['fields']}",
                    (
                        f"- Recursos: {_num(res['duration_s_total'], 3)} s totales, llamadas modelo {res['model_calls']}, "
                        f"herramientas {res['tool_calls']}, tokens {res['input_tokens']}/{res['output_tokens']}, "
                        f"coste observado {'no informado' if cost is None else cost}"
                    ),
                ]
                lines += [f"### {family} / {split}", "", *bullets, ""]
    lines += ["## Limitaciones", ""] + [f"- {item}" for item in report["limitations"]] + [""]
    return "\n".join(lines)
