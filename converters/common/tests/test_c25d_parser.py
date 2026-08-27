import sys
from pathlib import Path

import pytest


# Direct unit tests for C25D_parser.py and c25d_domain.py, the shared
# code used by every converter (fastercap, and whatever comes next).
# These call parse_c25d() / resolve_domain_box() / length_unit_scale_factor()
# in-process, NOT through a converter subprocess. 

THIS_DIR = Path(__file__).parent
COMMON_SRC_DIR = THIS_DIR.parent / "src"  # converters/common/src/
FIXTURES_DIR = THIS_DIR / "fixtures" / "c25d"

sys.path.insert(0, str(COMMON_SRC_DIR))

from C25D_parser import parse_c25d, C25DParseError, C25DScene  # noqa: E402
from c25d_domain import (  # noqa: E402
    length_unit_scale_factor,
    resolve_domain_box,
    LENGTH_UNIT_TO_METERS,
)

PARALLEL_PLATE = FIXTURES_DIR / "parallel_plate.c25d"
OVERLAP_PLATES = FIXTURES_DIR / "overlap_plates_100um_x_100um_li1_met1.c25d"


def _write_snippet(tmp_path: Path, content: str, name: str = "snippet.c25d") -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path


class TestParseHeader:
    def test_version_and_length_unit(self):
        scene = parse_c25d(str(PARALLEL_PLATE))
        assert scene.version == "1.0"
        assert scene.length_unit == "um"

    def test_metadata_captured(self):
        scene = parse_c25d(str(PARALLEL_PLATE))
        assert scene.metadata["technology"] == "test_synthetic"
        assert scene.metadata["source_cell"] == "parallel_plate"


class TestParseGroundPlaneAndLayers:
    def test_ground_plane_offsets(self):
        scene = parse_c25d(str(PARALLEL_PLATE))
        assert len(scene.ground_planes) == 1
        gp = scene.ground_planes[0]
        assert gp.name == "SUB"
        assert gp.zlow == pytest.approx(-0.1)
        assert gp.zhigh == pytest.approx(0.0)

    def test_metal_layer_offsets(self):
        scene = parse_c25d(str(PARALLEL_PLATE))
        assert "M1" in scene.layers
        layer = scene.layers["M1"]
        assert layer.kind == "METAL"
        assert layer.zlow == pytest.approx(2.0)
        assert layer.zhigh == pytest.approx(2.05)

    def test_no_ground_plane_is_valid(self):
        # GROUND_PLANE is optional in C25D
        scene = parse_c25d(str(OVERLAP_PLATES))
        assert scene.ground_planes == []


class TestParseConductorsAndShapes:
    def test_conductor_and_box_shape(self):
        scene = parse_c25d(str(PARALLEL_PLATE))
        assert "PLATE" in scene.conductors
        conductor = scene.conductors["PLATE"]
        assert conductor.net == "PLATE.net"
        assert len(conductor.shapes) == 1
        shape = conductor.shapes[0]
        assert shape.layer_name == "M1"
        assert (shape.llx, shape.lly, shape.urx, shape.ury) == (-25.0, -25.0, 25.0, 25.0)

    def test_two_conductors_on_different_layers(self):
        scene = parse_c25d(str(OVERLAP_PLATES))
        assert set(scene.conductors) == {"A", "B"}
        assert scene.conductors["A"].shapes[0].layer_name == "li1"
        assert scene.conductors["B"].shapes[0].layer_name == "met1"


