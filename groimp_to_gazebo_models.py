#!/usr/bin/env python3
from __future__ import annotations

from csv import DictReader
from pathlib import Path
from shutil import rmtree

import cv2
import numpy as np
from jinja2 import Template
from pymeshlab import Color, MeshSet


class PlantMesh:
    def __init__(self, artifact_path: Path) -> None:
        self._n_artifact_vertices = self.artifact_to_vertices_number(artifact_path)

    def make_mesh(
        self, input_path: Path, output_path: Path, plant_color: tuple[int, int, int] = (95, 140, 48)
    ) -> None:
        mesh = MeshSet()
        mesh.load_new_mesh(str(input_path))
        mesh.compute_selection_by_condition_per_vertex(condselect=f"vi<{self._n_artifact_vertices}")
        mesh.meshing_remove_selected_vertices()

        # Set mesh origin to lowest point (y-axis)
        vertex_matrix = mesh.current_mesh().vertex_matrix()
        lowest_vertices = vertex_matrix[vertex_matrix[:, 1] <= np.min(vertex_matrix[:, 1], 0) + 0.02, :]
        median_diff = np.abs(lowest_vertices - np.median(lowest_vertices, axis=0))
        inliers = lowest_vertices[(median_diff[:, 0] < 0.05) & (median_diff[:, 2] < 0.05), :]

        center_coordinate = np.mean(inliers, axis=0)

        mesh.compute_matrix_from_translation_rotation_scale(
            translationx=-center_coordinate[0],
            translationy=-center_coordinate[1],
            translationz=-center_coordinate[2],
            freeze=True,  # Apply direct
        )

        if mesh.current_mesh().vertex_number() == 0:
            print(f"ERROR: cannot save {output_path} because there are no vertices left!")
            return

        # Create texture
        mesh.set_color_per_vertex(color1=Color(r=plant_color[0], g=plant_color[1], b=plant_color[2]))
        # mesh.apply_color_noising_per_vertex(noisebits=30)
        mesh.compute_texcoord_parametrization_triangle_trivial_per_wedge()
        mesh.transfer_attributes_to_texture_per_vertex(
            textname=f"../materials/textures/{output_path.stem}.png",
            attributeenum="Vertex Color",
            textw=512,
            texth=512,
        )
        # TODO: make texture more interesting. Now it is just one value. Maybe use OpenCV to create some
        # random noise on the color.

        mesh.save_current_mesh(str(output_path), save_wedge_texcoord=True)

    @staticmethod
    def reject_outliers(data: np.ndarray, m: float = 2.0) -> np.ndarray:
        # Source: https://stackoverflow.com/questions/11686720/is-there-a-numpy-builtin-to-reject-outliers-from-a-list
        d = np.abs(data - np.median(data, axis=0))
        print(d)
        print(data)
        mdev = np.median(d, axis=0)
        s = d / (mdev if mdev else 1.0)
        return data[s < m, :]

    @staticmethod
    def artifact_to_vertices_number(artifact_path: Path) -> int:
        artifact = MeshSet()
        artifact.load_new_mesh(str(artifact_path))
        m = artifact.current_mesh()
        return m.vertex_number()


def extract_plant_details(plant_details_file: Path) -> dict[int, dict[str, str]]:
    plant_details = {}
    with plant_details_file.open("r") as fs:
        reader = DictReader(fs, delimiter="\t")
        for r in reader:
            plant_details[int(r["time(d)"])] = r

    return plant_details


def shuffle_texture_colors(texture_file: Path, scale_bgr: tuple[float] = (50, 150, 100)) -> None:
    texture = cv2.imread(str(texture_file), cv2.IMREAD_COLOR)
    mean_color = texture.mean(axis=0).mean(axis=0)
    noisy_texture = np.clip((np.random.rand(*texture.shape) - 0.5) * scale_bgr + mean_color, 0, 255)
    cv2.imwrite(str(texture_file), noisy_texture.astype(np.uint8))


