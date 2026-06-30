"""
================================================================================
 OPSINator - Batch Chemical Name & Image Converter
 Version: 1.4
================================================================================

WHAT THIS PROGRAM DOES
-----------------------
OPSINator has two independent "engines" living in one app:

  1. Name -> Structure, powered by OPSIN (a free web service run by the
     University of Cambridge / EMBL-EBI). You type or paste chemical
     names, and it looks up the corresponding chemical structure.

  2. Image -> Structure, powered by DECIMER (a deep-learning model from
     the Steinbeck Lab, Friedrich Schiller University Jena). You give it
     a picture of a drawn chemical structure, and it tries to figure out
     what molecule is drawn.

CREDITS
-------
  Code by:               Claude (Anthropic)
  Code review by:        Dave Gronbach
  Usage and output by:   Alex Rerick

SUPPORT
-------
This tool is provided WITHOUT any official support, warranty, or
guarantee that it will keep working in the future. It was built as an
internal convenience tool. If something breaks, the people listed above
may or may not be available to help - there is no formal support
contract behind this software.

# Send feedback to: email@someplace.com
# (Uncomment the line above and fill in a real address once you have one.
#  Until then, there is intentionally no feedback channel listed.)

LICENSING NOTE
---------------
OPSIN and DECIMER are both separate open-source projects, each under
their own MIT License. This program calls them but does not claim to
have written them. Full attribution and citation details are shown to
every user the first time they run this app (and any time afterward,
via Help > License & Attribution).


A NOTE FOR PYTHON LEARNERS READING THIS FILE
-----------------------------------------------
This file is intentionally commented more heavily than a typical
"real-world" program would be. The goal is that someone learning Python
could read top-to-bottom and pick up real patterns: functions, classes,
exception handling, threading, simple GUI programming with tkinter, and
working with files and the network. Comments that explain a *general*
Python or programming concept (rather than something specific to this
app) are marked with the word "CONCEPT:" so you can skim past them once
you already know the idea.
================================================================================
"""

# --------------------------------------------------------------------------
# IMPORTS
# --------------------------------------------------------------------------
# CONCEPT: In Python, "import" brings in code that someone else already
# wrote, so you don't have to write everything from scratch. The Python
# Standard Library (the stuff that comes built into Python itself, with
# nothing extra to install) includes modules for almost everything below.
# --------------------------------------------------------------------------

import csv                  # Reading and writing .csv (spreadsheet) files
import importlib.metadata   # Checking what's installed, and refreshing that after a pip install
import re                   # Pattern matching, used to pull "42%" out of status text
import shutil                # Deleting temporary folders (PDF scan scratch space)
import json                 # Converting between Python dictionaries and JSON text
import math                 # Trigonometry functions (sin, cos) used by the animation
import os                   # Talking to the operating system: file paths, folders, etc.
import queue                # A thread-safe "to-do list" used to pass messages between threads
import subprocess           # Launching the separate DECIMER and Segmentation engine programs
import sys                  # Information about how this program is being run
import tempfile             # Creating scratch folders for rendered PDF pages and crops
import threading            # Lets us run code in the background, without freezing the GUI
import tkinter as tk        # tkinter is Python's built-in GUI (graphical window) toolkit
import urllib.error         # Specific error types that can happen when fetching a URL
import urllib.parse         # Helpers for safely building URLs out of text
import urllib.request       # Lets Python make HTTP requests to web servers

# tkinterdnd2 adds drag-and-drop support, which plain tkinter doesn't
# have at all. It's an optional third-party package - if it isn't
# installed for some reason, the app still works fine; the drop zone
# just won't accept drags, and the Choose Image/Choose PDF buttons
# remain the way to get a file in either way.
try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND_AVAILABLE = True
except ImportError:
    _DND_AVAILABLE = False
from tkinter import filedialog, messagebox, ttk
# filedialog = "Open file" / "Save file" pop-up windows
# messagebox = simple pop-up boxes like "Are you sure?" or "Error!"
# ttk        = "themed tkinter" - nicer-looking versions of some tkinter widgets

# --------------------------------------------------------------------------
# VERSION
# --------------------------------------------------------------------------
# CONCEPT: It's good practice to keep a single "source of truth" for your
# program's version number, rather than typing "1.4" in five different
# places. Other parts of the code (and the About dialog) read this
# constant instead of repeating the literal text.
# --------------------------------------------------------------------------
__version__ = "1.4"

# A short, plain-language reminder that this tool comes with no formal
# support contract. Shown in the About dialog and the Help text.
SUPPORT_DISCLAIMER = (
    "This tool is provided as-is, without any official support or warranty. "
    "There is no guaranteed response time or fix schedule if something breaks."
)


# --------------------------------------------------------------------------
# PORTABILITY: finding a bundled DECIMER model, if one was packaged in
# --------------------------------------------------------------------------
# CONCEPT: A regular ".py" file you run with `python myfile.py` behaves
# differently from a compiled ".exe" made by a tool like PyInstaller.
# PyInstaller can bundle extra files alongside your code; at runtime, it
# unpacks them into a temporary folder and tells your program where that
# folder is via `sys._MEIPASS`. The `getattr(sys, "frozen", False)` check
# below is the standard way to ask "am I running as a compiled exe, or as
# a plain Python script?"
# --------------------------------------------------------------------------
def _configure_bundled_model_path():
    """If a model cache was bundled alongside this exe at build time, point
    the 'pystow' library (which DECIMER uses internally) at that bundled
    folder BEFORE DECIMER is ever imported. That way, DECIMER finds the
    model files already present and skips downloading them again - which
    is what keeps a built exe fully portable (copy it anywhere, run it,
    no first-run wait on a brand-new machine).
    """
    # `getattr(obj, "name", default)` looks for an attribute called "name"
    # on `obj`, and returns `default` instead of crashing if it doesn't
    # exist. This is the safe way to check for something that may or may
    # not be there.
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running as a PyInstaller-built exe: bundled files live here.
        bundle_root = sys._MEIPASS
    else:
        # Running as a plain .py script: "bundled" files (if any) would
        # simply sit in the same folder as this script.
        bundle_root = os.path.dirname(os.path.abspath(__file__))

    bundled_data_dir = os.path.join(bundle_root, "decimer_data")

    # os.path.isdir checks whether that folder actually exists on disk.
    if os.path.isdir(bundled_data_dir):
        # Setting an environment variable here changes it only for THIS
        # running program (and anything it starts), not for the whole
        # computer. pystow specifically checks for PYSTOW_HOME at import
        # time to decide where to look for / store its data.
        os.environ["PYSTOW_HOME"] = bundled_data_dir


# Run this check once, immediately, before any other code in this file
# runs - that's why the function call sits here at the top level instead
# of inside main().
_configure_bundled_model_path()


# ============================================================
# Licensing, attribution, and first-run acknowledgment
# ============================================================
# CONCEPT: A "constant" in Python is just a regular variable that, by
# convention, we write in ALL_CAPS to signal "please don't change this
# while the program is running." Python doesn't actually enforce this -
# it's a human convention, not a rule the language checks for you.
# ============================================================

# os.path.expanduser("~") turns "~" into the user's actual home folder,
# e.g. C:\Users\dave.gronbach on Windows. We store a small marker file
# there to remember "this user already agreed to the license," so we
# don't pester them with the same dialog every single time they open
# the app.
LICENSE_DIR = os.path.join(os.path.expanduser("~"), ".data", "OPSINator")
LICENSE_FLAG_PATH = os.path.join(LICENSE_DIR, "license_accepted.flag")

# CONCEPT: Triple-quoted strings ("""...""") can span many lines. This is
# the standard way in Python to store a big block of plain text (like an
# essay, or in this case, legal/attribution text) as a single value.
ATTRIBUTION_TEXT = """OPSINator uses two independent open-source chemistry engines.
Neither is created by, or affiliated with, the authors of this app.

------------------------------------------------------------
NAME -> STRUCTURE: OPSIN
------------------------------------------------------------
OPSIN (Open Parser for Systematic IUPAC Nomenclature) is developed
by Daniel Lowe and the University of Cambridge, hosted by EMBL-EBI.

License: MIT License
Source: https://github.com/dan2097/opsin
Web service: https://opsin.ch.cam.ac.uk

Citation:
Lowe, D. M., Corbett, P. T., Murray-Rust, P., & Glen, R. C. (2011).
Chemical Name to Structure: OPSIN, an Open Source Solution.
J. Chem. Inf. Model., 51(3), 739-753.

This app sends chemical names you provide to OPSIN's public web
service over the internet to retrieve structures. No other data is
sent.

------------------------------------------------------------
IMAGE -> STRUCTURE: DECIMER
------------------------------------------------------------
DECIMER (Deep lEarning for Chemical IMagE Recognition) is developed
by the Steinbeck Lab, Friedrich Schiller University Jena, Germany.

License: MIT License
Source: https://github.com/Kohulan/DECIMER-Image_Transformer

Citation:
Rajan, K., Brinkhaus, H. O., Agea, M. I., Zielesny, A., & Steinbeck, C.
(2023). DECIMER.ai: an open platform for automated optical chemical
structure identification, segmentation and recognition in scientific
publications. Nat. Commun. 14, 5045.

This component runs locally on your machine. The first time it is
used, a trained model (roughly 1-2 GB, or already bundled with this
build) is required. No image you process is sent anywhere over the
network by this component.

------------------------------------------------------------
A NOTE ON USE
------------------------------------------------------------
Both tools are provided "as is" by their original authors, with no
warranty of accuracy. Always verify results before relying on them
for scientific, regulatory, or legal purposes. You are responsible
for ensuring your use of any input material (e.g. images from
patents or publications) complies with applicable copyright and
licensing terms.

This OPSINator application itself is also provided as-is, without
official support or warranty (see Help > About for details).

By clicking "I Accept and Continue" below, you acknowledge the above
and agree to use this app and its underlying engines accordingly.
This notice will not be shown again on this computer.
"""

HELP_TEXT = """HOW TO USE OPSINATOR
====================

NAME -> STRUCTURE tab
----------------------
1. Paste chemical names, one per line, into the box (up to 200 at a
   time).
2. Click "Convert Names".
3. Results appear in the table below as they come back: Status,
   SMILES, InChIKey, and Message (an explanation when something
   fails or is flagged).
4. Click "Save CSV" to export everything as a spreadsheet, or
   "Save MOL" / "Save SDF" to export real structure files for
   chemistry software (select a row first for "Save MOL").

What to expect:
 - Most well-formed IUPAC names resolve in well under a second each.
 - Non-systematic or misspelled names will return FAILURE/ERROR -
   check the Message column for why.
 - This requires an internet connection (OPSIN is a remote service).

IMAGE -> STRUCTURE tab
------------------------
1. Click "Choose Image..." and select an image of a drawn chemical
   structure (PNG/JPG/BMP/GIF).
2. Click "Recognize Structure".
3. The first time this is ever used, you will see "Configuring image
   recognition engine - please wait" while required components load.
   This can take a while depending on your connection and whether a
   model was bundled with this build. After that, it is fast.
4. Recognized structures accumulate in a list for this session. Use
   "Save CSV" or "Save SDF" to export everything you've recognized.

What to expect:
 - Works best on clean, clearly drawn single structures.
 - Hand-drawn, low-resolution, or heavily annotated images (common in
   older patents) may produce a less accurate or incorrect result -
   always visually check the prediction against the source image.
 - This component runs locally; no internet connection is required
   once the model is available on your machine.

IF SOMETHING GOES WRONG
-------------------------
 - "Network error" on the Name tab: check your internet connection;
   OPSIN's public service may also occasionally be slow or briefly
   unavailable.
 - A name returns FAILURE/ERROR: read the Message column - it is
   usually a parsing explanation from OPSIN itself, not a bug.
 - Image recognition fails to load: check Help > Check for Updates,
   and confirm with whoever built this exe that the bundled model
   (if any) was included correctly.
 - The app does not open, or closes immediately: re-run from a normal
   Command Prompt (not double-click) to see any error text, and pass
   that along to whoever maintains this tool internally.

SUPPORT
-------
This tool comes with no official support or warranty. See Help >
About for the support disclaimer.

CREDITS
-------
Code by: Claude
Code review by: Dave Gronbach
Usage and output by: Alex Rerick

See Help > License & Attribution for full credit to the OPSIN and
DECIMER projects, whose work makes this tool possible.
"""


def is_license_accepted():
    """Returns True if the license-acceptance marker file already exists
    on this computer (meaning the user clicked Accept on a previous run).

    CONCEPT: A function that returns True or False, with no side effects,
    is sometimes called a "predicate." Naming it starting with "is_"
    (is_license_accepted) is a common convention that makes it obvious,
    just from the name, that it answers a yes/no question.
    """
    return os.path.isfile(LICENSE_FLAG_PATH)


# A separate flag, same pattern as the license one, for whether the user
# has opted in to DECIMER's large download. Kept distinct from license
# acceptance on purpose - accepting the license is not the same thing as
# agreeing to a multi-GB download, and shouldn't be bundled together.
DECIMER_ENABLED_FLAG_PATH = os.path.join(LICENSE_DIR, "decimer_enabled.flag")


def is_decimer_enabled():
    return os.path.isfile(DECIMER_ENABLED_FLAG_PATH)


def _decimer_components_present() -> bool:
    """Returns True only when both DECIMER model directories contain a
    saved_model.pb, meaning the download completed successfully.
    Mirrors the same path logic used by opsinator_engine.py so the check
    reflects the actual on-disk state, not just whether a button was clicked.
    """
    base = os.environ.get("PYSTOW_HOME") or os.path.join(os.path.expanduser("~"), ".data")
    model_base = os.path.join(base, "DECIMER-V2")
    for model_name in ("DECIMER", "DECIMER_HandDrawn"):
        pb = os.path.join(model_base, f"{model_name}_model", "saved_model.pb")
        if not os.path.isfile(pb):
            return False
    return True


def mark_decimer_enabled():
    try:
        os.makedirs(LICENSE_DIR, exist_ok=True)
        with open(DECIMER_ENABLED_FLAG_PATH, "w", encoding="utf-8") as f:
            f.write("enabled")
    except Exception:
        pass


def mark_decimer_disabled():
    try:
        if os.path.isfile(DECIMER_ENABLED_FLAG_PATH):
            os.remove(DECIMER_ENABLED_FLAG_PATH)
    except Exception:
        pass


# A small settings file for things worth remembering between runs that
# AREN'T a one-time yes/no choice (like the flags above) - right now,
# just the last folder the user picked a file from or saved one to.
SETTINGS_PATH = os.path.join(LICENSE_DIR, "settings.json")


def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(settings: dict):
    try:
        os.makedirs(LICENSE_DIR, exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f)
    except Exception:
        pass  # not critical - worst case, it just doesn't remember next time



def mark_license_accepted():
    """Writes a small marker file to remember that the user has accepted
    the license, so we never show the dialog again on this machine.
    """
    try:
        # CONCEPT: os.makedirs(..., exist_ok=True) creates a folder (and
        # any missing parent folders) - but if the folder already exists,
        # exist_ok=True means "don't treat that as an error."
        os.makedirs(LICENSE_DIR, exist_ok=True)

        # CONCEPT: `with open(...) as f:` is called a "context manager."
        # It automatically closes the file for you when the indented
        # block finishes, even if something goes wrong inside it. This is
        # the standard, safe way to work with files in Python.
        with open(LICENSE_FLAG_PATH, "w", encoding="utf-8") as f:
            f.write("accepted")
    except Exception:
        # CONCEPT: `except Exception:` catches essentially any error that
        # could happen in the "try" block above (e.g. no permission to
        # write that folder). We deliberately do nothing here, because
        # the worst-case outcome (the dialog reappears next time) is mild
        # and not worth crashing the whole app over.
        pass  # non-fatal - worst case the notice reappears next launch


def show_license_dialog(root, on_accept, on_decline):
    """Shows the first-run License & Attribution window. The user must
    tick the checkbox before "I Accept and Continue" becomes clickable.

    Parameters:
        root: the main tkinter window this dialog belongs to.
        on_accept: a function to call if the user accepts.
        on_decline: a function to call if the user declines or closes
                    the window.

    CONCEPT: Passing functions as arguments (on_accept, on_decline) is a
    very common pattern in GUI programming, sometimes called a
    "callback." Instead of this function deciding what happens next, it
    just calls whichever function was handed to it - which means the
    same dialog code can be reused for different situations.
    """
    # tk.Toplevel creates a new, separate window on top of the main one -
    # as opposed to tk.Frame, which creates an area *inside* an existing
    # window.
    dialog = tk.Toplevel(root)
    dialog.title("License & Attribution - OPSINator")
    dialog.geometry("620x560")   # width x height, in pixels

    # NOTE: we deliberately do NOT call dialog.transient(root) here.
    # root is withdrawn (hidden) at this point in the program, and on
    # some Linux window managers, marking a window "transient for" a
    # parent that was never actually shown can prevent the window from
    # displaying at all, even though Tk reports no error.

    # `grab_set()` makes this dialog "modal" - the user can't click on
    # the main window behind it until this dialog is closed.
    dialog.grab_set()

    # Force this window to actually appear on top and take focus,
    # rather than relying on the window manager's default behavior.
    dialog.update_idletasks()
    dialog.deiconify()
    dialog.lift()
    dialog.attributes("-topmost", True)
    dialog.after(200, lambda: dialog.attributes("-topmost", False))
    dialog.focus_force()

    # If the user clicks the window's [X] close button, treat that the
    # same as clicking "Decline and Exit".
    dialog.protocol("WM_DELETE_WINDOW", on_decline)

    tk.Label(dialog, text="Before you continue", font=("Segoe UI", 13, "bold")).pack(pady=(14, 4))

    # A scrollable read-only text box to show the (fairly long)
    # attribution text without needing a huge window.
    text_frame = tk.Frame(dialog)
    text_frame.pack(fill="both", expand=True, padx=14, pady=6)
    text_widget = tk.Text(text_frame, wrap="word", font=("Segoe UI", 9))
    vsb = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
    text_widget.configure(yscrollcommand=vsb.set)
    text_widget.insert("1.0", ATTRIBUTION_TEXT)  # "1.0" means "line 1, character 0"
    text_widget.config(state="disabled")          # read-only: user can scroll but not edit
    text_widget.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    # CONCEPT: tk.BooleanVar is a special tkinter "variable wrapper" that
    # GUI widgets (like checkboxes) can watch and update automatically.
    # Plain Python variables don't have this two-way connection to the
    # GUI, which is why tkinter has its own variable types.
    accepted_var = tk.BooleanVar(value=False)

    bottom = tk.Frame(dialog)
    bottom.pack(fill="x", padx=14, pady=(4, 14))

    # CONCEPT: `lambda: ...` creates a tiny, unnamed function inline. It's
    # shorthand for situations where writing a full `def my_function():`
    # would feel like overkill for something this small. Here, clicking
    # the button needs to do three things in a row (save acceptance,
    # close this dialog, then run whatever was passed in as on_accept) -
    # the lambda bundles all three into one callable.
    accept_btn = tk.Button(bottom, text="I Accept and Continue", state="disabled",
                            command=lambda: (mark_license_accepted(), dialog.destroy(), on_accept()))
    accept_btn.pack(side="right")

    def on_check():
        # Enable the Accept button only once the checkbox is ticked.
        accept_btn.config(state="normal" if accepted_var.get() else "disabled")

    chk = tk.Checkbutton(bottom, text="I have read and accept the above",
                          variable=accepted_var, command=on_check)
    chk.pack(side="left")

    decline_btn = tk.Button(bottom, text="Decline and Exit", command=on_decline)
    decline_btn.pack(side="left", padx=(10, 0))


