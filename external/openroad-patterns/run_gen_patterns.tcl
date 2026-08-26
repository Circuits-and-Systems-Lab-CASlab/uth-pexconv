# run_gen_patterns.tcl
#
# Wrapper around OpenROAD's pattern generator (gen_solver_patterns), used to
# produce the DEF wire calibration patterns for FasterCap-based extraction
# rule generation.
#
# This does not fork or duplicate OpenROAD's own script 
# (src/rcx/calibration/fasterCap/scripts/gen_patterns.tcl). It calls the
# same underlying command, but resolves the process file path against
# src/rcx/test/rcx_v2/FasterCapModel/data/process in the UTH-pexconv repo
# layout, since OpenROAD lives here as a git submodule under external/openroad/.
#
# Usage (from anywhere; paths are resolved relative to this script):
#   external/openroad/bin/openroad -exit external/openroad-patterns/run_gen_patterns.tcl
#
# Prerequisite:
#   git submodule update --init --recursive

set script_dir     [file dirname [file normalize [info script]]]
set openroad_root  [file normalize [file join $script_dir .. openroad]]
set fastercap_dir  [file join $openroad_root src rcx test rcx_v2 FasterCapModel]
set process_file   [file join $fastercap_dir data process]

# Number of wires per generated pattern.
set wire_cnt 5

if {![file exists $process_file]} {
    puts stderr "ERROR: process file not found at:"
    puts stderr "  $process_file"
    puts stderr ""
    puts stderr "Did you run 'git submodule update --init --recursive'?"
    exit 1
}

# Equivalent of OpenROAD's own:
#   gen_solver_patterns -process_file ../data/process -process_name TYP
# just with -process_file pointing at
# external/openroad/src/rcx/test/rcx_v2/FasterCapModel/data/process
# instead, plus an explicit -wire_cnt (see gen_solver_patterns' full
# signature: -process_file, -process_name, -version, -wire_cnt, -len,
# -w_list, -s_list, -over_dist, -under_dist).
gen_solver_patterns -process_file $process_file -process_name TYP -wire_cnt $wire_cnt