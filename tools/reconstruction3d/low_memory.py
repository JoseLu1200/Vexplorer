"""Load the pinned Idol SDK without mmap's Windows commit-memory spike.

Only checkpoint loading changes. Parameters retain the SDK's intended dtype;
no quantization, altered sampling, or extra conditioning is introduced.
"""

from pathlib import Path
import json
import struct


def load_streamed(model, checkpoint, *, dtype=None):
    import torch

    types = {
        "F32": torch.float32,
        "F16": torch.float16,
        "BF16": torch.bfloat16,
        "I64": torch.int64,
        "I32": torch.int32,
        "BOOL": torch.bool,
    }
    expected = model.state_dict()
    state = {}
    with Path(checkpoint).open("rb") as f:
        length = struct.unpack("<Q", f.read(8))[0]
        if length > 20_000_000:
            raise ValueError("invalid_safetensors_header")
        header = json.loads(f.read(length))
        start = 8 + length
        # Transformers 5.23 nests DINO's layer stack under model; embeddings stay unchanged.
        mapping = {
            key: key if key in expected else "model." + key
            for key in header
            if key != "__metadata__"
        }
        if set(mapping.values()) != set(expected) or len(mapping) != len(expected):
            raise ValueError("checkpoint_keys_mismatch")
        for key, spec in header.items():
            if key == "__metadata__":
                continue
            key = mapping[key]
            lo, hi = spec["data_offsets"]
            f.seek(start + lo)
            raw = bytearray(f.read(hi - lo))
            tensor = torch.frombuffer(raw, dtype=types[spec["dtype"]]).reshape(
                spec["shape"]
            )
            target = (
                dtype
                if dtype is not None and tensor.is_floating_point()
                else expected[key].dtype
            )
            state[key] = tensor.to(device="cuda", dtype=target)
    model.load_state_dict(state, strict=True, assign=True)
    return model.eval().requires_grad_(False).to("cuda")


def load_pipeline(paths):
    import torch
    from accelerate import init_empty_weights
    from transformers import AutoConfig, AutoModel
    from diffusers.models import AutoencoderKLFlux2
    from idol.pipeline import IdolPipeline
    from idol.conditioning import ImageEncoder
    from idol.models import (
        BiRefNet,
        GaussianFixedlenDecoder,
        LatentSeqMMFlowModel,
        OctreeProbabilityFixedlenDecoder,
    )

    root = Path(paths["speridlabs/idol"])
    pipe = object.__new__(IdolPipeline)
    pipe.device = torch.device("cuda")
    pipe.config = json.loads((root / "config.json").read_text())
    for name, cls in [
        ("denoiser", LatentSeqMMFlowModel),
        ("decoder", OctreeProbabilityFixedlenDecoder),
        ("decoder_gs", GaussianFixedlenDecoder),
        ("birefnet", BiRefNet),
    ]:
        print("Stream loading", name, flush=True)
        with init_empty_weights(include_buffers=False):
            model = cls(**pipe.config[name]["args"]) if name != "birefnet" else cls()
        model = load_streamed(
            model,
            root / f"{name}.safetensors",
            dtype=torch.float16 if name == "birefnet" else None,
        )
        setattr(pipe, "background_remover" if name == "birefnet" else name, model)
    dino = Path(paths["facebook/dinov3-vith16plus-pretrain-lvd1689m"])
    print("Stream loading DINOv3", flush=True)
    with init_empty_weights(include_buffers=False):
        model = AutoModel.from_config(
            AutoConfig.from_pretrained(str(dino), local_files_only=True)
        )
    dino_model = load_streamed(model, dino / "model.safetensors", dtype=torch.bfloat16)
    vae = Path(paths["black-forest-labs/FLUX.2-klein-4B"]) / "vae"
    print("Stream loading VAE", flush=True)
    with init_empty_weights(include_buffers=False):
        model = AutoencoderKLFlux2.from_config(
            json.loads((vae / "config.json").read_text())
        )
    vae_model = load_streamed(
        model, vae / "diffusion_pytorch_model.safetensors", dtype=torch.bfloat16
    )
    pipe.image_encoder = ImageEncoder(dino_model, vae_model, device="cuda")
    pipe.optimize = False
    pipe.cudnn_attention = False
    return pipe
