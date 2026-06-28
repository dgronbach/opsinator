"""
OPSINator DECIMER Engine - a small, standalone command-line program.

This is intentionally separate from the main OPSINator app. It does one
job: given an image path as its only argument, it loads DECIMER and
prints the predicted SMILES to stdout. Nothing else.

Why this is its own program instead of living inside the main app:
DECIMER pulls in TensorFlow, which is large and slow to load - on the
order of many seconds just for the dynamic linker to resolve shared
libraries across a huge bundled dependency tree. If that cost is paid
inside the main app's own startup path, the main window can't appear
until it's done - exactly the multi-second-to-much-longer launch delay
identified during testing.

By isolating it here, the main app launches instantly (no TensorFlow in
its own process at all) and only pays this cost on demand, once per
image recognized, in a separate process - the same way the Name tab
already treats OPSIN as an external thing it calls out to, not
something baked into its own startup.

Usage:
    opsinator_engine <path_to_image>

Output (stdout):
    A single line: the predicted SMILES string, or an empty line if
    recognition failed. Errors go to stderr, not stdout, so the caller
    can tell success from failure cleanly.
"""

import sys


def main():
    if len(sys.argv) != 2:
        print("Usage: opsinator_engine <path_to_image>", file=sys.stderr)
        sys.exit(2)

    image_path = sys.argv[1]

    try:
        # The slow import happens here, in this process, not in the
        # main app's process.
        from DECIMER import predict_SMILES
        smiles = predict_SMILES(image_path)
        print(smiles)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
