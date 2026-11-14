from __future__ import annotations

from pathlib import Path
import subprocess

import ezdxf
import pytest

from backend.app.ingesta.dwg_converter import DwgConverterUnavailable, DwgOutputInvalid, convert_dwg_to_dxf
from backend.app.ingesta.dxf_reader import parse_dxf


def _dwg_source(tmp_path: Path) -> Path:
    source = tmp_path / "original drawing.dwg"
    source.write_bytes(b"AC1032 synthetic converter boundary fixture")
    return source


def test_missing_oda_converter_is_an_explicit_unavailable_error(tmp_path: Path) -> None:
    with pytest.raises(DwgConverterUnavailable, match="ODA File Converter is not available"):
        convert_dwg_to_dxf(
            _dwg_source(tmp_path), tmp_path / "artifacts",
            executable=tmp_path / "missing" / "ODAFileConverter.exe",
        )


def test_oda_output_can_feed_the_existing_dxf_reader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _dwg_source(tmp_path)
    executable = tmp_path / "ODAFileConverter.exe"
    executable.write_bytes(b"fake executable boundary")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        document = ezdxf.new("R2018")
        document.header["$INSUNITS"] = 4
        document.modelspace().add_line((0, 0), (125, 0))
        document.saveas(Path(command[2]) / "original drawing.dxf")
        return subprocess.CompletedProcess(command, 0, stdout="converted", stderr="")

    monkeypatch.setattr("backend.app.ingesta.dwg_converter.subprocess.run", fake_run)
    result = convert_dwg_to_dxf(source, tmp_path / "artifacts", executable=executable)
    parsed = parse_dxf(result.dxf_path)

    assert result.source_name == "original drawing.dwg"
    assert result.source_media_type == "application/acad"
    assert result.source_size_bytes == len(source.read_bytes())
    assert len(result.source_sha256) == len(result.dxf_sha256) == 64
    assert result.converter == "oda_file_converter"
    assert parsed.source_unit == "mm"
    assert parsed.entities[0].points == ((0.0, 0.0), (125.0, 0.0))


def test_non_dxf_converter_output_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _dwg_source(tmp_path)
    executable = tmp_path / "ODAFileConverter.exe"
    executable.write_bytes(b"fake executable boundary")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        (Path(command[2]) / "original drawing.dxf").write_text("not a DXF", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("backend.app.ingesta.dwg_converter.subprocess.run", fake_run)
    with pytest.raises(DwgOutputInvalid, match="did not produce a readable DXF"):
        convert_dwg_to_dxf(source, tmp_path / "artifacts", executable=executable)


def test_libredwg_dwg2dxf_uses_the_same_validated_dxf_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _dwg_source(tmp_path)
    executable = tmp_path / "dwg2dxf.exe"
    executable.write_bytes(b"fake GNU LibreDWG boundary")

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        assert command[1:3] == ["--as", "r2018"]
        output = Path(command[command.index("-o") + 1])
        document = ezdxf.new("R2018")
        document.header["$INSUNITS"] = 4
        document.modelspace().add_line((0, 0), (50, 0))
        document.saveas(output)
        return subprocess.CompletedProcess(command, 0, stdout="converted", stderr="")

    monkeypatch.setattr("backend.app.ingesta.dwg_converter.subprocess.run", fake_run)
    result = convert_dwg_to_dxf(
        source, tmp_path / "libredwg-artifacts",
        converter="libredwg", executable=executable,
    )

    assert result.converter == "libredwg_dwg2dxf"
    assert "dwg_converted_with_libredwg" in result.warnings
    assert parse_dxf(result.dxf_path).entities[0].points[1] == (50.0, 0.0)


def test_libredwg_can_be_selected_explicitly_from_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = _dwg_source(tmp_path)
    executable = tmp_path / "dwg2dxf.exe"
    executable.write_bytes(b"fake GNU LibreDWG boundary")
    monkeypatch.setenv("VEXPLORER_DWG_CONVERTER", "libredwg")
    monkeypatch.setenv("VEXPLORER_DWG2DXF_EXECUTABLE", str(executable))

    def fake_run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        output = Path(command[command.index("-o") + 1])
        ezdxf.new("R2018").saveas(output)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr("backend.app.ingesta.dwg_converter.subprocess.run", fake_run)
    result = convert_dwg_to_dxf(source, tmp_path / "environment-artifacts")

    assert result.converter == "libredwg_dwg2dxf"
