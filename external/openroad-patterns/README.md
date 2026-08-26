# external/openroad-patterns/

Wrapper for generating the DEF wire calibration patterns used to build
FasterCap-based extraction rules, via OpenROAD's `gen_solver_patterns`
command.

## Context

OpenROAD is included in this repo as a git submodule
(`external/openroad/`), so its own pattern-generation
script (`external/openroad/src/rcx/calibration/fasterCap/scripts/gen_patterns.tcl`) remains unchanged.

This folder holds a wrapper (`run_gen_patterns.tcl`) that calls the
same `gen_solver_patterns` command, but resolves the process file path
against this repo's layout (`external/openroad/...`) instead of OpenROAD's own `scripts/` directory. 

## Prerequisites

```bash
git submodule update --init --recursive
```

You'll also need an OpenROAD build (`external/openroad/bin/openroad` after
building the submodule) since `gen_solver_patterns` is a built-in OpenROAD Tcl command.

## Usage

From the repo root:

```bash
external/openroad/bin/openroad -exit external/openroad-patterns/run_gen_patterns.tcl
```

The script resolves paths relative to its own location, so it also works
if invoked with a different working directory or an absolute path to
`openroad`.

## What it does

Equivalent to OpenROAD's own:

```tcl
gen_solver_patterns -process_file ../data/process -process_name TYP
```

(run from `external/openroad/src/rcx/calibration/fasterCap/scripts/`),
but with `-process_file` pointing at
`external/openroad/src/rcx/test/rcx_v2/FasterCapModel/data/process` explicitly,
and an explicit `-wire_cnt` (default 5).

`gen_solver_patterns` also accepts `-version`, `-len`, `-w_list`, `-s_list`,
`-over_dist`, and `-under_dist` if you need to control those as well —
none of these are currently set by the wrapper, so OpenROAD's own defaults
apply.

## Output

Generated patterns are saved wherever OpenROAD's `gen_solver_patterns` writes
them by default (under the submodule's calibration working directory). See OpenROAD's own
[calibration docs](https://openroad.readthedocs.io/en/latest/main/src/rcx/doc/calibration.html)
for the full pattern → FasterCap → extraction-rules flow this feeds into.