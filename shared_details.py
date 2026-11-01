"""Your details shared between phone and PC through a `WildThing/user/` folder (Google Drive, or a Drive-synced folder
on the PC). The format is in docs/formats.md; the decisions are tested by shared_tests/shared_details.json.

Shared: the master resume, the search settings (titles, keywords, places, profiles), the AI instructions, the
"I have this" skills and the career file (career.py). Never shared: keys, notification and source settings, and the postings database.

Each shared file X has a sidecar X.meta.json (resume: resume.meta.json) with a version number, when it changed, which
device changed it and the SHA-256 of its bytes. Each device remembers, per file, the hashes it saw at the last sync
(its own rendering and the folder's copy), so it can tell which side changed. Both changed means: ask, never guess.
"""
import hashlib
import json

FORMAT_SEARCH = "wildthing-search"
FORMAT_SKILLS = "wildthing-confirmed-skills"
# The shared files, by the key used in the sync record. The resume keeps its own extension (resume.docx, .md or .txt).
FILES = ("resume", "search.json", "instructions.md", "confirmed_skills.json", "career.json")
SEARCH_KEYS = ("target_titles", "search_keywords", "locations")
RESUME_EXTS = (".docx", ".md", ".txt")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def meta_name(key):
    return "resume.meta.json" if key == "resume" else key + ".meta.json"


def search_doc(cfg, profiles):
    """The shared search settings as bytes. profiles: [{name, keywords, titles, location}]."""
    doc = {"format": FORMAT_SEARCH, "version": 1}
    for k in SEARCH_KEYS:
        doc[k] = list(cfg.get(k) or [])
    doc["profiles"] = sorted(({k: (p.get(k) or "") for k in ("name", "keywords", "titles", "location")} for p in profiles),
                             key=lambda p: p["name"].lower())
    return (json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def skills_doc(terms):
    doc = {"format": FORMAT_SKILLS, "version": 1, "skills": sorted(set(terms))}
    return (json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def parse_doc(data, fmt):
    """The parsed document, or raises ValueError with a plain reason."""
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise ValueError("not a WildThing file")
    if not isinstance(doc, dict) or doc.get("format") != fmt:
        raise ValueError("not a WildThing file")
    return doc


def meta(file, version, changed_at, device, digest):
    return {"file": file, "version": version, "changed_at": changed_at, "device": device, "sha256": digest}


def decide(local_sha, remote, base):
    """What to do with one shared file.

    local_sha: hash of this device's current copy, or None if it has none.
    remote: the folder copy's meta ({sha256, version, ...}) or None if the folder has none.
    base: what this device recorded at its last sync of this file ({local, remote}) or None (never synced).

    Returns "none", "push" (folder gets this device's copy), "pull" (this device takes the folder's copy),
    "same" (nothing to move; record the hashes) or "conflict" (both changed: ask the person which to keep).
    """
    if local_sha is None and remote is None:
        return "none"
    if remote is None:
        return "push"
    if local_sha is None:
        return "pull"
    if base is None:
        return "same" if local_sha == remote["sha256"] else "conflict"
    local_changed = local_sha != base["local"]
    remote_changed = remote["sha256"] != base["remote"]
    if local_changed and remote_changed:
        return "same" if local_sha == remote["sha256"] else "conflict"
    if remote_changed:
        return "pull"
    if local_changed:
        return "push"
    return "same"


def next_version(remote, base):
    return max((remote or {}).get("version", 0), (base or {}).get("version", 0)) + 1
