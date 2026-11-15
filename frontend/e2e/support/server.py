from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

import uvicorn


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="vexplorer-browser-") as data_dir:
        os.environ["VEXPLORER_ENV"] = "local"
        os.environ["VEXPLORER_AUTH_ENABLED"] = "false"
        os.environ["VEXPLORER_EXPLORER_ENABLED"] = "0"
        os.environ["VEXPLORER_DATA_DIR"] = data_dir
        for variable in (
            "OPENAI_API_KEY",
            "OPENAI_BASE_URL",
            "VEXPLORER_JEV_API_KEY",
            "VEXPLORER_GENERAL_ASSEMBLY_API_KEY",
        ):
            os.environ[variable] = ""

        from backend.app.main import create_app

        app = create_app(data_dir=Path(data_dir), frontend_dir=ROOT / "frontend")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
