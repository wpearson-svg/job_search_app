# Shared formats

The desktop app (Python, repo root) and the Android app (`android/`) read and write the same formats, so a reply
from an AI and an export file mean the same thing on both. They are defined here once. The exact expected
text and values are in `shared_tests/*.json`, and both test suites check them. When this file and a fixture disagree,
the fixture is what the code is tested against; fix this file.

## 1. Statuses

| Key | Label | Applied stage |
|---|---|---|
| `new` | New | no |
| `saved` | Saved | no |
| `applied` | Applied | yes |
| `phone_screen` | Phone screen | yes |
| `interview` | Interview | yes |
| `offer` | Offer | yes |
| `rejected` | Rejected | yes |
| `no_response` | No response | yes |
| `withdrawn` | Withdrawn | yes |
| `dismissed` | Dismissed | no |

- The first time a posting enters an applied stage, today's date (`YYYY-MM-DD`, local) becomes `applied_on`.
- Apply never moves a posting from a later stage back to Applied.
- A posting still at `applied` 14 or more days after `applied_on` is due for a follow-up (`tracking.json`).

## 2. Requests to an AI

Every request is plain text for any AI assistant (the app never calls an AI itself). It is built from the posting and (when the setting `send_resume_in_requests` is on)
wrapped with the instructions and master resume:

```
<instructions>
...the resume-writing instructions...
</instructions>

<master_resume>
...the master resume as plain text...
</master_resume>

...the request itself...
```

The `<master_resume>` part is left out when there is no resume. The request bodies are:

| Request | Built by (desktop) | Fixture |
|---|---|---|
| Resume, or resume and cover letter | `writer.build_user_message` | `replies.json` → `build_user_message` |
| Interview prep | `writer.build_prep_message` | `replies.json` → `build_prep_message` |
| Gap plan | `gaps.build_message` | `gaps.json` → `build_message` |
| Wrapper above | `writer.with_context` | `replies.json` → `with_context` |

Every request says to use only facts from the master resume and never to invent experience.

## 3. Replies from an AI (tags)

A reply is any text. Each section sits between an opening and closing tag; text outside tags is ignored. The first
match of each tag is used, the content is trimmed, and an empty section counts as missing.

| Request | Tags, in display order (label) |
|---|---|
| Resume (and cover letter) | `resume`, `cover_letter`, `review_notes` |
| Interview prep | `likely_questions` (Questions they may ask you), `questions_to_ask` (Questions to ask them), `gap_prep` (Gaps to be ready for), `research` (Research before the interview) |
| Gap plan | `priorities` (What to work on first, and why), `plan` (Week-by-week plan), `proof` (Projects that prove each skill), `resume_changes` (Resume changes (only what is true)), `skip` (What not to chase), `questions` (Questions for you) |
| Career file | `career_file`: the whole file as JSON (section 9) |

- A resume reply with no `<resume>` tag keeps the whole reply as the resume, with a note saying so.
- A saved resume is checked: leftover `[bracket]` markers, more than 600 words, and the user's own phrase rules
  (`resume_check_phrases`: pairs of lower-case phrase and warning). See `replies.json` → `check_resume`.

## 4. Export file (`wildthing-export`, version 1)

One UTF-8 JSON file holding everything one person has. Both apps write it (Settings → Export data) and read it
(Settings → Import data). Importing **replaces** everything in that copy, then re-scores every posting against the
imported resume. **API keys are never in the file.** A sample is `shared_tests/export_sample.json`.

