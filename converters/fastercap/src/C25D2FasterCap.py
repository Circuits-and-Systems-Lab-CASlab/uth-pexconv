#!/usr/bin/python
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "common", "src"))

from C25D_parser import parse_c25d
import fastercap_panel_io as panel_io

# Converts a single C25D file into a FasterCap .lst pattern file plus its
# panel geometry files, using:
#   - C25D_parser.py and fastercap_panel_io.py 
#
# KT-NOTE: NOT YET SUPPORTED, raises NotImplementedError:
#   - Any DIELECTRIC_SIMPLE layer
#   - POLYGON shapes (inherited limitation from C25D_parser.py)
#   - Multiple GROUND_PLANE records, or zero

FACE_SAMPLE_OFFSET = 1e-4 
OUTWARD_FACING_RELATIVE_PERMITTIVITY = 1.0

# FasterCap expects panel coordinates in meters and treats the permittivity
# value in each D/C record as a relative permittivity scaled by that same
# meters assumption. 
# C25D geometry is in whatever LENGTH unit the file declares (um/nm/m)
#  so every permittivity value written must be scaled by the corresponding 
# length-to-meters factor to get a correct capacitance result. 
from c25d_domain import LENGTH_UNIT_TO_METERS, length_unit_scale_factor, resolve_domain_box as _resolve_domain_box

def _epsilon_scale_factor(scene):
    return length_unit_scale_factor(scene)

def resolve_domain_box(scene):
    return _resolve_domain_box(scene)

def write_ground_plane(currentpath, fastercap_file, scene, domain_box, epsilon_scale):
    if len(scene.ground_planes) != 1:
        raise NotImplementedError(
            f"expected exactly one GROUND_PLANE (found {len(scene.ground_planes)})"
        )
    ground_plane = scene.ground_planes[0]
    llx, lly, llz, urx, ury, urz = domain_box

    # Ground plane spans the full domain XY extent 
    thickness = round(ground_plane.zhigh - ground_plane.zlow, 6)
    height = ury - lly    
    offx, offy, offz = llx, ground_plane.zlow, lly

    outward_facing_epsilon = round(OUTWARD_FACING_RELATIVE_PERMITTIVITY * epsilon_scale, 14)

    fastercap_file.write(f"* {ground_plane.name} (ground plane)\n*\n")

    bottom_file = f"Wires/wire_{ground_plane.name}-bottom.txt"
    panel_io.write_wire_bottom_panel(currentpath, bottom_file, ground_plane.name, width, thickness, height)
    panel_io.insert_conductor_into_pattern_file(
        currentpath, fastercap_file, bottom_file, outward_facing_epsilon, offx, offy, offz
    )
    fastercap_file.write(" + \n")

    sides_file = f"Wires/wire_{ground_plane.name}-sides.txt"
    panel_io.write_wire_side_panels(currentpath, sides_file, ground_plane.name, width, thickness, height)
    panel_io.insert_conductor_into_pattern_file(
        currentpath, fastercap_file, sides_file, outward_facing_epsilon, offx, offy, offz
    )
    fastercap_file.write(" + \n")

    top_epsilon = round(
        scene.epsilon_at((llx + urx) / 2, (lly + ury) / 2, ground_plane.zhigh + FACE_SAMPLE_OFFSET)
        * epsilon_scale,
        14,
    )
    top_file = f"Wires/wire_{ground_plane.name}-top.txt"
    panel_io.write_wire_top_panel(currentpath, top_file, ground_plane.name, width, thickness, height)
    panel_io.insert_conductor_into_pattern_file(
        currentpath, fastercap_file, top_file, top_epsilon, offx, offy, offz
    )
    fastercap_file.write("\n\n")


