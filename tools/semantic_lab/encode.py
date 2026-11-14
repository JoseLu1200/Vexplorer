"""Generate learned embeddings for the isolated semantic laboratory.

The manifest is trusted only as an index.  Model adapters never receive labels,
paths, group identifiers or filenames: their complete input is neutral text,
decoded image bytes, or both.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

import numpy as np


SUPPORTED_MODES = {"text", "image", "mixed"}
MODEL_MODES = {
    "dinov3": {"image"},
    "embeddinggemma2": {"text", "image", "mixed"},
    "minilm": {"text"},
}
MODEL_IDS = {
    "dinov3": "facebook/dinov3-vits16-pretrain-lvd1689m",
    "embeddinggemma2": "google/embeddinggemma-2",
    "minilm": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
}
RUNNER_VERSION = "1"


@dataclass(frozen=True)
class EncoderInfo:
    model: str
    revision: str
    precision: str
    native_dimensions: int
    config: dict[str, Any]


class Encoder(Protocol):
    @property
    def info(self) -> EncoderInfo: ...

    def encode(
        self, inputs: list[object], *, mode: str, truncate_dim: int | None
    ) -> np.ndarray: ...


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return _sha256_bytes(payload)


def _metadata_path(output_path: Path) -> Path:
    return output_path.with_suffix(output_path.suffix + ".json")


def _load_manifest(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest must be valid UTF-8 JSON") from exc
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("manifest schema_version must be 1")
    if not isinstance(manifest.get("metadata"), dict):
        raise ValueError("manifest metadata must be an object")
    if not isinstance(manifest.get("samples"), list):
        raise ValueError("manifest samples must be an array")
    return manifest, raw


def _resolve_image_path(manifest_path: Path, value: object) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("image_path must be a non-empty string")
    path = Path(value)
    if not path.is_absolute():
        path = manifest_path.parent / path
    if not path.is_file():
        raise ValueError(f"image {value!r} does not exist")
    return path


def _model_inputs(
    manifest_path: Path, samples: Sequence[object], mode: str
) -> tuple[list[str], list[object], list[dict[str, str]]]:
    ids: list[str] = []
    inputs: list[object] = []
    content: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, raw_sample in enumerate(samples):
        if not isinstance(raw_sample, dict):
            raise ValueError(f"sample {index} must be an object")
        sample_id = raw_sample.get("id")
        if not isinstance(sample_id, str) or not sample_id:
            raise ValueError(f"sample {index} has invalid id")
        if sample_id in seen:
            raise ValueError(f"duplicate sample id: {sample_id}")
        seen.add(sample_id)
        ids.append(sample_id)

        text: str | None = None
        image_bytes: bytes | None = None
        item_hashes: dict[str, str] = {}
        if mode in {"text", "mixed"}:
            raw_text = raw_sample.get("text")
            if not isinstance(raw_text, str) or not raw_text.strip():
                raise ValueError(f"sample {sample_id} has empty text")
            text = raw_text
            item_hashes["text_sha256"] = _sha256_bytes(text.encode("utf-8"))
        if mode in {"image", "mixed"}:
            image_path = _resolve_image_path(manifest_path, raw_sample.get("image_path"))
            image_bytes = image_path.read_bytes()
            if not image_bytes:
                raise ValueError(f"sample {sample_id} image is empty")
            item_hashes["image_sha256"] = _sha256_bytes(image_bytes)

        if mode == "text":
            inputs.append(text)
        elif mode == "image":
            inputs.append(image_bytes)
        else:
            inputs.append((text, image_bytes))
        content.append(item_hashes)
    if not ids:
        raise ValueError("manifest must contain at least one sample")
    return ids, inputs, content


def _validate_matrix(
    matrix: object, *, rows: int, dimensions: int
) -> np.ndarray:
    array = np.asarray(matrix)
    if array.ndim != 2:
        raise ValueError("encoder output must be two-dimensional")
    if array.shape[0] != rows:
        raise ValueError(
            f"encoder output row count {array.shape[0]} does not match {rows}"
        )
    if array.shape[1] != dimensions:
        raise ValueError(
            f"encoder output dimension {array.shape[1]} does not match {dimensions}"
        )
    if not np.issubdtype(array.dtype, np.number):
        raise ValueError("encoder output must be numeric")
    array = np.asarray(array, dtype=np.float32)
    if not np.isfinite(array).all():
        raise ValueError("encoder output values must be finite")
    norms = np.linalg.norm(array, axis=1)
    if np.any(norms == 0):
        raise ValueError("encoder output contains a zero vector")
    return array / norms[:, None]


def _write_npz(path: Path, ids: Sequence[str], matrix: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        with temporary.open("wb") as handle:
            np.savez_compressed(
                handle,
                ids=np.asarray(ids, dtype=np.str_),
                embeddings=np.asarray(matrix, dtype=np.float32),
            )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    try:
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _load_valid_cache(
    npz_path: Path,
    metadata_path: Path,
    *,
    cache_key: str,
    ids: Sequence[str],
    dimensions: int,
) -> tuple[np.ndarray, dict[str, Any]] | None:
    if not npz_path.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("cache_key") != cache_key:
            return None
        if metadata.get("npz_sha256") != _sha256_file(npz_path):
            return None
        with np.load(npz_path, allow_pickle=False) as table:
            cached_ids = table["ids"].astype(str).tolist()
            matrix = _validate_matrix(
                table["embeddings"], rows=len(ids), dimensions=dimensions
            )
        if cached_ids != list(ids):
            return None
        return matrix, metadata
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def encode_manifest(
    *,
    manifest_path: Path | str,
    model: str,
    mode: str,
    output_path: Path | str,
    cache_dir: Path | str,
    truncate_dim: int | None = None,
    precision: str = "auto",
    device: str = "auto",
    encoder: Encoder | None = None,
    local_files_only: bool = False,
) -> dict[str, Any]:
    """Encode every sample in manifest order and persist an auditable table."""

    manifest_path = Path(manifest_path).resolve()
    output_path = Path(output_path).resolve()
    cache_dir = Path(cache_dir).resolve()
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"unsupported mode: {mode}")
    if encoder is None:
        if model not in MODEL_MODES:
            raise ValueError(f"unsupported model: {model}")
        if mode not in MODEL_MODES[model]:
            raise ValueError(f"model {model} does not support mode {mode}")
        encoder = create_encoder(
            model=model,
            mode=mode,
            cache_dir=cache_dir,
            precision=precision,
            device=device,
            local_files_only=local_files_only,
        )
    info = encoder.info
    if truncate_dim is not None:
        if model in {"dinov3", "minilm"}:
            raise ValueError(
                f"model {model} does not declare native Matryoshka truncation"
            )
        if model == "embeddinggemma2" and truncate_dim not in {
            128,
            256,
            512,
            768,
        }:
            raise ValueError(
                "EmbeddingGemma 2 truncate dimension must be 128, 256, 512 or 768"
            )
        if truncate_dim <= 0 or truncate_dim > info.native_dimensions:
            raise ValueError(
                f"truncate dimension must be in 1..{info.native_dimensions}"
            )
        dimensions = truncate_dim
    else:
        dimensions = info.native_dimensions

    manifest, manifest_raw = _load_manifest(manifest_path)
    ids, inputs, input_hashes = _model_inputs(
        manifest_path, manifest["samples"], mode
    )
    identity = {
        "schema_version": 1,
        "runner_version": RUNNER_VERSION,
        "manifest_sha256": _sha256_bytes(manifest_raw),
        "ordered_ids_sha256": _canonical_hash(ids),
        "ordered_input_hashes": input_hashes,
        "model": asdict(info),
        "mode": mode,
        "precision_request": precision,
        "device_request": device,
        "dimensions": dimensions,
        "postprocessing": "float32_l2_normalize_rows",
    }
    cache_key = _canonical_hash(identity)
    result_cache = cache_dir / "semantic-lab-results"
    cached_npz = result_cache / f"{cache_key}.npz"
    cached_json = result_cache / f"{cache_key}.json"
    cached = _load_valid_cache(
        cached_npz,
        cached_json,
        cache_key=cache_key,
        ids=ids,
        dimensions=dimensions,
    )
    if cached is not None:
        _matrix, previous_metadata = cached
        output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached_npz, output_path)
        metadata = {
            **previous_metadata,
            "cache_status": "hit",
            "output_path": str(output_path),
            "npz_sha256": _sha256_file(output_path),
        }
        _write_json(_metadata_path(output_path), metadata)
        return metadata

    started = time.perf_counter()
    matrix = encoder.encode(inputs, mode=mode, truncate_dim=truncate_dim)
    elapsed = time.perf_counter() - started
    matrix = _validate_matrix(matrix, rows=len(ids), dimensions=dimensions)
    _write_npz(output_path, ids, matrix)
    metadata = {
        "schema_version": 1,
        "cache_key": cache_key,
        "cache_status": "miss",
        "model": asdict(info),
        "mode": mode,
        "dimensions": dimensions,
        "sample_count": len(ids),
        "manifest_sha256": identity["manifest_sha256"],
        "ordered_ids_sha256": identity["ordered_ids_sha256"],
        "ordered_input_hashes": input_hashes,
        "synthetic_corpus": bool(manifest["metadata"].get("synthetic", False)),
        "timing": {
            "encode_seconds": elapsed,
            "samples_per_second": len(ids) / elapsed if elapsed else None,
        },
        "errors": [],
        "output_path": str(output_path),
        "npz_sha256": _sha256_file(output_path),
        "config_identity": identity,
    }
    _write_json(_metadata_path(output_path), metadata)
    result_cache.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(output_path, cached_npz)
    cached_metadata = {**metadata, "output_path": str(cached_npz)}
    cached_metadata["npz_sha256"] = _sha256_file(cached_npz)
    _write_json(cached_json, cached_metadata)
    return metadata


def _decode_images(values: Sequence[bytes]) -> list[Any]:
    from PIL import Image

    decoded = []
    for value in values:
        try:
            image = Image.open(io.BytesIO(value))
            image.load()
            decoded.append(image.convert("RGB"))
        except Exception as exc:
            raise ValueError("image bytes could not be decoded") from exc
    return decoded


def _find_local_snapshot(cache_root: Path, repo_id: str) -> Path | None:
    snapshots_root = (
        cache_root
        / f"models--{repo_id.replace('/', '--')}"
        / "snapshots"
    )
    candidates = sorted(
        path
        for path in snapshots_root.glob("*")
        if (path / "config.json").is_file()
        and any(
            (path / filename).is_file()
            for filename in ("model.safetensors", "pytorch_model.bin")
        )
    )
    return candidates[-1] if candidates else None


class DINOv3Encoder:
    def __init__(self, *, device: str, precision: str) -> None:
        import torch
        from transformers import AutoModel
        from transformers.models.dinov3_vit.image_processing_dinov3_vit import (
            DINOv3ViTImageProcessor,
        )

        snapshot = _find_local_snapshot(
            Path.home() / ".cache" / "huggingface" / "hub",
            MODEL_IDS["dinov3"],
        )
        if snapshot is None:
            raise FileNotFoundError(
                "complete local DINOv3-small snapshot (config and weights) not found"
            )
        self._device = (
            "cuda" if device == "auto" and torch.cuda.is_available() else device
        )
        if self._device == "auto":
            self._device = "cpu"
        self._model = AutoModel.from_pretrained(
            snapshot, local_files_only=True, trust_remote_code=False
        ).eval()
        self._model.to(self._device)
        self._processor = DINOv3ViTImageProcessor()
        self._batch_size = 16
        self._info = EncoderInfo(
            model=MODEL_IDS["dinov3"],
            revision=snapshot.name,
            precision="float32",
            native_dimensions=int(self._model.config.hidden_size),
            config={
                "pooling": "mean_last_hidden_state",
                "processor": "DINOv3ViTImageProcessor defaults",
                "requested_precision": precision,
                "local_files_only": True,
                "batch_size": self._batch_size,
            },
        )

    @property
    def info(self) -> EncoderInfo:
        return self._info

    def encode(
        self, inputs: list[object], *, mode: str, truncate_dim: int | None
    ) -> np.ndarray:
        import torch
        import torch.nn.functional as functional

        if mode != "image":
            raise ValueError("DINOv3 supports image mode only")
        images = _decode_images([bytes(value) for value in inputs])
        batches = []
        with torch.inference_mode():
            for start in range(0, len(images), self._batch_size):
                batch = self._processor(
                    images=images[start : start + self._batch_size],
                    return_tensors="pt",
                )
                pixel_values = batch["pixel_values"].to(self._device)
                output = self._model(pixel_values=pixel_values)
                vectors = output.last_hidden_state.mean(dim=1)
                vectors = functional.normalize(vectors.float(), p=2, dim=1)
                batches.append(vectors.cpu())
        return torch.cat(batches, dim=0).numpy()


class SentenceTransformerEncoder:
    def __init__(
        self,
        *,
        model_name: str,
        mode: str,
        cache_dir: Path,
        device: str,
        precision: str,
        local_files_only: bool,
    ) -> None:
        import torch
        from huggingface_hub import snapshot_download
        from sentence_transformers import SentenceTransformer

        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float32
        resolved_precision = "float32"
        if (
            model_name == "embeddinggemma2"
            and
            precision in {"auto", "bfloat16"}
            and device == "cuda"
            and torch.cuda.is_bf16_supported()
        ):
            dtype = torch.bfloat16
            resolved_precision = "bfloat16"
        if precision == "float32":
            dtype = torch.float32
            resolved_precision = "float32"

        repo_id = MODEL_IDS[model_name]
        snapshot_path = _find_local_snapshot(cache_dir, repo_id)
        if snapshot_path is None and local_files_only:
            snapshot_path = _find_local_snapshot(
                Path.home() / ".cache" / "huggingface" / "hub", repo_id
            )
        if snapshot_path is None:
            snapshot_path = Path(
                snapshot_download(
                    repo_id=repo_id,
                    cache_dir=str(cache_dir),
                    local_files_only=local_files_only,
                )
            )
        revision = snapshot_path.name
        config_kwargs: dict[str, Any] = {}
        if model_name == "embeddinggemma2":
            config_kwargs["audio_config"] = None
            if mode == "text":
                config_kwargs["vision_config"] = None
        self._model = SentenceTransformer(
            str(snapshot_path),
            cache_folder=str(cache_dir),
            device=device,
            model_kwargs={
                "torch_dtype": dtype,
                "local_files_only": local_files_only,
                "trust_remote_code": False,
            },
            config_kwargs=config_kwargs,
        )
        native_dimensions = int(self._model.get_embedding_dimension())
        self._model_name = model_name
        self._batch_size = 32 if mode == "text" else 8
        self._info = EncoderInfo(
            model=repo_id,
            revision=revision,
            precision=resolved_precision,
            native_dimensions=native_dimensions,
            config={
                "pooling": "repository_sentence_transformers_pipeline",
                "normalize_embeddings": True,
                "prompt": (
                    "SentenceSimilarity"
                    if model_name == "embeddinggemma2" and mode == "text"
                    else None
                ),
                "disabled_audio": model_name == "embeddinggemma2",
                "disabled_vision": model_name == "embeddinggemma2"
                and mode == "text",
                "trust_remote_code": False,
                "batch_size": self._batch_size,
            },
        )

    @property
    def info(self) -> EncoderInfo:
        return self._info

    def encode(
        self, inputs: list[object], *, mode: str, truncate_dim: int | None
    ) -> np.ndarray:
        import torch.nn.functional as functional

        model_inputs: list[object]
        encode_kwargs: dict[str, Any] = {
            "convert_to_tensor": True,
            "normalize_embeddings": True,
            "show_progress_bar": False,
            "batch_size": self._batch_size,
        }
        if mode == "text":
            model_inputs = [str(value) for value in inputs]
            if self._model_name == "embeddinggemma2":
                encode_kwargs["prompt_name"] = "SentenceSimilarity"
        elif mode == "image":
            model_inputs = _decode_images([bytes(value) for value in inputs])
        elif mode == "mixed":
            pairs = [
                (str(value[0]), bytes(value[1]))  # type: ignore[index]
                for value in inputs
            ]
            images = _decode_images([image for _text, image in pairs])
            model_inputs = [
                {"text": f"{text} <|image|>", "image": image}
                for (text, _image), image in zip(pairs, images, strict=True)
            ]
        else:
            raise ValueError(f"unsupported mode: {mode}")
        vectors = self._model.encode(model_inputs, **encode_kwargs)
        if truncate_dim is not None:
            vectors = vectors[:, :truncate_dim]
            vectors = functional.normalize(vectors.float(), p=2, dim=1)
        return vectors.float().cpu().numpy()


def create_encoder(
    *,
    model: str,
    mode: str,
    cache_dir: Path,
    precision: str,
    device: str,
    local_files_only: bool,
) -> Encoder:
    if model == "dinov3":
        return DINOv3Encoder(device=device, precision=precision)
    if model in {"embeddinggemma2", "minilm"}:
        return SentenceTransformerEncoder(
            model_name=model,
            mode=mode,
            cache_dir=cache_dir,
            device=device,
            precision=precision,
            local_files_only=local_files_only,
        )
    raise ValueError(f"unsupported model: {model}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Encode a neutral semantic-lab manifest."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--model", choices=sorted(MODEL_MODES), required=True
    )
    parser.add_argument("--mode", choices=sorted(SUPPORTED_MODES), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--truncate-dim", type=int)
    parser.add_argument(
        "--precision", choices=("auto", "bfloat16", "float32"), default="auto"
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--local-files-only", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        metadata = encode_manifest(
            manifest_path=args.manifest,
            model=args.model,
            mode=args.mode,
            output_path=args.output,
            cache_dir=args.cache_dir,
            truncate_dim=args.truncate_dim,
            precision=args.precision,
            device=args.device,
            local_files_only=args.local_files_only,
        )
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "model": args.model,
            "mode": args.mode,
            "errors": [{"type": type(exc).__name__, "message": str(exc)}],
        }
        _write_json(_metadata_path(args.output.resolve()), failure)
        print(f"semantic encoding failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(metadata, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
