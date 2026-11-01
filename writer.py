"""Requests for an AI assistant (resume, cover letter, interview prep) and the tagged replies that come back.

The app never calls an AI itself. A request is copied, shared or written to the work folder; any assistant that
follows written instructions can answer it, and the reply is parsed here and saved with the posting.
"""
import os
import re
import shutil
import subprocess
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = HERE            # where output/ goes: the data folder once home.start() has run
def with_context(message, instructions, resume_text):
    """Puts the instructions and master resume in front of a request, so it works in any AI chat."""
    r = (resume_text or "").strip()
    return ("<instructions>\n" + (instructions or "").strip() + "\n</instructions>\n\n"
            + ("<master_resume>\n" + r + "\n</master_resume>\n\n" if r else "") + message)


def build_user_message(job, want_cover):
    ask = "Build a resume and a cover letter for this listing." if want_cover else "Build a resume for this listing."
    head = []
    for label, key in (("Title", "title"), ("Company", "company"), ("Location", "location")):
        if job.get(key):
            head.append(f"{label}: {job[key]}")
    body = ("\n".join(head) + "\n\n" if head else "") + (job.get("description") or "")
    return f"{ask}\n\n<job_listing>\n{body}\n</job_listing>"


def parse_blocks(text):
    def block(tag):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text or "", re.S)
        return m.group(1).strip() if m else None
    return {"resume": block("resume"), "cover_letter": block("cover_letter"), "review_notes": block("review_notes")}


def check_resume(resume_md, rules=None):
    """Checks the prompt's own hard rules and returns a list of warnings (empty list means none found)."""
    warnings = []
    if not resume_md:
        return ["No <resume> block came back."]
    for m in re.findall(r"\[[^\]]*\]", resume_md):
        warnings.append(f"Bracket marker left in the resume: {m}")
    low = resume_md.lower()
    for needle, msg in (rules or []):
        if needle in low:
            warnings.append(msg)
    words = len(re.findall(r"[A-Za-z0-9'&+#/.-]+", re.sub(r"[*#\\]", " ", resume_md)))
    if words > 600:
        warnings.append(f"About {words} words; the one-page target is 450 to 550.")
    return warnings


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:40] or "posting"


def save_files(job, parts, cfg):
    """Writes .md files for a saved reply (and .docx copies if pandoc is installed). Returns the paths written."""
    out = os.path.join(BASE, cfg.get("output_dir", "output"))
    os.makedirs(out, exist_ok=True)
    base = f"{date.today():%Y-%m-%d}_{job['id']}_{slug(job.get('company') or job.get('title'))}"
    written = []
    for kind in ("resume", "cover_letter", "review_notes"):
        if parts.get(kind):
            p = os.path.join(out, f"{base}_{kind}.md")
            with open(p, "w", encoding="utf-8") as f:
                f.write(parts[kind] + "\n")
            written.append(p)
            if kind in ("resume", "cover_letter") and shutil.which("pandoc"):
                docx = p[:-3] + ".docx"
                cmd = ["pandoc", p, "-o", docx]
                ref = next((p for p in (os.path.join(d, cfg.get("reference_docx") or "-") for d in (BASE, os.path.join(BASE, "data"), HERE))
                            if os.path.isfile(p)), None)
                if ref:
                    cmd += [f"--reference-doc={ref}"]
                try:
                    subprocess.run(cmd, check=True, capture_output=True, timeout=60)
                    written.append(docx)
                except Exception:
                    pass  # the .md is the deliverable; .docx is a convenience
    return written


# ---- Interview prep: a request for your AI, and the reply parsed back ----
PREP_SECTIONS = [("likely_questions", "Questions they may ask you"), ("questions_to_ask", "Questions to ask them"),
                 ("gap_prep", "Gaps to be ready for"), ("research", "Research before the interview")]


def build_prep_message(job):
    head = []
    for label, key in (("Title", "title"), ("Company", "company"), ("Location", "location")):
        if job.get(key):
            head.append(f"{label}: {job[key]}")
    body = ("\n".join(head) + "\n\n" if head else "") + (job.get("description") or "")
    gaps = ", ".join(t for t, _w in job.get("gaps", [])) or "none found"
    return (
        "Prepare me for an interview for this listing. Use only facts from my master resume; "
        "do not invent experience.\n\n"
        "Reply using exactly these tags:\n"
        "<likely_questions> 8 to 12 questions I am likely to be asked (behavioral, technical, role-specific), each with a "
        "short answer outline built from my real experience </likely_questions>\n"
        "<questions_to_ask> 10 strong questions I should ask them: the team, what success looks like, how they work, "
        "the hiring process, and what worries them </questions_to_ask>\n"
        "<gap_prep> for each gap below, an honest way to address it </gap_prep>\n"
        "<research> what to look up about the company and role before the interview </research>\n\n"
        f"Gaps the app found between my resume and this listing: {gaps}\n\n"
        f"<job_listing>\n{body}\n</job_listing>")


def parse_prep(text):
    out = []
    for tag, label in PREP_SECTIONS:
        m = re.search(rf"<{tag}>(.*?)</{tag}>", text or "", re.S)
        if m and m.group(1).strip():
            out.append((label, m.group(1).strip()))
    return out


def save_prep(job, text, cfg):
    """Writes the prep as one markdown file next to the resumes. Returns its path."""
    out = os.path.join(BASE, cfg.get("output_dir", "output"))
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, f"{date.today():%Y-%m-%d}_{job['id']}_{slug(job.get('company') or job.get('title'))}_interview_prep.md")
    sections = parse_prep(text)
    body = "\n\n".join(f"## {label}\n\n{t}" for label, t in sections) if sections else text
    with open(p, "w", encoding="utf-8") as f:
        f.write(f"# Interview prep: {job.get('title', '')} at {job.get('company', '')}\n\n{body}\n")
    return p


def save_gap_plan(scope, text, parsed, cfg):
    """Writes a gap plan as one markdown file in the output folder. Returns its path."""
    out = os.path.join(BASE, cfg.get("output_dir", "output"))
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, f"{date.today():%Y-%m-%d}_gap_plan_{slug(scope)}.md")
    n = 2
    while os.path.exists(p):
        p = os.path.join(out, f"{date.today():%Y-%m-%d}_gap_plan_{slug(scope)}_{n}.md")
        n += 1
    body = "\n\n".join(f"## {label}\n\n{t}" for label, t in parsed) if parsed else text
    with open(p, "w", encoding="utf-8") as f:
        f.write(f"# Gap plan: {scope}\n\n{body}\n")
    return p