class TestParseDomain:
    def test_domain_margin_captured(self):
        scene = parse_c25d(str(PARALLEL_PLATE))
        assert scene.domain.margin == (20.0, 20.0, 20.0)
        assert scene.domain.box is None

    def test_domain_box_captured(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
GROUND_PLANE SUB Z_OFFSETS -0.1 0.0
METAL M1 Z_OFFSETS 2.0 2.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
CONDUCTOR PLATE PLATE.net
BOX CONDUCTOR PLATE LAYER M1 LL -25.0 -25.0 UR 25.0 25.0
DOMAIN_BOX LL -50.0 -50.0 -10.0 UR 50.0 50.0 20.0
""")
        scene = parse_c25d(str(c25d_path))
        assert scene.domain.box == (-50.0, -50.0, -10.0, 50.0, 50.0, 20.0)
        assert scene.domain.margin is None


class TestEpsilonAt:
    def test_uniform_background_everywhere(self):
        # parallel_plate.c25d has no DIELECTRIC_SIMPLE layers, so
        # epsilon_at() must return the background permittivity at any point
        scene = parse_c25d(str(PARALLEL_PLATE))
        assert scene.epsilon_at(0.0, 0.0, -5.0) == pytest.approx(4.0)
        assert scene.epsilon_at(0.0, 0.0, 1.0) == pytest.approx(4.0)
        assert scene.epsilon_at(100.0, 100.0, 50.0) == pytest.approx(4.0)

    def test_dielectric_simple_overrides_background_in_its_z_range(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
GROUND_PLANE SUB Z_OFFSETS -0.1 0.0
METAL M1 Z_OFFSETS 2.0 2.05
DIELECTRIC_SIMPLE OX Z_OFFSETS 0.0 2.0 PERMITTIVITY 3.9 WRAPS M1
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
CONDUCTOR PLATE PLATE.net
BOX CONDUCTOR PLATE LAYER M1 LL -25.0 -25.0 UR 25.0 25.0
DOMAIN_MARGIN X 20.0 Y 20.0 Z 20.0
""")
        scene = parse_c25d(str(c25d_path))
        assert scene.epsilon_at(0.0, 0.0, 1.0) == pytest.approx(3.9)  # inside OX
        assert scene.epsilon_at(0.0, 0.0, 5.0) == pytest.approx(1.0)  # outside OX, background


class TestParseErrors:
    def test_missing_background_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
GROUND_PLANE SUB Z_OFFSETS -0.1 0.0
METAL M1 Z_OFFSETS 2.0 2.05
CONDUCTOR PLATE PLATE.net
BOX CONDUCTOR PLATE LAYER M1 LL -25.0 -25.0 UR 25.0 25.0
DOMAIN_MARGIN X 20.0 Y 20.0 Z 20.0
""")
        with pytest.raises(C25DParseError, match="DIELECTRIC_BACKGROUND"):
            parse_c25d(str(c25d_path))

    def test_second_background_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
DIELECTRIC_BACKGROUND air2 PERMITTIVITY 2.0
""")
        with pytest.raises(C25DParseError, match="second DIELECTRIC_BACKGROUND"):
            parse_c25d(str(c25d_path))

    def test_duplicate_profile_name_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
METAL M1 Z_OFFSETS 0.0 0.05
METAL M1 Z_OFFSETS 1.0 1.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
""")
        with pytest.raises(C25DParseError, match="declared more than once"):
            parse_c25d(str(c25d_path))

    def test_box_referencing_undeclared_conductor_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
METAL M1 Z_OFFSETS 0.0 0.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
BOX CONDUCTOR GHOST LAYER M1 LL -1.0 -1.0 UR 1.0 1.0
""")
        with pytest.raises(C25DParseError, match="has not been declared"):
            parse_c25d(str(c25d_path))

    def test_dielectric_sidewall_raises_not_implemented(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
METAL M1 Z_OFFSETS 0.0 0.05
DIELECTRIC_SIDEWALL SW Z_OFFSETS 0.0 0.05 PERMITTIVITY 3.9 THICKNESS_SIDEWALL 0.01 WRAPS M1
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
""")
        with pytest.raises(NotImplementedError, match="DIELECTRIC_SIDEWALL"):
            parse_c25d(str(c25d_path))

    def test_polygon_raises_not_implemented(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
METAL M1 Z_OFFSETS 0.0 0.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
CONDUCTOR PLATE PLATE.net
POLYGON CONDUCTOR PLATE LAYER M1 OUTER 0.0 0.0 1.0 0.0 1.0 1.0
""")
        with pytest.raises(NotImplementedError, match="POLYGON"):
            parse_c25d(str(c25d_path))

    def test_unknown_keyword_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
