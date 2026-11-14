from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
from typing import Literal

from .dxf_reader import parse_dxf


MAX_DWG_BYTES = 20 * 1024 * 1024


class DwgConversionError(RuntimeError):
    """Base error for an honest DWG conversion boundary."""


class DwgConverterUnavailable(DwgConversionError):
    pass


class DwgConversionFailed(DwgConversionError):
    pass


class DwgOutputInvalid(DwgConversionError):
    pass


@dataclass(frozen=True)
class DwgConversionResult:
    source_path: Path
    source_name: str
    source_media_type: str
    source_size_bytes: int
    source_sha256: str
    dxf_path: Path
    dxf_sha256: str
    converter: str
    converter_executable: Path
    warnings: tuple[str, ...]


def _digest(path: Path) -> str:
    value = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _find_executable(candidate: Path | str | None, names: tuple[str, ...]) -> Path | None:
    if candidate:
        path = Path(candidate).expanduser().resolve()
        if path.is_file():
            return path
        return None
    for name in names:
        found = shutil.which(name)
        if found:
            return Path(found).resolve()
    return None


def _resolve_converter(
    converter: Literal["oda", "libredwg", "auto"] | str | None,
    executable: Path | str | None,
) -> tuple[Literal["oda", "libredwg"], Path]:
    requested = converter or os.getenv("VEXPLORER_DWG_CONVERTER") or ("oda" if executable else "auto")
    if requested not in {"oda", "libredwg", "auto"}:
        raise ValueError("converter must be one of: oda, libredwg, auto")

    if requested in {"libredwg", "auto"}:
        candidate = executable if requested == "libredwg" else os.getenv("VEXPLORER_DWG2DXF_EXECUTABLE")
        libredwg = _find_executable(
            candidate or os.getenv("VEXPLORER_DWG2DXF_EXECUTABLE"),
            ("dwg2dxf", "dwg2dxf.exe"),
        )
        if libredwg is not None:
            return "libredwg", libredwg
        if requested == "libredwg":
            raise DwgConverterUnavailable(
                "GNU LibreDWG dwg2dxf is not available; configure "
                "VEXPLORER_DWG2DXF_EXECUTABLE or install dwg2dxf"
            )

    oda_candidate = executable if requested == "oda" else os.getenv("VEXPLORER_ODA_EXECUTABLE")
    oda = _find_executable(
        oda_candidate or os.getenv("VEXPLORER_ODA_EXECUTABLE") or os.getenv("ODA_FILE_CONVERTER"),
        ("ODAFileConverter", "ODAFileConverter.exe"),
    )
    if oda is not None:
        return "oda", oda
    if requested == "oda":
        raise DwgConverterUnavailable(
            "ODA File Converter is not available; configure VEXPLORER_ODA_EXECUTABLE or pass executable"
        )
    raise DwgConverterUnavailable(
        "no DWG converter is available; configure GNU LibreDWG dwg2dxf or an authorized ODA installation"
    )


def convert_dwg_to_dxf(
    source: Path,
    output_dir: Path,
    *,
    converter: Literal["oda", "libredwg", "auto"] | str | None = None,
    executable: Path | str | None = None,
    timeout_seconds: float = 120,
    max_source_bytes: int = MAX_DWG_BYTES,
) -> DwgConversionResult:
    """Convert one DWG through ODA and validate that its DXF feeds the existing reader."""
    source = source.resolve()
    if not source.is_file() or source.suffix.lower() != ".dwg":
        raise DwgConversionError("DWG source must be an existing .dwg file")
    size = source.stat().st_size
    if size <= 0 or size > max_source_bytes:
        raise DwgConversionError(f"DWG source size outside allowed range: {size} bytes")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")

    provider, converter_path = _resolve_converter(converter, executable)
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = output_dir / f"{source.stem}.dxf"
    if expected.exists():
        raise DwgConversionError(f"refusing to overwrite existing conversion output: {expected.name}")

    if provider == "oda":
        command = [
            str(converter_path), str(source.parent), str(output_dir),
            "ACAD2018", "DXF", "0", "1", source.name,
        ]
    else:
        command = [
            str(converter_path), "--as", "r2018", "-o", str(expected), str(source),
        ]
    label = "ODA File Converter" if provider == "oda" else "GNU LibreDWG dwg2dxf"
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise DwgConversionFailed(
            f"{label} timed out after {timeout_seconds:g} seconds"
        ) from exc
    except OSError as exc:
        raise DwgConverterUnavailable(f"{label} could not be executed") from exc
    if completed.returncode != 0:
        raise DwgConversionFailed(
            f"{label} failed with exit code {completed.returncode}"
        )

    if not expected.is_file():
        matches = [path for path in output_dir.iterdir() if path.stem == source.stem and path.suffix.lower() == ".dxf"]
        if len(matches) == 1:
            expected = matches[0]
        else:
            raise DwgOutputInvalid(f"{label} did not produce the expected DXF")
    try:
        parse_dxf(expected)
    except Exception as exc:
        raise DwgOutputInvalid(f"{label} did not produce a readable DXF") from exc

    return DwgConversionResult(
        source_path=source,
        source_name=source.name,
        source_media_type="application/acad",
        source_size_bytes=size,
        source_sha256=_digest(source),
        dxf_path=expected.resolve(),
        dxf_sha256=_digest(expected),
        converter="oda_file_converter" if provider == "oda" else "libredwg_dwg2dxf",
        converter_executable=converter_path,
        warnings=(
            ("dwg_converted_with_audit" if provider == "oda" else "dwg_converted_with_libredwg"),
            ("oda_use_requires_authorized_license" if provider == "oda" else "libredwg_conversion_requires_review"),
            "original_source_preserved",
        ),
    )
