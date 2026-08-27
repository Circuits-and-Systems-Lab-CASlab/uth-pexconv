# Tests

Two independent test files, one per converter:

## test_universal2fastercap.py

Tests `Universal2FasterCap.py` against `tests/fixtures/universal_input/Test1`.

- **Basic run check:** converter runs, produces `wires.lst`, `Dielectrics/`, `Wires/`
- **Golden:** output file set and byte-for-byte content checked against
  `tests/golden/`

To regenerate `tests/golden/` after an intentional output change:

```
cd converters/fastercap/src
python3 Universal2FasterCap.py ../../../tests/fixtures/universal_input <tmp>/output standard 3D
```

## test_c25d2fastercap.py

Tests `C25D2FasterCap.py` (the C25D format converter) using two fixtures
from `../../common/tests/fixtures/c25d/`:
- `parallel_plate.c25d`: plate over a ground plane, 50x50um, 2um gap, epsr=4.0
- `overlap_plates_100um_x_100um_li1_met1.c25d`: two plates, no ground plane,
  sky130A li1/met1 heights

What each part checks:

- **Files get written correctly**: the converter runs without crashing and
  produces the expected `.lst` file and the 6 wire panel `.txt` files, with
  panel dimensions (width/thickness/height) matching the fixture's geometry.

- **.lst content is numerically correct**: the epsilon values and x/y/z
  positions written into the `.lst` file match numbers worked out by hand
  from the fixture (e.g. "the plate's faces should have epsilon 4e-06 and
  sit at z=2.0").

- **Length unit scaling is correct**: um/nm/m convert to the right
  meters-scale factor (1e-6/1e-9/1.0), and the `.lst` file contains the
  *scaled* epsilon, not the raw unscaled permittivity value.

- **Patterns with no ground plane still work**: C25D allows zero
  `GROUND_PLANE` entries (e.g. two conductors on different metal layers).

**Not covered:** this suite never runs FasterCap itself or checks the actual
extracted capacitance. It only checks that the converter's *output* is
correct, not that FasterCap gives the right answer from it.

## Running

```
pytest tests/
```