def show_help_dialog(root):
    """Shows a simple, read-only 'how to use this app' window. Can be
    opened any time from Help > How to use OPSINator."""
    dialog = tk.Toplevel(root)
    dialog.title("Help - OPSINator")
    dialog.geometry("640x600")
    dialog.transient(root)

    text_frame = tk.Frame(dialog)
    text_frame.pack(fill="both", expand=True, padx=12, pady=12)
    text_widget = tk.Text(text_frame, wrap="word", font=("Segoe UI", 9))
    vsb = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
    text_widget.configure(yscrollcommand=vsb.set)
    text_widget.insert("1.0", HELP_TEXT)
    text_widget.config(state="disabled")
    text_widget.pack(side="left", fill="both", expand=True)
    vsb.pack(side="right", fill="y")

    tk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=(0, 12))


# --------------------------------------------------------------------------
# Configuration constants used by the OPSIN (name -> structure) engine
# --------------------------------------------------------------------------
OPSIN_BASE = "https://opsin.ch.cam.ac.uk/opsin/"  # base web address for every lookup
MAX_NAMES = 200          # the most names we'll process in a single batch
TIMEOUT_SECONDS = 20     # give up waiting on a single name after this many seconds

PYPI_DECIMER_URL = "https://pypi.org/pypi/decimer/json"  # used for the update check


# ============================================================
# Patent activity table extraction (name -> OPSIN pipeline)
# ============================================================

# --- Extensible name-cleaning pipeline ---
# Each rule is a module-level function: (name: str) -> (cleaned: str, meta: dict)
# meta keys: salt_form, stereo_note, handling_notes (list).
# Rules are applied in order; each receives the output of the previous rule.
# To add a new rule: define a function here and append it to CLEANING_PIPELINE.

def _rule_strip_diast_annotations(name):
    meta = {}
    m = re.search(r'\b(DIAST-\d+)\b', name, re.IGNORECASE)
    if m:
        meta['stereo_note'] = m.group(1)
    name = re.sub(r',?\s*\[From DIAST-\d+ of precursor[^\]]*\]', '', name, flags=re.IGNORECASE)
    name = re.sub(r',?\s*DIAST-\d+', '', name).rstrip(',').strip()
    return name, meta

def _rule_strip_footnote_refs(name):
    # Complete reference: "(see footnote X in Table Y)" — strip exactly
    name = re.sub(r',?\s*\(see footnote \d+ in Table \d+[)\]]', '', name)
    # Incomplete/embedded: closing "Y)" was in a separately-filtered PDF fragment,
    # or the footnote text has embedded garbage following it.  Strip everything from
    # "(see footnote" to the end of the string — this marker NEVER appears inside a
    # valid IUPAC name and always terminates the cell content.
    name = re.sub(r',?\s*\(see footnote\b.*$', '', name, flags=re.DOTALL).rstrip(',').strip()
    return name, {}

def _rule_strip_trailing_garbage(name):
    """Truncate at table-footnote / patent-claims markers that may bleed in."""
    m = re.search(r'\s*[,;]?\s*1\.\s+Values represent\b', name, re.IGNORECASE)
    if m:
        name = name[:m.start()].rstrip(',').strip()
    m = re.search(r'\bCLAIMS\b|\bWHAT IS CLAIMED IS\b', name)
    if m:
        name = name[:m.start()].rstrip(',').strip()
    return name, {}