def write_conductor(currentpath, fastercap_file, scene, conductor, epsilon_scale):
    for shape in conductor.shapes:
        layer = scene.layers[shape.layer_name]
        width = shape.urx - shape.llx
        thickness = round(layer.zhigh - layer.zlow, 6)
        height = shape.ury - shape.lly
        offx, offy, offz = shape.llx, layer.zlow, shape.lly

        cx = (shape.llx + shape.urx) / 2  # box center X, for bottom/top face sampling
        cy = (shape.lly + shape.ury) / 2  # box center Y
        cz = (layer.zlow + layer.zhigh) / 2  # box mid Z, for side face sampling

        base = f"{conductor.shortname}_{shape.layer_name}"

        fastercap_file.write(f"* {conductor.shortname} ({conductor.net})\n*\n")

        bottom_epsilon = round(scene.epsilon_at(cx, cy, layer.zlow - FACE_SAMPLE_OFFSET) * epsilon_scale, 14)
        bottom_file = f"Wires/wire_{base}-bottom.txt"
        panel_io.write_wire_bottom_panel(currentpath, bottom_file, base, width, thickness, height)
        panel_io.insert_conductor_into_pattern_file(
            currentpath, fastercap_file, bottom_file, bottom_epsilon, offx, offy, offz
        )
        fastercap_file.write(" + \n")

        side_epsilon = round(scene.epsilon_at(shape.urx + FACE_SAMPLE_OFFSET, cy, cz) * epsilon_scale, 14)
        sides_file = f"Wires/wire_{base}-sides.txt"
        panel_io.write_wire_side_panels(currentpath, sides_file, base, width, thickness, height)
        panel_io.insert_conductor_into_pattern_file(
            currentpath, fastercap_file, sides_file, side_epsilon, offx, offy, offz
        )
        fastercap_file.write(" + \n")

        top_epsilon = round(scene.epsilon_at(cx, cy, layer.zhigh + FACE_SAMPLE_OFFSET) * epsilon_scale, 14)
        top_file = f"Wires/wire_{base}-top.txt"
        panel_io.write_wire_top_panel(currentpath, top_file, base, width, thickness, height)
        panel_io.insert_conductor_into_pattern_file(
            currentpath, fastercap_file, top_file, top_epsilon, offx, offy, offz
        )
        fastercap_file.write("\n\n")


def convert_c25d_to_fastercap(c25d_path, output_dir):
    scene = parse_c25d(c25d_path)

    if any(d.kind == "SIMPLE" for d in scene.dielectrics):
        raise NotImplementedError(
            "scene contains DIELECTRIC_SIMPLE layer(s) - C25D2FasterCap.py "
            "v1 only supports background-only scenes; writing interior "
            "dielectric-dielectric boundary panels needs row-scan/cutout "
            "logic not yet implemented here (see module docstring)"
        )
    domain_box = resolve_domain_box(scene)
    epsilon_scale = _epsilon_scale_factor(scene)

    currentpath = os.path.normpath(os.path.abspath(output_dir))
    if not os.path.exists(os.path.join(currentpath, "Wires")):
        os.makedirs(os.path.join(currentpath, "Wires"))
    if not os.path.exists(os.path.join(currentpath, "Dielectrics")):
        os.makedirs(os.path.join(currentpath, "Dielectrics"))

    pattern_name = os.path.splitext(os.path.basename(c25d_path))[0]
    lst_path = os.path.join(currentpath, f"{pattern_name}.lst")

    with open(lst_path, "w+") as fastercap_file:
        fastercap_file.write(f"* C25D pattern: {pattern_name}\n")
        fastercap_file.write("* ------------------------------\n\n")

        if scene.ground_planes:
            fastercap_file.write("* ------------------------------\n")
            fastercap_file.write("* Ground plane\n")
            fastercap_file.write("* ------------------------------\n\n")
            write_ground_plane(currentpath, fastercap_file, scene, domain_box, epsilon_scale)

        fastercap_file.write("* ------------------------------\n")
        fastercap_file.write("* Conductors\n")
        fastercap_file.write("* ------------------------------\n\n")
        for conductor in scene.conductors.values():
            write_conductor(currentpath, fastercap_file, scene, conductor, epsilon_scale)

    return lst_path


def main(argv):
    syntax = "python3 C25D2FasterCap.py <c25d_file> <output_dir>"
    if len(argv) != 3:
        print("ERROR! Wrong number of arguments!")
        print("Re-run with: " + syntax)
        sys.exit(-2)

    c25d_path, output_dir = argv[1], argv[2]

    if not os.path.exists(c25d_path):
        print("ERROR! Specified C25D file path does not exist!")
        print("Re-run with: " + syntax)
        sys.exit(-2)

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"Folder '{output_dir}' created successfully.")

    lst_path = convert_c25d_to_fastercap(c25d_path, output_dir)
    print(f"Wrote {lst_path}")


if __name__ == "__main__":
    main(sys.argv[0:])