```json
{
  "format": "wildthing-export",
  "version": 1,
  "exported_at": "2026-10-31T17:00:00+00:00",
  "app": "desktop | android",
  "settings": {
    "your_name": "", "target_titles": [], "search_keywords": [], "locations": [],
    "greenhouse_boards": [], "lever_companies": [],
    "usajobs": {"location": ""}, "sources": {"remoteok": true, "glassdoor": false},
    "send_resume_in_requests": true, "resume_check_phrases": [["phrase", "warning"]]
  },
  "resume": {"filename": "master_resume.docx", "base64": "..."},
  "instructions": "custom instructions text, or null for the app's default",
  "extras": [{"term": "itil", "added_at": "ISO time"}],
  "profiles": [{"id": 1, "name": "General", "keywords": "one per line", "titles": "one per line", "location": ""}],
  "jobs": [{
    "id": 2, "source": "pasted", "ext_id": "paste-1",
    "title": "", "company": "", "location": "", "url": "", "description": "", "posted": "",
    "pasted": true, "status": "applied", "score": 70,
    "matched": ["sql"], "gaps": [["salesforce", 1]], "flags": [], "title_match": true,
    "added_at": "ISO time", "applied_on": "YYYY-MM-DD or null", "notes": "", "status_updated": "ISO time or null",
    "profile_ids": [1], "links": [{"source": "indeed", "url": "https://..."}],
    "tags": ["scam", "c:Slow to reply"]
  }],
  "events": [{"id": 1, "job_id": 2, "kind": "Interview", "starts_at": "2030-05-06T14:30", "minutes": 45,
              "place": "", "notes": "", "time_zone": "America/Chicago or null"}],
  "outputs": [{"job_id": 2, "kind": "resume | cover_letter | review_notes | prep", "content": "", "warnings": [],
               "created_at": "ISO time"}],
  "gap_plans": [{"scope": "all postings", "content": "the whole reply", "created_at": "ISO time"}],
  "avoided": [{"company": "Acme Inc", "reason": "only you see it"}]
}
```

Rules:

- `resume` is `null` when there is none. `filename` ends in `.docx`, `.md` or `.txt` (Android also accepts `.pdf`
  in a later version; until then it is not written).
- `gaps` entries are `[term, weight]`; weight 2 means the term is in the posting's requirements part.
- `events.starts_at` is the wall-clock time where the event happens, `YYYY-MM-DDTHH:MM`. `time_zone` is an IANA
  zone name. The Android app always writes one. The desktop app writes `null`, which means "the zone of the device
  reading the file", and keeps phone events' local times without the zone.
- A reader refuses a file whose `format` is not `wildthing-export` or whose `version` is higher than it knows.
- Unknown fields are ignored, so a later version can add fields without breaking older readers.
- Files a desktop wrote to `output/` and the folder queue (`queue_items`) are not exported.
- `tags` and `avoided` were added without changing the version: an older reader ignores them, and a file without
  them reads as no tags and no avoided companies. Tag keys are listed in section 8.

## 5. The AI work queue (`aiqueue.py`; fixtures `shared_tests/queue.json`)

Both versions hand work to an assistant through the same folder layout. On Android the folder is `WildThing/` in
Google Drive; on the desktop it is the work folder set in Settings (the app's own folder by default, or a
Drive-synced `WildThing` folder). The assistant only reads and creates files; it never edits or deletes.

```
WildThing/
  AI_INSTRUCTIONS.md                        written by the app (copy of docs/AI_INSTRUCTIONS.md)
  requests/TODO_<batch>.md                  the batch table
  requests/<batch>_<nn>_<kind>_<slug>.md    one request per item
  replies/<batch>_<nn>_<kind>_<slug>.md     the assistant's reply, same name as the request
  replies/TODO_<batch>.reply.md             the assistant's report
  user/                                     shared details (section 6)
```

- **Batch id**: `YYYYMMDD-HHMM-xxxx` (local time of the first request, plus 4 random lower-case letters or digits).
  Drive allows two files with one name, so every name carries the batch id.
- **Kinds**: `resume`, `resume_cover`, `prep`, `gap`. `<nn>` is the item number, two digits. `<slug>` is the company
  (or title, or gap-plan focus) in lower case with dashes, at most 40 characters.
- **Open batch**: new requests join the newest batch the app made until the app has seen a reply report for it;
  after that a new batch starts.
