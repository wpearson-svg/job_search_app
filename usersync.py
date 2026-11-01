"""Keeps the shared details in step with a WildThing/user folder: in Google Drive itself (gdrive.py), or a folder on
this computer. Rules and file formats: shared_details.py and docs/formats.md.

The local copies in data/ stay the working copies, so the app works offline; this is only the sync step.
"""
import json
import os

import career
import db
import settings
import shared_details as sd
from workfolder import LocalDir

STATE_FILE = "sync_state.json"          # in data/: what this computer saw at its last sync, per file


def folder(cfg):
    return (cfg.get("shared_folder") or "").strip() or None


def _state(root):
    try:
        with open(os.path.join(settings.DATA_DIR, STATE_FILE), encoding="utf-8") as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    return s.get("files", {}) if s.get("root") == root else {}      # another folder: start over


def _save_state(root, files):
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    with open(os.path.join(settings.DATA_DIR, STATE_FILE), "w", encoding="utf-8") as f:
        json.dump({"root": root, "files": files}, f, indent=1)


def _profiles(conn):
    return [dict(r) for r in conn.execute("SELECT name, keywords, titles, location FROM profiles ORDER BY name")]


def local_copy(conn, key):
    """(bytes, file name) of this computer's copy of one shared file, or None."""
    cfg = settings.load()
    if key == "resume":
        p = settings.resume_path(cfg)
        if not p:
            return None
        with open(p, "rb") as f:
            return f.read(), "resume" + os.path.splitext(p)[1].lower()
    if key == "search.json":
        return sd.search_doc(cfg, _profiles(conn)), key
    if key == "instructions.md":
        return settings.instructions_text(cfg).encode("utf-8"), key
    if key == "career.json":
        data = settings.career_bytes()
        return (data, key) if data else None
    return sd.skills_doc([r["term"] for r in conn.execute("SELECT term FROM extras")]), key


def remote_copy(folder_, key):
    """(meta, file name) of the folder's copy, or None when it has none (or the meta points at a missing file)."""
    raw = folder_.read(sd.meta_name(key))
    try:
        meta = json.loads(raw) if raw is not None else None
    except ValueError:
        return None
    if not isinstance(meta, dict) or not meta.get("file"):
        return None
    name = os.path.basename(meta["file"])
    return (meta, name) if name in {f["name"] for f in folder_.files()} else None


def apply_local(conn, key, data, filename):
    """Takes the folder's copy as this computer's own."""
    if key == "resume":
        ok, msg = settings.save_resume(filename, data)
        if not ok:
            raise ValueError(msg)
    elif key == "search.json":
        doc = sd.parse_doc(data, sd.FORMAT_SEARCH)
        settings.save_user({k: list(doc.get(k) or []) for k in sd.SEARCH_KEYS})
        names = []
        for p in doc.get("profiles") or []:
            names.append(p["name"])
            vals = (p.get("keywords", ""), p.get("titles", ""), p.get("location", ""))
            if conn.execute("SELECT 1 FROM profiles WHERE name=?", (p["name"],)).fetchone():
                conn.execute("UPDATE profiles SET keywords=?, titles=?, location=? WHERE name=?", vals + (p["name"],))
            else:
                conn.execute("INSERT INTO profiles(name, keywords, titles, location) VALUES (?,?,?,?)", (p["name"],) + vals)
        for r in conn.execute("SELECT id, name FROM profiles").fetchall():   # removed on the other device
            if r["name"] not in names:
                conn.execute("DELETE FROM job_profiles WHERE profile_id=?", (r["id"],))
                conn.execute("DELETE FROM profiles WHERE id=?", (r["id"],))
        conn.commit()
    elif key == "career.json":              # checked like any new file: a bad copy never replaces a good one
        try:
            doc = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise ValueError("the shared career file is not valid JSON")
        problems = career.validate(doc)
        if problems:
            raise ValueError("the shared career file was not used: " + problems[0])
        settings.save_career(doc)
        fold_extras(conn)
    elif key == "instructions.md":
        text = data.decode("utf-8", errors="replace")
        with open(settings.DEFAULT_INSTRUCTIONS_FILE, encoding="utf-8") as f:
            default = f.read()
        settings.save_instructions("" if text.strip() == default.strip() else text)
    else:
        doc = sd.parse_doc(data, sd.FORMAT_SKILLS)
        conn.execute("DELETE FROM extras")
        for t in doc.get("skills") or []:
            conn.execute("INSERT OR IGNORE INTO extras(term, added_at) VALUES (?,?)", (t, db.now()))
        conn.commit()


