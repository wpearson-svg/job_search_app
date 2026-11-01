"""The career file: everything true about the person in one JSON file, WildThing/user/career.json. Format:
docs/formats.md, section 9. The cases in shared_tests/career.json are for both apps.

An AI builds it from the person's own documents, following "Building the career file" in AI_INSTRUCTIONS.md, and
replies with it inside <career_file> tags. The app checks it here, shows it for review, and keeps it. After that only
the app changes it: "I have this" adds a confirmed skill, and a rebuilt file replaces it once the person accepts it.
The master resume stays the example of format and tone; this file is where the facts come from.
"""
import json
import re

FORMAT = "wildthing-career"
VERSION = 1
FILE = "career.json"
TAG = "career_file"
SKILL_SOURCES = ("documents", "confirmed")
CERT_STATUSES = ("earned", "in_progress", "expired")
_DATE = re.compile(r"^\d{4}(-(0[1-9]|1[0-2]))?$")          # YYYY or YYYY-MM
_REPLY = re.compile(r"^career_(\d{8}-\d{4})\.reply\.md$")
_FENCE = re.compile(r"^```[a-zA-Z]*\s*\n(.*)\n```$", re.S)

# Each list section, the fields its items must have (non-empty text) and may have (text).
_TEXT = {
    "roles": (("id", "employer", "title", "start"), ("end", "show_as", "location", "type", "scope", "details")),
    "projects": (("id", "name"), ("date", "description", "link")),
    "skills": (("name", "source"), ("notes",)),
    "certifications": (("name", "status"), ("issuer", "date")),
    "education": (("school",), ("credential", "field", "start", "end", "notes")),
    "flags": (("text",), ()),
}
_DATES = {"roles": ("start", "end"), "projects": ("date",), "certifications": ("date",), "education": ("start", "end")}
_LISTS = {"roles": ("achievements",), "projects": ("skills",), "skills": ("evidence",), "flags": ("sources",)}


def empty(name=""):
    """A career file with nothing in it yet (the app makes one when "I have this" is used before any was built)."""
    return {"format": FORMAT, "version": VERSION, "updated_at": "",
            "person": {"name": name, "headline": "", "contact": {"email": "", "phone": "", "location": "", "links": []}},
            "summary": "", "roles": [], "skills": [], "certifications": [], "education": [], "projects": [],
            "privacy": {"never_name": [], "never_mention": []}, "wording": {"avoid": []}, "flags": []}


def _is_text(v):
    return isinstance(v, str)


def _texts(v):
    return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)


