"""Settings that belong to whoever is using this copy of the app.

config.json holds neutral defaults that ship with the app. Everything personal lives in the data/ folder, which is
never committed:
  data/shared_settings.json   the search settings shared with your other devices (titles, keywords, places)
  data/user_settings.json     settings for this computer only (sources, folders, ...)
  data/master_resume.<ext>, data/resume_instructions.md
  data/device.json            this copy's device id
keys.local.json (keys and the Google OAuth client) sits beside data/. Where that folder is: home.py.
"""
import copy
import json
import os
import secrets
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
RESUME_EXTS = (".docx", ".md", ".txt")
MAX_UPLOAD = 3 * 1024 * 1024
DEFAULT_INSTRUCTIONS_FILE = os.path.join(HERE, "default_instructions.md")
# Settings shared with the phone through WildThing/user/search.json; everything else stays on this computer.
SHARED_KEYS = ("target_titles", "search_keywords", "locations")


def _data(name=""):
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, name) if name else DATA_DIR


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def load():
    """config.json with the user's own settings laid over it."""
    return _merge(_read_json(os.path.join(HERE, "config.json"), {}), user_settings())


def _write_json(name, data):
    with open(_data(name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _migrate_split():
    """Older copies kept everything in user_settings.json; the shared search settings move to shared_settings.json."""
    device = _read_json(os.path.join(DATA_DIR, "user_settings.json"), {})
    moving = {k: device[k] for k in SHARED_KEYS if k in device}
    if not moving:
        return
    shared = _read_json(os.path.join(DATA_DIR, "shared_settings.json"), {})
    for k, v in moving.items():
        shared.setdefault(k, v)
        device.pop(k)
    _write_json("shared_settings.json", shared)
    _write_json("user_settings.json", device)


def device_settings():
    _migrate_split()
    return _read_json(os.path.join(DATA_DIR, "user_settings.json"), {})


def shared_settings():
    _migrate_split()
    return _read_json(os.path.join(DATA_DIR, "shared_settings.json"), {})


def user_settings():
    """Everything the user has set: this computer's settings with the shared ones laid over them."""
    return _merge(device_settings(), shared_settings())


def save_user(patch):
    shared = {k: v for k, v in patch.items() if k in SHARED_KEYS}
    device = {k: v for k, v in patch.items() if k not in SHARED_KEYS}
    if shared:
        _write_json("shared_settings.json", _merge(shared_settings(), shared))
    if device:
        _write_json("user_settings.json", _merge(device_settings(), device))
    return user_settings()


def device_id():
    """A random id for this copy of the app, so batches and shared files say which device made them."""
    d = _read_json(os.path.join(DATA_DIR, "device.json"), {})
    if not d.get("device_id"):
        d["device_id"] = "desktop-" + "".join(secrets.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(4))
        _write_json("device.json", d)
    return d["device_id"]


def resume_path(cfg=None):
    """The master resume: the uploaded one, else a file named in the settings (older setups), else None."""
    for ext in RESUME_EXTS:
        p = os.path.join(DATA_DIR, "master_resume" + ext)
        if os.path.exists(p):
            return p
    name = (cfg or load()).get("resume_file")
    for folder in ((os.path.dirname(DATA_DIR), HERE) if name else ()):
        p = os.path.join(folder, name)
        if os.path.exists(p):
            return p
    return None


def save_resume(filename, data):
    """Stores an uploaded master resume. Returns (ok, message)."""
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in RESUME_EXTS:
        return False, "Upload a Word (.docx), Markdown (.md) or text (.txt) file."
    if not data:
        return False, "That file is empty."
    if len(data) > MAX_UPLOAD:
        return False, "That file is larger than 3 MB, which is too big for a resume."
    if ext == ".docx":
        tmp = _data("incoming.docx")
        with open(tmp, "wb") as f:
            f.write(data)
        try:
            with zipfile.ZipFile(tmp) as z:
                z.getinfo("word/document.xml")
        except (zipfile.BadZipFile, KeyError):
            os.remove(tmp)
            return False, "That does not look like a Word document. Save it as .docx and try again."
        os.remove(tmp)
    for e in RESUME_EXTS:
        old = os.path.join(DATA_DIR, "master_resume" + e)
        if os.path.exists(old):
            os.remove(old)
    with open(_data("master_resume" + ext), "wb") as f:
        f.write(data)
    return True, "Master resume saved."


def instructions_text(cfg=None):
    """What the AI is told about how to write your resume: your own file, else the app's general default."""
    for p in (os.path.join(DATA_DIR, "resume_instructions.md"),
              os.path.join(HERE, (cfg or load()).get("system_prompt_file") or "-")):
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                return f.read()
    with open(DEFAULT_INSTRUCTIONS_FILE, encoding="utf-8") as f:
        return f.read()


def career_bytes():
    """This computer's career file (career.py) as saved, or None."""
    p = os.path.join(DATA_DIR, "career.json")
    if not os.path.isfile(p):
        return None
    with open(p, "rb") as f:
        return f.read()


def load_career():
    """The career file as a dict, or None when there is none (or it cannot be read)."""
    raw = career_bytes()
    try:
        return json.loads(raw.decode("utf-8")) if raw else None
    except ValueError:
        return None


def save_career(data):
    """Saves the career file. Only the app writes it (career.py); callers check it first."""
    with open(_data("career.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1, ensure_ascii=False)
        f.write("\n")


def has_custom_instructions(cfg=None):
    return (os.path.isfile(os.path.join(DATA_DIR, "resume_instructions.md"))
            or os.path.isfile(os.path.join(HERE, (cfg or load()).get("system_prompt_file") or "-")))


def save_instructions(text):
    text = (text or "").strip()
    p = _data("resume_instructions.md")
    if not text:
        if os.path.exists(p):
            os.remove(p)
        return
    with open(p, "w", encoding="utf-8") as f:
        f.write(text + "\n")
