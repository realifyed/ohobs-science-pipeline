"""Enforce the dependency direction independently of installed packages."""

import ast
import tomllib
from pathlib import Path

from ohobs_pipeline.cli import parser

ROOT = Path(__file__).resolve().parents[1]


def test_production_has_no_simulation_dependency():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert set(project["scripts"]) == {"osp"}
    assert all("ohobs-science-sim" not in spec for spec in project["dependencies"])
    assert all(
        "ohobs-science-sim" not in spec
        for specs in project["optional-dependencies"].values()
        for spec in specs
    )
    source = ROOT / "src" / "ohobs_pipeline"
    assert not (source / "simulation.py").exists()
    for module in source.rglob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        names = {
            name
            for node in ast.walk(tree)
            for name in (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [node.module or "", *(alias.name for alias in node.names)]
                if isinstance(node, ast.ImportFrom)
                else []
            )
        }
        assert all(name.split(".")[0] not in {"ohobs_sim", "simulation"} for name in names), module
    assert "simulate" not in parser().format_help()
