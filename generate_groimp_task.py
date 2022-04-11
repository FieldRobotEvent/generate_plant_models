#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

from jinja2 import Template

PLANT_TYPES = [
    "dicot1",
    "dicot2",
    "cheno",
    "at",
    "cereal",
    "grass",
    "hemp",
    "weed",
    "sunflower",
    "maize",
    "quinoa",
    "tulip",
    "pea",
    "soy",
    "faba",
    "basil",
]


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument(
        "--groimp_path",
        type=Path,
        default=Path(__file__).parent / "groimp",
        help="GroIMP folder path.",
    )
    parser.add_argument(
        "--groimp_output_path",
        type=Path,
        default=Path(__file__).parent / "generated_groimp",
        help="GroIMP output path.",
    )
    parser.add_argument(
        "--crop_type",
        type=str,
        default="maize",
        choices=PLANT_TYPES,
        help="Crop type to generate task.",
    )
    args = parser.parse_args()

    parameter_template = Template(Path("templates/parameters.rgg.template").read_text(encoding="utf-8"))

    output_folder: Path = args.groimp_output_path
    highest_run_number = 1
    for sub_output_folder in output_folder.glob(f"{args.crop_type}_*/"):
        try:
            highest_run_number = max(highest_run_number, int(sub_output_folder.name.split("_")[1]))
        except ValueError:
            pass

    run_output_folder = (output_folder / f"{args.crop_type}_{highest_run_number+1:03}").resolve()
    run_output_folder.mkdir()

    parameter_file: Path = args.groimp_path / "parameters.rgg"
    parameter_file.write_text(
        parameter_template.render(output_path=run_output_folder, crop_type=args.crop_type),
        encoding="utf-8",
    )
