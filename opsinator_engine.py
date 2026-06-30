"""
OPSINator DECIMER Engine - a small, standalone command-line program.

Separate from the main OPSINator app on purpose: DECIMER pulls in
TensorFlow, which is large and slow to load. Isolating it here means the
main app launches instantly and only pays this cost on demand, in a
short-lived helper process, once per image.

Usage:
    opsinator_engine --download
        Downloads/updates the DECIMER model components, with resumable
        progress reporting. Idempotent - safe to run even if everything
        is already up to date (finishes almost instantly in that case).
        Prints "OPSINATOR_DOWNLOAD_COMPLETE" as its final line.

    opsinator_engine <path_to_image>
        Runs recognition. Requires the components to already be
        downloaded (see --download above) - does NOT download anything
        itself. Prints "OPSINATOR_RESULT:<smiles>" as its final line.

    opsinator_engine --version
        Prints the installed 'decimer' package version and exits.
        Does NOT import DECIMER (no TensorFlow load, no download) - fast
        and safe to call often, e.g. for update checks.

    opsinator_engine --rollback
        Restores the previous model version, if a backup exists.

    opsinator_engine --cleanup
        Deletes the backed-up previous model version.
"""

import importlib.metadata
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile

# The exact URLs DECIMER's own code uses internally, copied here so we
# can download them OURSELVES with resume support - DECIMER's own
# downloader (via the 'pystow' library) has no resume capability at
# all, and actively DELETES partial files if interrupted, guaranteeing
# a full restart every time. By fetching the same files ourselves and
# placing them exactly where DECIMER expects, DECIMER's own code finds
# everything already done and never re-downloads anything itself.
MODEL_URLS = {
    "DECIMER": "https://zenodo.org/record/8300489/files/models.zip",
    "DECIMER_HandDrawn": "https://zenodo.org/records/10781330/files/DECIMER_HandDrawn_model.zip",
}


def _status(message):
    # flush=True matters here: stdout to a pipe (not a real terminal) is
    # normally buffered, meaning the parent app wouldn't see this line
    # until much later, in a big batch, defeating the whole point of
    # live status updates. Flushing forces it out immediately.
    print(message, flush=True)


def _model_base_dir():
    """Returns the folder DECIMER stores its model in - respects
    PYSTOW_HOME if set (e.g. by a bundled, portable build), otherwise
    matches DECIMER's own default location exactly."""
    base = os.environ.get("PYSTOW_HOME")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".data")
    return os.path.join(base, "DECIMER-V2")


def _resumable_download(url, dest_path, label=""):
    """Downloads a file with resume support: if dest_path + '.part'
    already exists from a previous, interrupted attempt, picks up from
    where it left off using an HTTP Range request, instead of starting
    over from zero.

    If the server doesn't honor the Range request (some servers don't),
    this falls back to a full restart for that file - gracefully, not
    a crash - since we can't force a server to support something it
    doesn't.
    """
    part_path = dest_path + ".part"
    existing_size = os.path.getsize(part_path) if os.path.isfile(part_path) else 0

    req = urllib.request.Request(url)
    if existing_size > 0:
        req.add_header("Range", f"bytes={existing_size}-")

    with urllib.request.urlopen(req, timeout=30) as resp:
        # A server that doesn't support partial content ignores the
        # Range header and sends the WHOLE file with a normal 200
        # status (not 206 Partial Content) - in that case we must
        # discard what we had and start clean, or the file would be
        # corrupted by duplicating the beginning.
        resumed = existing_size > 0 and getattr(resp, "status", 200) == 206
        mode = "ab" if resumed else "wb"
        if not resumed:
            existing_size = 0

        content_length = resp.headers.get("Content-Length")
        total_size = (int(content_length) + existing_size) if content_length else None

        downloaded = existing_size
        last_reported_pct = -1
        chunk_size = 256 * 1024  # 256 KB per chunk

        with open(part_path, mode) as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total_size:
                    pct = int(downloaded * 100 / total_size)
                    if pct != last_reported_pct:
                        last_reported_pct = pct
                        mb_done = downloaded / (1024 * 1024)
                        mb_total = total_size / (1024 * 1024)
                        _status(f"Downloading {label}: {pct}% "
                                f"({mb_done:.1f} MB of {mb_total:.1f} MB)")

    os.replace(part_path, dest_path)


