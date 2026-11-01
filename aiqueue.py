"""The AI work queue format, shared by the desktop (a local or Drive-synced folder) and Android (a Google Drive folder).

    WildThing/
      AI_INSTRUCTIONS.md                 how any assistant should work the queue (docs/AI_INSTRUCTIONS.md)
      requests/TODO_<batch>.md           the batch: one row per item
      requests/<batch>_<nn>_<kind>_<slug>.md   one request per item
      replies/<same name as the request>       the assistant's answer, in the tagged reply format
      replies/TODO_<batch>.reply.md      the assistant's report: done, skipped or failed for each item

The assistant only reads and creates files. WildThing imports a reply, confirms the save, then deletes that item's
reply and request; when a whole batch is imported it deletes both TODO files. Skipped and failed items stay, with
the reason shown. The full format is in docs/formats.md and the exact answers in shared_tests/queue.json.
"""
import re

import writer

KINDS = {"resume": "Resume", "resume_cover": "Resume and cover letter", "prep": "Interview prep", "gap": "Gap plan"}
REPLY_TAGS = {
    "resume": "<resume>, <review_notes>",
    "resume_cover": "<resume>, <cover_letter>, <review_notes>",
    "prep": "<likely_questions>, <questions_to_ask>, <gap_prep>, <research>",
    "gap": "<priorities>, <plan>, <proof>, <resume_changes>, <skip>, <questions>",
}
STATUSES = ("done", "skipped", "failed")
INSTRUCTIONS_FILE = "AI_INSTRUCTIONS.md"

_ITEM = re.compile(r"^(\d{8}-\d{4}-[a-z0-9]{4})_(\d{2,3})_(resume_cover|resume|prep|gap)_[a-z0-9-]*\.md$")
_TODO = re.compile(r"^TODO_(\d{8}-\d{4}-[a-z0-9]{4})\.md$")
_REPLY_TODO = re.compile(r"^TODO_(\d{8}-\d{4}-[a-z0-9]{4})\.reply\.md$")


def batch_id(now, suffix):
    """now: a datetime; suffix: 4 lower-case letters or digits that make the id unique (Drive allows duplicate names)."""
    return f"{now:%Y%m%d-%H%M}-{suffix}"


def item_name(batch, n, kind, label):
    return f"{batch}_{n:02d}_{kind}_{writer.slug(label)}.md"


def todo_name(batch):
    return f"TODO_{batch}.md"


def reply_todo_name(batch):
    return f"TODO_{batch}.reply.md"


def parse_item_name(name):
    """(batch, item number, kind) for a request or reply file name, or None."""
    m = _ITEM.match(name or "")
    return (m.group(1), int(m.group(2)), m.group(3)) if m else None


def batch_of_todo(name):
    m = _TODO.match(name or "")
    return m.group(1) if m else None


def batch_of_reply_todo(name):
    m = _REPLY_TODO.match(name or "")
    return m.group(1) if m else None


def render_request(batch, n, kind, label, body):
    """One request file. body is the request itself (already wrapped with instructions and resume when that is on)."""
    name = item_name(batch, n, kind, label)
    return (f"# Request {n:02d} of batch {batch}: {KINDS[kind]}, {label}\n\n"
            f"Write your answer to `replies/{name}`. Reply with the tagged parts only ({REPLY_TAGS[kind]}); "
            "use only facts from the master resume and do not invent experience.\n\n---\n\n" + body + "\n")


def render_todo(batch, origin, created, items, carries_context):
    """items: list of dicts with n, kind, label (in order). origin: the device id that made the batch."""
    context = ("Each request file contains the resume-writing instructions and the master resume." if carries_context
               else "Use the resume-writing instructions and master resume you already hold for this person.")
    lines = [
        f"# WildThing batch {batch}",
        "",
        f"- From: {origin}",
        f"- Created: {created}",
        f"- Items: {len(items)}",
        "",
        "Follow AI_INSTRUCTIONS.md in the WildThing folder. In short: do each item below, write each reply to "
        "`replies/` under the reply file name shown, then write `replies/" + reply_todo_name(batch) + "` with one row "
        "per item. Skip any item whose reply file already exists. Use only facts from the master resume; do not "
        "invent experience.",
        "",
        context,
        "",
        "| Item | Type | Request file | Reply file | Reply tags |",
        "|---|---|---|---|---|",
    ]
    for it in items:
        name = item_name(batch, it["n"], it["kind"], it["label"])
        lines.append(f"| {it['n']:02d} | {KINDS[it['kind']]} | {name} | {name} | {REPLY_TAGS[it['kind']]} |")
    return "\n".join(lines) + "\n"


