"""Where this computer keeps your own data: settings, master resume, instructions, keys, the postings database and
the files the app writes. Never the app folder, so the code can be shared, updated or deleted without touching it.

By default it is %LOCALAPPDATA%\\WildThing (on other systems ~/.local/share/WildThing). You can choose another folder
in Settings; the files move with it, and a small location.json in the default folder remembers where they went.
With Google linked, the shared copy lives in the WildThing folder in your Drive (gdrive.py); this is the working copy.
"""
import json
import os
import shutil

import db
import settings
import writer

APP_FOLDER = os.path.dirname(os.path.abspath(__file__))
DEFAULT = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(os.path.expanduser("~"), ".local", "share"),
                       "WildThing")
POINTER = "location.json"
# Everything personal, as it sits in the data folder (the same names older copies kept beside the app).
ITEMS = ("data", "jobs.db", "keys.local.json", "output", "requests", "replies", "AI_INSTRUCTIONS.md")

ROOT = None             # set by start(); None while tests or tools import the modules


def _pointer_path():
    return os.path.join(DEFAULT, POINTER)


def chosen():
    """The data folder: the one chosen in Settings, else the default."""
    try:
        with open(_pointer_path(), encoding="utf-8") as f:
            p = json.load(f).get("path")
    except (OSError, ValueError, AttributeError):
        p = None
    return p if p and os.path.isabs(p) else DEFAULT


def use(root):
    """Points every module at one data folder."""
    global ROOT
    os.makedirs(root, exist_ok=True)
    ROOT = root
    settings.DATA_DIR = os.path.join(root, "data")
    db.DB_PATH = os.path.join(root, "jobs.db")
    writer.BASE = root


def _move_items(src, dst, only_missing):
    moved = []
    for name in ITEMS:
        a, b = os.path.join(src, name), os.path.join(dst, name)
        if not os.path.exists(a) or (only_missing and os.path.exists(b)):
            continue
        shutil.move(a, b)
        moved.append(name)
    return moved


def start():
    """At app start: use the chosen folder, first moving in anything an older copy left in the app folder."""
    root = chosen()
    os.makedirs(root, exist_ok=True)
    moved = _move_items(APP_FOLDER, root, only_missing=True)
    use(root)
    return root, moved


def _inside(path, folder):
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return path == folder or path.startswith(folder.rstrip("\\/") + os.sep)


def move_to(new):
    """Moves the data to another folder and remembers it. Returns a message. Close database connections first."""
    new = os.path.abspath(os.path.expanduser((new or "").strip())) if (new or "").strip() else DEFAULT
    old = ROOT or chosen()
    if os.path.normcase(new) == os.path.normcase(os.path.abspath(old)):
        return "Your data is already there."
    if _inside(new, APP_FOLDER):
        raise ValueError("Choose a folder outside the app folder, so your data is never shared with the code.")
    if _inside(new, old) or _inside(old, new):
        raise ValueError("Choose a folder that is not inside the current one (or the other way round).")
    clash = [n for n in ITEMS if os.path.exists(os.path.join(old, n)) and os.path.exists(os.path.join(new, n))]
    if clash:
        raise ValueError(f"{new} already holds {', '.join(clash)}. Choose an empty folder, or move those away first.")
    os.makedirs(new, exist_ok=True)
    moved = _move_items(old, new, only_missing=False)
    os.makedirs(DEFAULT, exist_ok=True)
    if os.path.normcase(new) == os.path.normcase(DEFAULT):
        try:
            os.remove(_pointer_path())
        except OSError:
            pass
    else:
        with open(_pointer_path(), "w", encoding="utf-8") as f:
            json.dump({"path": new}, f, indent=1)
    use(new)
    return f"Moved {len(moved)} item(s) to {new}." if moved else f"Your data will be kept in {new} from now on."