def _rule_strip_salt_forms(name):
    """Strip trailing or leading salt descriptors; record them in metadata."""
    meta = {}
    m = re.search(
        r',?\s*((?:trifluoroacetate|hydrochloride|formate|acetate|mesylate|tosylate)'
        r'(?:\s+salt)?)\s*$',
        name, re.IGNORECASE,
    )
    if m:
        meta['salt_form'] = m.group(1).strip()
        name = name[:m.start()].rstrip(',').strip()
    elif re.match(r'^ammonium\s+', name, re.IGNORECASE):
        meta['salt_form'] = 'ammonium'
        name = re.sub(r'^ammonium\s+', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\bcarboxylate\b', 'carboxylic acid', name)
        name = re.sub(r'\bbenzoate\b',    'benzoic acid',    name)
    return name, meta

def _rule_normalize_n_locants(name):
    """Fix OCR-mangled superscript N-locants: JVn → Nn (e.g. JV2 → N2)."""
    meta = {}
    if re.search(r'\bJV\d+\b', name):
        meta['handling_notes'] = ['N-locant OCR corrected (JVn→Nn)']
        name = re.sub(r'\bJV(\d+)\b', r'N\1', name)
    return name, meta

def _rule_fix_spacing_artifacts(name):
    """Collapse PDF text-extraction spacing artifacts in chemical names."""
    name = re.sub(r'-\s+(?=[a-zA-Z0-9({[])', '-', name)                    # propan-2- yl → propan-2-yl
    name = re.sub(r'\bd\s+icarboxamide\b', 'dicarboxamide', name)           # d icarboxamide → dicarboxamide
    name = re.sub(r'\btetrahyd\s+roquinoline\b', 'tetrahydroquinoline', name, flags=re.IGNORECASE)  # tetrahyd roquinoline
    name = re.sub(r"(\d+'?)\s+,", r'\1,', name)                             # 2' ,5' → 2',5'
    name = re.sub(r',\s+(\d)', r',\1', name)                                # 5,6, 7 ,8 → 5,6,7,8
    name = re.sub(r'\s+\]', ']', name)                                      # amino ] → amino]
    name = re.sub(r'\s+', ' ', name).strip()
    return name, {}

CLEANING_PIPELINE = [
    _rule_strip_diast_annotations,
    _rule_strip_footnote_refs,
    _rule_strip_trailing_garbage,
    _rule_strip_salt_forms,
    _rule_normalize_n_locants,
    _rule_fix_spacing_artifacts,
]

def _apply_cleaning_pipeline(raw_name):
    """Apply all cleaning rules in sequence. Returns (clean_name, metadata_dict)."""
    name = raw_name
    combined = {}
    for rule_fn in CLEANING_PIPELINE:
        name, meta = rule_fn(name)
        for k, v in meta.items():
            if k == 'handling_notes':
                combined.setdefault('handling_notes', []).extend(v)
            else:
                combined[k] = v
    return name, combined


def parse_activity_table(pdf_path):
    """Extract Table 3 rows from a Pfizer patent PDF that has an embedded text layer.

    Returns a list of record dicts (may be more than one per PDF row for 'or' pairs):
      example        – integer example number
      example_suffix – '' normally; 'a'/'b' for stereoisomer 'or' pairs
      ic50           – IC50 string as read from PDF
      rep            – replicate count string
      name           – raw compound name as extracted (both halves for 'or' pairs)
      clean_name     – name ready for OPSIN (annotations stripped, artifacts fixed)
      smiles         – filled in by caller after OPSIN conversion
      status         – 'pending' until caller sets it
      message        – OPSIN message (filled by caller)
      page           – 1-based source page number
      salt_form      – extracted salt descriptor (e.g. 'ammonium', 'trifluoroacetate')
      stereo_note    – extracted DIAST stereo annotation
      handling_notes – list of transformations applied
      data_fields    – extensible dict; currently holds IC50_nM and n_replicates
    """
    import fitz  # PyMuPDF - imported locally to match existing pattern in this file

    TABLE_FIRST = 235   # 0-indexed page number of the first table data page
    TABLE_LAST  = 270   # stop scanning well past the end of Table 3

    ENTRY_RE = re.compile(
        r'^(\d{1,4}(?:\s+\d)?)\s*\n'   # Example number, optional space-separated footnote
        r'([\d.>]+)\s*\n'               # IC50 value (numeric, may have > prefix)
        r'(\d{1,2})\s*\n'               # replicate count
        r'(.*)',                          # start of compound name
        re.DOTALL
    )

    # PyMuPDF occasionally merges a right-column name prefix into the same block
    # as the left-column entry header, producing text ordered as:
    #   <name-prefix-lines>\n<NUM>\n<IC50>\n<REP>\n<name-suffix>
    # ENTRY_RE cannot match this because the block does not start with a digit.
    # This regex detects the embedded entry and reconstructs the correct order.
    EMBEDDED_ENTRY_RE = re.compile(
        r'^(.+?)\n'                       # name prefix (one or more lines, non-greedy)
        r'(\d{1,4}(?:\s+\d)?)\s*\n'     # example number
        r'([\d.>]+)\s*\n'               # IC50 value
        r'(\d{1,2})\s*\n'              # replicate count
        r'(.*)',                         # name suffix / continuation
        re.DOTALL
    )

    doc = fitz.open(pdf_path)
    all_items = []
    table_found = False
    table_done  = False
    header_skip = True  # ignore column-header fragments until the first entry block

    for pidx in range(TABLE_FIRST, min(TABLE_LAST, len(doc))):
        if table_done:
            break
        page = doc[pidx]
        for b in sorted(page.get_text("blocks"), key=lambda b: b[1]):
            x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
            text = text.strip()
            if not text:
                continue
            if 'WO 2024' in text or 'PCT' in text:
                continue
            if re.match(r'^\d{2,3}$', text) and y0 > 700:
                continue  # standalone page-number footer

            if not table_found:
                if 'Table 3.' in text or 'Table 3 ' in text:
                    table_found = True
                continue

            # End-of-table: footnote section immediately after the last entry
            if re.match(r'^1\.\s+Values represent\b', text, re.IGNORECASE):
                table_done = True
                break

            sk = pidx * 100000 + y0

            if x0 < 130:
                m = ENTRY_RE.match(text)
                if m:
                    header_skip = False
                    is_or = m.group(4).strip().lower() == 'or'
                    all_items.append({
                        'type': 'entry',
                        'ex_raw': m.group(1).strip(),
                        'ic50': m.group(2).strip(),
                        'rep': m.group(3).strip(),
                        'name_start': m.group(4).strip(),
                        'is_or_entry': is_or,
                        'page': pidx + 1,
                        'sk': sk,
                    })
                    continue
                em = EMBEDDED_ENTRY_RE.match(text)
                if em:
                    # Reconstruct: name = prefix + suffix (entry header was in the middle)
                    prefix = em.group(1).strip()
                    suffix = em.group(5).strip()
                    name_start = (prefix + suffix) if prefix.endswith('-') \
                                 else (prefix + ' ' + suffix).strip()
                    header_skip = False
                    all_items.append({
                        'type': 'entry',
                        'ex_raw': em.group(2).strip(),
                        'ic50': em.group(3).strip(),
                        'rep': em.group(4).strip(),
                        'name_start': name_start,
                        'is_or_entry': name_start.strip().lower() == 'or',
                        'page': pidx + 1,
                        'sk': sk,
                    })
                    continue

            if header_skip and x0 < 250:
                continue  # skip column-header fragments; name prefixes (x≥250) still captured

            # Skip standalone connector words and dangling bracket closers from footnotes
            if re.match(r'^(or|and|nor|of)$', text, re.IGNORECASE):
                continue
            if re.match(r'^\d*[)\]]$', text):
                continue

            all_items.append({'type': 'frag', 'text': text, 'page': pidx + 1, 'sk': sk})

    doc.close()
    if not all_items:
        return []

    entries = [i for i in all_items if i['type'] == 'entry']
    frags   = [i for i in all_items if i['type'] == 'frag']

    # Resolve example numbers; footnotes appear either concatenated ("12" = Ex1+fn2)
    # or space-separated ("11 2" = Ex11+fn2). Use sequence continuity to tell apart.
    last_ex = 0
    for e in entries:
        raw = e['ex_raw']
        m = re.match(r'^(\d+)\s+\d+$', raw)
        if m:
            ex = int(m.group(1))
        else:
            n = int(raw)
            if n > last_ex + 5 and len(raw) >= 2:
                cand = int(raw[:-1])
                ex = cand if 0 < cand <= 999 and cand > last_ex else n
            else:
                ex = n
        e['ex_num'] = ex
        e['name_parts'] = [e['name_start']] if e['name_start'] else []
        last_ex = ex

    # Assign each fragment to the nearest entry by sort-key proximity.
    # Special case for "or" entries: their second-isomer name fragments extend
    # toward the next entry but still belong to the "or" entry. Keep them there
    # unless the fragment is multi-line (= a full sub-name prefixing the next entry)
    # or is ≥2× closer to the next entry than to the "or" entry.
    for frag in frags:
        fk = frag['sk']
        prev = next_e = None
        for e in entries:
            if e['sk'] < fk:
                prev = e
            elif next_e is None and e['sk'] > fk:
                next_e = e
                break
        if next_e is None:
            if prev:
                prev['name_parts'].append(frag['text'])
        elif prev is None:
            next_e['name_parts'].insert(0, frag['text'])
        else:
            if prev.get('is_or_entry') and '\n' not in frag['text']:
                dist_prev = fk - prev['sk']
                dist_next = next_e['sk'] - fk
                if dist_next >= dist_prev / 2:
                    prev['name_parts'].append(frag['text'])
                    continue
            if (next_e['sk'] - fk) < (fk - prev['sk']):
                next_e['name_parts'].insert(0, frag['text'])
            else:
                prev['name_parts'].append(frag['text'])

    results = []
    for e in entries:
        parts = [p for p in e['name_parts'] if p]
        raw_name = ''
        for part in parts:
            # No space after a trailing hyphen: line-break artifact in chemical names
            if raw_name and raw_name[-1] == '-':
                raw_name += part.lstrip()
            elif raw_name:
                raw_name += ' ' + part
            else:
                raw_name = part
        raw_name = re.sub(r'\s+', ' ', raw_name).strip()

        clean, meta = _apply_cleaning_pipeline(raw_name)

        def _make_record(ex_num, suffix, cname, rname, e, meta):
            return {
                'example':        ex_num,
                'example_suffix': suffix,
                'ic50':           e['ic50'],
                'rep':            e['rep'],
                'name':           rname,
                'clean_name':     cname,
                'smiles':         '',
                'status':         'pending',
                'message':        '',
                'page':           e['page'],
                'salt_form':      meta.get('salt_form', ''),
                'stereo_note':    meta.get('stereo_note', ''),
                'handling_notes': list(meta.get('handling_notes', [])),
                'data_fields':    {'IC50_nM': e['ic50'], 'n_replicates': e['rep']},
            }

        # "or" stereoisomer pairs: split into a/b records (one per isomer)
        if e.get('is_or_entry') and ' or ' in clean:
            halves = clean.split(' or ', 1)
            for suffix, half in zip(('a', 'b'), halves):
                rec = _make_record(e['ex_num'], suffix, half.strip(), raw_name, e, meta)
                rec['handling_notes'].insert(0, 'or-pair split')
                results.append(rec)
        else:
            results.append(_make_record(e['ex_num'], '', clean, raw_name, e, meta))

    return results


# ============================================================
# OPSIN (name -> structure)
# ============================================================

def fetch_opsin(name: str) -> dict:
    """Asks OPSIN's public web service to convert one chemical name into
    a structure. Returns a dictionary describing what happened - this
    function never raises an exception itself; any error becomes part of
    the returned dictionary instead, so the calling code never has to
    worry about catching errors from this function.

    CONCEPT: `name: str` and `-> dict` are "type hints." They don't
    change how the code runs (Python doesn't enforce them), but they
    document, right in the function signature, what kind of value goes
    in and what kind comes out - which helps both human readers and
    some code-editing tools.
    """
    # urllib.parse.quote() makes a string safe to put inside a URL by
    # converting special characters (spaces, parentheses, etc.) into
    # their "percent-encoded" form, e.g. a space becomes %20.
    encoded = urllib.parse.quote(name, safe="")
    url = OPSIN_BASE + encoded + ".json"

    try:
        # Building a Request object lets us attach a custom header
        # (User-Agent) so the server can see which program is calling it.
        req = urllib.request.Request(url, headers={"User-Agent": "OPSINator/1.0"})

        # urllib.request.urlopen() actually sends the HTTP request and
        # waits for a response. Using it as `with ... as resp:` means the
        # network connection gets closed automatically afterward.
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            # The response comes back as raw bytes; .decode("utf-8")
            # turns those bytes into a normal Python text string, and
            # json.loads() turns that JSON text into a Python dictionary.
            data = json.loads(resp.read().decode("utf-8"))

        # CONCEPT: dict.get("key", default) looks up a key in a
        # dictionary, but instead of crashing if the key is missing, it
        # returns whatever "default" you provide. This is safer than
        # data["key"] when you're not 100% sure the key will be there.
        return {
            "name": name,
            "status": data.get("status", "UNKNOWN"),
            "smiles": data.get("smiles", ""),
            "inchikey": data.get("stdinchikey", ""),
            "message": data.get("message", ""),
        }

    except urllib.error.HTTPError as e:
        # OPSIN returns 404 when it cannot parse the input as a chemical
        # name - that's its normal "not found" response, not a real
        # internet error.  Never surface raw HTTP codes to the user.
        if e.code == 404:
            msg = "Not a recognized chemical name"
        else:
            msg = "OPSIN service error — try again shortly"
        return {"name": name, "status": "ERROR", "smiles": "", "inchikey": "",
                 "message": msg}

    except urllib.error.URLError as e:
        # We couldn't even reach the server at all - e.g. no internet
        # connection, DNS failure, or the server is completely down.
        return {"name": name, "status": "ERROR", "smiles": "", "inchikey": "",
                 "message": f"Network error: {e.reason}"}

    except Exception as e:
        # A catch-all for anything else unexpected (e.g. the response
        # wasn't valid JSON). `str(e)` turns the exception into readable
        # text we can show the user.
        return {"name": name, "status": "ERROR", "smiles": "", "inchikey": "",
                 "message": str(e)}


_SMILES_BRACKET  = re.compile(r'\[(?:[0-9]+)?[A-Za-z][^\]]*\]')  # [nH] [NH+] [13C] [3H]
_SMILES_AROMATIC = re.compile(r'[cnosp][0-9]')                   # c1 n1 aromatic ring-closure
_SMILES_BOND     = re.compile(r'\S=\S|\S#[A-Za-z0-9]')           # C=C C#N (= and # never in IUPAC)


def _looks_like_smiles(text: str) -> bool:
    """Conservative check: returns True only when the text contains
    patterns that are unambiguous SMILES and essentially never appear
    in legitimate IUPAC chemical names.

    Bracket atoms like [nH]/[NH+]/[13C], aromatic ring-closure digits
    (c1, n1), and bond characters = / # are all reliable SMILES
    signals.  IUPAC bridged-ring descriptors like [2.2.2] are NOT
    matched because the bracket pattern requires a letter after the
    optional isotope number."""
    t = text.strip()
    return bool(
        _SMILES_BRACKET.search(t)
        or _SMILES_AROMATIC.search(t)
        or _SMILES_BOND.search(t)
    )


def rotate_point(px, py, angle_deg, cx, cy):
    """Rotates the point (px, py) by angle_deg degrees around the pivot
    point (cx, cy), and returns the new (x, y) location.

    This is plain 2D rotation math (the kind taught in trigonometry):
    we first measure the point's position relative to the pivot (dx, dy),
    rotate that offset using sine and cosine, then add the pivot position
    back on at the end. It's used purely to animate the tilting test
    tubes in the little cartoon scientist below - there's no chemistry
    meaning here, just geometry.
    """
    # math.radians() converts degrees (the units humans usually think in)
    # into radians (the units math.sin/math.cos expect).
    angle = math.radians(angle_deg)
    dx, dy = px - cx, py - cy
    rx = dx * math.cos(angle) - dy * math.sin(angle)
    ry = dx * math.sin(angle) + dy * math.cos(angle)
    return cx + rx, cy + ry


class ScientistAnimation:
    """Draws and animates a small cartoon scientist pouring between two
    test tubes on a tkinter Canvas, to give the user something fun and
    informative to look at while a batch of names is being processed.

    CONCEPT: A "class" is a blueprint for creating objects that bundle
    together both data (here, the Canvas widget and a timer value `t`)
    and behavior (functions that act on that data, called "methods").
    Each time you write `ScientistAnimation(some_canvas)`, Python creates
    one fresh object following this blueprint - that object is called an
    "instance" of the class.
    """

    def __init__(self, canvas: tk.Canvas):
        # CONCEPT: __init__ is a special method automatically called the
        # moment a new instance is created. `self` refers to "this
        # particular instance" - it's how a method reaches the data that
        # belongs to one specific object, rather than the class in
        # general. Every method on a class takes `self` as its first
        # parameter (Python passes it in automatically; you never type it
        # yourself when calling the method).
        self.canvas = canvas
        self.t = 0.0  # an internal "clock" that drives the pouring motion

    def tick(self):
        """Advances the animation by one small step and redraws it.
        Call this repeatedly (e.g. every 80 milliseconds) to make it
        appear to move."""
        self.t += 0.18
        self._draw(self.t)

    def idle_frame(self, caption="Ready"):
        """Draws the scientist standing still, with a custom caption
        underneath (e.g. 'Ready' or 'Finished')."""
        self._draw(0.0, idle=True, idle_caption=caption)

    def _draw(self, t, idle=False, idle_caption="Ready"):
        # CONCEPT: a method name starting with a single underscore (like
        # _draw) is a Python convention meaning "this is an internal
        # implementation detail - other code shouldn't call it directly."
        # Python doesn't actually block you from calling it, it's just a
        # politeness signal between programmers.
        c = self.canvas
        c.delete("all")  # erase everything drawn on the canvas before redrawing

        cx, cy = 60, 95   # the scientist's rough body center, in canvas pixels
        skin = "#f2c9a0"
        coat = "#ffffff"
        outline = "#3a3a3a"
        glass = "#cfd8dc"
        liquid_a = "#3e8ed0"
        liquid_b = "#3aa66b"

        if idle:
            # Resting pose: tubes tilted slightly, liquid roughly settled.
            angle_l, angle_r = -8, 8
            frac_l, frac_r = 0.55, 0.45
        else:
            # Active pose: the tubes swing back and forth using a sine
            # wave, which naturally oscillates smoothly between -1 and 1.
            swing = 22 * math.sin(t)
            angle_l = -10 + swing
            angle_r = 10 - swing
            frac_l = 0.5 + 0.35 * math.sin(t)
            frac_r = 1.0 - frac_l

        # --- body (a simple oval standing in for a lab coat) ---
        c.create_oval(cx - 16, cy - 10, cx + 16, cy + 50, fill=coat, outline=outline, width=2)

        # --- bald head, with glasses and a small smile ---
        head_cy = cy - 28
        c.create_oval(cx - 14, head_cy - 14, cx + 14, head_cy + 14, fill=skin, outline=outline, width=2)
        c.create_oval(cx - 6, head_cy - 9, cx, head_cy - 5, fill="#ffe3c4", outline="")  # head "shine"
        c.create_oval(cx - 11, head_cy - 1, cx - 1, head_cy + 7, outline=outline, width=2)   # left lens
        c.create_oval(cx + 1, head_cy - 1, cx + 11, head_cy + 7, outline=outline, width=2)   # right lens
        c.create_line(cx - 1, head_cy + 2, cx + 1, head_cy + 2, fill=outline, width=2)        # bridge
        c.create_arc(cx - 6, head_cy + 4, cx + 6, head_cy + 12, start=200, extent=140,
                     style="arc", outline=outline, width=2)  # smile

        # --- two test tubes (left and right), each rotated by its own angle ---
        # CONCEPT: this for-loop iterates over a small tuple of tuples, so
        # the exact same drawing code runs twice (once per side) instead
        # of being duplicated. `side` is -1 or +1 to mirror left vs right.
        for side, angle, frac, liquid in (
            (-1, angle_l, frac_l, liquid_a),
            (1, angle_r, frac_r, liquid_b),
        ):
            hand_x = cx + side * 26
            hand_y = cy + 8
            tube_w = 10
            tube_h = 34

            # Define the tube's four corners as if it were standing
            # perfectly upright (no rotation yet)...
            top_l = (hand_x - tube_w / 2, hand_y - tube_h)
            top_r = (hand_x + tube_w / 2, hand_y - tube_h)
            bot_l = (hand_x - tube_w / 2, hand_y)
            bot_r = (hand_x + tube_w / 2, hand_y)

            pts = [top_l, top_r, bot_r, bot_l]
            # ...then rotate every corner around the "hand" pivot point,
            # using the rotate_point() helper defined above. This list
            # comprehension is shorthand for: "build a new list by
            # applying rotate_point to every (px, py) pair in pts."
            rotated = [rotate_point(px, py, angle, hand_x, hand_y) for px, py in pts]

            # The liquid is just a shorter rectangle sitting at the
            # bottom of the tube, sized by `frac` (the fraction full),
            # rotated the same way as the tube itself.
            liquid_top_y = hand_y - tube_h * frac
            liq_pts = [
                (hand_x - tube_w / 2, liquid_top_y),
                (hand_x + tube_w / 2, liquid_top_y),
                (hand_x + tube_w / 2, hand_y),
                (hand_x - tube_w / 2, hand_y),
            ]
            liq_rotated = [rotate_point(px, py, angle, hand_x, hand_y) for px, py in liq_pts]

            # The arm is just a line from the shoulder to the tube.
            shoulder_x = cx + side * 14
            shoulder_y = cy + 2
            c.create_line(shoulder_x, shoulder_y, hand_x, hand_y, fill=skin, width=6, capstyle="round")

            # tkinter's create_polygon wants one flat list of numbers
            # (x1, y1, x2, y2, ...) rather than a list of (x, y) pairs, so
            # this nested comprehension flattens our list of pairs.
            flat = [coord for pt in liq_rotated for coord in pt]
            c.create_polygon(flat, fill=liquid, outline="")

            flat_tube = [coord for pt in rotated for coord in pt]
            c.create_polygon(flat_tube, fill="", outline=glass, width=2)

        # --- a small caption underneath, so it doesn't feel frozen ---
        if idle:
            caption = idle_caption
        else:
            msgs = ["Parsing nomenclature...", "Querying OPSIN...", "Retrieving structure...", "Validating result..."]
            # int(t) % len(msgs) cycles through the four messages in
            # order as `t` (our animation clock) keeps increasing.
            caption = msgs[int(t) % len(msgs)]
        c.create_text(60, 148, text=caption, font=("Segoe UI", 8), fill="#666666")


# ============================================================
# DECIMER (image -> structure) - lazy-loaded, heavy dependency
# ============================================================

def _is_harmless_startup_noise(line: str) -> bool:
    """TensorFlow (and the GPU libraries it tries to use) print a
    predictable set of harmless diagnostic lines on every startup, on
    every machine without an NVIDIA GPU - things like 'could not find
    cuda drivers' and 'TF-TRT Warning'. None of this indicates an actual
    problem; it's just TensorFlow announcing it's running in CPU-only
    mode, which is expected and fine. Filtering these out means a real
    error, if one occurs, isn't buried under - or mistaken for - this
    routine noise.
    """
    noise_markers = (
        "tensorflow/", "external/local_", "cuda", "cudnn", "cufft", "cublas",
        "tf-trt", "cpu_feature_guard", "onednn", "could not find cuda drivers",
        # The AVX2/FMA line is a continuation printed WITHOUT a "tensorflow/" prefix,
        # so it needs its own marker.  "absl::" catches the absl log-init warning.
        "avx", "absl::", "rebuild tensorflow",
    )
    lowered = line.lower()
    return any(marker in lowered for marker in noise_markers)


class DecimerEngine:
    """Talks to a SEPARATE program (the 'OPSINator DECIMER Engine') rather
    than importing DECIMER directly into this process.

    Why: DECIMER pulls in TensorFlow, which is large and slow to load -
    testing showed this can meaningfully delay a window even appearing,
    because the cost is paid the moment it's imported. By running it as
    a separate executable instead, that cost is paid in a short-lived
    helper process, on demand, once per image - never blocking this
    app's own startup or its window from appearing immediately.

    This mirrors how the Name -> Structure tab already treats OPSIN: as
    an external thing this app calls out to, not something baked into
    its own process.
    """

    def __init__(self):
        self.load_error = None
        self.dev_mode_missing = False  # True only when running from source, not built yet
        self._engine_path = self._find_engine_executable()
        if self._engine_path is None:
            if getattr(sys, "frozen", False):
                # This IS a real problem - we're a built app, and a file
                # that should have been installed alongside us isn't.
                self.load_error = (
                    "Could not find the OPSINator DECIMER Engine executable. "
                    "It should be installed alongside this app."
                )
            else:
                # This is EXPECTED, not a problem - we're running the raw
                # .py source directly, before any build has produced a
                # compiled opsinator_engine to sit next to it.
                self.dev_mode_missing = True

    def _find_engine_executable(self):
        """Looks for something runnable in the same folder as this app:
        first a real compiled executable (the normal case once this app
        has actually been built), and if that's not there, a plain
        opsinator_engine.py sitting alongside it instead - so the app
        works directly during development, without needing a build or
        a manual shim script first.

        Sets self._invoke_prefix to the extra command-line piece needed
        to run whatever was found: empty for a real executable (it runs
        itself), or [sys.executable] for a plain .py file (which needs
        "python3 opsinator_engine.py ..." rather than being run directly).
        """
        if getattr(sys, "frozen", False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        compiled_candidates = [
            os.path.join(app_dir, "opsinator_engine.exe"),   # Windows
            os.path.join(app_dir, "opsinator_engine"),         # Linux / macOS
        ]
        for path in compiled_candidates:
            if os.path.isfile(path):
                self._invoke_prefix = []
                return path

        # No compiled engine yet - fall back to running the plain source
        # file directly with this same Python interpreter, IF it's
        # actually sitting there and DECIMER is importable by this
        # interpreter. This is what lets the GUI work end-to-end during
        # development with no manual setup beyond "pip install decimer".
        source_fallback = os.path.join(app_dir, "opsinator_engine.py")
        if os.path.isfile(source_fallback):
            self._invoke_prefix = [sys.executable]
            return source_fallback

        self._invoke_prefix = []
        return None

    def is_loaded(self):
        # There's no "loading" step anymore in this process - the engine
        # is a separate program we just call each time. We report
        # "loaded" as soon as we've confirmed the executable exists, so
        # the rest of the app's logic (which expects this method) still
        # behaves sensibly.
        return self._engine_path is not None and self.load_error is None

    def ensure_loaded(self, status_callback=None):
        # Nothing to lazily import anymore - the only thing to check is
        # whether the engine executable was found, which already
        # happened in __init__. This method still exists so the calling
        # code (written for the old in-process design) doesn't need to
        # change at all.
        if status_callback and self.is_loaded():
            status_callback("Ready.")

    def predict(self, image_path: str, status_callback=None) -> str:
        """Runs image recognition by launching the separate engine
        program as a subprocess, reading its output LINE BY LINE as it's
        produced (rather than waiting silently for it to finish).

        status_callback, if provided, is called with each line of
        output that ISN'T the final result - this is how DECIMER's own
        progress messages (e.g. "Downloading trained model to ...",
        printed during a first-run model download) reach the GUI live,
        instead of the user staring at an unchanging "please wait" for
        however long that download takes.
        """
        if self._engine_path is None:
            raise RuntimeError(self.load_error or "DECIMER engine not found")

        # CONCEPT: subprocess.Popen() (unlike subprocess.run()) doesn't
        # wait for the program to finish before handing control back -
        # it gives us a live handle to the still-running process, so we
        # can read its output as it arrives, line by line, in real time.
        #
        # stderr=subprocess.STDOUT merges both streams into one. This
        # matters more than it might look: reading only stdout while
        # stderr fills up UNREAD in its own pipe can deadlock the whole
        # thing outright once that pipe's buffer is full - the child
        # process blocks trying to write more, while we're blocked
        # waiting for output that will now never arrive. TensorFlow
        # writes a lot to stderr on startup, so this isn't a theoretical
        # risk - merging the streams removes it completely.
        process = subprocess.Popen(
            [*self._invoke_prefix, self._engine_path, image_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,  # line-buffered: hand us each line as soon as it's printed
        )

        result_smiles = None
        result_prefix = "OPSINATOR_RESULT:"
        other_lines = []

        # Read every line as it's produced. This loop ends naturally
        # once the engine process closes its output (i.e. when it
        # finishes), without us needing to poll or sleep.
        for line in process.stdout:
            line = line.rstrip("\n")
            if line.startswith(result_prefix):
                result_smiles = line[len(result_prefix):]
            elif line and not _is_harmless_startup_noise(line):
                other_lines.append(line)
                if status_callback:
                    status_callback(line)

        process.wait(timeout=300)  # generous ceiling - first-run model download can be slow

        if process.returncode != 0 or result_smiles is None:
            error_text = "\n".join(other_lines[-10:]) or "Unknown error from DECIMER engine"
            raise RuntimeError(error_text)

        return result_smiles.strip()


class SegmentationEngine:
    """Talks to a SEPARATE program (the 'OPSINator Segmentation Engine'),
    the same way DecimerEngine talks to the recognition engine.

    Why this is its own program: DECIMER Segmentation needs an OLDER
    TensorFlow version than the recognition engine does, and that older
    TensorFlow has no installable wheel at all for the Python version
    this app itself runs on (confirmed directly, not assumed) - so it
    genuinely cannot live in the same Python environment as anything
    else in OPSINator. It needs its own separate Python 3.11 setup,
    packaged as its own separate executable.
    """

    def __init__(self):
        self.load_error = None
        self.dev_mode_missing = False
        self._engine_path = self._find_engine_executable()
        if self._engine_path is None:
            if getattr(sys, "frozen", False):
                self.load_error = (
                    "Could not find the OPSINator Segmentation Engine executable. "
                    "It should be installed alongside this app."
                )
            else:
                self.dev_mode_missing = True

    def _find_engine_executable(self):
        if getattr(sys, "frozen", False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        compiled_candidates = [
            os.path.join(app_dir, "opsinator_segmentation.exe"),
            os.path.join(app_dir, "opsinator_segmentation"),
        ]
        for path in compiled_candidates:
            if os.path.isfile(path):
                self._invoke_prefix = []
                return path

        # Same .py fallback idea as DecimerEngine - BUT with an honest
        # limit: Segmentation needs an older Python (3.11) than this
        # app itself runs on, confirmed directly earlier.
        source_fallback = os.path.join(app_dir, "opsinator_segmentation.py")
        if os.path.isfile(source_fallback):
            self._invoke_prefix = [self._find_compatible_python()]
            return source_fallback

        self._invoke_prefix = []
        return None

    def _find_compatible_python(self):
        """Looks for a Python interpreter that can actually run
        Segmentation, automatically - no manual setup needed at launch
        time. Checks, in order: an explicit override (for anyone who
        wants to point at something unusual), a few common local
        locations where a compatible environment is typically set up
        during development/testing, and only then falls back to this
        app's own interpreter (which will likely be incompatible,
        producing the clear Python-version error rather than failing
        silently)."""
        override = os.environ.get("OPSINATOR_SEGMENTATION_PYTHON")
        if override and os.path.isfile(override):
            return override

        common_candidates = [
            os.path.join(os.path.expanduser("~"), "opsinator_segmentation_env", "bin", "python3"),
            os.path.join(os.path.expanduser("~"), "opsinator_segmentation_env", "Scripts", "python.exe"),
        ]
        for candidate in common_candidates:
            if os.path.isfile(candidate):
                return candidate

        return sys.executable

    def is_loaded(self):
        return self._engine_path is not None and self.load_error is None

    def find_all_structures(self, pages_dir: str, output_dir: str, total_pages: int,
                             status_callback=None, on_structure_found=None) -> list:
        """Runs page segmentation ONCE for an entire folder of rendered
        pages - not once per page - so TensorFlow and the model only
        ever load a single time, no matter how many pages the document
        has. Streams live "page N of M" progress back as it works
        through them, rather than going silent until everything's done.

        on_structure_found: optional callable(dict) called immediately
        for each structure as it is found (background thread), where the
        dict is {"page": int, "crop_path": str, "bbox": tuple}.

        Returns a list of all found structure dicts (same objects passed
        to on_structure_found, if provided).
        """
        if self._engine_path is None:
            raise RuntimeError(self.load_error or "Segmentation engine not found")

        # stderr=subprocess.STDOUT merges both streams into one pipe -
        # same reasoning as DecimerEngine.predict(): reading only stdout
        # while a separate stderr pipe fills up unread (TensorFlow is
        # genuinely verbose on stderr at startup) can deadlock the whole
        # call outright, not just produce confusing output.
        process = subprocess.Popen(
            [*self._invoke_prefix, self._engine_path, pages_dir, output_dir],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        found = []
        other_lines = []
        for line in process.stdout:
            line = line.rstrip("\n")
            if line.startswith("PAGE:"):
                pass  # page counter suppressed; status label holds "Scanning for structures" throughout
            elif line.startswith("CROP:"):
                rest = line[len("CROP:"):].strip()
                crop_path, _, remainder = rest.partition("|")
                page_text, _, bbox_text = remainder.partition("|")
                try:
                    page_num = int(page_text)
                    bbox = tuple(int(n) for n in bbox_text.split(","))
                except ValueError:
                    page_num, bbox = 0, None
                structure = {"page": page_num, "crop_path": crop_path, "bbox": bbox}
                found.append(structure)
                if on_structure_found:
                    on_structure_found(structure)
            elif line and not _is_harmless_startup_noise(line):
                other_lines.append(line)

        # A whole document, processed in one run, genuinely needs a
        # generous ceiling - the model load alone can take a while, and
        # each page after that takes real CPU time too on a machine
        # with no GPU. An hour is a deliberately high ceiling, not a
        # guess at the "right" duration.
        process.wait(timeout=3600)

        if process.returncode != 0:
            error_text = "\n".join(other_lines[-10:]) or "Unknown error from Segmentation engine"
            raise RuntimeError(error_text)

        return found


def sanitize_filename(text: str, max_length: int = 60) -> str:
    """Turns arbitrary text (a chemical name, which can contain all
    sorts of punctuation) into something safe to use as a filename on
    Windows, macOS, and Linux alike - replacing anything that any of
    those operating systems would reject, and trimming overly long names."""
    safe = re.sub(r'[<>:"/\\|?*]', "_", text).strip()
    safe = safe or "structure"
    return safe[:max_length]


def ask_save_scope(root, item_count):
    """Shows a small dialog asking whether to save just the currently
    selected row, or every result at once. Returns "selected", "all",
    or None if the user closed the dialog without choosing.

    A plain yes/no messagebox isn't expressive enough for this choice
    (the two options aren't naturally "yes" and "no"), so this builds a
    minimal custom dialog with clearly labeled buttons instead.
    """
    choice = {"value": None}

    dialog = tk.Toplevel(root)
    dialog.title("Save MOL")
    dialog.resizable(False, False)
    dialog.grab_set()

    tk.Label(
        dialog,
        text=f"Save just the selected row, or all {item_count} result(s)?\n\n"
             "A MOL file holds exactly one structure, so saving all results "
             "creates one separate file per structure in a folder you choose.",
        justify="left", wraplength=360, padx=16, pady=12,
    ).pack()

    btn_row = tk.Frame(dialog)
    btn_row.pack(pady=(0, 12))

    def pick(value):
        choice["value"] = value
        dialog.destroy()

    tk.Button(btn_row, text="Save Selected Row", width=16,
              command=lambda: pick("selected")).pack(side="left", padx=6)
    tk.Button(btn_row, text=f"Save All {item_count} as Separate Files", width=26,
              command=lambda: pick("all")).pack(side="left", padx=6)
    tk.Button(btn_row, text="Cancel", width=10,
              command=lambda: pick(None)).pack(side="left", padx=6)

    dialog.update_idletasks()
    dialog.deiconify()
    dialog.lift()
    dialog.attributes("-topmost", True)
    dialog.after(200, lambda: dialog.attributes("-topmost", False))
    dialog.focus_force()

    root.wait_window(dialog)  # blocks here until the dialog is closed
    return choice["value"]


def render_pdf_pages_to_images(pdf_path: str, output_dir: str, dpi: int = 200,
                                status_callback=None) -> list:
    """Renders every page of a PDF to its own PNG image file, using
    PyMuPDF (imported as 'fitz', its internal module name - the package
    name on PyPI is 'pymupdf'). Returns a list of the saved image file
    paths, one per page, in page order.

    This runs directly in the main app's own process - PyMuPDF is light
    (tens of MB, no TensorFlow involved), unlike the recognition and
    segmentation engines, which is why it doesn't need to be split out
    into a separate program the way those did.
    """
    try:
        import fitz
    except ImportError:
        if not ensure_package_installed("pymupdf", status_callback=status_callback):
            raise RuntimeError("Could not install PyMuPDF (needed to read PDF files) automatically.")
        import fitz

    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    image_paths = []
    zoom = dpi / 72  # PDF coordinates are in 72-DPI points by convention

    doc = fitz.open(pdf_path)
    try:
        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            image_path = os.path.join(output_dir, f"{base_name}_page_{page_index + 1}.png")
            pix.save(image_path)
            image_paths.append(image_path)
    finally:
        doc.close()

    return image_paths


def find_label_near_bbox(pdf_path: str, page_index: int, bbox_pixels, dpi: int = 200,
                          page_image_path: str = None) -> str:
    """Looks for a text label (a compound name or number) printed near a
    structure's position on the page.

    Tries the PDF's own text layer first (fast, exact). Falls back to
    OCR via pytesseract on the rendered page PNG when the text layer is
    empty (e.g. scanned/image-only PDFs - the common case for patents).

    bbox_pixels is (y0, x0, y1, x1) in the pixel coordinate system used
    when the page was rendered at the given dpi.

    Returns the found text, or "No label" if nothing turned up nearby.
    """
    if not bbox_pixels:
        return "No label"

    try:
        import fitz
    except ImportError:
        if not ensure_package_installed("pymupdf"):
            return "No label"
        import fitz

    zoom = dpi / 72
    y0, x0, y1, x1 = bbox_pixels
    # Convert pixel coordinates back to the PDF's own point coordinates.
    px0, py0, px1, py1 = x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom

    doc = fitz.open(pdf_path)
    try:
        page = doc.load_page(page_index)

        # Checked in this order based on two different REAL examples
        # from an actual patent: a compound's name is often printed
        # directly ABOVE its structure (e.g. an "Intermediate Example"
        # heading), while a short Roman-numeral label in a reaction
        # scheme sits BESIDE its structure instead. BELOW is checked
        # too, but last and most cautiously - that's exactly where a
        # paragraph of unrelated procedure text is also likely to start
        # (confirmed directly: real procedure text sits there in the
        # same document), so a match there needs to look genuinely
        # label-shaped, not just be "the nearest text downward."
        #
        # The window heights here (22pt) are deliberately short -
        # roughly one typeset line - specifically so a multi-line
        # paragraph mostly falls OUTSIDE the search area in the first
        # place, rather than relying only on the length check below.
        search_rects = [
            fitz.Rect(px0 - 10, py0 - 22, px1 + 10, py0),       # above
            fitz.Rect(px1, py0 - 5, px1 + 50, py1 + 5),         # right
            fitz.Rect(px0 - 50, py0 - 5, px0, py1 + 5),         # left
            fitz.Rect(px0 - 10, py1, px1 + 10, py1 + 22),       # below
        ]

        for rect in search_rects:
            raw = page.get_text("text", clip=rect).strip()
            if not raw:
                continue

            # A real label is essentially one line, even if that line
            # itself is long (IUPAC names can be lengthy). Multiple
            # internal line breaks is the signature of wrapped
            # paragraph prose spilling into the search area, not a
            # genuine single label - skip it and try the next direction
            # rather than returning a misleading snippet of someone
            # else's sentence.
            if raw.count("\n") > 1:
                continue

            text = " ".join(raw.split())
            if text:
                return text[:150]
    finally:
        doc.close()

    # PDF text layer found nothing (image-only PDF). Try OCR on the
    # rendered page PNG if we have it.
    if page_image_path and os.path.isfile(page_image_path):
        ocr_label = _ocr_label_near_bbox(page_image_path, bbox_pixels)
        if ocr_label:
            return ocr_label

    return "No label"


def _ocr_label_near_bbox(page_image_path: str, bbox_pixels) -> str:
    """Crops search regions around a structure's bbox in a rendered page
    PNG and runs tesseract OCR on each, returning the first plausible
    single-line label found, or an empty string if nothing was found."""
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return ""

    try:
        img = Image.open(page_image_path)
        iw, ih = img.size
        y0, x0, y1, x1 = bbox_pixels
        pad = 8

        # Same direction order as the PDF text-layer search: above,
        # right, left, below. Pixel crop windows are proportionally
        # deeper than the pt windows above because rendered PNGs are at
        # 200 DPI vs the 72-pt PDF coordinate space.
        regions = [
            (max(0, x0 - pad), max(0, y0 - 90), min(iw, x1 + pad), max(0, y0 - pad)),   # above
            (min(iw, x1 + pad), max(0, y0 - pad), min(iw, x1 + 200), min(ih, y1 + pad)), # right
            (max(0, x0 - 200), max(0, y0 - pad), max(0, x0 - pad), min(ih, y1 + pad)),   # left
            (max(0, x0 - pad), min(ih, y1 + pad), min(iw, x1 + pad), min(ih, y1 + 90)), # below
        ]

        for left, top, right, bottom in regions:
            if right <= left or bottom <= top:
                continue
            crop = img.crop((left, top, right, bottom))
            # PSM 7 = single text line; best for short compound labels
            text = pytesseract.image_to_string(crop, config="--psm 7").strip()
            if not text:
                text = pytesseract.image_to_string(crop, config="--psm 6").strip()
            if not text or len(text) > 200 or text.count("\n") > 2:
                continue
            clean = " ".join(text.split())
            if clean:
                return clean[:150]

        return ""
    except Exception:
        return ""


def _lookup_iupac_pubchem(smiles: str):
    """Looks up the IUPAC name for a SMILES string from PubChem REST API.
    Returns the name string, or None if the lookup failed for any reason.
    Safe to call from a background thread.
    """
    if not smiles:
        return None
    try:
        encoded = urllib.parse.quote(smiles, safe="")
        url = (
            "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/smiles/"
            f"{encoded}/property/IUPACName/TXT"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "OPSINator/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            name = resp.read().decode("utf-8").strip()
        return name if name else None
    except Exception:
        return None


def check_decimer_update(engine_path, invoke_prefix=None) -> dict:
    """Compares the DECIMER engine's installed 'decimer' package version
    against the latest one published on PyPI. Returns a dictionary
    describing what it found. This function is careful never to raise
    an exception - any network or parsing problem is reported inside
    the returned dictionary as an "error" entry instead.

    IMPORTANT: this asks the SEPARATE engine program for its version,
    rather than checking this process's own installed packages. After
    splitting DECIMER out into its own executable, this app's own
    process never has the 'decimer' package installed at all - only the
    engine does. Checking locally would always (incorrectly) report
    "not installed".

    engine_path: full path to the opsinator_engine executable, or None
                 if it wasn't found.
    """
    result = {"installed": None, "latest": None, "update_available": False, "error": None}

    if engine_path is None:
        result["error"] = "DECIMER engine executable not found"
        return result

    try:
        # Ask the separate engine program for its version. This is fast
        # and safe - the engine's --version flag deliberately avoids
        # importing DECIMER itself, so this doesn't trigger TensorFlow
        # loading or a model download.
        proc = subprocess.run(
            [*(invoke_prefix or []), engine_path, "--version"],
            capture_output=True, text=True, timeout=15
        )
        version_text = proc.stdout.strip()
        if proc.returncode != 0 or not version_text or version_text == "not-installed":
            result["installed"] = None
        else:
            result["installed"] = version_text
    except Exception as e:
        result["error"] = str(e)
        return result

    try:
        req = urllib.request.Request(PYPI_DECIMER_URL, headers={"User-Agent": "OPSINator/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        # PyPI's JSON API nests the version number under data["info"]["version"].
        result["latest"] = data.get("info", {}).get("version")
    except Exception as e:
        result["error"] = str(e)
        return result

    if result["installed"] and result["latest"] and result["installed"] != result["latest"]:
        result["update_available"] = True
    return result


# ============================================================
# RDKit (SMILES -> MOL / SDF structure files) - lazy-loaded
# ============================================================

def ensure_package_installed(package_name: str, status_callback=None) -> bool:
    """Checks whether a package is importable by THIS Python interpreter,
    and installs it automatically via pip if not - same proven approach
    already used for the DECIMER engine, applied here for RDKit (which
    runs directly in this app's own process, not a separate engine).

    Returns True if the package is now available (whether it already
    was, or was just installed), False if installation genuinely failed.
    """
    def status(msg):
        if status_callback:
            status_callback(msg)

    try:
        importlib.metadata.version(package_name)
        return True  # already installed - nothing to do
    except importlib.metadata.PackageNotFoundError:
        pass

    status(f"Installing '{package_name}'...")

    base_cmd = [sys.executable, "-m", "pip", "install", package_name]

    def _try_install(cmd):
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        output_lines = []
        for line in process.stdout:
            line = line.rstrip("\n")
            if line:
                status(line)
                output_lines.append(line)
        process.wait(timeout=600)
        return process.returncode, "\n".join(output_lines)

    returncode, output = _try_install(base_cmd)

    # Same Ubuntu-specific "externally managed" handling as the engine.
    if returncode != 0 and "externally-managed-environment" in output:
        status("Retrying install (this system protects its default Python "
               "environment by default)...")
        returncode, output = _try_install(base_cmd + ["--break-system-packages"])

    # The install just happened in a SEPARATE process - this process's
    # own cache of "what's installed" is stale until refreshed.
    importlib.invalidate_caches()

    try:
        importlib.metadata.version(package_name)
        status(f"'{package_name}' installed successfully.")
        return True
    except importlib.metadata.PackageNotFoundError:
        return False


class MolConverter:
    """A small wrapper around RDKit, the standard open-source chemistry
    toolkit, used only to turn a SMILES string into a real structure
    file (.mol / .sdf) that chemistry software can open directly.

    Like DecimerEngine above, this delays its import until actually
    needed - RDKit is much lighter than TensorFlow (tens of MB, no model
    download), but there's still no reason to load it for someone who
    never clicks an export-to-structure-file button.
    """

    def __init__(self):
        self._Chem = None
        self._AllChem = None
        self.load_error = None

    def is_loaded(self):
        return self._Chem is not None

    def ensure_loaded(self, status_callback=None):
        if self._Chem is not None or self.load_error is not None:
            return
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            self._Chem = Chem
            self._AllChem = AllChem
        except ImportError:
            # Not installed at all - try installing it automatically,
            # then try the import again, rather than just giving up.
            if ensure_package_installed("rdkit", status_callback=status_callback):
                try:
                    from rdkit import Chem
                    from rdkit.Chem import AllChem
                    self._Chem = Chem
                    self._AllChem = AllChem
                except Exception as e:
                    self.load_error = str(e)
            else:
                self.load_error = "Could not install RDKit automatically."
        except Exception as e:
            self.load_error = str(e)

    def smiles_to_molblock(self, smiles: str, title: str = "") -> str:
        """Converts a SMILES string into a MOL block - a standard plain-
        text chemistry file format that includes real, computed 2D
        coordinates (not just a list of atoms and bonds with no layout).

        Raises ValueError if the SMILES text can't be parsed as a valid
        molecule at all.
        """
        if self._Chem is None:
            raise RuntimeError(self.load_error or "RDKit not loaded")

        mol = self._Chem.MolFromSmiles(smiles)
        if mol is None:
            # RDKit returns None (instead of raising an exception) when a
            # SMILES string is invalid, so we convert that into a proper
            # exception here for the rest of our code to catch normally.
            raise ValueError(f"Could not parse SMILES: {smiles}")

        # Compute2DCoords invents a reasonable 2D layout for the molecule,
        # so the exported file shows a real drawing, not overlapping atoms
        # all sitting at the same point.
        self._AllChem.Compute2DCoords(mol)

        if title:
            # Embeds a name into the molecule's metadata (its "_Name"
            # property), which shows up as the title line of the MOL file.
            mol.SetProp("_Name", title)

        return self._Chem.MolToMolBlock(mol)


def build_sdf(records) -> str:
    """Builds a multi-record SDF file (a standard format for storing many
    chemical structures in one file) out of a list of
    (molblock, properties_dict) pairs.

    Each entry in `records` is a 2-item tuple: the MOL block text for one
    structure, plus a dictionary of extra labeled data to attach to it
    (e.g. {'Source name': 'aspirin', 'InChIKey': '...'}). SDF format
    separates structures with a line containing four dollar signs.
    """
    blocks = []
    for molblock, props in records:
        block = molblock.rstrip("\n")  # remove any trailing blank lines first
        for key, value in props.items():
            # This is exactly the data-field syntax the SDF format
            # expects: a line like "> <FieldName>", then the value on its
            # own line, then a blank line.
            block += f"\n> <{key}>\n{value}\n"
        block += "\n$$$$"  # the official "end of this record" marker in SDF files
        blocks.append(block)
    return "\n".join(blocks) + "\n"


# ============================================================
# Main application
# ============================================================
# CONCEPT: Putting the entire GUI into one class like this (rather than a
# pile of loose functions and global variables) keeps all the related
# pieces - the window, its buttons, its data - bundled together as
# `self.something`, which makes the code much easier to follow as it
# grows. This is one of the most common ways to structure a tkinter app.
# ============================================================

class OpsinatorApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"OPSINator v{__version__} - Batch Chemical Name & Image Converter")
        self.root.geometry("980x740")

        # --- state for the Name -> Structure tab ---
        self.results = []           # list of dicts, one per converted name
        self.ui_queue = queue.Queue()
        # CONCEPT: GUI toolkits like tkinter are NOT thread-safe - you're
        # only supposed to touch widgets from the main thread. But we
        # also don't want to freeze the window while waiting on 200 slow
        # network requests. The standard fix is: do the slow work on a
        # background thread, and have that thread put small "here's what
        # happened" messages into a Queue. The main thread then checks
        # that queue periodically (see _poll_queue below) and only it
        # ever updates the actual widgets.
        self.worker_thread = None
        self.is_processing = False

        # --- the two heavy, lazily-loaded engines ---
        self.decimer = DecimerEngine()
        self.segmentation = SegmentationEngine()
        self.mol_converter = MolConverter()

        # --- state for the Image -> Structure tab ---
        self.current_image_paths = []
        self.found_structures = []   # list of {"page": int, "crop_path": str} from the last PDF scan
        self.pdf_scratch_dir = None  # temp folder holding that scan's rendered pages and crops
        self.pdf_source_name = ""    # the PDF's filename, used to label results once recognized

        # Remembered across restarts via load_settings() - defaults to
        # the user's home folder the very first time the app ever runs.
        self.last_directory = load_settings().get("last_directory") or os.path.expanduser("~")
        self.image_results = []     # list of dicts: {"source": filename, "smiles": "..."}

        self._build_menu()
        self._build_ui()

        # `root.after(100, function)` tells tkinter "call this function
        # again in 100 milliseconds." Using it like this, where the
        # function re-schedules itself every time it runs, creates a
        # repeating timer without needing a separate thread for it.
        self.root.after(100, self._poll_queue)
        self.anim.idle_frame()

        # Kick off a one-time, non-blocking check for a newer DECIMER
        # version, entirely in the background so it never delays startup.
        threading.Thread(target=self._check_for_updates_background, daemon=True).start()
        # CONCEPT: `daemon=True` means "if the main program exits, don't
        # wait around for this thread to finish - just end it too." This
        # is the right choice for background helper threads like this
        # one, which should never keep the app alive on their own.

    # ---------------- menu ----------------

    def _build_menu(self):
        """Builds the File / Help menu bar along the top of the window."""
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        # CONCEPT: `command=lambda: show_help_dialog(self.root)` is needed
        # here (instead of `command=show_help_dialog`) because tkinter
        # calls the command with no arguments - but show_help_dialog
        # needs to know which window it belongs to. The lambda "wraps" the
        # call so the right argument gets passed in when the menu item is
        # actually clicked, not when the menu is being built.
        help_menu.add_command(label="How to use OPSINator", command=lambda: show_help_dialog(self.root))
        help_menu.add_command(label="License & Attribution", command=self._show_license_readonly)
        help_menu.add_separator()
        help_menu.add_command(label="Check for updates", command=self._check_for_updates_manual)
        help_menu.add_command(label="Roll back DECIMER model update", command=self._on_rollback_decimer)
        help_menu.add_command(label="Clean up old DECIMER model backup", command=self._on_cleanup_decimer)
        help_menu.add_separator()
        help_menu.add_command(label="About OPSINator", command=self._show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _show_license_readonly(self):
        """Shows the same license/attribution text as the first-run
        dialog, but as a plain read-only window reachable any time from
        the Help menu (no checkbox, since acceptance already happened)."""
        dialog = tk.Toplevel(self.root)
        dialog.title("License & Attribution - OPSINator")
        dialog.geometry("620x520")
        dialog.transient(self.root)
        text_frame = tk.Frame(dialog)
        text_frame.pack(fill="both", expand=True, padx=12, pady=12)
        text_widget = tk.Text(text_frame, wrap="word", font=("Segoe UI", 9))
        vsb = ttk.Scrollbar(text_frame, orient="vertical", command=text_widget.yview)
        text_widget.configure(yscrollcommand=vsb.set)
        text_widget.insert("1.0", ATTRIBUTION_TEXT)
        text_widget.config(state="disabled")
        text_widget.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        tk.Button(dialog, text="Close", command=dialog.destroy).pack(pady=(0, 12))

    def _show_about(self):
        """Shows the small About box: version number, credits, and the
        no-official-support disclaimer."""
        about = tk.Toplevel(self.root)
        about.title("About OPSINator")
        about.resizable(False, False)
        about.geometry("380x300")
        about.transient(self.root)
        about.grab_set()

        tk.Label(about, text="OPSINator", font=("Segoe UI", 14, "bold")).pack(pady=(18, 2))
        tk.Label(about, text=f"Version {__version__}", font=("Segoe UI", 9)).pack()
        tk.Label(about, text="Batch Chemical Name & Image Converter",
                 font=("Segoe UI", 9)).pack(pady=(0, 14))

        info_frame = tk.Frame(about)
        info_frame.pack(pady=(0, 4))
        # CONCEPT: iterating over a list of (label, value) tuples like
        # this, and building one GUI row per tuple inside the loop, is a
        # common way to avoid repeating near-identical code three times.
        rows = [
            ("Code by", "Claude"),
            ("Code review by", "Dave Gronbach"),
            ("Usage and output by", "Alex Rerick"),
        ]
        for label, value in rows:
            row = tk.Frame(info_frame)
            row.pack(anchor="w", pady=2)
            tk.Label(row, text=f"{label}:", font=("Segoe UI", 9),
                     width=18, anchor="w").pack(side="left")
            tk.Label(row, text=value, font=("Segoe UI", 9, "bold"),
                     anchor="w").pack(side="left")

        tk.Label(about, text="Name->Structure powered by OPSIN\n"
                              "(University of Cambridge / EMBL-EBI)\n"
                              "Image->Structure powered by DECIMER\n"
                              "(Steinbeck Lab, Friedrich Schiller University Jena)",
                 font=("Segoe UI", 8), fg="#666666", justify="center").pack(pady=(10, 4))

        tk.Label(about, text=SUPPORT_DISCLAIMER, font=("Segoe UI", 8),
                 fg="#888888", wraplength=320, justify="center").pack(pady=(0, 4))

        tk.Button(about, text="OK", command=about.destroy, width=10).pack(pady=10)

    # ---------------- update checking ----------------

    def _check_for_updates_background(self):
        """Runs on a background thread at startup. Checks for a newer
        DECIMER version, but only updates the status text if one is
        found or genuinely couldn't be checked - it never pops up a
        dialog box on its own (that would be annoying every launch)."""
        result = check_decimer_update(self.decimer._engine_path, self.decimer._invoke_prefix)
        # CONCEPT: we're currently running on a background thread, but
        # updating a tkinter Label must happen on the main thread. So
        # instead of touching the widget directly here, we use
        # `self.root.after(0, ...)` to ask the main thread to run our
        # lambda "as soon as possible" (0 milliseconds from now).
        self.root.after(0, lambda: self._handle_update_result(result, silent=True))

    def _check_for_updates_manual(self):
        """Runs when the user clicks Help > Check for updates. This time
        it's allowed to show a pop-up dialog with the result, since the
        user explicitly asked."""
        self.status_label2.config(text="Checking for updates...")
        threading.Thread(target=self._check_for_updates_worker, daemon=True).start()

    def _check_for_updates_worker(self):
        result = check_decimer_update(self.decimer._engine_path, self.decimer._invoke_prefix)
        self.root.after(0, lambda: self._handle_update_result(result, silent=False))

    def _show_engine_unavailable(self, action_description):
        """Shows the right kind of message depending on WHY the engine
        is unavailable: a calm, informational note if this is simply
        expected (running from source, before any build exists), or a
        real error if something that should be there genuinely isn't."""
        if self.decimer.dev_mode_missing:
            messagebox.showinfo(
                "Not yet built",
                f"{action_description} requires the compiled DECIMER engine, "
                "which doesn't exist yet because this is running directly "
                "from source rather than as a built app. This is expected "
                "during development, not an error - it will work normally "
                "once the app is packaged.",
            )
        else:
            messagebox.showerror("Not available", self.decimer.load_error or "DECIMER engine not found.")

    def _on_rollback_decimer(self):
        """Asks the engine to restore the previous DECIMER model version,
        if one was backed up before the most recent update."""
        if self.decimer._engine_path is None:
            self._show_engine_unavailable("Rolling back a model update")
            return
        try:
            result = subprocess.run(
                [*self.decimer._invoke_prefix, self.decimer._engine_path, "--rollback"],
                capture_output=True, text=True, timeout=30,
            )
            message = (result.stdout or result.stderr).strip()
            if result.returncode == 0:
                messagebox.showinfo("Rollback", message or "Rolled back successfully.")
            else:
                messagebox.showwarning("Rollback", message or "Nothing to roll back to.")
        except Exception as e:
            messagebox.showerror("Rollback failed", str(e))

    def _on_cleanup_decimer(self):
        """Asks the engine to delete any backed-up old model version."""
        if self.decimer._engine_path is None:
            self._show_engine_unavailable("Cleaning up old model backups")
            return
        try:
            result = subprocess.run(
                [*self.decimer._invoke_prefix, self.decimer._engine_path, "--cleanup"],
                capture_output=True, text=True, timeout=30,
            )
            message = (result.stdout or result.stderr).strip()
            messagebox.showinfo("Cleanup", message or "Done.")
        except Exception as e:
            messagebox.showerror("Cleanup failed", str(e))

    def _handle_update_result(self, result, silent):
        """Shared logic for both the silent startup check and the manual
        Help-menu check. `silent=True` means: update the status bar text
        quietly, but never interrupt the user with a pop-up dialog."""
        if result.get("error"):
            if self.decimer.dev_mode_missing:
                self.status_label2.config(text="Update check unavailable (running from source).")
                if not silent:
                    messagebox.showinfo(
                        "Not yet built",
                        "Checking for updates requires the compiled DECIMER engine, "
                        "which doesn't exist yet because this is running from source, "
                        "not as a built app. This is expected during development."
                    )
            else:
                self.status_label2.config(text="Could not check for updates.")
                if not silent:
                    messagebox.showerror("Check for updates failed", result["error"])
            return

        if result["installed"] is None:
            self.status_label2.config(text="DECIMER not yet installed in this build.")
            if not silent:
                messagebox.showwarning("Not installed", "DECIMER is not installed in this build.")
            return

        if result["update_available"]:
            msg = (f"A newer DECIMER engine is available "
                   f"(installed: {result['installed']}, latest: {result['latest']}).")
            self.status_label2.config(text=msg)
            if not silent:
                messagebox.showinfo(
                    "Update available",
                    msg + "\n\nThis app cannot update itself automatically - the engine "
                          "would need to be rebuilt with the newer decimer package first. "
                          "Ask your sysadmin to rebuild OPSINator when convenient."
                )
        else:
            self.status_label2.config(text=f"DECIMER engine up to date (v{result['installed']}).")
            if not silent:
                messagebox.showinfo("Up to date", f"DECIMER v{result['installed']} is the latest version.")

    # ---------------- main UI ----------------

    def _build_ui(self):
        """Builds the two-tab layout (Name -> Structure, Image -> Structure)
        plus the thin status bar along the very bottom of the window."""
        # Give all Treeview column headers a groove relief so vertical
        # dividers are visible between adjacent heading cells - without
        # this, the default flat style makes column boundaries ambiguous.
        ttk.Style().configure("Treeview.Heading", relief="groove")

        # ttk.Notebook is tkinter's "tabbed panel" widget - each tab is
        # really just a regular Frame that gets shown or hidden.
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        name_tab     = tk.Frame(notebook)
        image_tab    = tk.Frame(notebook)
        activity_tab = tk.Frame(notebook)
        notebook.add(name_tab,     text="Name -> Structure")
        notebook.add(image_tab,    text="Image -> Structure")
        notebook.add(activity_tab, text="Patent Activity")

        self._build_name_tab(name_tab)
        self._build_image_tab(image_tab)
        self._build_activity_tab(activity_tab)

        self.status_label2 = tk.Label(self.root, text="", anchor="w", fg="#555555")
        self.status_label2.pack(fill="x", padx=10, pady=(0, 6))

    def _build_name_tab(self, parent):
        """Builds every widget that lives inside the 'Name -> Structure' tab."""
        pad = {"padx": 10, "pady": 6}

        tk.Label(parent, text="Paste chemical names below, one per line "
                              f"(up to {MAX_NAMES}):").pack(anchor="w", **pad)
        # CONCEPT: `**pad` "unpacks" the pad dictionary into separate
        # keyword arguments - it's exactly the same as writing
        # `.pack(anchor="w", padx=10, pady=6)` by hand, just without
        # repeating padx/pady on every single line below.

        self.input_box = tk.Text(parent, height=7, font=("Consolas", 10))
        self.input_box.pack(fill="x", padx=10)

        btn_frame = tk.Frame(parent)
        btn_frame.pack(fill="x", **pad)

        self.convert_btn = tk.Button(btn_frame, text="Convert Names",
                                      command=self.on_convert, width=16)
        self.convert_btn.pack(side="left", padx=(0, 8))

        self.clear_btn = tk.Button(btn_frame, text="Clear",
                                    command=self.on_clear, width=10)
        self.clear_btn.pack(side="left", padx=(0, 8))

        self.save_btn = tk.Button(btn_frame, text="Save CSV",
                                   command=self.on_save_csv, width=10,
                                   state="disabled")
        self.save_btn.pack(side="left", padx=(0, 8))

        self.save_mol_btn = tk.Button(btn_frame, text="Save MOL",
                                       command=self.on_save_mol, width=10,
                                       state="disabled")
        self.save_mol_btn.pack(side="left", padx=(0, 8))

        self.save_sdf_btn = tk.Button(btn_frame, text="Save SDF",
                                       command=self.on_save_sdf, width=10,
                                       state="disabled")
        self.save_sdf_btn.pack(side="left", padx=(0, 8))

        self.status_label = tk.Label(btn_frame, text="", anchor="w")
        self.status_label.pack(side="left", padx=10)

        # Row holding the cartoon scientist canvas + the progress bar,
        # side by side.
        anim_row = tk.Frame(parent)
        anim_row.pack(fill="x", padx=10, pady=(0, 6))

        self.anim_canvas = tk.Canvas(anim_row, width=120, height=160,
                                      highlightthickness=0, bg=self.root.cget("bg"))
        self.anim_canvas.pack(side="left", padx=(0, 12))
        self.anim = ScientistAnimation(self.anim_canvas)

        progress_col = tk.Frame(anim_row)
        progress_col.pack(side="left", fill="both", expand=True)
        self.progress = ttk.Progressbar(progress_col, mode="determinate")
        self.progress.pack(fill="x", pady=(40, 0))

        # The results table. ttk.Treeview is tkinter's "table with
        # columns" widget - even though its name suggests trees, it works
        # perfectly well as a flat spreadsheet-style grid too.
        columns = ("name", "status", "smiles", "inchikey", "message")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings")
        headings = {"name": "Name (as entered)", "status": "Status",
                    "smiles": "SMILES", "inchikey": "InChIKey", "message": "Message"}
        widths = {"name": 230, "status": 80, "smiles": 200, "inchikey": 140, "message": 200}
        for col in columns:
            self.tree.heading(col, text=headings[col], anchor="w")
            self.tree.column(col, width=widths[col], anchor="w")

        vsb = ttk.Scrollbar(parent, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True, padx=(10, 0), pady=(0, 10))
        vsb.pack(side="right", fill="y", padx=(0, 10), pady=(0, 10))

        # "Tags" let us color-code rows by status: green for success,
        # amber for warnings, red for anything that failed.
        self.tree.tag_configure("success", foreground="#1a7a36")
        self.tree.tag_configure("warning", foreground="#b8860b")
        self.tree.tag_configure("error", foreground="#b22222")

    def _build_image_tab(self, parent):
        """Builds every widget that lives inside the 'Image -> Structure' tab."""
        pad = {"padx": 10, "pady": 6}

        tk.Label(parent, text="Recognize a drawn chemical structure from an image "
                              "(e.g. a screenshot or crop from a patent figure).",
                 wraplength=600, justify="left").pack(anchor="w", **pad)

        # --- the gating checkbox: nothing below it is usable until this
        # is checked, and checking it for the first time shows a clear
        # size warning before anything downloads. ---
        gate_frame = tk.Frame(parent)
        gate_frame.pack(fill="x", **pad)

        self.decimer_enabled_var = tk.BooleanVar(value=is_decimer_enabled())
        self.decimer_gate_check = tk.Checkbutton(
            gate_frame,
            text="Enable image recognition (DECIMER) - downloads approximately "
                 "700 MB-2 GB of components the first time it's actually used",
            variable=self.decimer_enabled_var,
            command=self.on_toggle_decimer_gate,
        )
        self.decimer_gate_check.pack(anchor="w")

        gate_on = is_decimer_enabled()
        decimer_btn_row = tk.Frame(gate_frame)
        decimer_btn_row.pack(anchor="w", pady=(6, 0))

        self.download_decimer_btn = tk.Button(
            decimer_btn_row, text="Begin Download (DECIMER components)",
            command=self.on_download_decimer,
            state="normal" if gate_on else "disabled",
        )
        self.download_decimer_btn.pack(side="left")

        self.check_updates_image_btn = tk.Button(
            decimer_btn_row, text="Check for Updates",
            command=self._check_for_updates_manual,
            state="normal" if gate_on else "disabled",
        )
        self.check_updates_image_btn.pack(side="left", padx=(8, 0))

        # Hide the consent checkbox and Begin Download button once the
        # components are confirmed present on disk. Check for Updates
        # stays visible in both cases. pack_forget removes the widgets
        # from the layout entirely so no dead space is left behind.
        if _decimer_components_present():
            self.decimer_gate_check.pack_forget()
            self.download_decimer_btn.pack_forget()

        btn_row = tk.Frame(parent)
        btn_row.pack(fill="x", **pad)

        gate_on = self.decimer_enabled_var.get()
        self.choose_image_btn = tk.Button(btn_row, text="Choose Image...", command=self.on_choose_image,
                  width=16, state="normal" if gate_on else "disabled")
        self.choose_image_btn.pack(side="left", padx=(0, 8))
        self.choose_pdf_btn = tk.Button(btn_row, text="Choose PDF...", command=self.on_choose_pdf,
                  width=14, state="normal" if gate_on else "disabled")
        self.choose_pdf_btn.pack(side="left", padx=(0, 8))
        self.recognize_btn = tk.Button(btn_row, text="Recognize Structure",
                                        command=self.on_recognize_image, width=18,
                                        state="disabled")
        self.recognize_btn.pack(side="left", padx=(0, 8))

        # A visible drop zone for dragging an image or PDF straight onto
        # the window, as an alternative to the buttons above. Requires
        # the tkinterdnd2 package - if it isn't available for some
        # reason, this area still displays normally, it just won't
        # accept drops (the buttons above still work either way).
        self.drop_zone = tk.Label(
            parent,
            text="...or drag an image or PDF here...",
            relief="ridge", borderwidth=2,
            fg="#777777", height=2,
        )
        self.drop_zone.pack(fill="x", padx=10, pady=(0, 6))
        self._wire_up_drag_and_drop()

        self.image_path_label = tk.Label(parent, text="No image selected.", fg="#555555")
        self.image_path_label.pack(anchor="w", padx=10)

        self.image_preview_label = tk.Label(parent)
        self.image_preview_label.pack(anchor="w", padx=10, pady=8)

        wait_frame = tk.Frame(parent)
        wait_frame.pack(fill="x", padx=10, pady=(0, 6))
        self.image_status_label = tk.Label(wait_frame, text="", fg="#555555")
        self.image_status_label.pack(anchor="w")
        # mode="indeterminate" makes the progress bar bounce back and
        # forth, rather than fill up toward a known percentage - useful
        # here because we genuinely don't know how long the first-run
        # download or a single image recognition will take.
        self.image_progress = ttk.Progressbar(wait_frame, mode="indeterminate")
        self.image_progress.pack(fill="x", pady=(4, 0))

        # Both scrollable tables live inside a PanedWindow so they share
        # the remaining vertical space and the user can drag the divider.
        tables_pane = tk.PanedWindow(parent, orient="vertical", sashrelief="raised",
                                     sashwidth=6, opaqueresize=True)
        tables_pane.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        # --- Structures found in PDF ---
        found_frame = tk.LabelFrame(tables_pane,
                                    text="Structures found in PDF - select, then Recognize")
        tables_pane.add(found_frame, stretch="always")

        found_tree_frame = tk.Frame(found_frame)
        found_tree_frame.pack(fill="both", expand=True, padx=8, pady=(6, 4))

        self.found_tree = ttk.Treeview(found_tree_frame, columns=("label", "page"),
                                        show="headings", height=10, selectmode="extended")
        self.found_tree.heading("label", text="Label", anchor="w")
        self.found_tree.heading("page", text="Page", anchor="center")
        self.found_tree.column("label", width=420, anchor="w")
        self.found_tree.column("page", width=80, anchor="center")
        found_vsb = ttk.Scrollbar(found_tree_frame, orient="vertical",
                                   command=self.found_tree.yview)
        self.found_tree.configure(yscrollcommand=found_vsb.set)
        self.found_tree.pack(side="left", fill="both", expand=True)
        found_vsb.pack(side="right", fill="y")

        found_btn_row = tk.Frame(found_frame)
        found_btn_row.pack(fill="x", padx=8, pady=(0, 8))
        self.select_all_found_btn = tk.Button(found_btn_row, text="Select All",
                                               command=self.on_select_all_found, state="disabled")
        self.select_all_found_btn.pack(side="left")
        self.recognize_found_btn = tk.Button(found_btn_row, text="Recognize Selected/All Structures",
                                              command=self.on_recognize_found, state="disabled")
        self.recognize_found_btn.pack(side="left", padx=(8, 0))

        # --- Recognized structures (this session) ---
        results_frame = tk.LabelFrame(tables_pane, text="Recognized structures (this session)")
        tables_pane.add(results_frame, stretch="always")

        img_columns = ("source", "smiles")
        self.image_tree = ttk.Treeview(results_frame, columns=img_columns, show="headings", height=8)
        self.image_tree.heading("source", text="Image file", anchor="w")
        self.image_tree.heading("smiles", text="Predicted SMILES", anchor="w")
        self.image_tree.column("source", width=200, anchor="w")
        self.image_tree.column("smiles", width=360, anchor="w")
        img_vsb = ttk.Scrollbar(results_frame, orient="vertical", command=self.image_tree.yview)
        self.image_tree.configure(yscrollcommand=img_vsb.set)
        self.image_tree.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        img_vsb.pack(side="right", fill="y", pady=6)

        img_btn_row = tk.Frame(parent)
        img_btn_row.pack(fill="x", padx=10, pady=(0, 6))

        self.copy_smiles_btn = tk.Button(img_btn_row, text="Copy Selected SMILES",
                                          command=self.on_copy_smiles, state="disabled")
        self.copy_smiles_btn.pack(side="left", padx=(0, 8))

        self.image_save_csv_btn = tk.Button(img_btn_row, text="Save CSV",
                                             command=self.on_save_image_csv, width=10,
                                             state="disabled")
        self.image_save_csv_btn.pack(side="left", padx=(0, 8))

        self.image_save_sdf_btn = tk.Button(img_btn_row, text="Save SDF",
                                             command=self.on_save_image_sdf, width=10,
                                             state="disabled")
        self.image_save_sdf_btn.pack(side="left", padx=(0, 8))

        self.image_save_mol_btn = tk.Button(img_btn_row, text="Save MOL",
                                             command=self.on_save_image_mol, width=10,
                                             state="disabled")
        self.image_save_mol_btn.pack(side="left", padx=(0, 8))

        note = ("Note: image recognition runs locally using the DECIMER model. The first "
                "time this is used on a machine, required components (roughly 1-2 GB) are "
                "downloaded automatically into your own user profile - no admin rights needed. "
                "After that, it runs offline. Always visually check predicted structures "
                "against the source image before relying on them.")
        tk.Label(parent, text=note, wraplength=600, justify="left",
                 fg="#777777", font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 10))

    def _build_activity_tab(self, parent):
        """Builds the Patent Activity tab: load a patent PDF, extract its activity
        table, convert compound names to SMILES via OPSIN, and display results."""
        pad = {"padx": 10, "pady": 6}

        tk.Label(parent,
                 text="Extract compounds with biological data from a patent PDF "
                      "(activity table → compound names → OPSIN → SMILES).",
                 wraplength=600, justify="left").pack(anchor="w", **pad)

        btn_row = tk.Frame(parent)
        btn_row.pack(fill="x", **pad)

        self.activity_load_btn = tk.Button(btn_row, text="Load Patent PDF...",
                                           command=self.on_activity_load, width=18)
        self.activity_load_btn.pack(side="left", padx=(0, 8))

        self.activity_run_btn = tk.Button(btn_row, text="Extract & Convert",
                                          command=self.on_activity_run, width=16,
                                          state="disabled")
        self.activity_run_btn.pack(side="left", padx=(0, 8))

        self.activity_save_btn = tk.Button(btn_row, text="Save CSV",
                                           command=self.on_activity_save_csv, width=10,
                                           state="disabled")
        self.activity_save_btn.pack(side="left", padx=(0, 8))

        self.activity_pdf_label = tk.Label(parent, text="No PDF loaded.", fg="#555555")
        self.activity_pdf_label.pack(anchor="w", padx=10)

        self.activity_status_label = tk.Label(parent, text="", fg="#555555")
        self.activity_status_label.pack(anchor="w", padx=10)

        self.activity_progress = ttk.Progressbar(parent, mode="determinate")
        self.activity_progress.pack(fill="x", padx=10, pady=(2, 4))

        tree_frame = tk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, padx=10, pady=(0, 4))

        cols = ("example", "name", "ic50", "smiles", "status", "page")
        self.activity_tree = ttk.Treeview(tree_frame, columns=cols, show="headings")
        self.activity_tree.heading("example", text="Example #",    anchor="w")
        self.activity_tree.heading("name",    text="Compound Name", anchor="w")
        self.activity_tree.heading("ic50",    text="IC50 (nM)",    anchor="w")
        self.activity_tree.heading("smiles",  text="SMILES",       anchor="w")
        self.activity_tree.heading("status",  text="Status",       anchor="w")
        self.activity_tree.heading("page",    text="Page",         anchor="center")
        self.activity_tree.column("example", width=70,  minwidth=50,  anchor="w", stretch=False)
        self.activity_tree.column("name",    width=380, minwidth=150, anchor="w", stretch=True)
        self.activity_tree.column("ic50",    width=70,  minwidth=50,  anchor="w", stretch=False)
        self.activity_tree.column("smiles",  width=300, minwidth=100, anchor="w", stretch=True)
        self.activity_tree.column("status",  width=80,  minwidth=60,  anchor="w", stretch=False)
        self.activity_tree.column("page",    width=50,  minwidth=40,  anchor="center", stretch=False)

        act_vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                                 command=self.activity_tree.yview)
        act_hsb = ttk.Scrollbar(parent, orient="horizontal",
                                 command=self.activity_tree.xview)
        self.activity_tree.configure(yscrollcommand=act_vsb.set,
                                      xscrollcommand=act_hsb.set)
        self.activity_tree.pack(side="left", fill="both", expand=True)
        act_vsb.pack(side="right", fill="y")
        act_hsb.pack(fill="x", padx=10, pady=(0, 4))

        self._activity_pdf_path = None
        self._activity_results  = []
        self._activity_queue    = queue.Queue()

    # ---------------- name tab handlers ----------------
    # CONCEPT: functions named "on_something" (a common GUI convention)
    # are "event handlers" - they don't get called directly by the rest
    # of our code; tkinter calls them automatically whenever the matching
    # button is clicked, because we hooked them up with `command=...`
    # when we built each button above.

    def on_clear(self):
        """Wipes the input box, the results table, and resets every
        button back to its starting, disabled state."""
        self.input_box.delete("1.0", tk.END)   # erase all typed text
        self.tree.delete(*self.tree.get_children())
        # CONCEPT: `*self.tree.get_children()` "unpacks" a list of row
        # IDs into separate arguments. tree.delete() can remove several
        # rows in one call if you give it several IDs - this is just a
        # convenient way to say "delete every single row."
        self.results = []
        self.status_label.config(text="")
        self.progress["value"] = 0
        self.save_btn.config(state="disabled")
        self.save_mol_btn.config(state="disabled")
        self.save_sdf_btn.config(state="disabled")
        self.anim.idle_frame()

    def on_convert(self):
        """Reads whatever names are in the input box, then kicks off a
        background thread to look each one up via OPSIN, so the window
        stays responsive instead of freezing for the whole batch."""
        raw = self.input_box.get("1.0", tk.END)

        # CONCEPT: this is a "list comprehension" - a compact way to
        # build a new list by transforming and/or filtering an existing
        # sequence. The line below is equivalent to writing:
        #
        #   names = []
        #   for line in raw.splitlines():
        #       stripped = line.strip()
        #       if stripped:
        #           names.append(stripped)
        #
        # `.splitlines()` breaks the text into one entry per line.
        # `.strip()` removes leading/trailing whitespace from each line.
        # `if line.strip()` skips any line that's empty after stripping.
        names = [line.strip() for line in raw.splitlines() if line.strip()]

        if not names:
            return  # nothing to do

        if len(names) > MAX_NAMES:
            # Python's "slice" syntax names[:MAX_NAMES] grabs everything
            # from the start of the list up to (but not including)
            # position MAX_NAMES - i.e. "just the first 200 items."
            names = names[:MAX_NAMES]

        self.tree.delete(*self.tree.get_children())
        self.results = []
        self.progress["maximum"] = len(names)
        self.progress["value"] = 0
        self.convert_btn.config(state="disabled")
        self.save_btn.config(state="disabled")
        self.save_mol_btn.config(state="disabled")
        self.save_sdf_btn.config(state="disabled")
        self.status_label.config(text=f"Processing 0 / {len(names)}...")

        self.is_processing = True
        self._animate_step()

        # threading.Thread(target=function, args=(...)) creates a new
        # background thread that will run `function(*args)`. Calling
        # .start() actually launches it; the rest of this method (and the
        # whole GUI) keeps running normally while that thread works.
        self.worker_thread = threading.Thread(target=self._run_batch, args=(names,), daemon=True)
        self.worker_thread.start()

    def _animate_step(self):
        """Advances the cartoon scientist by one frame, then schedules
        itself to run again in 80ms - but only while a batch is actively
        processing."""
        if not self.is_processing:
            return
        self.anim.tick()
        self.root.after(80, self._animate_step)

    def _run_batch(self, names):
        """Runs on the BACKGROUND thread. For each name, fetches the
        OPSIN result and places a small message into the thread-safe
        queue, rather than touching any GUI widget directly (which would
        not be safe from a background thread)."""
        smiles_in_batch = False
        for i, name in enumerate(names, start=1):
            if _looks_like_smiles(name):
                result = {
                    "name": name, "status": "ERROR",
                    "smiles": "", "inchikey": "",
                    "message": "Looks like SMILES, not a name",
                }
                smiles_in_batch = True
            else:
                result = fetch_opsin(name)
            self.ui_queue.put(("row", i, len(names), result))
        self.ui_queue.put(("done", len(names), smiles_in_batch))

    def _poll_queue(self):
        """Runs on the MAIN thread, roughly 10 times a second (every
        100ms). Drains any pending messages from the background thread's
        queue and updates the actual GUI widgets - this is the only place
        in the whole program where it's safe to do that for these
        particular updates."""
        try:
            while True:
                # get_nowait() either returns the next item immediately,
                # or raises queue.Empty if there's nothing waiting - it
                # never blocks/waits, which is exactly what we want here.
                msg = self.ui_queue.get_nowait()
                kind = msg[0]

                if kind == "row":
                    _, i, total, result = msg
                    # CONCEPT: using `_` as a variable name is a common
                    # Python convention for "I have to unpack this value,
                    # but I don't actually need it" - here we don't care
                    # about re-reading "row" again, we already checked it
                    # with `kind` above.
                    self.results.append(result)

                    status = result["status"]
                    if status == "SUCCESS":
                        tag = "success"
                    elif status == "WARNING":
                        tag = "warning"
                    else:
                        tag = "error"

                    self.tree.insert("", "end", values=(
                        result["name"], result["status"], result["smiles"],
                        result["inchikey"], result["message"]
                    ), tags=(tag,))
                    self.progress["value"] = i
                    self.status_label.config(text=f"Processing {i} / {total}...")

                elif kind == "done":
                    total = msg[1]
                    smiles_in_batch = msg[2] if len(msg) > 2 else False
                    # CONCEPT: `sum(1 for r in self.results if ...)` is a
                    # "generator expression" - very similar to a list
                    # comprehension, but it produces values one at a time
                    # instead of building a whole list first. Feeding it
                    # straight into sum() is a common, memory-efficient
                    # way to count how many items match a condition.
                    success = sum(1 for r in self.results if r["status"] == "SUCCESS")
                    warn = sum(1 for r in self.results if r["status"] == "WARNING")
                    fail = total - success - warn
                    self.status_label.config(
                        text=f"{total} processed - {success} success, {warn} warning, {fail} failed."
                    )
                    self.convert_btn.config(state="normal")
                    has_results = bool(self.results)
                    self.save_btn.config(state="normal" if has_results else "disabled")
                    self.save_mol_btn.config(state="normal" if has_results else "disabled")
                    self.save_sdf_btn.config(state="normal" if has_results else "disabled")
                    self.is_processing = False
                    self.anim.idle_frame(caption="Finished")
                    if smiles_in_batch:
                        messagebox.showwarning(
                            "Wrong input type",
                            "Doh! Need a chemical name, not SMILES."
                        )
        except queue.Empty:
            pass  # nothing left to process right now - that's fine, just move on

        # Schedule this exact same method to run again shortly - this is
        # what makes _poll_queue behave like a repeating timer.
        self.root.after(100, self._poll_queue)

    def on_save_csv(self):
        """Exports every Name -> Structure result as a .csv spreadsheet."""
        if not self.results:
            return

        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="opsin_results.csv",
            initialdir=self.last_directory,
        )
        if not path:
            return  # user clicked Cancel on the save dialog
        self._remember_directory(path)

        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                # csv.DictWriter writes one row per dictionary, matching
                # dictionary keys to column headers automatically -
                # easier than building comma-separated text by hand.
                writer = csv.DictWriter(f, fieldnames=["name", "status", "smiles", "inchikey", "message"])
                writer.writeheader()
                writer.writerows(self.results)
            messagebox.showinfo("Saved", f"Results saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error saving file", str(e))

    def _ensure_rdkit_then(self, on_ready, status_label, progress_bar=None):
        """Loads RDKit (installing it automatically first, if needed) on
        a BACKGROUND thread, so a real pip install never freezes the
        window - then calls on_ready() back on the MAIN thread once
        it's confirmed working, or shows a clear error if it couldn't be."""
        if self.mol_converter.is_loaded():
            on_ready()
            return

        def status(msg):
            self.root.after(0, lambda: status_label.config(text=msg))

        if progress_bar:
            self.root.after(0, lambda: progress_bar.config(mode="indeterminate"))
            self.root.after(0, lambda: progress_bar.start(12))

        def worker():
            self.mol_converter.ensure_loaded(status_callback=status)

            def finish():
                if progress_bar:
                    progress_bar.stop()
                if self.mol_converter.load_error:
                    status_label.config(text="")
                    messagebox.showerror("Chemistry toolkit unavailable",
                                          f"Could not load RDKit: {self.mol_converter.load_error}")
                else:
                    status_label.config(text="")
                    on_ready()

            self.root.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _remember_directory(self, path):
        """Updates and persists the last-used folder, given either a
        file path (in which case its containing folder is remembered)
        or a folder path directly."""
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        if folder and os.path.isdir(folder):
            self.last_directory = folder
            save_settings({"last_directory": folder})

    def on_save_mol(self):
        """Saves either the currently selected row, or ALL results, as
        MOL file(s) - the user explicitly chooses which, rather than
        this only ever working on a single selected row."""
        usable = [r for r in self.results if r.get("smiles") and r["status"] in ("SUCCESS", "WARNING")]
        if not usable:
            messagebox.showwarning("Nothing to export", "None of the results have a usable structure.")
            return

        selected = self.tree.selection()

        scope = ask_save_scope(self.root, len(usable))
        if scope is None:
            return
        if scope == "selected" and not selected:
            messagebox.showinfo("Select a row", "Click a row in the table first, then try again.")
            return

        def proceed():
            if scope == "selected":
                values = self.tree.item(selected[0], "values")
                name, status, smiles = values[0], values[1], values[2]
                if not smiles:
                    messagebox.showwarning("No structure", f"'{name}' has no SMILES to convert "
                                                             f"(status: {status}).")
                    return
                try:
                    molblock = self.mol_converter.smiles_to_molblock(smiles, title=name)
                except Exception as e:
                    messagebox.showerror("Conversion failed", str(e))
                    return

                path = filedialog.asksaveasfilename(
                    defaultextension=".mol",
                    filetypes=[("MOL files", "*.mol")],
                    initialfile="structure.mol",
                    initialdir=self.last_directory,
                )
                if not path:
                    return
                self._remember_directory(path)
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(molblock)
                    messagebox.showinfo("Saved", f"Structure saved to:\n{path}")
                except Exception as e:
                    messagebox.showerror("Error saving file", str(e))

            else:  # scope == "all"
                folder = filedialog.askdirectory(title="Choose a folder for the MOL files",
                                                  initialdir=self.last_directory)
                if not folder:
                    return
                self._remember_directory(folder)

                saved_count = 0
                failed_names = []
                used_filenames = set()
                for r in usable:
                    try:
                        molblock = self.mol_converter.smiles_to_molblock(r["smiles"], title=r["name"])
                    except Exception:
                        failed_names.append(r["name"])
                        continue

                    base = sanitize_filename(r["name"])
                    filename = f"{base}.mol"
                    # Two different results could sanitize down to the same
                    # name - number them rather than silently overwriting.
                    counter = 2
                    while filename in used_filenames:
                        filename = f"{base}_{counter}.mol"
                        counter += 1
                    used_filenames.add(filename)

                    try:
                        with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
                            f.write(molblock)
                        saved_count += 1
                    except Exception:
                        failed_names.append(r["name"])

                note = f"{saved_count} structure(s) saved to:\n{folder}"
                if failed_names:
                    note += f"\n\n{len(failed_names)} could not be converted and were skipped."
                messagebox.showinfo("Saved", note)

        self._ensure_rdkit_then(proceed, self.status_label, self.progress)

    def on_save_sdf(self):
        """Saves every successfully-converted result as one multi-record
        SDF file - the standard format for a batch of structures."""
        usable = [r for r in self.results if r.get("smiles") and r["status"] in ("SUCCESS", "WARNING")]
        skipped = len(self.results) - len(usable)
        if not usable:
            messagebox.showwarning("Nothing to export", "None of the results have a usable structure.")
            return

        def proceed():
            records = []
            failed_conversions = []
            for r in usable:
                try:
                    molblock = self.mol_converter.smiles_to_molblock(r["smiles"], title=r["name"])
                    records.append((molblock, {
                        "Source name": r["name"],
                        "Status": r["status"],
                        "InChIKey": r["inchikey"],
                    }))
                except Exception:
                    # If one structure fails to convert, don't let it ruin
                    # the whole export - just remember its name and continue
                    # with the rest of the batch.
                    failed_conversions.append(r["name"])

            if not records:
                messagebox.showwarning("Nothing to export", "None of the results could be converted.")
                return

            path = filedialog.asksaveasfilename(
                defaultextension=".sdf",
                filetypes=[("SDF files", "*.sdf")],
                initialfile="opsin_results.sdf",
                initialdir=self.last_directory,
            )
            if not path:
                return
            self._remember_directory(path)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(build_sdf(records))
                note = f"{len(records)} structure(s) saved to:\n{path}"
                if skipped or failed_conversions:
                    note += f"\n\n{skipped + len(failed_conversions)} row(s) were skipped (no usable structure)."
                messagebox.showinfo("Saved", note)
            except Exception as e:
                messagebox.showerror("Error saving file", str(e))

        self._ensure_rdkit_then(proceed, self.status_label, self.progress)

    # ---------------- image tab handlers ----------------

    def _update_progress_from_status(self, line):
        """Looks for something like '42%' inside a status line. If
        found, switches the progress bar to determinate mode and sets
        it to that exact value - so it visibly fills up to match real
        progress, instead of just bouncing back and forth indefinitely.
        If no percentage is found (e.g. 'Extracting model...'), leaves
        it bouncing, since that step's duration genuinely isn't known.
        """
        match = re.search(r"(\d{1,3})%", line)
        if match:
            percent = min(100, int(match.group(1)))
            if str(self.image_progress["mode"]) != "determinate":
                self.image_progress.stop()
                self.image_progress.config(mode="determinate", maximum=100)
            self.image_progress["value"] = percent
        else:
            if str(self.image_progress["mode"]) != "indeterminate":
                self.image_progress.config(mode="indeterminate")
            self.image_progress.start(12)

    def _finish_progress_bar(self, success):
        """Called once a task is fully done. On success, the bar fills
        all the way to the right rather than just stopping mid-bounce -
        so 'complete' actually looks complete. On failure, it resets to
        empty instead, since nothing was actually finished."""
        self.image_progress.stop()
        self.image_progress.config(mode="determinate", maximum=100)
        self.image_progress["value"] = 100 if success else 0

    def on_toggle_decimer_gate(self):
        """Called whenever the 'Enable image recognition' checkbox is
        clicked. Shows a clear size warning the first time it's turned
        on, and enables/disables the Choose Image/Choose PDF buttons
        accordingly."""
        if self.decimer_enabled_var.get():
            # User just checked it. If they've never confirmed this
            # before, show the warning before actually turning it on.
            if not is_decimer_enabled():
                confirmed = messagebox.askyesno(
                    "Enable image recognition?",
                    "Image recognition (DECIMER) requires downloading "
                    "approximately 700 MB-2 GB of components the first "
                    "time you actually recognize an image. This happens "
                    "once and is saved for future use.\n\n"
                    "Continue?",
                )
                if not confirmed:
                    # They backed out - leave it unchecked and disabled.
                    self.decimer_enabled_var.set(False)
                    self.choose_image_btn.config(state="disabled")
                    self.choose_pdf_btn.config(state="disabled")
                    self.download_decimer_btn.config(state="disabled")
                    self.check_updates_image_btn.config(state="disabled")
                    return
                mark_decimer_enabled()
            self.choose_image_btn.config(state="normal")
            self.choose_pdf_btn.config(state="normal")
            self.download_decimer_btn.config(state="normal")
            self.check_updates_image_btn.config(state="normal")
        else:
            # User unchecked it - remember that choice, and disable the
            # controls so nothing can be triggered accidentally.
            mark_decimer_disabled()
            self.choose_image_btn.config(state="disabled")
            self.choose_pdf_btn.config(state="disabled")
            self.download_decimer_btn.config(state="disabled")
            self.check_updates_image_btn.config(state="disabled")
            self.recognize_btn.config(state="disabled")

    def on_download_decimer(self):
        """Runs the engine's explicit --download command as its own
        deliberate action, separate from recognition. Safe to click
        even if everything is already downloaded - it finishes almost
        instantly in that case rather than re-downloading anything."""
        if self.decimer._engine_path is None:
            self._show_engine_unavailable("Downloading DECIMER components")
            return
        self.download_decimer_btn.config(state="disabled")
        self.image_progress.config(mode="indeterminate")
        self.image_progress.start(12)
        self.image_status_label.config(text="Starting download...")
        threading.Thread(target=self._run_decimer_download, daemon=True).start()

    def _run_decimer_download(self):
        """Runs on the BACKGROUND thread. Streams the engine's live
        download progress lines straight into the status label, the
        same pattern used for recognition itself."""
        def status(msg):
            self.root.after(0, lambda: self.image_status_label.config(text=msg))
            self.root.after(0, lambda: self._update_progress_from_status(msg))

        process = subprocess.Popen(
            [*self.decimer._invoke_prefix, self.decimer._engine_path, "--download"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        completed = False
        other_lines = []
        for line in process.stdout:
            line = line.rstrip("\n")
            if line == "OPSINATOR_DOWNLOAD_COMPLETE":
                completed = True
            elif line and not _is_harmless_startup_noise(line):
                other_lines.append(line)
                status(line)

        process.wait(timeout=3600)  # a full multi-GB download can genuinely take a while

        if process.returncode == 0 and completed:
            self.root.after(0, lambda: self._decimer_download_done())
        else:
            error_text = "\n".join(other_lines[-10:]) or "Download failed for an unknown reason."
            self.root.after(0, lambda err=error_text: self._decimer_download_done(error=err))

    def _decimer_download_done(self, error=None):
        self._finish_progress_bar(success=not error)
        self.download_decimer_btn.config(state="normal")
        if error:
            self.image_status_label.config(text="Download failed.")
            messagebox.showerror("Download failed", error)
        else:
            self.image_status_label.config(text="DECIMER components ready.")
            messagebox.showinfo("Download complete", "DECIMER components are ready to use.")

    def on_choose_image(self):
        """Opens a file-picker dialog that allows selecting MULTIPLE
        images at once (up to the app's normal 200-entry batch size),
        remembers the last folder used, and shows a preview of the
        first one plus a count of how many were chosen."""
        paths = filedialog.askopenfilenames(
            title="Choose chemical structure image(s) - multiple selection allowed",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
            initialdir=self.last_directory,
        )
        if not paths:
            return
        self._remember_directory(paths[0])
        self._set_current_images(list(paths))

    def _set_current_images(self, paths):
        """Shared by the file-picker and drag-and-drop. paths is always
        a list now, even when it's just one image, so the rest of the
        app only has to handle one case."""
        self.current_image_paths = paths
        if len(paths) == 1:
            self.image_path_label.config(text=os.path.basename(paths[0]))
        else:
            self.image_path_label.config(text=f"{len(paths)} images selected")
        self.recognize_btn.config(state="normal")

        try:
            img = tk.PhotoImage(file=paths[0])
            max_dim = 220
            w, h = img.width(), img.height()
            factor = max(1, int(max(w, h) / max_dim))
            if factor > 1:
                img = img.subsample(factor, factor)
            self.image_preview_label.config(image=img, text="")
            self.image_preview_label.image = img
        except Exception:
            self.image_preview_label.config(image="", text="(preview unavailable for this file type)")

    def on_choose_pdf(self):
        """Opens a file-picker dialog for a PDF, then runs the full
        pipeline: render every page -> find structures on each page ->
        recognize each one."""
        path = filedialog.askopenfilename(
            title="Choose a PDF document",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=self.last_directory,
        )
        if not path:
            return
        self._remember_directory(path)
        self._start_pdf_scan(path)

    def _wire_up_drag_and_drop(self):
        """Registers the drop zone to accept dragged files, if the
        tkinterdnd2 package is available. If it isn't, the drop zone
        just sits there as a (non-functional) label - the Choose Image
        and Choose PDF buttons still work regardless."""
        if not _DND_AVAILABLE:
            self.drop_zone.config(text="(drag-and-drop unavailable - use the buttons above)")
            return
        self.drop_zone.drop_target_register(DND_FILES)
        self.drop_zone.dnd_bind("<<Drop>>", self.on_file_dropped)

    def on_file_dropped(self, event):
        """Called when files are dropped onto the drop zone. If any of
        them is a PDF, processes the first PDF found (one at a time,
        since each runs the full page-by-page pipeline). Otherwise,
        treats everything dropped as a batch of images."""
        # CONCEPT: dropped file paths arrive as a Tcl-formatted list
        # (paths with spaces get wrapped in curly braces) - splitlist()
        # is the correct way to parse that format back into a normal
        # Python list of plain strings.
        paths = list(self.root.tk.splitlist(event.data))
        if not paths:
            return

        pdf_paths = [p for p in paths if p.lower().endswith(".pdf")]
        if pdf_paths:
            self._start_pdf_scan(pdf_paths[0])
        else:
            self._remember_directory(paths[0])
            self._set_current_images(paths)

    def _start_pdf_scan(self, pdf_path):
        """Stage 1: finds every structure in the PDF (rendering pages,
        running Segmentation) but does NOT recognize any of them yet.
        Recognition is a separate, deliberate step the user triggers
        afterward, on whichever found structures they actually want."""
        if self.segmentation.dev_mode_missing:
            messagebox.showinfo(
                "Not yet built",
                "PDF scanning requires the compiled Segmentation engine, which "
                "doesn't exist yet because this is running from source, not as "
                "a built app. This is expected during development."
            )
            return
        if self.segmentation.load_error:
            messagebox.showerror("Not available", self.segmentation.load_error)
            return

        # Clear out any structures found by a previous scan, and their
        # scratch files - this scan replaces that one.
        self._cleanup_pdf_scratch_dir()
        for row in self.found_tree.get_children():
            self.found_tree.delete(row)
        self.found_structures = []
        self.recognize_found_btn.config(state="disabled")
        self.select_all_found_btn.config(state="disabled")

        self.pdf_source_name = os.path.basename(pdf_path)
        self.image_status_label.config(text="Scanning for structures...")
        self.image_progress.config(mode="indeterminate")
        self.image_progress.start(12)
        self.choose_image_btn.config(state="disabled")
        self.choose_pdf_btn.config(state="disabled")
        threading.Thread(target=self._run_pdf_scan, args=(pdf_path,), daemon=True).start()

    def _run_pdf_scan(self, pdf_path):
        """Runs on the BACKGROUND thread. Renders every page, then runs
        Segmentation ONCE across the whole batch of pages (not once per
        page - see find_all_structures for why that distinction matters
        for anything beyond a couple of pages). Each structure is
        streamed to the GUI immediately as it is found."""
        def status(msg):
            self.root.after(0, lambda: self.image_status_label.config(text=msg))

        try:
            # mkdtemp (not the `with tempfile.TemporaryDirectory()`
            # context-manager form) is used deliberately here: the crop
            # files need to keep existing AFTER this function returns,
            # so the user can come back later and choose to recognize
            # them - a context manager would delete them immediately.
            scratch_dir = tempfile.mkdtemp(prefix="opsinator_pdf_")
            self.pdf_scratch_dir = scratch_dir

            status("Scanning for structures...")
            page_dir = os.path.join(scratch_dir, "pages")
            page_paths = render_pdf_pages_to_images(pdf_path, page_dir, status_callback=status)
            pdf_basename = os.path.splitext(os.path.basename(pdf_path))[0]

            if not self.segmentation.is_loaded():
                raise RuntimeError(self.segmentation.load_error or "Segmentation engine not available")

            crop_dir = os.path.join(scratch_dir, "crops")

            def on_structure(structure):
                page_image_path = os.path.join(
                    page_dir, f"{pdf_basename}_page_{structure['page']}.png")
                label = find_label_near_bbox(
                    pdf_path, structure["page"] - 1, structure["bbox"],
                    page_image_path=page_image_path)
                item = {
                    "page": structure["page"],
                    "crop_path": structure["crop_path"],
                    "label": label,
                }
                self.root.after(0, lambda it=item: self._stream_found_structure(it))

            self.segmentation.find_all_structures(
                page_dir, crop_dir, total_pages=len(page_paths),
                on_structure_found=on_structure)

            self.root.after(0, self._pdf_scan_done)

        except Exception as e:
            self.root.after(0, lambda err=str(e): self._pdf_scan_done(error=err))

    def _stream_found_structure(self, item):
        """Runs on the MAIN thread for each structure as it is found
        during scanning - inserts it into the tree immediately rather
        than waiting until the full scan completes."""
        iid = str(len(self.found_structures))
        item["_tree_iid"] = iid
        self.found_structures.append(item)

        label = item["label"]
        display_label = label if label != "No label" else "No label (pending recognition)"
        self.found_tree.insert("", "end", iid=iid, values=(display_label, item["page"]))

        if len(self.found_structures) == 1:
            self.recognize_found_btn.config(state="normal")
            self.select_all_found_btn.config(state="normal")

        self.image_status_label.config(
            text=f"Found structure {label} on page {item['page']}")

    def _pdf_scan_done(self, error=None):
        """Runs on the MAIN thread once scanning has finished. By this
        point every structure has already been streamed into the tree
        by _stream_found_structure; this just finalizes the UI state."""
        self.choose_image_btn.config(state="normal" if self.decimer_enabled_var.get() else "disabled")
        self.choose_pdf_btn.config(state="normal" if self.decimer_enabled_var.get() else "disabled")

        if error:
            self._finish_progress_bar(success=False)
            self.image_status_label.config(text="Scan failed.")
            messagebox.showerror("PDF scan failed", error)
            return

        self._finish_progress_bar(success=True)
        count = len(self.found_structures)
        if count:
            self.image_status_label.config(text=f"{count} structure(s) found.")
            self.recognize_found_btn.config(state="normal")
            self.select_all_found_btn.config(state="normal")
        else:
            self.image_status_label.config(text="No structures found in this document.")

    def on_select_all_found(self):
        self.found_tree.selection_set(self.found_tree.get_children())

    def on_recognize_found(self):
        """Recognizes whichever found structures are selected - or, if
        none are selected, asks whether to recognize all of them rather
        than silently doing nothing or silently doing everything."""
        selected_ids = self.found_tree.selection()
        if not selected_ids:
            if not self.found_structures:
                return
            confirmed = messagebox.askyesno(
                "Recognize all?",
                f"No rows are selected. Recognize all {len(self.found_structures)} "
                "found structure(s)?"
            )
            if not confirmed:
                return
            selected_ids = self.found_tree.get_children()

        items = [self.found_structures[int(i)] for i in selected_ids]

        self.recognize_found_btn.config(state="disabled")
        self.image_progress.config(mode="indeterminate")
        self.image_progress.start(12)
        self.image_status_label.config(text="Preparing...")
        threading.Thread(target=self._run_found_recognition, args=(items,), daemon=True).start()

    def _run_found_recognition(self, items):
        """Runs on the BACKGROUND thread. Recognizes only the specific
        found structures passed in, adding each to the main results
        table as it finishes."""
        def status_cb(msg):
            self.root.after(0, lambda: self.image_status_label.config(text=msg))
            self.root.after(0, lambda: self._update_progress_from_status(msg))

        if self.decimer.dev_mode_missing:
            self.root.after(0, lambda: self._found_recognition_done(
                dev_mode_note="Recognition requires the compiled DECIMER engine, which "
                              "doesn't exist yet because this is running from source, not "
                              "as a built app. This is expected during development."))
            return
        if self.decimer.load_error:
            self.root.after(0, lambda: self._found_recognition_done(
                error=f"Could not load image recognition engine: {self.decimer.load_error}"))
            return

        total = len(items)
        for i, item in enumerate(items, start=1):
            self.root.after(0, lambda i=i, total=total, page=item["page"]: self.image_status_label.config(
                text=f"Recognizing {i} of {total} (page {page})..."))
            label = item.get("label", "No label")
            try:
                smiles = self.decimer.predict(item["crop_path"], status_callback=status_cb)
                # For unlabeled structures, try PubChem for an IUPAC name.
                if smiles and (not label or label == "No label"):
                    pubchem_name = _lookup_iupac_pubchem(smiles)
                    if pubchem_name:
                        label = pubchem_name
                        iid = item.get("_tree_iid")
                        if iid is not None:
                            self.root.after(0, lambda iid=iid, n=pubchem_name:
                                            self._update_found_label(iid, n))
                if label and label != "No label":
                    source_name = f"{label} | Page {item['page']}"
                else:
                    source_name = f"{self.pdf_source_name} - No label | Page {item['page']}"
                self.root.after(0, lambda src=source_name, s=smiles: self._add_image_result(src, s))
            except Exception as e:
                if label and label != "No label":
                    source_name = f"{label} | Page {item['page']}"
                else:
                    source_name = f"{self.pdf_source_name} - No label | Page {item['page']}"
                self.root.after(0, lambda src=source_name, err=str(e): self._add_image_result(src, "", error=err))

        self.root.after(0, lambda: self._found_recognition_done(total=total))

    def _found_recognition_done(self, total=0, dev_mode_note=None, error=None):
        self.recognize_found_btn.config(state="normal")
        if dev_mode_note:
            self._finish_progress_bar(success=False)
            messagebox.showinfo("Not yet built", dev_mode_note)
            return
        if error:
            self._finish_progress_bar(success=False)
            self.image_status_label.config(text="Failed.")
            messagebox.showerror("Recognition failed", error)
            return
        self._finish_progress_bar(success=True)
        self.image_status_label.config(text=f"Done. Recognized {total} structure(s).")

    def _update_found_label(self, iid: str, name: str):
        """Updates the label shown in the found-structures tree row and
        the in-memory list. Called on the MAIN thread after PubChem
        returns an IUPAC name for a previously unlabeled structure."""
        try:
            self.found_tree.set(iid, column="label", value=name)
        except Exception:
            pass
        try:
            idx = int(iid)
            if 0 <= idx < len(self.found_structures):
                self.found_structures[idx]["label"] = name
        except (ValueError, IndexError):
            pass

    def _cleanup_pdf_scratch_dir(self):
        """Deletes the temporary folder holding the current scan's
        rendered pages and crops, if one exists."""
        if self.pdf_scratch_dir and os.path.isdir(self.pdf_scratch_dir):
            shutil.rmtree(self.pdf_scratch_dir, ignore_errors=True)
        self.pdf_scratch_dir = None

    def _add_image_result(self, source_name, smiles, error=None):
        """Adds one row to the persistent image-results table and list -
        shared by the single-image flow, batch image flow, and the PDF
        pipeline. If error is given, the row shows that instead of a
        SMILES, so a failed item in a batch is visible, not silently
        dropped."""
        display_smiles = smiles or (f"(failed: {error})" if error else "")
        record = {"source": source_name, "smiles": smiles or ""}
        self.image_results.append(record)
        self.image_tree.insert("", "end", values=(record["source"], display_smiles))

        has_results = any(r.get("smiles") for r in self.image_results)
        self.image_save_csv_btn.config(state="normal" if self.image_results else "disabled")
        self.image_save_sdf_btn.config(state="normal" if has_results else "disabled")
        self.image_save_mol_btn.config(state="normal" if has_results else "disabled")
        self.copy_smiles_btn.config(state="normal" if has_results else "disabled")

    def on_recognize_image(self):
        """Starts image recognition on a background thread, the same way
        on_convert() does for the Name tab - so the (potentially slow,
        first-run) DECIMER loading never freezes the window. Processes
        every selected image in sequence, not just one."""
        if not self.current_image_paths:
            return
        self.recognize_btn.config(state="disabled")
        self.image_progress.config(mode="indeterminate")
        self.image_progress.start(12)  # start the indeterminate "bouncing" animation
        self.image_status_label.config(text="Preparing...")
        threading.Thread(target=self._run_image_recognition, daemon=True).start()

    def _run_image_recognition(self):
        """Runs on the BACKGROUND thread. Loops over every image that
        was selected, adding each result to the table as it finishes -
        one failed image doesn't stop the rest of the batch."""
        def status_cb(msg):
            # Same pattern as elsewhere: hop back to the main thread
            # before touching any widget.
            self.root.after(0, lambda: self.image_status_label.config(text=msg))
            self.root.after(0, lambda: self._update_progress_from_status(msg))

        if self.decimer.dev_mode_missing:
            self.root.after(0, lambda: self._image_recognition_done(
                dev_mode_note="Recognition requires the compiled DECIMER engine, which "
                              "doesn't exist yet because this is running from source, not "
                              "as a built app. This is expected during development."))
            return

        if not self.decimer.is_loaded():
            self.decimer.ensure_loaded(status_callback=status_cb)

        if self.decimer.load_error:
            self.root.after(0, lambda: self._image_recognition_done(
                error=f"Could not load image recognition engine: {self.decimer.load_error}"))
            return

        total = len(self.current_image_paths)
        succeeded = 0
        failed_names = []

        for i, path in enumerate(self.current_image_paths, start=1):
            name = os.path.basename(path)
            if total > 1:
                self.root.after(0, lambda i=i, total=total, name=name: self.image_status_label.config(
                    text=f"Recognizing {i} of {total}: {name}..."))
            else:
                self.root.after(0, lambda: self.image_status_label.config(text="Recognizing structure..."))

            try:
                smiles = self.decimer.predict(path, status_callback=status_cb)
                self.root.after(0, lambda n=name, s=smiles: self._add_image_result(n, s))
                succeeded += 1
            except Exception as e:
                failed_names.append(name)
                self.root.after(0, lambda n=name, err=str(e): self._add_image_result(n, "", error=err))

        self.root.after(0, lambda: self._image_recognition_done(
            succeeded=succeeded, total=total, failed_names=failed_names))

    def _image_recognition_done(self, succeeded=0, total=0, failed_names=None, dev_mode_note=None, error=None):
        """Runs back on the MAIN thread (via root.after above) once the
        whole batch has finished, succeeded or failed."""
        self.recognize_btn.config(state="normal")
        if dev_mode_note:
            self._finish_progress_bar(success=False)
            self.image_status_label.config(text="Not available in source mode.")
            messagebox.showinfo("Not yet built", dev_mode_note)
            return
        if error:
            self._finish_progress_bar(success=False)
            self.image_status_label.config(text="Failed.")
            messagebox.showerror("Recognition failed", error)
            return

        self._finish_progress_bar(success=True)
        if total > 1:
            note = f"Done. {succeeded} of {total} recognized successfully."
            if failed_names:
                note += f" Failed: {', '.join(failed_names[:5])}" + ("..." if len(failed_names) > 5 else "")
            self.image_status_label.config(text=note)
        else:
            self.image_status_label.config(text="Done." if not failed_names else "Failed.")

    def on_copy_smiles(self):
        """Copies SMILES from every selected row in the image results
        table (newline-separated when multiple are selected), or the
        most recently recognized one if nothing is selected."""
        selected = self.image_tree.selection()
        if selected:
            smiles_list = [
                self.image_tree.item(iid, "values")[1]
                for iid in selected
            ]
            value = "\n".join(s for s in smiles_list if s and not s.startswith("(failed"))
        elif self.image_results:
            value = self.image_results[-1]["smiles"]
        else:
            return
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)

    def on_save_image_mol(self):
        """Saves either the selected image result or all of them as MOL
        file(s), using the same scope-choice dialog as the Name tab."""
        usable = [r for r in self.image_results if r.get("smiles")]
        if not usable:
            messagebox.showwarning("Nothing to export", "No recognized structures to export.")
            return

        selected = self.image_tree.selection()

        scope = ask_save_scope(self.root, len(usable))
        if scope is None:
            return
        if scope == "selected" and not selected:
            messagebox.showinfo("Select a row", "Click a row in the table first, then try again.")
            return

        def proceed():
            if scope == "selected":
                values = self.image_tree.item(selected[0], "values")
                source, smiles = values[0], values[1]
                if not smiles or smiles.startswith("(failed"):
                    messagebox.showwarning("No structure", "The selected row has no usable SMILES.")
                    return
                try:
                    molblock = self.mol_converter.smiles_to_molblock(smiles, title=source)
                except Exception as e:
                    messagebox.showerror("Conversion failed", str(e))
                    return
                path = filedialog.asksaveasfilename(
                    defaultextension=".mol",
                    filetypes=[("MOL files", "*.mol")],
                    initialfile="structure.mol",
                    initialdir=self.last_directory,
                )
                if not path:
                    return
                self._remember_directory(path)
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(molblock)
                    messagebox.showinfo("Saved", f"Structure saved to:\n{path}")
                except Exception as e:
                    messagebox.showerror("Error saving file", str(e))

            else:  # scope == "all"
                folder = filedialog.askdirectory(title="Choose a folder for the MOL files",
                                                  initialdir=self.last_directory)
                if not folder:
                    return
                self._remember_directory(folder)

                saved_count = 0
                failed_sources = []
                used_filenames = set()
                for r in usable:
                    try:
                        molblock = self.mol_converter.smiles_to_molblock(
                            r["smiles"], title=r["source"])
                    except Exception:
                        failed_sources.append(r["source"])
                        continue
                    base = sanitize_filename(r["source"])
                    filename = f"{base}.mol"
                    counter = 2
                    while filename in used_filenames:
                        filename = f"{base}_{counter}.mol"
                        counter += 1
                    used_filenames.add(filename)
                    try:
                        with open(os.path.join(folder, filename), "w", encoding="utf-8") as f:
                            f.write(molblock)
                        saved_count += 1
                    except Exception:
                        failed_sources.append(r["source"])

                note = f"{saved_count} structure(s) saved to:\n{folder}"
                if failed_sources:
                    note += f"\n\n{len(failed_sources)} could not be converted and were skipped."
                messagebox.showinfo("Saved", note)

        self._ensure_rdkit_then(proceed, self.image_status_label, self.image_progress)

    def on_save_image_csv(self):
        """Exports every recognized image result this session as a
        simple two-column .csv file."""
        if not self.image_results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="decimer_results.csv",
            initialdir=self.last_directory,
        )
        if not path:
            return
        self._remember_directory(path)
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["source", "smiles"])
                writer.writeheader()
                writer.writerows(self.image_results)
            messagebox.showinfo("Saved", f"Results saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error saving file", str(e))

    def on_save_image_sdf(self):
        """Exports every recognized image result this session as one
        multi-record SDF structure file."""
        usable = [r for r in self.image_results if r.get("smiles")]
        if not usable:
            messagebox.showwarning("Nothing to export", "No recognized structures to export.")
            return

        def proceed():
            records = []
            for r in usable:
                try:
                    molblock = self.mol_converter.smiles_to_molblock(r["smiles"], title=r["source"])
                    records.append((molblock, {"Source image": r["source"]}))
                except Exception:
                    continue  # CONCEPT: `continue` skips straight to the next loop iteration

            if not records:
                messagebox.showwarning("Nothing to export",
                                        "None of the predicted SMILES could be converted to a structure.")
                return

            path = filedialog.asksaveasfilename(
                defaultextension=".sdf",
                filetypes=[("SDF files", "*.sdf")],
                initialfile="decimer_results.sdf",
                initialdir=self.last_directory,
            )
            if not path:
                return
            self._remember_directory(path)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(build_sdf(records))
                skipped = len(usable) - len(records)
                note = f"{len(records)} structure(s) saved to:\n{path}"
                if skipped:
                    note += f"\n\n{skipped} could not be converted and were skipped."
                messagebox.showinfo("Saved", note)
            except Exception as e:
                messagebox.showerror("Error saving file", str(e))

        self._ensure_rdkit_then(proceed, self.image_status_label, self.image_progress)

    # ---------------- patent activity tab handlers ----------------

    def on_activity_load(self):
        path = filedialog.askopenfilename(
            title="Select patent PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
            initialdir=getattr(self, "last_directory", None) or os.path.expanduser("~"),
        )
        if not path:
            return
        self._remember_directory(path)
        self._activity_pdf_path = path
        self.activity_pdf_label.config(text=f"PDF: {os.path.basename(path)}")
        self.activity_run_btn.config(state="normal")
        self.activity_status_label.config(text="Ready — click Extract & Convert.")

    def on_activity_run(self):
        if not self._activity_pdf_path:
            return
        self.activity_tree.delete(*self.activity_tree.get_children())
        self._activity_results = []
        self.activity_save_btn.config(state="disabled")
        self.activity_load_btn.config(state="disabled")
        self.activity_run_btn.config(state="disabled")
        self.activity_status_label.config(text="Parsing PDF…")
        self.activity_progress.config(mode="indeterminate", value=0)
        self.activity_progress.start(10)
        self._activity_queue = queue.Queue()
        threading.Thread(
            target=self._run_activity_extraction,
            args=(self._activity_pdf_path,),
            daemon=True,
        ).start()
        self._poll_activity_queue()

    def _run_activity_extraction(self, pdf_path):
        try:
            rows = parse_activity_table(pdf_path)
            if not rows:
                self._activity_queue.put(("error", "No activity table found in PDF."))
                return
            self._activity_queue.put(("parsed", len(rows)))
            for i, row in enumerate(rows, start=1):
                result = fetch_opsin(row["clean_name"])
                row["smiles"]  = result.get("smiles", "")
                row["status"]  = result.get("status", "ERROR")
                row["message"] = result.get("message", "")
                self._activity_queue.put(("row", i, len(rows), row))
            self._activity_queue.put(("done", len(rows)))
        except Exception as e:
            self._activity_queue.put(("error", str(e)))

    def _poll_activity_queue(self):
        try:
            while True:
                msg = self._activity_queue.get_nowait()
                kind = msg[0]
                if kind == "parsed":
                    n = msg[1]
                    self.activity_status_label.config(
                        text=f"Parsed {n} entries — converting names via OPSIN…")
                    self.activity_progress.stop()
                    self.activity_progress.config(mode="determinate", maximum=n, value=0)
                elif kind == "row":
                    _, i, total, row = msg
                    self._activity_results.append(row)
                    ex_label = f"{row['example']}{row.get('example_suffix', '')}"
                    smiles_display = (row["smiles"]
                                      if row["smiles"]
                                      else f"({row['message'][:40]})")
                    self.activity_tree.insert("", "end", values=(
                        ex_label,
                        row["clean_name"],
                        row["ic50"],
                        smiles_display,
                        row["status"],
                        row["page"],
                    ))
                    self.activity_tree.yview_moveto(1.0)
                    self.activity_progress.config(value=i)
                    self.activity_status_label.config(
                        text=f"Converting… {i}/{total}  (Example {ex_label})")
                elif kind == "done":
                    total = msg[1]
                    ok   = sum(1 for r in self._activity_results if r["smiles"])
                    fail = total - ok
                    self.activity_status_label.config(
                        text=f"Done: {total} entries — {ok} SMILES resolved, {fail} failed.")
                    self.activity_progress.config(value=total)
                    self.activity_load_btn.config(state="normal")
                    self.activity_run_btn.config(state="normal")
                    if self._activity_results:
                        self.activity_save_btn.config(state="normal")
                    return
                elif kind == "error":
                    messagebox.showerror("Extraction error", msg[1])
                    self.activity_progress.stop()
                    self.activity_progress.config(mode="determinate", value=0)
                    self.activity_load_btn.config(state="normal")
                    self.activity_run_btn.config(state="normal")
                    return
        except queue.Empty:
            pass
        self.root.after(100, self._poll_activity_queue)

    def on_activity_save_csv(self):
        if not self._activity_results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="patent_activity.csv",
            initialdir=getattr(self, "last_directory", None) or os.path.expanduser("~"),
        )
        if not path:
            return
        self._remember_directory(path)
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "Example #", "Compound Name (OPSIN input)", "Raw Name (PDF extracted)",
                    "IC50 (nM)", "n Replicates",
                    "SMILES", "Status", "Message", "Source Page",
                    "Salt Form", "Stereo Note", "Handling Notes",
                ])
                for r in self._activity_results:
                    ex_label = f"{r['example']}{r.get('example_suffix', '')}"
                    notes    = "; ".join(r.get("handling_notes", []))
                    writer.writerow([
                        ex_label, r["clean_name"], r["name"], r["ic50"], r.get("rep", ""),
                        r["smiles"], r["status"], r["message"], r["page"],
                        r.get("salt_form", ""), r.get("stereo_note", ""), notes,
                    ])
            messagebox.showinfo("Saved",
                                f"{len(self._activity_results)} rows saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error saving file", str(e))