def confirmed_skills(conn):
    """"I have this" skills: confirmed skills in the career file, plus any still in the extras table (where they
    are kept until there is a career file)."""
    terms = {r["term"] for r in conn.execute("SELECT term FROM extras")}
    data = settings.load_career()
    if data:
        terms |= {s["name"].strip().lower() for s in data.get("skills", []) if s.get("source") == "confirmed"}
    return terms


def fold_extras(conn):
    """Once there is a career file, the extras table's skills move into it as confirmed skills. Returns True when
    the file changed."""
    data = settings.load_career()
    terms = [r["term"] for r in conn.execute("SELECT term FROM extras ORDER BY term")]
    if not data or not terms:
        return False
    for t in terms:
        data = career.add_confirmed(data, t, db.now())
    if career.validate(data):
        return False
    settings.save_career(data)
    conn.execute("DELETE FROM extras")
    conn.commit()
    return True


def _write_remote(folder_, key, data, filename, remote_meta, base):
    if key == "resume":                         # only one resume in the folder
        names = {f["name"] for f in folder_.files()}
        for ext in sd.RESUME_EXTS:
            if "resume" + ext != filename and "resume" + ext in names:
                folder_.remove("resume" + ext)
    folder_.write(filename, data)
    meta = sd.meta(filename, sd.next_version(remote_meta, base), db.now(), settings.device_id(), sd.sha256(data))
    folder_.write(sd.meta_name(key), json.dumps(meta, indent=1).encode("utf-8"))
    return meta


def describe_local(key, copy):
    if not copy:
        return "none"
    data, name = copy
    if key == "search.json":
        doc = json.loads(data)
        return f"{len(doc['target_titles'])} titles, {len(doc['search_keywords'])} keywords, {len(doc['locations'])} places, {len(doc['profiles'])} profiles"
    if key == "confirmed_skills.json":
        return f"{len(json.loads(data)['skills'])} skills"
    if key == "career.json":
        doc = json.loads(data)
        return f"career file: {len(doc.get('roles', []))} roles, {len(doc.get('skills', []))} skills"
    return f"{name}, {len(data):,} bytes"


def sync(conn, resolve=None, target=None):
    """Runs the sync once. resolve: {key: "here" | "folder"} answers for earlier conflicts. target: the folder
    (workfolder.LocalDir or DriveDir); by default the Shared details folder setting.
    Returns {"pushed", "pulled", "conflicts", "errors", "rescore"} or None when there is nowhere to sync with."""
    if target is None:
        root = folder(settings.load())
        if not root:
            return None
        target = LocalDir(root)
    root = target.label
    try:
        target.ensure()
    except OSError as e:
        return {"pushed": [], "pulled": [], "conflicts": [], "errors": [str(e)], "rescore": False}
    state = _state(root)
    out = {"pushed": [], "pulled": [], "conflicts": [], "errors": [], "rescore": False}
    for key in sd.FILES:
        copy = local_copy(conn, key)
        local_sha = sd.sha256(copy[0]) if copy else None
        try:
            remote = remote_copy(target, key)
        except OSError as e:
            out["errors"].append(f"{key}: {e}")
            continue
        rmeta = remote[0] if remote else None
        base = state.get(key)
        action = sd.decide(local_sha, rmeta, base)
        if action == "conflict" and resolve and key in resolve:
            action = "push" if resolve[key] == "here" else "pull"
        try:
            if action == "push":
                meta = _write_remote(target, key, copy[0], copy[1], rmeta, base)
                state[key] = {"local": local_sha, "remote": meta["sha256"], "version": meta["version"]}
                out["pushed"].append(key)
            elif action == "pull":
                data = target.read(remote[1])
                if data is None:
                    raise OSError("the shared copy could not be read")
                apply_local(conn, key, data, remote[1])
                now = local_copy(conn, key)
                state[key] = {"local": sd.sha256(now[0]) if now else None, "remote": rmeta["sha256"],
                              "version": rmeta.get("version", 0)}
                out["pulled"].append(key)
                out["rescore"] = out["rescore"] or key != "instructions.md"
            elif action == "same":
                state[key] = {"local": local_sha, "remote": rmeta["sha256"], "version": rmeta.get("version", 0)}
            elif action == "conflict":
                out["conflicts"].append({"key": key, "here": describe_local(key, copy),
                                         "folder": f"changed {(rmeta.get('changed_at') or '')[:16].replace('T', ' ')} "
                                                   f"on {rmeta.get('device') or 'another device'}"})
        except (OSError, ValueError) as e:
            out["errors"].append(f"{key}: {e}")
    _save_state(root, state)
    return out
