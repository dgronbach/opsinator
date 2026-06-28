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
import importlib.metadata   # Lets us ask "what version of package X is installed?"
import json                 # Converting between Python dictionaries and JSON text
import math                 # Trigonometry functions (sin, cos) used by the animation
import os                   # Talking to the operating system: file paths, folders, etc.
import queue                # A thread-safe "to-do list" used to pass messages between threads
import subprocess           # Launching the separate DECIMER engine program
import sys                  # Information about how this program is being run
import threading            # Lets us run code in the background, without freezing the GUI
import tkinter as tk        # tkinter is Python's built-in GUI (graphical window) toolkit
import urllib.error         # Specific error types that can happen when fetching a URL
import urllib.parse         # Helpers for safely building URLs out of text
import urllib.request       # Lets Python make HTTP requests to web servers
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

    # `transient(root)` tells the operating system "this window belongs
    # to root" (so it minimizes/restores together with it, for example).
    dialog.transient(root)

    # `grab_set()` makes this dialog "modal" - the user can't click on
    # the main window behind it until this dialog is closed.
    dialog.grab_set()

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
        # The server responded, but with an error status code (like 404
        # Not Found or 500 Server Error). e.code holds that number.
        return {"name": name, "status": "ERROR", "smiles": "", "inchikey": "",
                 "message": f"HTTP {e.code}"}

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
        self._engine_path = self._find_engine_executable()
        if self._engine_path is None:
            self.load_error = (
                "Could not find the OPSINator DECIMER Engine executable. "
                "It should be installed alongside this app."
            )

    def _find_engine_executable(self):
        """Looks for the engine executable in the same folder as this
        app. Returns its full path, or None if it isn't there.

        CONCEPT: sys.executable is the path to the currently running
        program when this app itself has been frozen into an exe by
        PyInstaller/Nuitka. os.path.dirname() then gives us the folder
        it lives in, so we can look for a sibling file right next to it.
        """
        if getattr(sys, "frozen", False):
            app_dir = os.path.dirname(sys.executable)
        else:
            app_dir = os.path.dirname(os.path.abspath(__file__))

        candidates = [
            os.path.join(app_dir, "opsinator_engine.exe"),   # Windows
            os.path.join(app_dir, "opsinator_engine"),         # Linux / macOS
        ]
        for path in candidates:
            if os.path.isfile(path):
                return path
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

    def predict(self, image_path: str) -> str:
        """Runs image recognition by launching the separate engine
        program as a subprocess and reading its output, instead of
        calling a function inside this process."""
        if self._engine_path is None:
            raise RuntimeError(self.load_error or "DECIMER engine not found")

        # CONCEPT: subprocess.run() starts another program, waits for it
        # to finish, and hands back what it printed. capture_output=True
        # captures both its normal output (stdout) and any error
        # messages (stderr) instead of letting them print to this app's
        # own console.
        result = subprocess.run(
            [self._engine_path, image_path],
            capture_output=True,
            text=True,
            timeout=300,  # generous ceiling - first-run model download can be slow
        )

        if result.returncode != 0:
            error_text = result.stderr.strip() or "Unknown error from DECIMER engine"
            raise RuntimeError(error_text)

        return result.stdout.strip()


