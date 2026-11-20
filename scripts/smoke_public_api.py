"""Run the Core-only Python example published in docs/api/PUBLIC.md."""

import ast
import os
import shutil
import tempfile
from pathlib import Path


def main():
    document = Path(__file__).resolve().parents[1] / "docs/api/PUBLIC.md"
    example = document.read_text(encoding="utf-8").split("```python\n", 1)[1].split("```", 1)[0]
    code = compile(ast.parse(example), str(document), "exec")
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="osp-api-") as temporary:
        folder = Path(temporary)
        (folder / "examples").mkdir()
        shutil.copyfile(
            document.parents[2] / "examples/core-smoke-fixture.zip",
            folder / "examples/core-smoke-fixture.zip",
        )
        try:
            os.chdir(folder)
            # Execute only the trusted, checked-in documentation example.
            exec(code, {"__name__": "__main__"})  # noqa: S102
        finally:
            os.chdir(previous)


if __name__ == "__main__":
    main()