- **Request TODO** (`render_todo`): a heading, `From:` (the device id that made it), `Created:`, `Items:`, the
  standing rules (skip an item whose reply exists; use only facts from the master resume), whether request files
  carry the instructions and resume, then a table `Item | Type | Request file | Reply file | Reply tags`.
- **Request file** (`render_request`): a heading naming the item, where to write the reply and which tags, `---`,
  then the request body (the same text as Copy, including instructions and resume when that setting is on).
- **Reply report** (`replies/TODO_<batch>.reply.md`): a table `Item | Status | Reply file | Reason`, one row per
  item; status is `done`, `skipped` or `failed`, with a one-line reason for the last two. The reader also accepts
  plain lines like `02: skipped - the posting text was empty`; a later row for the same item wins.
- **Import** (`plan_import`), per item of each batch this device made:
  - request file gone: already handled (`gone`);
  - report says `skipped` / `failed`: show the reason, keep the files;
  - a reply with the item's name (or the name the report gives) exists: import the newest; after the save is
    confirmed, delete every copy of that reply and the request file;
  - report says `done` but no reply file: `missing` (wait);
  - otherwise `waiting`.
  When every item is imported or gone, delete the request TODO and the reply report. With no report, replies are
  matched by file name. "Waiting" always comes from the files, never from a status the app edits.
- **Import triggers**: Import replies button, opening the app (Android) or the Queue page (desktop), pull to
  refresh on the Android queue screen.
- **Deleting on Drive**: to the Drive trash by default; a setting makes it permanent. On the desktop the files are
  deleted (in a Drive-synced folder, Drive for desktop moves them to the Drive trash).
- Each app imports only the batches it made (it keeps their ids and items locally), so a phone and a PC can share
  one folder.

## 6. Shared details (`shared_details.py`; fixtures `shared_tests/shared_details.json`)

`WildThing/user/` holds what the phone and the PC share. Each device keeps its own working copy (so it works
offline) and syncs on start-up and on **Sync now**.

