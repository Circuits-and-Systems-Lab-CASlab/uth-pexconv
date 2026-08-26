# Runs FasterCap on the FasterCap .lst input files produced by
# run_fastercap_conversion.py.
#
# Universal2FasterCapConverter.py writes its output using the same base
# filename as the input Universal Format file - "wires" - with a ".lst"
# extension. This script matches on that extension by default when given
# a folder; pass a file_extension if your converted files are named
# differently.
#
# Usage:
#     python3 run_fastercap_solver.py <fastercap_executable> [fastercap_file_or_folder] [file_extension] [--threads N]
#
# <fastercap_executable>     required; path to (or name of) the FasterCap
#                            executable to run, e.g. /opt/fastercap/FasterCap
# [fastercap_file_or_folder] optional; either a single .lst file to run
#                            FasterCap on directly, or a folder to walk.
#                            Defaults to ./output next to this script (same
#                            default as run_fastercap_conversion.py)
# [file_extension]          optional; only used when the file/folder argument
#                            is a folder. Defaults to "lst"
# [--threads N]             optional; sets OMP_NUM_THREADS=N for the
#                            FasterCap subprocess only (does not affect
#                            your shell's environment). FasterCap doesn't
#                            expose a thread-count CLI flag of its own;
#                            it's built with OpenMP, so this is the
#                            standard way to cap it. Can appear anywhere
#                            in the argument list. If omitted, FasterCap
#                            runs with whatever OMP_NUM_THREADS (if any)
#                            is already set in your shell - same as
#                            before this flag was added.
#
# NOTE: the FasterCap command-line flags below (-b -a1.0e-4) are:
#   -b        run as console/shell application, without the GUI (avoids
#             needing GUI shared libraries like libwx_baseu at all)
#   -a1.0e-4  placeholder accuracy setting


import sys
import os
import subprocess
import shutil

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_INPUT = os.path.join(SCRIPT_DIR, "output")
DEFAULT_EXTENSION = "lst"


def run_fastercap(filepath, executable, num_threads=None):
    file_dir = os.path.dirname(filepath)
    filename = os.path.basename(filepath)

    env = None
    if num_threads is not None:
        # Copy the parent environment and override just OMP_NUM_THREADS
        # for this subprocess - doesn't touch the calling shell's env.
        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = str(num_threads)

    # FasterCap reads/writes the panel files it references (Dielectrics/,
    # Wires/) relative to the current working directory, so run from the
    # folder containing the .lst file, same as run_raphael_fx.py does for
    # raphael_fx.
    result = subprocess.run(
        [executable, "-b", "-a1.0e-4", filename],
        cwd=file_dir,
        capture_output=True,
        text=True,
        env=env,
    )

    log_path = os.path.join(file_dir, os.path.splitext(filename)[0] + ".log")
    with open(log_path, "w") as log_file:
        thread_note = f" (OMP_NUM_THREADS={num_threads})" if num_threads is not None else ""
        log_file.write(f"Command: {executable} -b -a1.0e-4 {filename}{thread_note}\n")
        log_file.write(f"Exit code: {result.returncode}\n\n")
        log_file.write("--- stdout ---\n")
        log_file.write(result.stdout or "")
        log_file.write("\n--- stderr ---\n")
        log_file.write(result.stderr or "")

    return result, log_path


def main():
    raw_args = sys.argv[1:]

    # Pull --threads N out of the argument list, wherever it appears, so
    # positional argument parsing below stays unaffected by its position.
    num_threads = None
    if "--threads" in raw_args:
        idx = raw_args.index("--threads")
        try:
            num_threads = int(raw_args[idx + 1])
        except (IndexError, ValueError):
            print("ERROR: --threads requires an integer argument, e.g. --threads 4")
            sys.exit(1)
        del raw_args[idx:idx + 2]

    if len(raw_args) < 1:
        print("Usage: python3 run_fastercap.py <fastercap_executable> [fastercap_file_or_folder] [file_extension] [--threads N]")
        print("")
        print("<fastercap_executable>     required; path to (or name of) the FasterCap executable")
        print("[fastercap_file_or_folder] optional; defaults to ./output next to this script")
        print("[file_extension]          optional; defaults to 'lst' (only used for folders)")
        print("[--threads N]             optional; sets OMP_NUM_THREADS=N for FasterCap only")
        sys.exit(1)

    executable = raw_args[0]
    fastercap_input = raw_args[1] if len(raw_args) >= 2 else DEFAULT_INPUT
    extension = raw_args[2] if len(raw_args) >= 3 else DEFAULT_EXTENSION

    resolved_executable = shutil.which(executable)
    if resolved_executable is None:
        print(f"FasterCap executable not found: {executable}")
        print("Pass the full path if it isn't on your PATH.")
        sys.exit(1)
    executable = os.path.abspath(resolved_executable)

    if os.path.isfile(fastercap_input):
        target_files = [fastercap_input]
    elif os.path.isdir(fastercap_input):
        target_files = []
        for root, _, files in os.walk(fastercap_input):
            for f in files:
                if f.endswith(f".{extension}"):
                    target_files.append(os.path.join(root, f))

        if not target_files:
            print(f"No '.{extension}' files found under {fastercap_input}")
            sys.exit(1)
    else:
        print(f"FasterCap input file or folder not found: {fastercap_input}!")
        sys.exit(1)

    thread_note = f" with OMP_NUM_THREADS={num_threads}" if num_threads is not None else ""
    print(f"Running FasterCap ({executable}) on {len(target_files)} file(s){thread_note}")
    print("")

    failures = []
    for filepath in target_files:
        print(f"  {filepath}")
        result, log_path = run_fastercap(filepath, executable, num_threads)
        print(f"    log: {log_path}")
        if result.returncode != 0:
            failures.append(filepath)
            print(f"    FAILED (exit {result.returncode})")
            if result.stderr:
                print(f"    {result.stderr.strip()}")

    print("")
    if failures:
        print(f"Done: {len(failures)} of {len(target_files)} file(s) failed:")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)

    print(f"Done: FasterCap ran successfully on all {len(target_files)} file(s)")


if __name__ == "__main__":
    main()