if __name__ == "__main__":
    from argparse import ArgumentParser

    parser = ArgumentParser()
    parser.add_argument("groimp_folders", type=str, nargs="+", help="List of plant numbers")
    parser.add_argument(
        "--groimp_output_folder",
        type=Path,
        help="groimp output path with .obj files",
        default=Path("generated_groimp"),
    )
    parser.add_argument(
        "--model_output_folder",
        type=Path,
        help="Output path for Gazebo models",
        default=Path("generated"),
    )
    parser.add_argument("--min_days", type=int, help="Minimum day number", default=25)
    parser.add_argument("--max_days", type=int, help="Maximum day number", default=100)
    parser.add_argument("--increment", type=int, help="Increment in day numbers", default=5)

    args = parser.parse_args()

    if not args.groimp_output_folder.is_dir():
        print("ERROR: cannot find the GroIMP output folder!")

    config_template = Template(Path("templates/model.config.template").read_text(encoding="utf-8"))
    model_template = Template(Path("templates/model.sdf.template").read_text(encoding="utf-8"))

    for plant_name in args.groimp_folders:
        plant_path: Path = args.groimp_output_folder / plant_name

        if not plant_path.is_dir():
            print(
                f"ERROR: cannot find plant number {plant_name}! Did you specify the 'path' variable correctly in GroIMP?"
            )
            exit(1)

        artifact_path = plant_path / "basic001.obj"
        plant_mesh = PlantMesh(artifact_path)

        plant_details_file = plant_path / "plant.txt"
        if not plant_details_file.is_file():
            print(
                f"ERROR: cannot find plant.txt! Did you specify the 'pathData' variable correctly in GroIMP?"
            )
            exit(1)

        plant_details = extract_plant_details(plant_details_file)

        for mesh in plant_path.glob("*.obj"):
            day_number = int(mesh.stem[-3:])

            if (
                args.min_days <= day_number <= args.max_days
                and (day_number - args.min_days) % args.increment == 0
            ):
                model_name = f"{plant_name}_day_{day_number:03d}"

                print(f"Generating model {model_name}")

                # create gazebo model folders
                #   model_name
                #   |-materials
                #   |    |-textures
                #   |
                #   |-meshes
                #   |    |- model_name.obj
                #   |
                #   |-model.config
                #   |-model.sdf

                model_folder: Path = args.model_output_folder / model_name

                if model_folder.is_dir():
                    if (
                        input(
                            f"Model {model_folder.name} already exist. Do you want to overwrite it? [y/n] "
                        ).lower()
                        == "y"
                    ):
                        rmtree(model_folder)
                    else:
                        print(f"Skipping {model_folder.name} because it already exist")
                        continue

                textures_folder = model_folder / "materials" / "textures"
                meshes_folder = model_folder / "meshes"

                # Create folders
                textures_folder.mkdir(parents=True)
                meshes_folder.mkdir(parents=True)

                mesh_file = meshes_folder / (model_name + ".dae")
                plant_mesh.make_mesh(mesh, mesh_file)

                shuffle_texture_colors(textures_folder / (model_name + ".png"))

                config_file = model_folder / "model.config"
                config_file.write_text(config_template.render(model_name=model_name), encoding="utf-8")

                try:
                    plant_height = max(float(plant_details[day_number]["Plant height"]), 0.10)
                    mass = (
                        (float(plant_details[day_number]["aboveBiom(mg)"]) / 1e6) / 0.25,
                    )  # 25% dry matter

                    if isinstance(mass, tuple):
                        mass = mass[0]

                except KeyError:
                    plant_height = 0.5
                    mass = 1.0

                model_file = model_folder / "model.sdf"
                model_file.write_text(
                    model_template.render(
                        model_name=model_name,
                        mesh_file=mesh_file.name,
                        plant_height=plant_height,
                        mass=mass,
                    ),
                    encoding="utf-8",
                )
