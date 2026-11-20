"""Command-line interface for seeded synthetic observations."""

import argparse
import json
from pathlib import Path

from . import __version__
from .generator import PROFILES, Simulation, generate_dataset


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="osp-sim", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    generate = parser.add_subparsers(dest="command", required=True).add_parser("generate")
    generate.add_argument("--output", required=True, type=Path)
    generate.add_argument("--profile", choices=(*PROFILES, "adversarial"), default="standard")
    generate.add_argument("--seed", type=int, default=1234)
    generate.add_argument("--height", type=int, default=96)
    generate.add_argument("--width", type=int, default=128)
    generate.add_argument("--lights", type=int, default=3)
    generate.add_argument("--masters", type=int, default=12)
    generate.add_argument("--adversarial", action="store_true")
    args = parser.parse_args(argv)
    faults = args.profile == "adversarial"
    fields = {
        name: getattr(args, name) for name in ("seed", "height", "width", "lights", "masters")
    }
    try:
        settings = Simulation.model_validate(
            {**fields, "profile": "standard" if faults else args.profile}
        )
        result = generate_dataset(args.output, settings, adversarial=faults or args.adversarial)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"osp-sim: {exc}\n")
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
