#!/usr/bin/python

#   - resolve_domain_box(): turns DOMAIN_BOX/DOMAIN_MARGIN into an explicit
#     (llx, lly, llz, urx, ury, urz) computational domain box.
#   - LENGTH_UNIT_TO_METERS: the C25D LENGTH unit (um/nm/m) expressed as a
#     meters-per-unit factor, needed because FasterCap and Raphael FX each
#     have their own (different) convention for how a file's declared
#     length unit relates to the physical answer - see each converter's
#     own epsilon/UNIT handling for how this gets used.
#
# This lives in common/ rather than being duplicated per-converter

LENGTH_UNIT_TO_METERS = {"um": 1e-6, "nm": 1e-9, "m": 1.0}

def length_unit_scale_factor(scene):
    if scene.length_unit not in LENGTH_UNIT_TO_METERS:
        raise NotImplementedError(
            f"unrecognized LENGTH unit '{scene.length_unit}' - expected one "
            f"of {sorted(LENGTH_UNIT_TO_METERS)}"
        )
    return LENGTH_UNIT_TO_METERS[scene.length_unit]


def resolve_domain_box(scene):
    if scene.domain.box is not None:
        return scene.domain.box

    if scene.domain.margin is None:
        raise NotImplementedError(
            "scene has neither DOMAIN_BOX nor DOMAIN_MARGIN - v1 requires "
            "one of the two to be specified explicitly (no default "
            "open-domain treatment implemented yet)"
        )

    if len(scene.ground_planes) > 1:
        raise NotImplementedError(
            f"DOMAIN_MARGIN resolution with more than one GROUND_PLANE "
            f"(found {len(scene.ground_planes)}) is not yet supported - "
            "ambiguous which plane, if any, should anchor the domain's "
            "lower Z bound"
        )

    all_box_shapes = [
        shape for conductor in scene.conductors.values() for shape in conductor.shapes
    ]
    if not all_box_shapes:
        raise NotImplementedError(
            "scene has no conductor shapes - domain resolution from "
            "DOMAIN_MARGIN needs at least one finite shape to expand "
            "around"
        )

    finite_minx = min(shape.llx for shape in all_box_shapes)
    finite_maxx = max(shape.urx for shape in all_box_shapes)
    finite_miny = min(shape.lly for shape in all_box_shapes)
    finite_maxy = max(shape.ury for shape in all_box_shapes)
    finite_minz = min(scene.layers[shape.layer_name].zlow for shape in all_box_shapes)
    finite_maxz = max(scene.layers[shape.layer_name].zhigh for shape in all_box_shapes)

    xmargin, ymargin, zmargin = scene.domain.margin
    llx = round(finite_minx - xmargin, 6)
    urx = round(finite_maxx + xmargin, 6)
    lly = round(finite_miny - ymargin, 6)
    ury = round(finite_maxy + ymargin, 6)
    urz = round(finite_maxz + zmargin, 6)

    if len(scene.ground_planes) == 1:
        llz = scene.ground_planes[0].zhigh
    else:
        llz = round(finite_minz - zmargin, 6)

    return (llx, lly, llz, urx, ury, urz)