import subprocess
import sys
from pathlib import Path

import pytest

THIS_DIR = Path(__file__).parent
CONVERTER_SRC_DIR = THIS_DIR.parent / "src"  # converters/fastercap/src/
COMMON_SRC_DIR = THIS_DIR.parent.parent / "common" / "src"  # converters/common/src/

sys.path.insert(0, str(CONVERTER_SRC_DIR))
sys.path.insert(0, str(COMMON_SRC_DIR))
FIXTURE_PATH = THIS_DIR.parent.parent / "common" / "tests" / "fixtures" / "c25d" / "parallel_plate.c25d"

def run_converter(c25d_path: Path, output_dir: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(CONVERTER_SRC_DIR / "C25D2FasterCap.py"),
            str(c25d_path),
            str(output_dir),
        ],
        capture_output=True,
        text=True,
    )

def _write_snippet(tmp_path: Path, content: str, name: str = "snippet.c25d") -> Path:
    path = tmp_path / name
    path.write_text(content)
    return path

class TestSmoke:
    def test_runs_without_error(self, tmp_path):
        result = run_converter(FIXTURE_PATH, tmp_path / "out")
        assert result.returncode == 0, (
            f"Converter exited non-zero.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

    def test_produces_lst_file(self, tmp_path):
        output_dir = tmp_path / "out"
        run_converter(FIXTURE_PATH, output_dir)
        assert (output_dir / "parallel_plate.lst").exists()

    def test_produces_expected_wire_panel_files(self, tmp_path):
        output_dir = tmp_path / "out"
        run_converter(FIXTURE_PATH, output_dir)
        wires_dir = output_dir / "Wires"
        expected = {
            "wire_SUB-bottom.txt", "wire_SUB-sides.txt", "wire_SUB-top.txt",
            "wire_PLATE_M1-bottom.txt", "wire_PLATE_M1-sides.txt", "wire_PLATE_M1-top.txt",
        }
        actual = {p.name for p in wires_dir.glob("*.txt")}
        assert actual == expected


class TestLstContent:

    @pytest.fixture(scope="class")
    def lst_lines(self, tmp_path_factory):
        output_dir = tmp_path_factory.mktemp("out")
        run_converter(FIXTURE_PATH, output_dir)
        return (output_dir / "parallel_plate.lst").read_text().splitlines()

    def test_ground_plane_bottom_and_sides_use_outward_facing_epsilon(self, lst_lines):
        matching = [l for l in lst_lines if "wire_SUB-bottom" in l or "wire_SUB-sides" in l]
        assert len(matching) == 2
        for line in matching:
            assert " 1e-06 " in line

    def test_ground_plane_top_touches_background_epsilon(self, lst_lines):
        matching = [l for l in lst_lines if "wire_SUB-top" in l]
        assert len(matching) == 1
        assert " 4e-06 " in matching[0]

    def test_plate_faces_all_touch_background_epsilon(self, lst_lines):
        matching = [l for l in lst_lines if "wire_PLATE_M1" in l]
        assert len(matching) == 3
        for line in matching:
            assert " 4e-06 " in line

    def test_ground_plane_position_matches_resolved_domain(self, lst_lines):
        matching = [l for l in lst_lines if "wire_SUB-bottom" in l]
        assert " -45.0 -0.1 -45.0 " in matching[0]

    def test_plate_position_matches_fixture(self, lst_lines):
        matching = [l for l in lst_lines if "wire_PLATE_M1-bottom" in l]
        assert " -25.0 2.0 -25.0 " in matching[0]


class TestPanelGeometry:

    def test_ground_plane_panel_spans_resolved_domain(self, tmp_path):
        output_dir = tmp_path / "out"
        run_converter(FIXTURE_PATH, output_dir)
        content = (output_dir / "Wires" / "wire_SUB-bottom.txt").read_text()
        assert "90.0x0.1x90.0um box" in content

    def test_plate_panel_matches_fixture_dimensions(self, tmp_path):
        output_dir = tmp_path / "out"
        run_converter(FIXTURE_PATH, output_dir)
        content = (output_dir / "Wires" / "wire_PLATE_M1-bottom.txt").read_text()
        assert "50.0x0.05x50.0um box" in content


class TestLengthUnitScaling:
    def test_um_scale_is_1e_minus_6(self, tmp_path):
        from C25D2FasterCap import _epsilon_scale_factor
        from C25D_parser import parse_c25d
        scene = parse_c25d(str(FIXTURE_PATH))
        assert _epsilon_scale_factor(scene) == pytest.approx(1e-6)

    def test_written_epsilon_equals_relative_permittivity_times_scale(self, tmp_path):
        output_dir = tmp_path / "out"
        run_converter(FIXTURE_PATH, output_dir)
        lst_content = (output_dir / "parallel_plate.lst").read_text()
        assert " 4e-06 " in lst_content
        assert " 4.0 " not in lst_content  

    def test_nm_and_m_scale_factors(self):
        from C25D_parser import C25DScene
        from C25D2FasterCap import _epsilon_scale_factor
        for unit, expected in [("um", 1e-6), ("nm", 1e-9), ("m", 1.0)]:
            scene = C25DScene()
            scene.length_unit = unit
            assert _epsilon_scale_factor(scene) == pytest.approx(expected)

    def test_unknown_length_unit_raises(self):
        from C25D_parser import C25DScene
        from C25D2FasterCap import _epsilon_scale_factor
        scene = C25DScene()
        scene.length_unit = "furlongs"
        with pytest.raises(NotImplementedError, match="furlongs"):
            _epsilon_scale_factor(scene)


class TestNoGroundPlane:
    def test_converts_without_error(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
METAL LOWER Z_OFFSETS 0.0 0.05
METAL UPPER Z_OFFSETS 1.0 1.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 4.0
CONDUCTOR A A.net
BOX CONDUCTOR A LAYER LOWER LL -50.0 -50.0 UR 50.0 50.0
CONDUCTOR B B.net
BOX CONDUCTOR B LAYER UPPER LL -50.0 -50.0 UR 50.0 50.0
DOMAIN_MARGIN X 20.0 Y 20.0 Z 5.0
""")
        result = run_converter(c25d_path, tmp_path / "out")
        assert result.returncode == 0, result.stderr

    def test_no_ground_plane_section_in_lst(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
METAL LOWER Z_OFFSETS 0.0 0.05
METAL UPPER Z_OFFSETS 1.0 1.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 4.0
CONDUCTOR A A.net
BOX CONDUCTOR A LAYER LOWER LL -50.0 -50.0 UR 50.0 50.0
CONDUCTOR B B.net
BOX CONDUCTOR B LAYER UPPER LL -50.0 -50.0 UR 50.0 50.0
DOMAIN_MARGIN X 20.0 Y 20.0 Z 5.0
""")
        output_dir = tmp_path / "out"
        run_converter(c25d_path, output_dir)
        lst_files = list(output_dir.glob("*.lst"))
        assert len(lst_files) == 1
        content = lst_files[0].read_text()
        assert "Ground plane" not in content
        assert "wire_A_LOWER" in content
        assert "wire_B_UPPER" in content

    def test_symmetric_z_margin_with_no_ground_plane(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
METAL LOWER Z_OFFSETS 0.0 0.05
METAL UPPER Z_OFFSETS 1.0 1.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 4.0
CONDUCTOR A A.net
BOX CONDUCTOR A LAYER LOWER LL -50.0 -50.0 UR 50.0 50.0
CONDUCTOR B B.net
BOX CONDUCTOR B LAYER UPPER LL -50.0 -50.0 UR 50.0 50.0
DOMAIN_MARGIN X 20.0 Y 20.0 Z 5.0
""")
        output_dir = tmp_path / "out"
        run_converter(c25d_path, output_dir)
        lst_files = list(output_dir.glob("*.lst"))
        content = lst_files[0].read_text()
        assert "wire_A_LOWER-bottom" in content


class TestOverlapPlatesFixture:

    FIXTURE = Path(__file__).parent.parent.parent / "common" / "tests" / "fixtures" / "c25d" / "overlap_plates_100um_x_100um_li1_met1.c25d"

    @pytest.fixture(scope="class")
    def lst_content(self, tmp_path_factory):
        output_dir = tmp_path_factory.mktemp("out")
        result = run_converter(self.FIXTURE, output_dir)
        assert result.returncode == 0, result.stderr
        lst_files = list(output_dir.glob("*.lst"))
        assert len(lst_files) == 1
        return lst_files[0].read_text()

    def test_no_ground_plane_section(self, lst_content):
        assert "Ground plane" not in lst_content

    def test_both_conductors_present(self, lst_content):
        assert "wire_A_li1" in lst_content
        assert "wire_B_met1" in lst_content

    def test_li1_position_matches_real_sky130a_height(self, lst_content):
        matching = [l for l in lst_content.splitlines() if "wire_A_li1-bottom" in l]
        assert " -50.0 0.9361 -50.0 " in matching[0]

    def test_met1_position_matches_real_sky130a_height(self, lst_content):
        matching = [l for l in lst_content.splitlines() if "wire_B_met1-bottom" in l]
        assert " -50.0 1.3761 -50.0 " in matching[0]

    def test_uniform_background_epsilon_everywhere(self, lst_content):
        conductor_lines = [
            l for l in lst_content.splitlines()
            if l.startswith("C ") and ("wire_A_li1" in l or "wire_B_met1" in l)
        ]
        assert len(conductor_lines) == 6  # 3 faces x 2 conductors
        for line in conductor_lines:
            assert " 4.1e-06 " in line

    def test_panel_dimensions_match_real_layer_thicknesses(self, tmp_path):
        output_dir = tmp_path / "out"
        run_converter(self.FIXTURE, output_dir)
        li1_content = (output_dir / "Wires" / "wire_A_li1-bottom.txt").read_text()
        met1_content = (output_dir / "Wires" / "wire_B_met1-bottom.txt").read_text()
        assert "100.0x0.075x100.0um box" in li1_content
        assert "100.0x0.36x100.0um box" in met1_content


class TestOutOfScopeFailsLoudly:
    def test_dielectric_simple_layer_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
GROUND_PLANE SUB Z_OFFSETS -0.1 0.0
METAL M1 Z_OFFSETS 2.0 2.05
DIELECTRIC_SIMPLE OX Z_OFFSETS 0.0 1.0 PERMITTIVITY 3.9 WRAPS M1
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
CONDUCTOR PLATE PLATE.net
BOX CONDUCTOR PLATE LAYER M1 LL -25.0 -25.0 UR 25.0 25.0
DOMAIN_MARGIN X 20.0 Y 20.0 Z 20.0
""")
        result = run_converter(c25d_path, tmp_path / "out")
        assert result.returncode != 0
        assert "DIELECTRIC_SIMPLE" in result.stderr
        assert "NotImplementedError" in result.stderr

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
        result = run_converter(c25d_path, tmp_path / "out")
        assert result.returncode != 0
        assert "more than one GROUND_PLANE" in result.stderr

    def test_missing_domain_settings_raises(self, tmp_path):
        c25d_path = _write_snippet(tmp_path, """
C25D 1.0
UNITS LENGTH um
GROUND_PLANE SUB Z_OFFSETS -0.1 0.0
METAL M1 Z_OFFSETS 2.0 2.05
DIELECTRIC_BACKGROUND air PERMITTIVITY 1.0
CONDUCTOR PLATE PLATE.net
BOX CONDUCTOR PLATE LAYER M1 LL -25.0 -25.0 UR 25.0 25.0
""")
        result = run_converter(c25d_path, tmp_path / "out")
        assert result.returncode != 0
        assert "neither DOMAIN_BOX nor DOMAIN_MARGIN" in result.stderr