def validate(data):
    """Plain reasons the data is not a usable career file; an empty list means it is fine. Fields the app does not
    know are allowed (and kept), so a later version can add some."""
    if not isinstance(data, dict):
        return ["That is not a career file (it should be one JSON object)."]
    if data.get("format") != FORMAT:
        return [f'That is not a WildThing career file ("format" should be "{FORMAT}").']
    if not isinstance(data.get("version"), int):
        return ['"version" should be a whole number.']
    if data["version"] > VERSION:
        return ["That career file comes from a newer version of WildThing. Update this copy first."]
    bad = []
    person = data.get("person")
    if not isinstance(person, dict) or not _is_text(person.get("name")) or not person["name"].strip():
        bad.append('"person.name" is missing.')
    elif not isinstance(person.get("contact", {}), dict):
        bad.append('"person.contact" should be an object.')
    for key in ("summary", "updated_at"):
        if not _is_text(data.get(key, "")):
            bad.append(f'"{key}" should be text.')

    ids = set()
    for section, (need, may) in _TEXT.items():
        items = data.get(section, [])
        if not isinstance(items, list):
            bad.append(f'"{section}" should be a list.')
            continue
        for i, it in enumerate(items):
            at = f"{section}[{i}]"
            if not isinstance(it, dict):
                bad.append(f"{at} should be an object.")
                continue
            for f in need:
                if not _is_text(it.get(f)) or not it[f].strip():
                    bad.append(f'{at} needs "{f}".')
            for f in may:
                if not _is_text(it.get(f, "")):
                    bad.append(f'{at}.{f} should be text.')
            for f in _DATES.get(section, ()):
                v = it.get(f, "")
                if _is_text(v) and v and not _DATE.match(v):
                    bad.append(f'{at}.{f} should be YYYY or YYYY-MM, not "{v}".')
            for f in _LISTS.get(section, ()):
                if not isinstance(it.get(f, []), list):
                    bad.append(f'{at}.{f} should be a list.')
            if section in ("roles", "projects") and _is_text(it.get("id")) and it["id"].strip():
                if it["id"] in ids:
                    bad.append(f'{at} uses the id "{it["id"]}" again; every role and project needs its own.')
                ids.add(it["id"])
            if section == "roles":
                s, e = it.get("start", ""), it.get("end", "")
                if _is_text(s) and _is_text(e) and _DATE.match(s or "x") and _DATE.match(e or "x") and e < s[:len(e)]:
                    bad.append(f"{at} ends before it starts.")
                for j, a in enumerate(it.get("achievements", []) if isinstance(it.get("achievements", []), list) else []):
                    if not isinstance(a, dict) or not _is_text(a.get("text")) or not a["text"].strip():
                        bad.append(f'{at}.achievements[{j}] needs "text".')
                    elif not all(isinstance(a.get(k, []), list) and all(_is_text(x) for x in a.get(k, [])) for k in ("skills", "numbers")):
                        bad.append(f"{at}.achievements[{j}] skills and numbers should be lists of text.")
            if section == "certifications" and it.get("status") not in CERT_STATUSES and _is_text(it.get("status")) and it["status"].strip():
                bad.append(f'{at}.status should be one of {", ".join(CERT_STATUSES)}.')

    seen = {}
    for i, s in enumerate(data.get("skills", []) if isinstance(data.get("skills", []), list) else []):
        if not isinstance(s, dict) or not _is_text(s.get("name")):
            continue
        at = f"skills[{i}]"
        key = s["name"].strip().lower()
        if key in seen:
            bad.append(f'{at} repeats the skill "{s["name"]}" (also skills[{seen[key]}]).')
        seen.setdefault(key, i)
        if _is_text(s.get("source")) and s["source"].strip() and s["source"] not in SKILL_SOURCES:
            bad.append(f'{at}.source should be "documents" or "confirmed".')
        ev = s.get("evidence", [])
        if isinstance(ev, list):
            for e in ev:
                if e not in ids:
                    bad.append(f'{at} points to "{e}", which is not a role or project id.')
            if s.get("source") == "documents" and not ev and not str(s.get("notes", "")).strip():
                bad.append(f'{at} ("{s["name"]}") needs evidence (a role or project id) or notes saying where it comes from.')

    for section, fields in (("privacy", ("never_name", "never_mention")), ("wording", ("avoid",))):
        part = data.get(section, {})
        if not isinstance(part, dict):
            bad.append(f'"{section}" should be an object.')
            continue
        for f in fields:
            v = part.get(f, [])
            if f == "avoid":
                if not isinstance(v, list) or not all(isinstance(x, dict) and _is_text(x.get("phrase")) and x["phrase"].strip() for x in v):
                    bad.append('"wording.avoid" should be a list of {"phrase", "why"}.')
            elif not _texts(v):
                bad.append(f'"{section}.{f}" should be a list of text.')
    return bad


def read_reply(text):
    """(career file, problems) from an AI's reply: the JSON between <career_file> tags, optionally inside a ```json
    fence. The file is None when there are problems."""
    m = re.search(rf"<{TAG}>(.*?)</{TAG}>", text or "", re.S)
    if not m:
        return None, [f"The reply has no <{TAG}> block."]
    body = m.group(1).strip()
    f = _FENCE.match(body)
    if f:
        body = f.group(1).strip()
    try:
        data = json.loads(body)
    except ValueError as e:
        return None, [f"The career file is not valid JSON: {e}"]
    problems = validate(data)
    return (None, problems) if problems else (data, [])


def skill_names(data):
    return [s["name"] for s in data.get("skills", [])]


def _find(data, name):
    key = name.strip().lower()
    return next((i for i, s in enumerate(data.get("skills", [])) if s["name"].strip().lower() == key), None)


def add_confirmed(data, name, now):
    """"I have this": the skill is added as confirmed, unless the file already lists it. Returns a new file."""
    out = json.loads(json.dumps(data))
    if name.strip() and _find(out, name) is None:
        out.setdefault("skills", []).append({"name": name.strip(), "source": "confirmed", "evidence": [], "notes": ""})
        out["updated_at"] = now
    return out


def remove_confirmed(data, name, now):
    """Undoes "I have this". Only a confirmed skill is removed; one from the person's documents stays."""
    out = json.loads(json.dumps(data))
    i = _find(out, name)
    if i is not None and out["skills"][i].get("source") == "confirmed":
        del out["skills"][i]
        out["updated_at"] = now
    return out


def replace(old, new, now):
    """A rebuilt file replacing the current one: the skills confirmed in the app that the new file does not list are
    carried over, so a rebuild never loses them."""
    out = json.loads(json.dumps(new))
    for s in (old or {}).get("skills", []):
        if s.get("source") == "confirmed" and _find(out, s["name"]) is None:
            out.setdefault("skills", []).append(dict(s))
    out["updated_at"] = now
    return out