def main():
    """The program's entry point - the very first thing that runs.

    CONCEPT: Wrapping the startup logic in a function called main(), and
    only calling it inside an `if __name__ == "__main__":` guard at the
    bottom of the file, is a long-standing Python convention. It means
    this file can also be safely *imported* by some other program without
    automatically launching the GUI - the GUI only starts if this file is
    run directly.
    """
    # TkinterDnD.Tk() is a drop-in replacement for tk.Tk() that adds
    # drag-and-drop capability to the whole window. If the package
    # isn't available, plain tk.Tk() works exactly as it always has -
    # the only difference is the drop zone won't accept drags.
    root = TkinterDnD.Tk() if _DND_AVAILABLE else tk.Tk()
    root.withdraw()        # ...but hide it immediately, until the license is accepted

    def launch_app():
        root.deiconify()   # un-hide the main window
        OpsinatorApp(root)  # build everything inside it

    def decline():
        root.destroy()     # close the window and end the program entirely

    if is_license_accepted():
        # Already agreed to the license on a previous run - skip straight
        # to the real app.
        launch_app()
    else:
        # First run on this computer (or the marker file was deleted) -
        # show the dialog and only proceed if/when it's accepted.
        show_license_dialog(root, on_accept=launch_app, on_decline=decline)

    # CONCEPT: `root.mainloop()` hands control over to tkinter itself.
    # From this point on, tkinter is in charge: it waits for clicks,
    # keypresses, and timer events (like our root.after calls), and
    # calls our functions in response. This call doesn't return until
    # the window is closed.
    root.mainloop()


if __name__ == "__main__":
    # CONCEPT: `__name__` is a special built-in variable that Python sets
    # automatically. It equals "__main__" only when this specific file is
    # the one that was launched directly (e.g. `python opsinator.py`) -
    # not when it's imported as a module from somewhere else. This guard
    # is the standard way to say "only do this if I'm being run directly."
    main()
