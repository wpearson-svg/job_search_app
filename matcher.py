"""Scores a job posting against the resume, and lists what the posting wants that the resume does not show.

Plain rules, no AI: a list of skill terms (skills.json) is searched for in the resume and in each posting.
A term found in the posting's requirements part counts double. Nothing here changes the resume.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))

SENIOR = re.compile(r"\b(senior|sr\.?|principal|director|vice president|vp|head of|chief)\b", re.I)
REQ_HEAD = re.compile(
    r"(requirements|qualifications|what you.ll need|what you bring|must have|minimum qualifications|"
    r"skills and experience|experience required|who you are)", re.I)
PREF_HEAD = re.compile(r"(preferred|nice to have|bonus|a plus|desired)", re.I)
YEARS = re.compile(r"(\d{1,2})\s*\+?\s*(?:-\s*\d{1,2}\s*)?years", re.I)


def load_lexicon(path=None):
    with open(path or os.path.join(HERE, "skills.json"), encoding="utf-8") as f:
        terms = json.load(f)["terms"]
    compiled = {}
    for term, info in terms.items():
        if info.get("pattern"):
            pat = re.compile(info["pattern"], re.I)
        else:
            alts = "|".join(re.escape(a.lower()) for a in sorted(info["aliases"], key=len, reverse=True))
            pat = re.compile(r"(?<![a-z0-9])(?:" + alts + r")(?![a-z0-9])", re.I)
        compiled[term] = {"kind": info.get("kind", "skill"), "pattern": pat}
    return compiled


def find_terms(text, lexicon):
    """Terms from the lexicon that appear in the text."""
    return {t for t, info in lexicon.items() if info["pattern"].search(text or "")}


def _zones(text):
    """(start, end) of the requirements part of a posting, or None when it has no such heading."""
    m = REQ_HEAD.search(text)
    if not m:
        return None
    start = m.start()
    p = PREF_HEAD.search(text, m.end())
    return (start, p.start() if p else len(text))


def score_job(title, text, have_terms, lexicon, target_titles):
    """Returns a dict: score (0-100), matched, gaps [(term, weight)], flags, title_match."""
    text = text or ""
    title = title or ""
    zone = _zones(text)
    weights = {}
    for term, info in lexicon.items():
        if not info["pattern"].search(text):
            continue
        w = 1
        if zone and info["pattern"].search(text[zone[0]:zone[1]]):
            w = 2
        weights[term] = w

    flags = []
    total = sum(weights.values())
    matched = sorted(t for t in weights if t in have_terms)
    gaps = sorted(((t, w) for t, w in weights.items() if t not in have_terms), key=lambda x: (-x[1], x[0]))
    got = sum(weights[t] for t in matched)

    if total == 0:
        flags.append("No skills from your list found in this posting. It may be a short snippet or an unusual role.")
        skill_pct = 0.0
    else:
        skill_pct = 100.0 * got / total

    low_title = title.lower()
    title_match = any(p.lower() in low_title for p in target_titles)
    score = skill_pct * 0.85 + (15 if title_match else 0)

    if SENIOR.search(title):
        score -= 15
        flags.append("Senior-level title.")
    years = [int(y) for y in YEARS.findall(text)]
    top = max(years) if years else 0
    if top >= 7:
        score -= 10
        flags.append(f"Asks for {top}+ years of experience.")
    elif top >= 5:
        score -= 5
        flags.append(f"Asks for {top}+ years of experience.")
    if len(text) < 400:
        flags.append("Very short description (possibly only a snippet), so the score is a rough guide.")

    return {
        "score": max(0, min(100, round(score))),
        "matched": matched,
        "gaps": gaps,
        "flags": flags,
        "title_match": title_match,
    }


# "Worldwide" and "Anywhere" mean no real place, so they never count as in your area (even beside "Remote").
NOT_APPLICABLE = ("worldwide", "anywhere", "global")


def location_ok(location, text, allowed):
    hay = f"{location or ''}".lower()
    if not hay.strip():
        return True
    if any(w in hay for w in NOT_APPLICABLE):
        return False
    return any(a in hay for a in allowed)
