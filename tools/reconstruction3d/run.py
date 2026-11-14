from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import time


def write_new(path, value):
    with path.open("x", encoding="utf8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def public_input(root, case):
    path = (root / case["input"]).resolve()
    if not path.is_relative_to((root / "inputs").resolve()):
        raise ValueError("non_public_input")
    b = path.read_bytes()
    if sha256(b).hexdigest() != case["source_sha256"]:
        raise ValueError("input_hash_mismatch")
    return path, b


def run_b(root, env_file, model):
    from dotenv import load_dotenv
    from backend.app.agente.config import ProviderSettings
    from backend.app.agente.provider import OpenAIResponsesProvider
    from backend.app.reconstruction3d.service import reconstruct, SYSTEM_PROMPT
    from backend.app.reconstruction3d.models import AssemblyProposal
    from backend.app.reconstruction3d.artifacts import export_package

    load_dotenv(env_file)
    settings = ProviderSettings.from_env()
    from dataclasses import replace

    settings = replace(
        settings, model=model, max_output_tokens=8192, vision_enabled=True
    )
    provider = OpenAIResponsesProvider(settings, instructions=SYSTEM_PROMPT)
    manifest = json.loads((root / "public-manifest.json").read_text())
    for case in manifest["cases"]:
        dest = root / "results" / "B" / case["id"]
        if dest.exists():
            print("Exists, preserving", case["id"], flush=True)
            continue
        dest.mkdir(parents=True)
        _, content = public_input(root, case)
        print("B", case["id"], flush=True)
        try:
            outcome = reconstruct(
                content,
                provider=provider,
                known_unit=case["unit"],
                on_baseline=lambda x: write_new(dest / "baseline.json", x),
            )
            write_new(dest / "outcome.json", outcome)
            export_package(
                AssemblyProposal.model_validate(outcome["proposal"]), dest / "artifacts"
            )
            write_new(
                dest / "SHA256SUMS.json",
                {
                    p.relative_to(dest).as_posix(): sha256(p.read_bytes()).hexdigest()
                    for p in dest.rglob("*")
                    if p.is_file()
                },
            )
            print(
                "Ready B",
                case["id"],
                len(outcome["proposal"]["components"]),
                round(outcome["duration_s"], 2),
                flush=True,
            )
        except Exception as e:
            write_new(
                dest / "failure.json",
                {
                    "error_type": type(e).__name__,
                    "code": str(e)[:160]
                    if type(e).__name__ == "ReconstructionError"
                    else "execution_failed",
                },
            )
            print("Failed B", case["id"], type(e).__name__, flush=True)


def run_idol(root, model_paths, variants):
    import torch
    from .low_memory import load_pipeline

    paths = json.loads(model_paths.read_text())
    manifest = json.loads((root / "public-manifest.json").read_text())
    print("Loading Idol", flush=True)
    loaded = time.monotonic()
    pipeline = load_pipeline(paths)
    print("Loaded seconds", time.monotonic() - loaded, flush=True)
    for variant in variants:
        if variant not in ("A", "C", "D"):
            raise ValueError("invalid_variant")
        for case in manifest["cases"]:
            for seed in manifest["seeds"]:
                dest = root / "results" / variant / case["id"] / f"seed-{seed}"
                if dest.exists() and any(dest.iterdir()):
                    continue
                dest.mkdir(parents=True, exist_ok=True)
                public_input(root, case)
                source = (
                    root / case["input"]
                    if variant == "A"
                    else root
                    / "results"
                    / "B"
                    / case["id"]
                    / "artifacts"
                    / "view-00.png"
                    if variant == "C"
                    else root / "references" / case["id"] / "view-00.png"
                )
                if not source.exists():
                    write_new(
                        dest / "failure.json",
                        {
                            "error": "missing_B_output"
                            if variant == "C"
                            else "missing_input"
                        },
                    )
                    continue
                torch.cuda.reset_peak_memory_stats()
                started = time.monotonic()
                print(variant, case["id"], seed, flush=True)
                try:
                    result = pipeline(
                        str(source),
                        mode=manifest["mode"],
                        seed=seed,
                        steps=manifest["steps"],
                        num_gaussians=manifest["num_gaussians"],
                        verbose=False,
                    )
                    torch.cuda.synchronize()
                    duration = time.monotonic() - started
                    result.gaussian.save_ply(str(dest / "model.ply"))
                    result.preprocessed_image.save(dest / "input.png")
                    write_new(dest / "camera.json", result.camera)
                    write_new(
                        dest / "run.json",
                        {
                            "variant": variant,
                            "case_id": case["id"],
                            "seed": seed,
                            "steps": manifest["steps"],
                            "num_gaussians": manifest["num_gaussians"],
                            "duration_s": duration,
                            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                            "source_sha256": sha256(source.read_bytes()).hexdigest(),
                            "ply_sha256": sha256(
                                (dest / "model.ply").read_bytes()
                            ).hexdigest(),
                            "privileged_reference_input": variant == "D",
                            "torch": torch.__version__,
                            "optimized": False,
                            "model_paths": paths,
                        },
                    )
                    print("Ready", variant, case["id"], round(duration, 2), flush=True)
                    del result
                except Exception as e:
                    write_new(
                        dest / "failure.json",
                        {"error_type": type(e).__name__, "error": str(e)[:500]},
                    )
                    print(
                        "Failed",
                        variant,
                        case["id"],
                        type(e).__name__,
                        str(e)[:180],
                        flush=True,
                    )
                torch.cuda.empty_cache()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase", choices=["B", "idol"])
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--env-file", type=Path)
    p.add_argument("--model", default="gpt-6.1-sol")
    p.add_argument("--model-paths", type=Path)
    p.add_argument("--variants", default="A,C,D")
    a = p.parse_args()
    if a.phase == "B":
        run_b(a.root, a.env_file, a.model)
    else:
        run_idol(a.root, a.model_paths, a.variants.split(","))