| File | Contents |
|---|---|
| `resume.docx` / `resume.md` / `resume.txt` | the master resume (one of them) |
| `search.json` | `{"format": "wildthing-search", "version": 1, "target_titles", "search_keywords", "locations", "profiles": [{name, keywords, titles, location}]}` |
| `instructions.md` | the AI instructions (the app's default when the person has not written their own) |
| `confirmed_skills.json` | `{"format": "wildthing-confirmed-skills", "version": 1, "skills": [...]}`: the "I have this" list while there is no career file; once there is one, the list moves into it as confirmed skills and this file is empty |
| `<file>.meta.json` (`resume.meta.json` for the resume) | `{"file", "version", "changed_at", "device", "sha256"}` |

Never shared: keys, notification and background settings, which sources are on, and the postings database
(postings, statuses, notes and interviews stay per device; move them with Export and Import).

Sync rule (`decide`), per file, using the hash of this device's current copy, the folder's meta, and the two hashes
this device recorded at its last sync of that file (its own copy, the folder's copy):

| Situation | Action |
|---|---|
| only this device has it | push |
| only the folder has it | pull |
| first sync, same content | record |
| first sync, different content | **ask** |
| only this device changed | push (version + 1) |
| only the folder changed | pull |
| both changed (to different content) | **ask**: show both and let the person keep one |
| neither changed | nothing |

After pulling the resume, search settings or skills, every posting is re-scored. Profiles are matched by name.

## 7. Shared postings (`shared_db.py`; fixtures `shared_tests/shared_db.json`)

`WildThing/user/wildthing.db` in Google Drive, used only on a device with a Google account linked. It is an SQLite file
that no device edits in place: each keeps working on its own `jobs.db`, and a sync downloads the shared file, merges it
in, applies the result locally and uploads a fresh copy. Every upload holds everything that device knows, so a copy
overwritten by an upload that crossed is rebuilt on the other device's next sync. If Drive holds two copies, both are
merged and one is left.

Tables (all text columns hold `""` rather than NULL):

| Table | Columns |
|---|---|
| `info` | `key`, `value`: `format` = `wildthing-shared-db`, `version` = `2`, `written_at`, `device` |
| `postings` | `uid` (key), `source`, `ext_id`, `title`, `company`, `location`, `url`, `description`, `posted`, `pasted` (0/1), `added_at`, `status`, `status_at`, `applied_on`, `notes` |
| `links` | `posting` (uid), `source`, `url` |
| `events` | `uid`, `posting`, `kind`, `starts_at`, `minutes`, `place`, `notes`, `time_zone`, `changed_at` |
| `outputs` | `posting`, `kind`, `content`, `warnings_json`, `created_at` (saved AI work) |
| `gap_plans` | `uid`, `scope`, `content`, `created_at` |
| `tombstones` | `uid`, `kind` (`posting`, `event`, `gap_plan`), `at`: what was deleted |
| `avoided` | `key` (the company name through `norm`: lower case, no Inc/LLC/punctuation), `company`, `reason`, `active` (0/1), `changed_at` (version 2) |
| `tags` | `posting` (uid), `tag` (section 8), `active` (0/1), `changed_at` (version 2) |

Version 2 added `avoided` and `tags`. A version 1 file has neither table and reads as having none; an app that only
knows version 1 refuses a version 2 file, so update both apps together.

Not shared: scores and profile tags (each device works them out), the AI queue's records, keys, settings (section 6).
A file whose `version` is higher than the app knows is refused.

Each device's `jobs.db` gains `uid` on postings, interviews and gap plans (random 32 hex characters), `changed_at` on
interviews, a `tombstones` table filled by delete triggers, and `sync_notes` (each posting's notes at the last sync).
An import from an export file clears both, so what it replaced is not deleted on other devices.

Merge rules, the same in both apps:

1. **Same posting, different uid** (found on both devices before they first synced): a posting only in the shared file
   takes over a local one that has the same source and id, else a shared link, else the same title and company
   (`dup_key`) in the same place (`same_place`). The local posting takes the shared uid.
2. **Deleted** anywhere wins: the posting goes, with its interviews and saved AI work. Tombstones are kept.
3. **Status**: the side with the later `status_at` wins (ties: the higher status name), bringing its `applied_on`.
4. **Notes**: if only one side changed them since the last sync, that side wins. If both changed, both are kept:
   this device's text, then a blank line, the line `--- Also written on another device ---`, and the other's.
5. **Text and links**: blank fields are filled from the other side; links from both are kept.
6. **Interviews**: the later `changed_at` wins. **Saved AI work**: the later `created_at` wins. **Gap plans**: all are kept.
7. **Avoided companies and tags**: the copy with the later `changed_at` wins. Removing one keeps its row with
   `active` 0, so a removal travels like any other change; at the same `changed_at`, active beats removed. Tags follow
   their posting through rule 1 and go with it when it is deleted.

The app syncs postings when it starts, after Fetch and on Sync now (desktop), and when it opens, on pull to refresh
and on Sync (Android).

## 8. Tags and avoided companies (`db.TAGS`; Android `Marks.kt`)

A tag says something about a posting that its status does not. The built-in keys are fixed, so that the same tag
from many people could one day be counted together:

| Key | Label | Meaning |
|---|---|---|
| `ai_interview` | AI interview | Uses AI to screen or interview applicants |
| `scam` | Possible scam | Signs of a fake job or a scam |
| `ghost` | Ghost posting | Reposted again and again, never seems to be filled |
| `no_pay` | No pay listed | The posting gives no pay or pay range |
| `agency` | Agency or recruiter | Posted by a staffing agency or outside recruiter |
| `unpaid_test` | Unpaid test task | Asks for unpaid work as part of applying |

A tag you type yourself is kept as `c:` followed by your words (spaces squeezed, 40 characters at most). Typing a
built-in tag's label gives that tag instead. Tagged postings are never removed by the list clean-up.

Avoiding a company hides its postings from the list (both apps have a "Show avoided" switch). Companies match by
`norm(company)`, the same cleanup duplicate matching uses. Locally both are rows in `job_tags(job_id, tag, active,
changed_at)` and `avoided(key, company, reason, active, changed_at)`; a removal sets `active` to 0.

## 9. The career file (`career.py`; fixtures `shared_tests/career.json`, sample `shared_tests/career_sample.json`)

Everything true about the person, in one JSON file: `WildThing/user/career.json`. It is the source of facts for
scoring and for everything an AI writes. The master resume stays the example of format and tone.

- **Made by an AI**, once, from the person's own documents (old resumes, a knowledge base, a skills list), following
  "Building the career file" in `AI_INSTRUCTIONS.md`. The reply holds the file between `<career_file>` tags; a
  `json` code fence inside the tags is allowed.
- **Checked by the app** before it is kept (`career.validate`). A file that fails is refused with the reasons and the
  current file stays. The person reviews a new file before accepting it.
- **The request** (`career.build_request`) carries the "Building the career file" part of `AI_INSTRUCTIONS.md`
  between `<career_file_instructions>` tags, the current file between `<current_career_file>` tags when rebuilding,
  and each document's text as `<source_document name="...">`. It can be copied into any AI chat, or written to the work
  folder as `requests/career_<YYYYMMDD-HHMM>.md`; the AI then creates `replies/career_<YYYYMMDD-HHMM>.reply.md`. It is
  not a batch item: no TODO row and no report. "Look in the work folder" takes the newest such reply; once the file is
  accepted, that reply and its request are deleted.
- **Kept** in the data folder as `career.json` (Android: the app's private storage) and shared through `WildThing/user/`
  like the other shared details (section 6): a copy pulled from the folder is checked, and one that fails is not used.
  While it is being built, `career_request.md` (the request) and `career_pending.json` (a checked file waiting for
  review) sit beside it.
- **Changed only by the app** after that: "I have this" adds a skill with `source` `confirmed` (`add_confirmed`), and
  undoing it removes only a confirmed skill (`remove_confirmed`). Skills marked before there was a career file (the
  `extras` table, shared as `confirmed_skills.json`) move into it when a file is accepted or arrives, and before each
  sync (`usersync.fold_extras`). A major revision is a rebuilt file, made the same
  way, that replaces the current one once accepted (`replace`); confirmed skills it does not list are carried over.
  The person does not edit the file by hand. A copy changed outside the app is treated as a new upload and checked.

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

Rules (`career.validate`; every case is in `shared_tests/career.json`):

- `format` must be `wildthing-career`; a `version` higher than the app knows is refused. Unknown fields are allowed
  and kept, so a later version can add some.
- `person.name` is required. In each list, these are required and non-empty: roles `id`, `employer`, `title`,
  `start`; projects `id`, `name`; skills `name`, `source`; certifications `name`, `status`; education `school`;
  flags `text`; achievements `text`. Other text fields may be empty.
- Dates are `YYYY` or `YYYY-MM`. An empty `end` means the role is current. A role may not end before it starts.
- Every role and project `id` is unique; skill `evidence` may name only those ids.
- A skill name appears once (case does not matter). A skill with `source` `documents` needs `evidence` or `notes`
  saying where it comes from.
- `privacy` lists and `wording.avoid` phrases are checked against every resume and letter the app saves
  (`career.check_document`): a hit is a warning shown with the document. Case does not matter.
- **Scoring reads it in place of the master resume** whenever there is a usable career file (the resume is the
  fallback). The matcher's skill list is searched in `career.text`: the summary, headline, role titles, scope,
  details and achievements, project text, skill names, earned certifications (`status` `earned`; one in progress or
  expired does not count) and education. Privacy lists, wording rules and flags are left out. Only terms on the skill
  list count, as before. Scores stay on each posting in the device's own database; every posting is re-scored when a
  file is accepted and when one arrives from the other device.
