"""Small public-only abstention and scale checks using the real harness."""

import argparse
from dataclasses import replace
import io
import json
from pathlib import Path
from PIL import Image
from dotenv import load_dotenv
from backend.app.agente.config import ProviderSettings
from backend.app.agente.provider import OpenAIResponsesProvider
from backend.app.reconstruction3d.service import reconstruct, SYSTEM_PROMPT
from backend.app.reconstruction3d.models import AssemblyProposal
from backend.app.reconstruction3d.artifacts import export_package


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--env-file", type=Path, required=True)
    a = p.parse_args()
    load_dotenv(a.env_file)
    provider = OpenAIResponsesProvider(
        replace(
            ProviderSettings.from_env(),
            model="gpt-6.1-sol",
            max_output_tokens=8192,
            vision_enabled=True,
        ),
        instructions=SYSTEM_PROMPT,
    )
    blank = io.BytesIO()
    Image.new("RGB", (512, 512), "white").save(blank, format="PNG")
    cases = [
        ("no-scale", (a.root / "inputs/case-01/unscaled.png").read_bytes(), "relative"),
        ("single-front", (a.root / "inputs/case-03/front.png").read_bytes(), "mm"),
        ("blank", blank.getvalue(), "relative"),
        (
            "ambiguous-frame-v2",
            (a.root / "inputs/case-05/drawing.png").read_bytes(),
            "mm",
        ),
        ("completion-v2", (a.root / "inputs/case-06/drawing.png").read_bytes(), "mm"),
    ]
    for name, content, unit in cases:
        dest = a.root / "stress" / name
        if dest.exists():
            continue
        dest.mkdir(parents=True)
        (dest / "input.png").write_bytes(content)
        print(name, flush=True)
        try:
            outcome = reconstruct(content, provider=provider, known_unit=unit)
            (dest / "outcome.json").write_text(
                json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf8"
            )
            export_package(
                AssemblyProposal.model_validate(outcome["proposal"]), dest / "artifacts"
            )
            print(name, outcome["status"], outcome["proposal"]["unit"], flush=True)
        except Exception as exc:
            (dest / "failure.json").write_text(
                json.dumps({"error_type": type(exc).__name__, "code": str(exc)[:100]})
            )
