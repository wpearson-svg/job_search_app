"""Turns the gaps across all your saved postings into one ranked plan."""
import re
from collections import Counter, defaultdict

ACTIONS = {
    "cert": "Certification. Look up the exam objectives, book the exam, and add it to the resume only after you pass.",
    "tool": "Tool. Use it for a small real project (a week or two), then add the project to the resume with what you built.",
    "skill": "Skill. First check whether your past work already shows it and the resume just does not say so (use \"I have this\"). If not, practice it on a project or in a volunteer role.",
    "method": "Method. Take a short course or read the standard guide, then apply it to your current project and write down the result.",
}


def build_plan(jobs, lexicon, per_phase=2):
    """jobs: list of dicts with 'gaps' [[term, weight], ...]. Returns ranked rows and phases."""
    agg = defaultdict(lambda: {"jobs": 0, "weight": 0, "required": 0})
    for j in jobs:
        for term, w in j["gaps"]:
            a = agg[term]
            a["jobs"] += 1
            a["weight"] += w
            if w >= 2:
                a["required"] += 1
    rows = []
    for term, a in agg.items():
        kind = lexicon.get(term, {}).get("kind", "skill")
        rows.append({"term": term, "kind": kind, "jobs": a["jobs"], "required": a["required"],
                     "weight": a["weight"], "action": ACTIONS.get(kind, ACTIONS["skill"])})
    rows.sort(key=lambda r: (-r["weight"], -r["jobs"], r["term"]))
    phases = []
    for i in range(0, min(len(rows), 10), per_phase):
        start = (i // per_phase) * 2 + 1
        phases.append({"label": f"Weeks {start}-{start + 1}", "items": rows[i:i + per_phase]})
    return rows, phases


# ---- Planning with Claude: the app gathers the evidence, Claude does the planning -----------------------
PLAN_SECTIONS = [("priorities", "What to work on first, and why"), ("plan", "Week-by-week plan"),
                 ("proof", "Projects that prove each skill"), ("resume_changes", "Resume changes (only what is true)"),
                 ("skip", "What not to chase"), ("questions", "Questions for you")]


def snippets(term, jobs, lexicon, limit=2, width=220):
    """Short quotes from postings that ask for the term, so the planner sees how employers actually phrase it."""
    pat = lexicon[term]["pattern"]
    out = []
    for j in jobs:
        if term not in {t for t, _w in j["gaps"]}:
            continue
        text = j.get("description") or ""
        m = pat.search(text)
        if not m:
            continue
        start = max(text.rfind("\n", 0, m.start()), text.rfind(". ", 0, m.start())) + 1
        ends = [e for e in (text.find("\n", m.end()), text.find(". ", m.end())) if e != -1]
        sentence = " ".join(text[start:min(ends) if ends else len(text)].split())
        if len(sentence) > width:
            sentence = sentence[:width].rstrip() + "..."
        out.append(f'{j.get("title", "")} ({j.get("company") or "company not listed"}): "{sentence}"')
        if len(out) >= limit:
            break
    return out


def top_matched(jobs, n=12):
    c = Counter(t for j in jobs for t in j["matched"])
    return [(t, k) for t, k in c.most_common(n)]


def build_message(rows, jobs, lexicon, focus="all postings", extras=(), hours=5, weeks=12, top=15):
    lines = [
        "Build me a realistic skills plan from the gaps below. Use only facts from my master resume "
        "when you talk about what I already have. Do not invent experience, and do not tell me to claim a skill I "
        "have not shown. If you are unsure whether I have something, ask me in <questions>.",
        "",
        f"Focus: {focus}. Based on {len(jobs)} saved job postings.",
        f"Time I can give: about {hours} hours a week for {weeks} weeks.",
        "",
        "Reply using exactly these tags:",
        "<priorities> the gaps in the order I should work on them, and why that order (what employers ask for most, "
        "what is required rather than preferred, and what builds on what) </priorities>",
        "<plan> a week-by-week plan that fits my hours, with specific free or low-cost resources and what to finish "
        "each week </plan>",
        "<proof> for each priority skill, a small project or result I can show an employer, ideally built on my real "
        "work from my resume </proof>",
        "<resume_changes> wording I could add to my resume now, only where it is already true, and what to add later "
        "once I finish each step </resume_changes>",
        "<skip> gaps that are not worth chasing for this focus, and why </skip>",
        "<questions> anything you need to ask me before the plan is right </questions>",
        "",
        "Gaps, most wanted first (a gap is a skill the postings ask for that my resume does not show):",
    ]
    for i, r in enumerate(rows[:top], 1):
        lines.append(f'{i}. {r["term"]} ({r["kind"]}): in {r["jobs"]} postings, listed as required in {r["required"]}')
        for q in snippets(r["term"], jobs, lexicon):
            lines.append("   - " + q)
    if len(rows) > top:
        lines.append(f"({len(rows) - top} smaller gaps left out.)")
    tm = top_matched(jobs)
    if tm:
        lines += ["", "Skills those postings ask for that my resume already shows (with how many postings): " +
                  ", ".join(f"{t} ({k})" for t, k in tm)]
    if extras:
        lines += ["", "Things I told the app I have, which my resume does not yet say: " + ", ".join(sorted(extras))]
    return "\n".join(lines)


def parse_plan(text):
    out = []
    for tag, label in PLAN_SECTIONS:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text or "", re.S)
        if m and m.group(1).strip():
            out.append((label, m.group(1).strip()))
    return out
