# examples/fastercap-conversion/

Example showing the Universal Format → FasterCap conversion step, using
`converters/fastercap/src/Universal2FasterCap.py`.

## What this is

A runnable demonstration of one step in the flow: turning a folder of
Universal Format pattern files into FasterCap input files (`.lst` files
plus their referenced `Dielectrics/` and `Wires/` panel geometry files),
using `converters/fastercap/src/Universal2FasterCap.py`. It
assumes you already have Universal Format files ready (it does not
generate patterns itself).

If you need to generate patterns first, see `external/openroad-patterns/`.

## Status

The FasterCap converter is a work in progress. It has mainly been tested
on `M1oM0` patterns so far - support for other layer combinations will
be extended and validated over time.

## Prerequisites

- Python 3
- A folder of Universal Format "wires" files (see the Universal Format
  specification for the expected structure: GROUND_PLANE, DIELECTRIC,
  WIRE, WINDOW_BBOX / SIM_WIN_EXT directives)
- The FasterCap executable, if you also want to run
  `run_fastercap_solver.py`

## Usage

From the repo root:

```bash
python3 examples/fastercap-conversion/run_fastercap_conversion.py <universal_format_folder> <heights_reference> <2D|3D>
```

- `<heights_reference>` is `normalized` or `standard`
- `<2D|3D>` selects the geometry mode

By default, converted FasterCap files are written to
`examples/fastercap-conversion/output/`. To choose a different output
location:

```bash
python3 examples/fastercap-conversion/run_fastercap_conversion.py <universal_format_folder> <heights_reference> <2D|3D> <output_folder>
```

To then run FasterCap on the converted files:

```bash
python3 examples/fastercap-conversion/run_fastercap_solver.py <fastercap_executable>
```

This runs FasterCap (in headless mode, `-b`) against every `.lst` file
under `examples/fastercap-conversion/output/` by default. A specific
`.lst` file or a different folder can be given instead:

```bash
python3 examples/fastercap-conversion/run_fastercap_solver.py <fastercap_executable> <fastercap_file_or_folder>
```

When pointed at a folder, it only matches files ending in `.lst` by
default; a different extension can be given as a third argument:

```bash
python3 examples/fastercap-conversion/run_fastercap_solver.py <fastercap_executable> <fastercap_folder> <file_extension>
```

`<fastercap_executable>` can be a path or a name resolved from `PATH`.

## What it does

`run_fastercap_conversion.py` calls
`converters/fastercap/src/Universal2FasterCap.py` with the
input folder, output folder, heights reference, and mode you provide,
then reports how many files were generated and where they landed.

`run_fastercap_solver.py` resolves the FasterCap executable, runs it
against each matched `.lst` file (or the single file given), writes a
`.log` file alongside each one with the command, exit code, stdout, and
stderr, and reports a pass/fail summary across all files.