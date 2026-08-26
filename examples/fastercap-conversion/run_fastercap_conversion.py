import sys
import os
import subprocess

# run_fastercap_conversion.py
#
# Example: convert a folder of Universal Format files into FasterCap
# input files using converters/fastercap/src/Universal2FasterCap.py.
#
# This assumes you already have Universal Format files (e.g. generated via
# external/openroad-patterns/, or your own). It does not generate patterns
# itself - it only demonstrates the conversion step.
#
# Unlike the Raphael converter, Universal2FasterCap.py needs a
# heights reference mode and a 2D/3D mode in addition to the input/output
# folders. See the converter's own usage string for the full argument
# list, including the optional simulation window extension arguments.
#
# Usage:
#     python3 run_fastercap_conversion.py <universal_base_folder> <heights_reference> <2D|3D> [fastercap_output_folder] [-sim_window_ext ...]
#
# <universal_base_folder>   folder containing Universal Format "wires" files
# <heights_reference>       "normalized" or "standard"
# <2D|3D>                   geometry mode
# [fastercap_output_folder] optional; if omitted, output goes to ./output
#                           next to this script
# [-sim_window_ext ...]     optional simulation window extension override;
#                           passed through unchanged to the converter (see
#                           the converter's usage string for the expected
#                           number of values for 2D vs 3D)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONVERTER = os.path.join(SCRIPT_DIR, "..", "..", "converters", "fastercap", "src", "Universal2FasterCap.py")
DEFAULT_OUTPUT = os.path.join(SCRIPT_DIR, "output")

def main():
    if len(sys.argv) < 4:
        print("Usage: python3 run_fastercap_conversion.py <universal_base_folder> <heights_reference> <2D|3D> [fastercap_output_folder] [-sim_window_ext ...]")
        print("")
        print("<universal_base_folder>   folder containing Universal Format 'wires' files")
        print("<heights_reference>       'normalized' or 'standard'")
        print("<2D|3D>                   geometry mode")
        print("[fastercap_output_folder] optional; defaults to ./output next to this script")
        print("[-sim_window_ext ...]     optional; passed through to the converter unchanged")
        sys.exit(1)

    universal_base = sys.argv[1]
    heights_reference = sys.argv[2]
    mode = sys.argv[3]

    remaining = sys.argv[4:]
    if remaining and not remaining[0].startswith("-"):
        fastercap_output = remaining[0]
        passthrough_args = remaining[1:]
    else:
        fastercap_output = DEFAULT_OUTPUT
        passthrough_args = remaining

    if not os.path.isdir(universal_base):
        print(f"Universal Format folder not found: {universal_base}")
        sys.exit(1)

    if heights_reference not in ("normalized", "standard"):
        print(f"Invalid heights_reference '{heights_reference}': expected 'normalized' or 'standard'")
        sys.exit(1)

    if mode not in ("2D", "3D"):
        print(f"Invalid mode '{mode}': expected '2D' or '3D'")
        sys.exit(1)

    if not os.path.isfile(CONVERTER):
        print(f"Converter script not found: {CONVERTER}")
        print("Expected it at converters/fastercap/src/Universal2FasterCap.py")
        sys.exit(1)

    os.makedirs(fastercap_output, exist_ok=True)

    print("Converting Universal Format files to FasterCap input files")
    print(f"  Input:             {universal_base}")
    print(f"  Output:            {fastercap_output}")
    print(f"  Heights reference: {heights_reference}")
    print(f"  Mode:              {mode}")
    if passthrough_args:
        print(f"  Extra args:        {' '.join(passthrough_args)}")
    print("")

    result = subprocess.run(
        [sys.executable, CONVERTER, universal_base, fastercap_output, heights_reference, mode] + passthrough_args,
        capture_output=True,
        text=True,
    )

    if result.stdout:
        print(result.stdout)

    if result.returncode != 0:
        print("Converter exited with an error:")
        if result.stderr:
            print(result.stderr)
        sys.exit(1)

    output_files = []
    for root, _, files in os.walk(fastercap_output):
        for f in files:
            output_files.append(os.path.join(root, f))

    print(f"Done - {len(output_files)} file(s) written to {fastercap_output}")


if __name__ == "__main__":
    main()