def ensure_models_resumable():
    """Makes sure both DECIMER models are present, downloading (with
    resume support) only whatever is actually missing or out of date.
    Mirrors DECIMER's own internal logic for deciding what counts as
    "needs downloading," so its own code sees everything already done
    and never tries to download anything itself afterward.
    """
    default_path = _model_base_dir()
    os.makedirs(default_path, exist_ok=True)

    for model_name, model_url in MODEL_URLS.items():
        model_path = os.path.join(default_path, f"{model_name}_model")
        saved_model_file = os.path.join(model_path, "saved_model.pb")
        version_file = os.path.join(model_path, ".model_url")

        needs_download = not os.path.isfile(saved_model_file)
        if not needs_download and os.path.isfile(version_file):
            with open(version_file, "r", encoding="utf-8") as f:
                cached_url = f.read().strip()
            if cached_url != model_url:
                needs_download = True

        if not needs_download:
            continue

        _status(f"Preparing {model_name} model...")

        if os.path.isdir(model_path):
            shutil.rmtree(model_path, ignore_errors=True)

        zip_filename = os.path.basename(model_url)
        zip_path = os.path.join(default_path, zip_filename)

        _resumable_download(model_url, zip_path, label=model_name)

        _status(f"Extracting {model_name} model...")
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            zip_ref.extractall(default_path)
        os.remove(zip_path)

        os.makedirs(model_path, exist_ok=True)
        with open(version_file, "w", encoding="utf-8") as f:
            f.write(model_url)

        _status(f"{model_name} model ready.")


def models_ready() -> bool:
    """Quick check, no downloading, no network call: are both models
    already fully present and matching the currently installed
    decimer package's expected URLs? Used to decide whether recognition
    can proceed, or whether the user needs to download first."""
    default_path = _model_base_dir()
    for model_name, model_url in MODEL_URLS.items():
        model_path = os.path.join(default_path, f"{model_name}_model")
        saved_model_file = os.path.join(model_path, "saved_model.pb")
        version_file = os.path.join(model_path, ".model_url")

        if not os.path.isfile(saved_model_file):
            return False
        if not os.path.isfile(version_file):
            return False
        with open(version_file, "r", encoding="utf-8") as f:
            cached_url = f.read().strip()
        if cached_url != model_url:
            return False
    return True


def _version_marker_path(model_dir):
    return os.path.join(model_dir, ".opsinator_model_version")


def _read_marker(model_dir):
    path = _version_marker_path(model_dir)
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    return None


def _write_marker(model_dir, version):
    try:
        with open(_version_marker_path(model_dir), "w", encoding="utf-8") as f:
            f.write(version)
    except Exception:
        pass


def _installed_decimer_version():
    try:
        return importlib.metadata.version("decimer")
    except importlib.metadata.PackageNotFoundError:
        return None


def backup_model_if_outdated():
    """If the model on disk was set up by a different decimer package
    version than what's installed now, back it up (keeping only ONE
    previous copy) before fetching a fresh one."""
    model_dir = _model_base_dir()
    if not os.path.isdir(model_dir):
        return

    current_version = _installed_decimer_version()
    recorded_version = _read_marker(model_dir)

    if current_version and recorded_version and current_version != recorded_version:
        previous_dir = model_dir + "-previous"
        if os.path.isdir(previous_dir):
            shutil.rmtree(previous_dir, ignore_errors=True)
        shutil.move(model_dir, previous_dir)
        _status(f"Backed up previous model version ({recorded_version}) "
                f"before fetching the new one ({current_version}).")


def rollback():
    model_dir = _model_base_dir()
    previous_dir = model_dir + "-previous"

    if not os.path.isdir(previous_dir):
        print("No previous model version available to roll back to.", file=sys.stderr)
        sys.exit(1)

    bad_dir = model_dir + "-rolledback"
    if os.path.isdir(model_dir):
        if os.path.isdir(bad_dir):
            shutil.rmtree(bad_dir, ignore_errors=True)
        shutil.move(model_dir, bad_dir)

    shutil.move(previous_dir, model_dir)
    print("Rolled back to the previous model version.")