def check_decimer_update() -> dict:
    """Compares the installed 'decimer' package version against the
    latest one published on PyPI (the Python Package Index, the official
    place Python packages are published). Returns a dictionary describing
    what it found. This function is careful never to raise an exception -
    any network or parsing problem is reported inside the returned
    dictionary as an "error" entry instead.
    """
    result = {"installed": None, "latest": None, "update_available": False, "error": None}

    try:
        # importlib.metadata.version() asks Python's own package manager
        # "what version of this package is currently installed?" without
        # needing to actually import (and therefore load TensorFlow) the
        # package itself.
        result["installed"] = importlib.metadata.version("decimer")
    except importlib.metadata.PackageNotFoundError:
        # The package genuinely isn't installed in this build at all.
        result["installed"] = None
    except Exception as e:
        result["error"] = str(e)
        return result  # CONCEPT: an early `return` lets us stop a function partway through

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

    def ensure_loaded(self):
        if self._Chem is not None or self.load_error is not None:
            return
        try:
            from rdkit import Chem
            from rdkit.Chem import AllChem
            self._Chem = Chem
            self._AllChem = AllChem
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
        self.mol_converter = MolConverter()

        # --- state for the Image -> Structure tab ---
        self.current_image_path = None
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
        result = check_decimer_update()
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
        result = check_decimer_update()
        self.root.after(0, lambda: self._handle_update_result(result, silent=False))

    def _handle_update_result(self, result, silent):
        """Shared logic for both the silent startup check and the manual
        Help-menu check. `silent=True` means: update the status bar text
        quietly, but never interrupt the user with a pop-up dialog."""
        if result.get("error") and not silent:
            self.status_label2.config(text="Could not check for updates (offline?).")
            return
        if result.get("error"):
            return  # silent check failed - just say nothing rather than alarm anyone

        if result["installed"] is None:
            if not silent:
                self.status_label2.config(text="DECIMER not yet installed in this build.")
            return

        if result["update_available"]:
            msg = (f"A newer DECIMER engine is available "
                   f"(installed: {result['installed']}, latest: {result['latest']}).")
            self.status_label2.config(text=msg)
            if not silent:
                messagebox.showinfo(
                    "Update available",
                    msg + "\n\nThis app cannot update itself automatically. "
                          "Ask your sysadmin to rebuild OPSINator with the "
                          "newer decimer package version when convenient."
                )
        else:
            self.status_label2.config(text=f"DECIMER engine up to date (v{result['installed']}).")
            if not silent:
                messagebox.showinfo("Up to date", f"DECIMER v{result['installed']} is the latest version.")

    # ---------------- main UI ----------------

    def _build_ui(self):
        """Builds the two-tab layout (Name -> Structure, Image -> Structure)
        plus the thin status bar along the very bottom of the window."""
        # ttk.Notebook is tkinter's "tabbed panel" widget - each tab is
        # really just a regular Frame that gets shown or hidden.
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        name_tab = tk.Frame(notebook)
        image_tab = tk.Frame(notebook)
        notebook.add(name_tab, text="Name -> Structure")
        notebook.add(image_tab, text="Image -> Structure")

        self._build_name_tab(name_tab)
        self._build_image_tab(image_tab)

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
            self.tree.heading(col, text=headings[col])
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

        btn_row = tk.Frame(parent)
        btn_row.pack(fill="x", **pad)

        tk.Button(btn_row, text="Choose Image...", command=self.on_choose_image,
                  width=16).pack(side="left", padx=(0, 8))
        self.recognize_btn = tk.Button(btn_row, text="Recognize Structure",
                                        command=self.on_recognize_image, width=18,
                                        state="disabled")
        self.recognize_btn.pack(side="left", padx=(0, 8))

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

        # A persistent table of everything recognized so far this
        # session, so results don't disappear the moment you process a
        # second image.
        results_frame = tk.LabelFrame(parent, text="Recognized structures (this session)")
        results_frame.pack(fill="both", expand=True, padx=10, pady=10)

        img_columns = ("source", "smiles")
        self.image_tree = ttk.Treeview(results_frame, columns=img_columns, show="headings", height=8)
        self.image_tree.heading("source", text="Image file")
        self.image_tree.heading("smiles", text="Predicted SMILES")
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

        note = ("Note: image recognition runs locally using the DECIMER model. The first "
                "time this is used on a machine, required components (roughly 1-2 GB) are "
                "downloaded automatically into your own user profile - no admin rights needed. "
                "After that, it runs offline. Always visually check predicted structures "
                "against the source image before relying on them.")
        tk.Label(parent, text=note, wraplength=600, justify="left",
                 fg="#777777", font=("Segoe UI", 8)).pack(anchor="w", padx=10, pady=(0, 10))

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
        for i, name in enumerate(names, start=1):
            # CONCEPT: enumerate(names, start=1) walks through the list
            # while also handing you a running count, starting at 1
            # instead of the default 0 - handy for "item 1 of 5" style
            # progress messages.
            result = fetch_opsin(name)
            self.ui_queue.put(("row", i, len(names), result))
        self.ui_queue.put(("done", len(names)))

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
        )
        if not path:
            return  # user clicked Cancel on the save dialog

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

    def on_save_mol(self):
        """Saves a single structure file (.mol) for the currently
        selected row in the table. MOL files hold exactly one structure -
        use Save SDF for the whole batch."""
        selected = self.tree.selection()  # returns a tuple of selected row IDs
        if not selected:
            messagebox.showinfo("Select a row", "Click a row in the table first, then Save MOL.")
            return

        # tree.item(row_id, "values") gives back the same tuple of values
        # we originally inserted for that row.
        values = self.tree.item(selected[0], "values")
        name, status, smiles = values[0], values[1], values[2]
        if not smiles:
            messagebox.showwarning("No structure", f"'{name}' has no SMILES to convert "
                                                     f"(status: {status}).")
            return

        self.mol_converter.ensure_loaded()
        if self.mol_converter.load_error:
            messagebox.showerror("Chemistry toolkit unavailable",
                                  f"Could not load RDKit: {self.mol_converter.load_error}")
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
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(molblock)
            messagebox.showinfo("Saved", f"Structure saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error saving file", str(e))

    def on_save_sdf(self):
        """Saves every successfully-converted result as one multi-record
        SDF file - the standard format for a batch of structures."""
        usable = [r for r in self.results if r.get("smiles") and r["status"] in ("SUCCESS", "WARNING")]
        skipped = len(self.results) - len(usable)
        if not usable:
            messagebox.showwarning("Nothing to export", "None of the results have a usable structure.")
            return

        self.mol_converter.ensure_loaded()
        if self.mol_converter.load_error:
            messagebox.showerror("Chemistry toolkit unavailable",
                                  f"Could not load RDKit: {self.mol_converter.load_error}")
            return

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
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(build_sdf(records))
            note = f"{len(records)} structure(s) saved to:\n{path}"
            if skipped or failed_conversions:
                note += f"\n\n{skipped + len(failed_conversions)} row(s) were skipped (no usable structure)."
            messagebox.showinfo("Saved", note)
        except Exception as e:
            messagebox.showerror("Error saving file", str(e))

    # ---------------- image tab handlers ----------------

    def on_choose_image(self):
        """Opens a file-picker dialog, remembers the chosen image path,
        and shows a small preview thumbnail."""
        path = filedialog.askopenfilename(
            title="Choose a chemical structure image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif"), ("All files", "*.*")],
        )
        if not path:
            return

        self.current_image_path = path
        self.image_path_label.config(text=os.path.basename(path))
        self.recognize_btn.config(state="normal")

        try:
            img = tk.PhotoImage(file=path)
            max_dim = 220
            w, h = img.width(), img.height()
            # `.subsample(n, n)` shrinks an image by keeping only every
            # nth pixel in each direction - a simple (if a little crude)
            # way to make a quick thumbnail without extra libraries.
            factor = max(1, int(max(w, h) / max_dim))
            if factor > 1:
                img = img.subsample(factor, factor)
            self.image_preview_label.config(image=img, text="")
            # CONCEPT: tkinter doesn't keep its own reference to images,
            # so if we don't store `img` somewhere (here, as an attribute
            # on the label widget itself), Python's garbage collector
            # would clean it up and the picture would vanish from screen.
            # Assigning it to `.image` is the standard workaround.
            self.image_preview_label.image = img
        except Exception:
            self.image_preview_label.config(image="", text="(preview unavailable for this file type)")

    def on_recognize_image(self):
        """Starts image recognition on a background thread, the same way
        on_convert() does for the Name tab - so the (potentially slow,
        first-run) DECIMER loading never freezes the window."""
        if not self.current_image_path:
            return
        self.recognize_btn.config(state="disabled")
        self.image_progress.start(12)  # start the indeterminate "bouncing" animation
        self.image_status_label.config(text="Preparing...")
        threading.Thread(target=self._run_image_recognition, daemon=True).start()

    def _run_image_recognition(self):
        """Runs on the BACKGROUND thread."""
        def status_cb(msg):
            # Same pattern as elsewhere: hop back to the main thread
            # before touching any widget.
            self.root.after(0, lambda: self.image_status_label.config(text=msg))

        if not self.decimer.is_loaded():
            self.decimer.ensure_loaded(status_callback=status_cb)

        if self.decimer.load_error:
            self.root.after(0, lambda: self._image_recognition_done(
                error=f"Could not load image recognition engine: {self.decimer.load_error}"))
            return

        self.root.after(0, lambda: self.image_status_label.config(text="Recognizing structure..."))
        try:
            smiles = self.decimer.predict(self.current_image_path)
            self.root.after(0, lambda: self._image_recognition_done(smiles=smiles))
        except Exception as e:
            self.root.after(0, lambda: self._image_recognition_done(error=str(e)))

    def _image_recognition_done(self, smiles=None, error=None):
        """Runs back on the MAIN thread (via root.after above) once
        recognition has either succeeded or failed. Appends a successful
        result to the persistent session list, rather than overwriting a
        single field - so a second image doesn't erase the first one."""
        self.image_progress.stop()
        self.recognize_btn.config(state="normal")
        if error:
            self.image_status_label.config(text="Failed.")
            messagebox.showerror("Recognition failed", error)
            return
        self.image_status_label.config(text="Done.")

        source_name = os.path.basename(self.current_image_path) if self.current_image_path else ""
        record = {"source": source_name, "smiles": smiles or ""}
        self.image_results.append(record)
        self.image_tree.insert("", "end", values=(record["source"], record["smiles"]))

        has_results = bool(self.image_results)
        self.image_save_csv_btn.config(state="normal" if has_results else "disabled")
        self.image_save_sdf_btn.config(state="normal" if has_results else "disabled")
        self.copy_smiles_btn.config(state="normal" if has_results else "disabled")

    def on_copy_smiles(self):
        """Copies the SMILES from whichever row is selected in the image
        results table - or, if nothing's selected, the most recently
        recognized one - onto the clipboard."""
        selected = self.image_tree.selection()
        if selected:
            value = self.image_tree.item(selected[0], "values")[1]
        elif self.image_results:
            value = self.image_results[-1]["smiles"]  # [-1] means "the last item in the list"
        else:
            return
        if not value:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(value)

    def on_save_image_csv(self):
        """Exports every recognized image result this session as a
        simple two-column .csv file."""
        if not self.image_results:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile="decimer_results.csv",
        )
        if not path:
            return
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

        self.mol_converter.ensure_loaded()
        if self.mol_converter.load_error:
            messagebox.showerror("Chemistry toolkit unavailable",
                                  f"Could not load RDKit: {self.mol_converter.load_error}")
            return

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
        )
        if not path:
            return
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


def main():
    """The program's entry point - the very first thing that runs.

    CONCEPT: Wrapping the startup logic in a function called main(), and
    only calling it inside an `if __name__ == "__main__":` guard at the
    bottom of the file, is a long-standing Python convention. It means
    this file can also be safely *imported* by some other program without
    automatically launching the GUI - the GUI only starts if this file is
    run directly.
    """
    root = tk.Tk()        # creates the actual operating-system window
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