def text(data):
    """All the factual text, for matching postings against: what the matcher reads in place of the resume."""
    parts = [data.get("summary", ""), data.get("person", {}).get("headline", "")]
    for r in data.get("roles", []):
        parts += [r.get("title", ""), r.get("scope", ""), r.get("details", "")]
        for a in r.get("achievements", []):
            parts += [a.get("text", "")] + a.get("skills", [])
    for p in data.get("projects", []):
        parts += [p.get("name", ""), p.get("description", "")] + p.get("skills", [])
    parts += [s["name"] for s in data.get("skills", [])]
    for c in data.get("certifications", []):
        if c.get("status", "earned") == "earned":       # one still in progress, or lapsed, does not close a gap
            parts += [c.get("name", ""), c.get("issuer", "")]
    for e in data.get("education", []):
        parts += [e.get("credential", ""), e.get("field", "")]
    return "\n".join(p for p in parts if p)


def check_document(doc, data):
    """Warnings for a resume or letter that breaks the file's privacy and wording rules: a name it must never use,
    a subject it must never mention, a phrase to avoid. Case does not matter."""
    low = (doc or "").lower()
    out = []
    for n in data.get("privacy", {}).get("never_name", []):
        if n.lower() in low:
            out.append(f'Names "{n}", which your career file says never to name.')
    for n in data.get("privacy", {}).get("never_mention", []):
        if n.lower() in low:
            out.append(f'Mentions "{n}", which your career file says never to mention.')
    for w in data.get("wording", {}).get("avoid", []):
        if w["phrase"].lower() in low:
            out.append(f'Uses "{w["phrase"]}"' + (f': {w["why"]}' if w.get("why") else "."))
    return out


# ---- the request an AI builds the file from, and the reply's file names --------------------------------------------
def instructions_section(md):
    """The "Building the career file" part of AI_INSTRUCTIONS.md, which every request carries."""
    m = re.search(r"^## Building the career file\s*$(.*?)(?=^## |\Z)", md or "", re.S | re.M)
    return m.group(1).strip() if m else ""


def build_request(section, sources, current=None):
    """The request: the build instructions, the current file when rebuilding, and the person's documents.
    sources: [(file name, text)]."""
    parts = ["Build my career file, following these instructions. Use only the documents below and the current file. "
             f"Reply with the whole file between <{TAG}> and </{TAG}>, and nothing else.",
             "<career_file_instructions>\n" + section.strip() + "\n</career_file_instructions>"]
    if current:
        parts.append("<current_career_file>\n" + json.dumps(current, indent=1, ensure_ascii=False) + "\n</current_career_file>")
    for name, body in sources:
        parts.append(f'<source_document name="{name.replace(chr(34), "")}">\n' + body.strip() + "\n</source_document>")
    return "\n\n".join(parts) + "\n"


def request_name(now):
    """requests/career_<YYYYMMDD-HHMM>.md; the reply goes to replies/career_<same>.reply.md."""
    return f"career_{now:%Y%m%d-%H%M}.md"


def reply_name(request):
    return request[:-3] + ".reply.md"


def newest_reply(names):
    """The newest career reply among the file names in replies/, or None."""
    found = sorted(n for n in names if _REPLY.match(n))
    return found[-1] if found else None


def request_for(reply):
    return reply[:-len(".reply.md")] + ".md"


# ---- what the review shows -----------------------------------------------------------------------------------------
def _labels(data):
    def span(a, b):
        return f"{a or '?'} to {b or 'now'}"
    return {
        "roles": [f"{r.get('title', '')} at {r.get('employer', '')} ({span(r.get('start'), r.get('end'))})" for r in data.get("roles", [])],
        "skills": [s["name"] for s in data.get("skills", [])],
        "certifications": [c["name"] + (f" ({c['status']})" if c.get("status") else "") for c in data.get("certifications", [])],
        "education": [", ".join(x for x in (" ".join(y for y in (e.get("credential", ""), e.get("field", "")) if y), e.get("school", "")) if x)
                      for e in data.get("education", [])],
        "projects": [p["name"] for p in data.get("projects", [])],
    }


def changes(old, new):
    """{section: {"added": [...], "removed": [...]}} between the current file (or None) and a new one, for the review.
    Sections with no change are left out. A changed item shows as removed and added."""
    a, b = _labels(old or empty()), _labels(new)
    out = {}
    for k in b:
        added = [x for x in b[k] if x not in a[k]]
        removed = [x for x in a[k] if x not in b[k]]
        if added or removed:
            out[k] = {"added": added, "removed": removed}
    return out