def render_reply_todo(batch, rows):
    """What the assistant writes (used in AI_INSTRUCTIONS.md and tests). rows: (n, status, reply, reason)."""
    lines = [f"# Replies for batch {batch}", "", "| Item | Status | Reply file | Reason |", "|---|---|---|---|"]
    lines += [f"| {n:02d} | {status} | {reply} | {reason} |" for n, status, reply, reason in rows]
    return "\n".join(lines) + "\n"


_LIST_ROW = re.compile(r"^\s*[-*]?\s*(\d{1,3})\s*[:.)-]?\s*(done|skipped|failed)\b(.*)$", re.I)


def parse_reply_todo(text):
    """{item number: {status, reply, reason}} from the assistant's report. Reads the table it is asked for, and also
    plain lines like "02: skipped - the posting text was empty". Later rows for the same item win."""
    out = {}
    for line in (text or "").splitlines():
        if "|" in line:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            n = next((c for c in cells if re.fullmatch(r"\d{1,3}", c)), None)
            status = next((c.lower() for c in cells if c.lower() in STATUSES), None)
            if n is None or status is None:
                continue
            reply = next((c.strip("`") for c in cells if c.strip("`").lower().endswith(".md")), "")
            rest = [c for c in cells if c and c != n and c.lower() != status and c.strip("`") != reply]
            out[int(n)] = {"status": status, "reply": reply, "reason": rest[-1] if rest else ""}
            continue
        m = _LIST_ROW.match(line)
        if m:
            rest = m.group(3)
            reply = next((w.strip("`,.;()") for w in rest.split() if w.strip("`,.;()").lower().endswith(".md")), "")
            reason = rest.replace(reply, "").strip(" -:;,.`()")
            out[int(m.group(1))] = {"status": m.group(2).lower(), "reply": reply, "reason": reason}
    return out


def plan_import(items, requests_present, replies, reply_todo):
    """What to do with one batch.

    items: [{n, name}] the batch's items, as this app recorded them.
    requests_present: names of the request files still in requests/.
    replies: [{name, modified}] every file in replies/ (Drive allows several with one name; modified is ISO time).
    reply_todo: the text of the newest TODO_<batch>.reply.md, or None.

    Returns {"items": [{n, action, reply, delete, reason}], "complete": bool}. action is one of:
      import  - reply is replies[reply] (the newest match); after the save, delete replies[delete] and the request
      waiting - no reply yet
      missing - the report says done but the reply file is not there (yet)
      skipped / failed - the assistant's reason is in reason; the files stay
      gone    - the request file is no longer there (imported or removed before)
    complete: every item is import or gone, so the TODO files can go once the imports are saved.
    """
    report = parse_reply_todo(reply_todo) if reply_todo else {}
    out = []
    for it in items:
        n, name = it["n"], it["name"]
        if name not in requests_present:
            out.append({"n": n, "action": "gone", "reply": None, "delete": [], "reason": ""})
            continue
        entry = report.get(n)
        names = {name} | ({entry["reply"]} if entry and entry["reply"] else set())
        found = [i for i, r in enumerate(replies) if r["name"] in names]
        found.sort(key=lambda i: (replies[i]["modified"] or "", i), reverse=True)
        if entry and entry["status"] in ("skipped", "failed"):
            out.append({"n": n, "action": entry["status"], "reply": None, "delete": [],
                        "reason": entry["reason"] or "No reason given."})
        elif found:
            out.append({"n": n, "action": "import", "reply": found[0], "delete": sorted(found), "reason": ""})
        elif entry and entry["status"] == "done":
            out.append({"n": n, "action": "missing", "reply": None, "delete": [],
                        "reason": "The report says done, but the reply file is not in replies/ yet."})
        else:
            out.append({"n": n, "action": "waiting", "reply": None, "delete": [], "reason": ""})
    return {"items": out, "complete": all(x["action"] in ("import", "gone") for x in out)}
