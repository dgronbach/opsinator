"""
OPSINator Segmentation Engine - a small, standalone command-line program.

This is the THIRD separate program in OPSINator, alongside the main app
and the DECIMER recognition engine. It runs in its own Python 3.11
environment (DECIMER Segmentation requires an older TensorFlow version
that has no installable wheel for newer Python versions - confirmed
directly, not assumed).

Its one job: given a directory of rendered page images, find every
chemical structure drawing on each page and save each one as its own
cropped image file - so each crop can then be fed, separately, through
the existing DECIMER recognition engine to get a SMILES for it.

Usage:
    opsinator_segmentation <pages_directory> <output_directory>

Output (stdout):
    PAGE:<page_number>                         -- before processing each page
    CROP:<path>|<page_number>|<y0>,<x0>,<y1>,<x1>  -- for each structure found
"""

import importlib.metadata
import os
import re
import subprocess
import sys


def _status(message):
    print(message, flush=True)


def _ensure_segmentation_installed():
    """Installs decimer-segmentation automatically if it's missing
    (opencv-python comes along as one of its own dependencies, so it
    doesn't need a separate install step).

    IMPORTANT, honest limitation: this package requires Python 3.11 or
    older - there's no installable build for newer Python versions at
    all (confirmed directly). If this script is somehow being run under
    an incompatible Python, no amount of retrying will fix that - so we
    check for that specific case FIRST and give one clear, calm
    sentence explaining it, rather than letting pip fail with a long,
    confusing dependency-resolution error.
    """
    try:
        importlib.metadata.version("decimer-segmentation")
        return  # already installed
    except importlib.metadata.PackageNotFoundError:
        pass

    if sys.version_info >= (3, 12):
        raise RuntimeError(
            "Structure segmentation requires Python 3.11 or older - this "
            f"system is running Python {sys.version_info.major}.{sys.version_info.minor}, "
            "which has no compatible version available. This needs a separate "
            "Python 3.11 setup - ask your sysadmin to configure one."
        )

    _status("Installing 'decimer-segmentation' (this can take a while)...")

    process = subprocess.Popen(
        [sys.executable, "-m", "pip", "install", "decimer-segmentation"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    output_lines = []
    for line in process.stdout:
        line = line.rstrip("\n")
        if line:
            _status(line)
            output_lines.append(line)
    process.wait(timeout=1800)

    if process.returncode != 0 and "externally-managed-environment" in "\n".join(output_lines):
        _status("Retrying install (this system protects its default Python "
                "environment by default)...")
        process = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "decimer-segmentation", "--break-system-packages"],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
        for line in process.stdout:
            line = line.rstrip("\n")
            if line:
                _status(line)
        process.wait(timeout=1800)

    importlib.invalidate_caches()
    try:
        importlib.metadata.version("decimer-segmentation")
    except importlib.metadata.PackageNotFoundError:
        raise RuntimeError("Could not install 'decimer-segmentation' automatically.")


def _page_number_key(filename):
    """Sort key that orders page files by their trailing page number.
    Takes the LAST run of digits in the filename so that base names
    that themselves contain numbers don't interfere (e.g.
    'compound_42_page_3.png' → 3, not 423).
    """
    nums = re.findall(r'\d+', filename)
    return int(nums[-1]) if nums else 0


def main():
    if len(sys.argv) != 3:
        print("Usage: opsinator_segmentation <pages_directory> <output_directory>",
              file=sys.stderr)
        sys.exit(2)

    pages_dir = sys.argv[1]
    output_dir = sys.argv[2]
    os.makedirs(output_dir, exist_ok=True)

    try:
        _ensure_segmentation_installed()

        # This import is the expensive part for THIS engine (its own
        # TensorFlow load), same reasoning as the DECIMER engine - kept
        # out of the main app's process entirely.
        from decimer_segmentation import segment_chemical_structures
        import cv2

        image_extensions = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif"}
        page_files = sorted(
            [f for f in os.listdir(pages_dir)
             if os.path.splitext(f)[1].lower() in image_extensions],
            key=_page_number_key,
        )

        if not page_files:
            print(f"ERROR: no image files found in {pages_dir}", file=sys.stderr)
            sys.exit(1)

        for page_num, page_filename in enumerate(page_files, start=1):
            page_image_path = os.path.join(pages_dir, page_filename)
            print(f"PAGE:{page_num}", flush=True)

            image = cv2.imread(page_image_path)
            if image is None:
                print(f"ERROR: could not read image file {page_image_path}", file=sys.stderr)
                sys.exit(1)

            # return_bboxes=True also gives back each structure's exact
            # pixel position on the page - (y0, x0, y1, x1) - needed so
            # the main app can search the PDF's own text near that position
            # for a label (compound name/number).
            segments, bboxes = segment_chemical_structures(image, expand=True, return_bboxes=True)

            base_name = os.path.splitext(page_filename)[0]
            for i, (segment, bbox) in enumerate(zip(segments, bboxes), start=1):
                crop_path = os.path.join(output_dir, f"{base_name}_structure_{i}.png")
                cv2.imwrite(crop_path, segment)
                y0, x0, y1, x1 = bbox
                print(f"CROP:{crop_path}|{page_num}|{y0},{x0},{y1},{x1}", flush=True)

    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