def cleanup():
    model_dir = _model_base_dir()
    previous_dir = model_dir + "-previous"
    bad_dir = model_dir + "-rolledback"

    removed_any = False
    for d in (previous_dir, bad_dir):
        if os.path.isdir(d):
            shutil.rmtree(d, ignore_errors=True)
            removed_any = True

    print("Removed old model backup(s)." if removed_any else "No old model backups to remove.")


def print_version():
    version = _installed_decimer_version()
    print(version if version else "not-installed")
    if not version:
        sys.exit(1)


def ensure_decimer_installed():
    """Checks whether the 'decimer' package is importable by THIS
    Python interpreter, and installs it automatically via pip if not -
    so clicking Begin Download in the GUI needs no manual terminal
    commands, on any platform.

    In the FINAL, BUILT version of this app, decimer is already bundled
    in at build time, so this never actually does anything there - it
    only matters when running from raw source (development/testing) or
    as a defensive fallback.
    """
    if _installed_decimer_version() is not None:
        return  # already installed - nothing to do, instantly

    _status("Installing the 'decimer' package (includes TensorFlow, "
            "roughly 300-500 MB - this can take a while)...")

    # CONCEPT: calling pip as [sys.executable, "-m", "pip", ...] - a
    # plain list of separate arguments, not one shell command string -
    # works identically on Windows, macOS, and Linux. A shell string
    # like "python -m pip install X && echo done" would need different
    # syntax per OS; this form never touches a shell at all.
    base_cmd = [sys.executable, "-m", "pip", "install", "decimer"]

    def _try_install(cmd):
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        output_lines = []
        for line in process.stdout:
            line = line.rstrip("\n")
            if line:
                _status(line)
                output_lines.append(line)
        process.wait(timeout=1800)  # installing TensorFlow can genuinely take a while
        return process.returncode, "\n".join(output_lines)

    returncode, output = _try_install(base_cmd)

    # Some Linux distributions (Ubuntu 24.04 and newer, specifically)
    # mark their system Python as "externally managed" and refuse plain
    # pip installs outright, to protect OS-level packages. If that's
    # what just happened, retry with the explicit override flag for
    # exactly that situation - rather than failing outright.
    if returncode != 0 and "externally-managed-environment" in output:
        _status("Retrying install (this system protects its default Python "
                "environment by default)...")
        returncode, output = _try_install(base_cmd + ["--break-system-packages"])

    # CONCEPT: pip just ran as a SEPARATE process. This process's own
    # Python has already cached "what packages exist" from when it
    # started up, before the install happened - so checking again right
    # now, without refreshing that cache first, would incorrectly say
    # "still not found" even though it just succeeded a moment ago.
    # invalidate_caches() forces a fresh look instead of trusting the
    # stale, outdated answer.
    importlib.invalidate_caches()

    if returncode != 0 or _installed_decimer_version() is None:
        raise RuntimeError(
            "Failed to install the 'decimer' package automatically. "
            "Last output:\n" + output[-500:]
        )

    _status("'decimer' package installed successfully.")


def download_components():
    """Explicit, standalone download command - this is the ONLY place
    a model download is ever triggered from. Idempotent: if everything
    is already present and up to date, this finishes almost instantly
    with nothing to do, so it's always safe to click/run again."""
    try:
        ensure_decimer_installed()
        backup_model_if_outdated()
        ensure_models_resumable()
        version = _installed_decimer_version()
        if version:
            _write_marker(_model_base_dir(), version)
        print("OPSINATOR_DOWNLOAD_COMPLETE", flush=True)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def run_recognition(image_path):
    if not models_ready():
        print("ERROR: DECIMER components are not downloaded yet. "
              "Click 'Download DECIMER Components' first.", file=sys.stderr)
        sys.exit(1)
    try:
        ensure_decimer_installed()  # defensive - should already be done by --download
        from DECIMER import predict_SMILES
        smiles = predict_SMILES(image_path)
        print(f"OPSINATOR_RESULT:{smiles}", flush=True)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    if len(sys.argv) != 2:
        print("Usage: opsinator_engine <path_to_image> | --version | --rollback | --cleanup",
              file=sys.stderr)
        sys.exit(2)

    arg = sys.argv[1]
    if arg == "--version":
        print_version()
    elif arg == "--rollback":
        rollback()
    elif arg == "--cleanup":
        cleanup()
    elif arg == "--download":
        download_components()
    else:
        run_recognition(arg)


if __name__ == "__main__":
    main()
