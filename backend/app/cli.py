"""Command-line helpers.

    python -m app.cli load-project --csv data.csv --config project.json

Loads a dataset and its project definition (the same fields as the Step 1 form: name, case_description, variables with
role / calibration / definition / instrument / original anchors or breakpoints, reference_cutoffs, drop_missing) into the
local database and prints a link that opens it. Handy for studies whose setup you want to keep in a file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.api import service
from app.projects import ProjectError, configure, create_upload


def load_project(csv_path: Path, config_path: Path) -> str:
    cfg = json.loads(config_path.read_text())
    with service.session() as s:
        up = create_upload(s, csv_path.name, csv_path.read_bytes())
        configure(s, up["project_id"], cfg)
    return str(up["project_id"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m app.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lp = sub.add_parser("load-project", help="load a CSV and a project definition")
    lp.add_argument("--csv", type=Path, required=True)
    lp.add_argument("--config", type=Path, required=True)
    lp.add_argument("--frontend", default="http://localhost:5173")
    args = ap.parse_args(argv)
    try:
        pid = load_project(args.csv, args.config)
    except (ProjectError, OSError, ValueError) as e:
        print(f"Could not load the project: {e}")
        return 1
    print(f"Project {pid} loaded.\nOpen it at: {args.frontend}/?project={pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
