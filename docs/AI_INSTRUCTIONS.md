# Instructions for the AI assistant working this folder

This folder is a work queue from WildThing, a job search app. The person you are helping uses it to get tailored
resumes, cover letters, interview prep and skills plans. You only need to **read** files and **create** new ones.
Never edit, rename, move or delete a file here; WildThing cleans up after it has saved your work.

## The folder

```
AI_INSTRUCTIONS.md          this file
requests/
  TODO_<batch>.md           a batch: a table with one row per item
  career_<time>.md          a request to build the career file (see "Building the career file")
  <batch>_<nn>_<type>_<name>.md   one request per item
replies/                    you create your files here
user/                       the person's shared details (WildThing keeps these in step; leave them alone)
```

A batch id looks like `20261031-1810-k3f9`. Every file name carries it, so names never clash.

## What to do

1. Look in `requests/` for every `TODO_<batch>.md` that has no matching `TODO_<batch>.reply.md` in `replies/`.
   Those are the pending batches. Do them oldest first. A `career_<time>.md` with no matching
   `career_<time>.reply.md` in `replies/` is a career file request: do it as "Building the career file" says.
2. Read the batch's TODO. For each row:
   - If a file named like the row's **Reply file** already exists in `replies/`, skip that item (it is done).
   - Otherwise open the **Request file** and follow it. It says what to write and which tags to use. It contains
     the posting and, unless the person keeps them with you already, their resume-writing instructions and their
     master resume.
   - Create the reply in `replies/` with **exactly** the reply file name from the row. Put only the tagged parts in
     it (see the table below), nothing before or after.
3. When every item of the batch has been handled, create `replies/TODO_<batch>.reply.md`:

   ```
   # Replies for batch <batch>

   | Item | Status | Reply file | Reason |
   |---|---|---|---|
   | 01 | done | <the reply file name> | |
   | 02 | skipped | | <one line: why> |
   | 03 | failed | | <one line: what went wrong> |
   ```

   - **done**: you created the reply file.
   - **skipped**: you chose not to do it (for example, the posting text is empty, or it is not a real job posting).
   - **failed**: you tried and could not (for example, the request file could not be read).
   Give a reason for every skipped or failed item. WildThing shows it to the person.

## Rules

- Use only facts from the master resume. Do not invent experience, employers, dates, numbers, skills or
  certifications. If something the posting asks for is not in the resume, do not claim it; say so in the review
  notes or the gap prep instead.
- Follow the person's resume-writing instructions when the request includes them (or the copy you already hold).
- Skip any item whose reply file already exists.
- Create new files only. Do not change or delete anything.

## Reply tags by request type

| Type | Tags in the reply file |
|---|---|
| Resume | `<resume>`, `<review_notes>` |
| Resume and cover letter | `<resume>`, `<cover_letter>`, `<review_notes>` |
| Interview prep | `<likely_questions>`, `<questions_to_ask>`, `<gap_prep>`, `<research>` |
| Gap plan | `<priorities>`, `<plan>`, `<proof>`, `<resume_changes>`, `<skip>`, `<questions>` |
| Career file | `<career_file>` (see below) |

Each tag opens and closes around its part, for example `<resume>...</resume>`.

## Building the career file

The career file holds everything true about the person: their full work history, skills, certifications and
education, in more detail than any one resume. WildThing scores postings against it and every request draws its
facts from it. You build it once from the person's own documents; after that WildThing keeps it up to date. Do this
when a request or the person asks you to build (or rebuild) their career file.

**Sources.** Use only what the person gave you for this: their documents (old resumes, a knowledge base, skills
lists, performance reviews) and what they tell you. A job posting is never a source. It describes a job, not the
person; nothing in a posting goes into this file.

**What to write.** One JSON object in this shape:

```json
{
  "format": "wildthing-career", "version": 1, "updated_at": "ISO time",
  "person": {"name": "", "headline": "", "contact": {"email": "", "phone": "", "location": "",
             "links": [{"label": "", "url": ""}]}},
  "summary": "",
  "roles": [{"id": "r1", "employer": "", "show_as": "how to name the employer on documents, or empty",
             "title": "", "start": "YYYY-MM", "end": "YYYY-MM, or empty for now", "location": "", "type": "",
             "scope": "what the person owned, led or supported", "details": "the full story, any length",
             "achievements": [{"text": "", "skills": ["sql"], "numbers": ["18%"]}]}],
  "skills": [{"name": "sql", "source": "documents | confirmed", "evidence": ["r1"], "notes": ""}],
  "certifications": [{"name": "", "issuer": "", "date": "YYYY or YYYY-MM or empty", "status": "earned | in_progress | expired"}],
  "education": [{"school": "", "credential": "", "field": "", "start": "", "end": "", "notes": ""}],
  "projects": [{"id": "p1", "name": "", "date": "", "description": "", "skills": [], "link": ""}],
  "privacy": {"never_name": ["names never to put on a document"], "never_mention": ["subjects never to bring up"]},
  "wording": {"avoid": [{"phrase": "managed a team", "why": "led and implemented; did not manage people"}]},
  "flags": [{"text": "a conflict or doubt in the sources, for the person to settle", "sources": ["file names"]}]
}
```

In detail:

- `"format": "wildthing-career"`, `"version": 1`, `"updated_at"`: the time now, `"person"`: name, headline, contact.
- `roles`: every job, newest first. Give each an `id` (`r1`, `r2`, ...). `start` and `end` are `YYYY-MM` or `YYYY`;
  leave `end` empty for a current job. In `scope`, say plainly what the person owned, led or only supported. Put the
  full story in `details`; it can be long. `achievements` are single claims with the skills and numbers in them.
- `skills`: each skill once, lower case. `"source": "documents"`, and `evidence`: the ids of the roles or projects
  where it was used. If a skill has no single role, leave `evidence` empty and say in `notes` where it comes from.
- `certifications` (status `earned`, `in_progress` or `expired`), `education`, `projects` (ids `p1`, `p2`, ...).
- `privacy`: names the person never wants on a document (an employer or client they cannot name) and subjects never
  to bring up, but only those the person or their documents state. For an employer that must not be named, also
  write how to describe it in that role's `show_as`, for example "a regional clinic network".
- `wording.avoid`: phrases the person has said not to use about themselves, with the reason.
- `flags`: anything you could not settle. When sources disagree, or a claim appears only once in an old file and
  nothing else supports it, leave the claim out and add a flag naming the files. Do not choose for the person.

**Rules.** Keep every fact as the sources state it: dates, titles, numbers and scope. Do not round up, merge two jobs
or upgrade a title. Nothing goes in the file without a source.

**The reply.** Put the whole file between `<career_file>` and `</career_file>`, and nothing else. For a request file
`requests/career_<YYYYMMDD-HHMM>.md` in this folder, create `replies/career_<YYYYMMDD-HHMM>.reply.md` (the same name,
ending `.reply.md`). In a chat, reply with it. A rebuild request includes the current file: keep the skills it marks
`"source": "confirmed"` (the person confirmed them in WildThing) unless their documents now cover them.

## For the person

Tell your assistant: **"Read AI_INSTRUCTIONS.md in the WildThing folder and process the pending batch."**
This needs an assistant that can read and create files in this folder (for a Google Drive folder, one with access
to that Drive). Then open WildThing: it imports the replies when it opens, or press **Import replies**.