BOGUS_KEYWORD foo bar
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
""")
        with pytest.raises(C25DParseError, match="unknown keyword"):
            parse_c25d(str(c25d_path))


class TestLengthUnitScaleFactor:
    def test_um_nm_m(self):
        for unit, expected in LENGTH_UNIT_TO_METERS.items():
            scene = C25DScene()
            scene.length_unit = unit
            assert length_unit_scale_factor(scene) == pytest.approx(expected)

    def test_unknown_unit_raises(self):
        scene = C25DScene()
        scene.length_unit = "furlongs"
        with pytest.raises(NotImplementedError, match="furlongs"):
            length_unit_scale_factor(scene)


class TestResolveDomainBox:
    def test_explicit_domain_box_takes_precedence(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
GROUND_PLANE SUB Z_OFFSETS -0.1 0.0
METAL M1 Z_OFFSETS 2.0 2.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
CONDUCTOR PLATE PLATE.net
BOX CONDUCTOR PLATE LAYER M1 LL -25.0 -25.0 UR 25.0 25.0
DOMAIN_MARGIN X 999.0 Y 999.0 Z 999.0
DOMAIN_BOX LL -50.0 -50.0 -10.0 UR 50.0 50.0 20.0
""")
        scene = parse_c25d(str(c25d_path))
        assert resolve_domain_box(scene) == (-50.0, -50.0, -10.0, 50.0, 50.0, 20.0)

    def test_margin_resolution_anchors_to_ground_plane(self):
        # parallel_plate.c25d: plate 50x50 centered at origin, X/Y margin=20
        # -> llx=-45, urx=45 (same for y). Ground plane zhigh=0.0 anchors llz.
        scene = parse_c25d(str(PARALLEL_PLATE))
        domain_box = resolve_domain_box(scene)
        llx, lly, llz, urx, ury, urz = domain_box
        assert (llx, urx) == pytest.approx((-45.0, 45.0))
        assert (lly, ury) == pytest.approx((-45.0, 45.0))
        assert llz == pytest.approx(0.0)  # ground plane's own zhigh

    def test_margin_resolution_without_ground_plane_uses_symmetric_z(self):
        # overlap_plates fixture has no GROUND_PLANE: li1 z=[0.9361,1.0111],
        # met1 z=[1.3761,1.7361], Z margin=2.0
        # -> llz = 0.9361 - 2.0, urz = 1.7361 + 2.0
        scene = parse_c25d(str(OVERLAP_PLATES))
        domain_box = resolve_domain_box(scene)
        llx, lly, llz, urx, ury, urz = domain_box
        assert llz == pytest.approx(0.9361 - 2.0)
        assert urz == pytest.approx(1.7361 + 2.0)

    def test_no_domain_box_or_margin_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
GROUND_PLANE SUB Z_OFFSETS -0.1 0.0
METAL M1 Z_OFFSETS 2.0 2.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
CONDUCTOR PLATE PLATE.net
BOX CONDUCTOR PLATE LAYER M1 LL -25.0 -25.0 UR 25.0 25.0
""")
        scene = parse_c25d(str(c25d_path))
        with pytest.raises(NotImplementedError, match="neither DOMAIN_BOX nor DOMAIN_MARGIN"):
            resolve_domain_box(scene)

    def test_two_ground_planes_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
GROUND_PLANE SUB1 Z_OFFSETS -0.1 0.0
GROUND_PLANE SUB2 Z_OFFSETS 10.0 10.1
METAL M1 Z_OFFSETS 2.0 2.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
CONDUCTOR PLATE PLATE.net
BOX CONDUCTOR PLATE LAYER M1 LL -25.0 -25.0 UR 25.0 25.0
DOMAIN_MARGIN X 20.0 Y 20.0 Z 20.0
""")
        scene = parse_c25d(str(c25d_path))
        with pytest.raises(NotImplementedError, match="more than one GROUND_PLANE"):
            resolve_domain_box(scene)

    def test_no_conductor_shapes_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
GROUND_PLANE SUB Z_OFFSETS -0.1 0.0
METAL M1 Z_OFFSETS 2.0 2.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
DOMAIN_MARGIN X 20.0 Y 20.0 Z 20.0
""")
        scene = parse_c25d(str(c25d_path))
        with pytest.raises(NotImplementedError, match="no conductor shapes"):
            resolve_domain_box(scene)