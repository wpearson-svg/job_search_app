"""Settings that belong to whoever is using this copy of the app.

config.json holds neutral defaults that ship with the app. Everything personal lives in the data/ folder, which is
never committed: data/user_settings.json (overrides config.json), data/master_resume.<ext> and
data/resume_instructions.md. keys.local.json (API keys) stays beside the app, also never committed.
"""
import copy
import json
import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(HERE, "data")
RESUME_EXTS = (".docx", ".md", ".txt")
MAX_UPLOAD = 3 * 1024 * 1024
DEFAULT_INSTRUCTIONS_FILE = os.path.join(HERE, "default_instructions.md")


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


def user_settings():
    return _read_json(os.path.join(DATA_DIR, "user_settings.json"), {})


def save_user(patch):
    new = _merge(user_settings(), patch)
    with open(_data("user_settings.json"), "w", encoding="utf-8") as f:
        json.dump(new, f, indent=2)
    return new


def resume_path(cfg=None):
    """The master resume: the uploaded one, else a file named in the settings (older setups), else None."""
    for ext in RESUME_EXTS:
        p = os.path.join(DATA_DIR, "master_resume" + ext)
        if os.path.exists(p):
            return p
    name = (cfg or load()).get("resume_file")
    if name:
        p = os.path.join(HERE, name)
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
    """What Claude is told about how to write your resume: your own file, else the app's general default."""
    for p in (os.path.join(DATA_DIR, "resume_instructions.md"),
              os.path.join(HERE, (cfg or load()).get("system_prompt_file") or "-")):
        if os.path.isfile(p):
            with open(p, encoding="utf-8", errors="replace") as f:
                return f.read()
    with open(DEFAULT_INSTRUCTIONS_FILE, encoding="utf-8") as f:
        return f.read()


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
