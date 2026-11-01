# WildThing

A local app that finds job postings, scores each one against your master resume, shows what each posting asks for that your resume does not, and helps you get a tailored resume, cover letter, interview prep and a skills plan from an AI assistant of your choice. It runs only on your computer at http://127.0.0.1:5050. Nothing is sent anywhere unless you copy it into an AI yourself or switch on an optional source.

The app never edits your resume and never makes up experience. Matching is a word list, not understanding (see Limits).

There is also an **Android app** in the [`android/`](android/) folder: the same scoring, tracking and AI hand-off, standalone on the phone. See [Android app](#android-app) below.

## Start it

Double-click `run.bat` (Windows). The first run sets itself up; it needs Python from python.org with the "py launcher" option ticked. A browser tab opens. To run the checks: `python -m unittest tests` (this includes the shared cases in `shared_tests/`, see below).

## First run: Settings

Open **Settings** (top bar) and go top to bottom:

1. **Master resume.** Upload a .docx, .md or .txt. Every posting is scored against it until you have a career file (below), and the AI is told to use only facts from it. Uploading a new one re-scores everything.
2. **Your search.** The job titles you want, search keywords, the places that count as a match (your city, state, "remote"), and your main place to search.
3. **Sources.** A list of every source with a box to switch each one on or off (see "Where postings come from"). USAJOBS needs your free key.
4. **How the AI writes for you.** The app ships general resume-writing instructions. Replace them with your own if you have some.
5. **Google Drive** (optional): link Google so the AI queue and shared details use the `WildThing` folder in your Drive directly, the same one the phone uses. See [Google Drive on the desktop](#google-drive-on-the-desktop).
6. **Keys** (optional): for USAJOBS and the Google OAuth client. Saved on this computer and never shown again.

Until a master resume and target titles are set, a banner reminds you.

**Move your data** (section 7) saves everything as one file (settings, resume, instructions, postings, applications, interviews, AI work, gap plans; never your keys), for a backup or to open in the Android app. **Import data** replaces what is in this copy with a file's contents.

## What each page does

- **Postings.** Every posting with a 0 to 100 match score, filters for status and profile, and a button to **Fetch** new ones. Click a row to fill the side panels: the **bottom panel is about the posting** (its text, profile tags, what you match and what it asks for that your resume does not show, with an "I have this" button for each gap) and the **right panel is about you** (status, applied date and notes, interviews with calendar links, and the state of your resume, cover letter and prep). With nothing selected the right panel shows follow-ups due, interviews coming up, replies waiting and your top gaps. The three icons at the top of the page open and close the menu, the right panel and the bottom panel, and the app remembers your choice. On a phone the menu slides over the page, postings become cards, and a tap opens the full posting page. On each row: **Apply** opens the posting in a new tab and marks it applied. Clean-up buttons: **Merge duplicates**, **Re-score all**, and removing fetched postings you have not touched, or the untouched ones outside your areas. Only postings still at status New that you did not paste yourself are ever removed. Click a title to open the posting page.
- **Posting page.** What it matches, what it asks for that your resume does not show, the full text, the links where else it was listed, your status and notes, interview dates, and the AI buttons described below.
- **Profiles.** A profile is a saved focus: its own keywords, target titles and place (for example "Project management" or "Help desk, Denver"). Pick one when you press Fetch and every posting found is tagged with it. Filter the Postings page by profile to see one focus at a time. A posting can carry several tags.
- **Paste a posting.** Paste the description from LinkedIn, Indeed or anywhere. This always works, even when the fetchers are off.
- **Applications.** Everything you applied for with a status (Applied, Phone screen, Interview, Offer, Rejected, No response, Withdrawn), the date applied, notes, a count per status, and upcoming interviews. A posting still at "Applied" after 14 days is marked for a follow-up. You can log an application made somewhere else at the bottom.
- **Queue.** The folder way of working with an AI (next section).
- **Weekly.** Choose 7, 14 or 30 days back: applications sent, phone screens and interviews, the rate, and how many are waiting 14+ days, with a plain-facts block you can copy into a post or check-in. It also lists what is coming up in the next two weeks.
- **Gap plan.** The gaps across all postings you have not dismissed, ranked by how often they appear and how often they are required, with a quick list and plans you can have the AI write (below).
- **My resume.** The skills the app found in your master resume, and anything you marked "I have this".
- **Settings.** As above.

### Interviews and calendar
On a posting page, add an interview or follow-up with a date and time. Each one gets an **Add to Google Calendar** link and a downloadable `.ics` file; `/calendar.ics` has all of them for any calendar app. Times are saved as local times with no time zone, so check them after adding.

### "I have this"
If a posting asks for something you have really done but your resume does not say, press **I have this**. It counts as a match from then on and postings are re-scored. It does not change your resume. Once you have a career file it is kept there as a confirmed skill (before that, in a list of its own, which moves into the file when you accept one). Removing it on the My resume page takes out only a skill you confirmed; one from your documents stays. If it is true and belongs on resumes, add it to your master resume.

### Tags and companies you avoid
Tags say something about a posting that its status does not: **AI interview**, **Possible scam**, **Ghost posting**, **No pay listed**, **Agency or recruiter**, **Unpaid test task**, or one you type yourself. Tick them in the side panel or on the full posting page, and pick one under **Tag** above the list to see only those postings. Tagged postings are never removed by **Clean up the list**.

**Avoid** on a posting (or Settings, section 9) hides that company's postings from the list; tick **Show avoided** to see them again, dimmed. Names match without Inc, LLC and punctuation, so "Acme, Inc." and "ACME" are the same company. The reason you give is only for you. With Google linked, both are shared with the phone.

### Career file
**Career file** in the menu holds everything true about you in one file: your full history, skills, certifications, education and the rules for your documents (names never to use, phrases to avoid). Your master resume has to fit on a page; this file does not. To build it, choose your documents (old resumes, a knowledge base, skills lists) and press **Make the request**, then copy it into your AI or **Send to the work folder**. Bring the reply back with **Look in the work folder** or by pasting it. WildThing checks the file, shows you what it holds (and, for a rebuild, what changed), and keeps it only when you press **Accept and save**. Things your AI could not settle from your documents are listed under "To settle". With Google linked it is shared with the phone. The format is in [`docs/formats.md`](docs/formats.md), section 9.

Once you have one, postings are scored against the career file instead of the master resume (the resume is still the example of format and tone), and every posting is re-scored when a new file is accepted or arrives from the phone. The Career file page lists the skills scoring finds in it. Only skills on WildThing's skill list count, and a certification counts only once it is earned. "I have this" skills are kept in it too.

### Duplicates
The same job found on two boards (or fetched twice) is detected by company, title and place. **Merge duplicates** keeps one posting, keeps your status and notes, and lists the other links under "Also listed at".

## Working with an AI assistant

The app never calls an AI itself, and it does not depend on any one assistant. It writes a request, you give it to the assistant you already use, and the answer comes back to the app. There are two ways to hand things over; both do the same job.

### Way 1: copy and paste (any assistant)
On a posting, press a **Copy for your AI** button: resume, resume and cover letter, or interview prep. On the Gap plan page, press **Copy for your AI: gap plan**. Paste it into your assistant, then paste the whole reply into the box on the same page and press **Keep this reply** (or **Keep this prep**, **Keep this plan**). The app saves what it finds and warns about things like leftover [bracket markers] or a resume that runs long.

### Way 2: the AI queue (an assistant that can read and create files)
Use the **Send to folder** buttons instead. Requests gather in a **batch** in the work folder, and the assistant answers them there. The full guide is the app's **How the AI queue works** page (Queue page, the **?** next to the title).

```
AI_INSTRUCTIONS.md                        what the assistant should do (the app writes it)
requests/TODO_<batch>.md                  the batch: one row per request
requests/<batch>_<nn>_<type>_<name>.md    one file per request
replies/<same name>                       the assistant's answer
replies/TODO_<batch>.reply.md             the assistant's report: done, skipped or failed, with a reason
```

**For the person:** tell your assistant "read AI_INSTRUCTIONS.md and process the pending batch". Then open the **Queue** page: it imports what has come back (or press **Import replies**). Each reply is filed exactly as if you had pasted it. After a reply is saved, its reply and request files are deleted; when a whole batch is in, its TODO files go too, so after a normal run the folders are empty. Anything the assistant skipped or could not do stays, and the Queue page shows its reason.

The work folder is the app's own folder unless you set **AI work folder** in Settings. To share one queue with the Android app, link Google (see [Google Drive on the desktop](#google-drive-on-the-desktop)): the app then uses the `WildThing` folder in your Drive directly. Each app only imports the batches it made. If you change the work folder while requests are waiting, they are kept, and the Queue page says where; switch back to import them.

**For an AI agent reading this:** follow `AI_INSTRUCTIONS.md` in the work folder (the master copy is [docs/AI_INSTRUCTIONS.md](docs/AI_INSTRUCTIONS.md)). Read and create files only; never edit or delete. Use only facts from the master resume. Do not invent experience.

Reply tags, for reference (each request file repeats them):

| Request | Tags in the reply |
|---|---|
| Resume | `<resume>`, `<review_notes>` |
| Resume and cover letter | `<resume>`, `<cover_letter>`, `<review_notes>` |
| Interview prep | `<likely_questions>`, `<questions_to_ask>`, `<gap_prep>`, `<research>` |
| Gap plan | `<priorities>`, `<plan>`, `<proof>`, `<resume_changes>`, `<skip>`, `<questions>` |

A resume reply without `<resume>` tags is kept whole as the resume. Saved resumes and letters also go in `output/` as `.md` files, and as `.docx` copies when [pandoc](https://pandoc.org) is installed.

### If your AI already holds your resume and instructions
Requests normally include your instructions and master resume, so they work in any new chat. If your assistant has a project or saved chat that already holds them, tick the box on the Settings page to stop repeating them. Keep that copy the same as the master resume in WildThing.

### Sharing your details with the phone
Link Google in Settings (section 5), or set **Shared details folder** to a `WildThing\user` folder that something else keeps in step. Your master resume, search settings and profiles, AI instructions, career file and "I have this" skills then stay in step with the Android app: the app syncs when it starts and after you change one of them. If one was changed in both places since the last sync, the **Sync** page shows both and asks which to keep.

With Google linked, your **postings** are shared too, through `WildThing/user/wildthing.db`: each posting with its status, applied date, notes, interviews, saved AI work, and your gap plans. Each device keeps working on its own copy; the app merges with the shared file when it starts, after Fetch and on **Sync now**, so a status changed on the phone shows on the PC and the other way round. The newer status wins; notes written on both devices since the last sync are both kept; deleting a posting deletes it on both. Scores are worked out on each device. Without Google linked nothing is shared, and keys and sources always stay on each device. The rules are in [docs/formats.md](docs/formats.md), section 7.

### Google Drive on the desktop
The desktop app can use the `WildThing` folder in your Google Drive directly, the way the phone does, with no Drive for desktop installed. It needs an OAuth client of type **Desktop app** in the same Google Cloud project as the phone's Android client (see [android/README.md](android/README.md), "Setting up Google", for the project itself).

1. In **console.cloud.google.com**, with the WildThing project selected, open **Google Auth Platform > Clients > Create client**.
2. Application type **Desktop app**, any name (for example "WildThing desktop"), then **Create**.
3. Google shows a client id and a client secret. Type them into **Settings > 6. Keys** in this app (**Google OAuth client id** and **Google OAuth client secret**) and save. They are kept in `keys.local.json`, which is never committed. Do not paste them anywhere else.
4. In **Settings > 5. Google Drive**, press **Link Google**. Your browser goes to Google; choose the account, allow access, and Google sends you back to this app. "Use Google Drive" is switched on for you.
5. Press **Check Drive access**: it lists every file the app can see in `WildThing/`, `requests/`, `replies/` and `user/`.

The same two Drive access choices as the phone apply: **Only files WildThing creates** (`drive.file`) or **All of my Drive** (`drive`); changing it needs **Link again**. Google most likely lets the phone and the desktop see each other's files with `drive.file` when both clients are in the same project, but files your AI creates are probably invisible with it; Check Drive access shows which. While the project is in testing mode, Google asks you to link again about every 7 days; the app says so when it happens. The token Google gives back is kept in `data/google_token.json` (never committed); **Unlink** revokes it and deletes it.

## Fetching postings

**Fetch** pulls from every source that is switched on and reports each one's result, or why it was skipped. One source failing never stops the others. A posting whose location does not match your places (worldwide and "anywhere" do not count as a match) is skipped.

Settings section 3 lists every source with a box to switch it on or off (this computer only):

- **RemoteOK and Remotive** (on by default): mostly remote jobs. No key.
- **Indeed and LinkedIn** (on by default), **ZipRecruiter, Glassdoor and Google Jobs** (off by default), all through the free [python-jobspy](https://github.com/speedyapply/JobSpy) library, installed by `run.bat`. No key or account. Indeed returns full descriptions. LinkedIn returns descriptions when `jobspy.linkedin_fetch_description` is true, which costs one extra request per posting, and it may rate-limit (HTTP 429). ZipRecruiter and Glassdoor block automated requests often; Google Jobs gathers postings from many boards and is searched as "keyword jobs near your place". Other settings in `config.json` under `jobspy`: `results_wanted`, `linkedin_results_wanted`, `hours_old` (168 is one week), `max_keywords`, `distance`.
- **USAJOBS** (on by default, runs once the key is saved): US federal jobs. Request a free key at developer.usajobs.gov ("API Request"); it is emailed to you. Enter it and that email address in Settings section 6.
- **Company boards:** list Greenhouse board names or Lever company names in Settings section 3.

LinkedIn's and Indeed's terms restrict automated collection. Use them at your own judgment and keep the volume small.

## Your files and privacy

Everything personal stays on this computer and is listed in `.gitignore`, so sharing the code does not share your information:

- `data/`: your settings (`shared_settings.json` for what the phone shares, `user_settings.json` for this computer only), master resume, instructions, this copy's device id and the last sync state
- `keys.local.json`: your keys and the Google OAuth client (copy `keys.local.example.json` to create it, or use the Settings page)
- `data/google_token.json`: the Google sign-in token, when Google is linked

These live in your data folder, by default `%LOCALAPPDATA%\WildThing`, never in the app folder; **Settings > 8** shows where and can move it. A copy that kept them in the app folder moves them there the first time it starts.
- `jobs.db`: postings, statuses and notes
- `output/`, `requests/`, `replies/`, `AI_INSTRUCTIONS.md`: generated resumes and the work folder (when it is the app's own folder)

Defaults live in `config.json`; your own settings in `data/user_settings.json` are laid over them. `skills.json` is the word list the matching uses: add terms and aliases as you meet them in postings.

## Limits

- Matching is a word list. "Help desk" and "service desk" are both covered; wording not in `skills.json` is missed.
- Live job feeds and AI replies could not be tested from the build environment. If a source fails, the page says which and the rest still work.
- Calendar links carry local times only; there is no two-way calendar sync.
- An export file from the phone keeps each interview's time zone; the desktop reads the local time and ignores the zone.

## Android app

The Android app lives in [`android/`](android/). It is a native app (Kotlin and Jetpack Compose) that runs on the phone by itself: it does not need this desktop app or a PC. It needs an internet connection only to fetch postings and open them, and a Google account only if you want interviews written to Google Calendar. How to build and install it, and what is different on a phone, is in [android/README.md](android/README.md).

### What the two versions share

Both versions keep getting features, so the parts that must agree live in one place:

| Shared | Where | How the Android build uses it |
|---|---|---|
| The skill list the matcher searches for | `skills.json` | Copied into the app by a Gradle task at build time. Edit only the root copy. |
| Neutral default settings | `config.json` | Same Gradle task. |
| Default resume-writing instructions | `default_instructions.md` | Same Gradle task. |
| Behavior test cases: scoring, gaps, duplicate detection, AI requests and replies, source parsers, follow-up rules, reading .docx | `shared_tests/*.json` | The Kotlin tests (`android/core`) run every case, and so does `python -m unittest tests`. |
| AI reply tags, statuses, and the export/import file | [`docs/formats.md`](docs/formats.md) | Both read and write the same formats; `shared_tests/export_sample.json` is the sample both import. |
| The AI queue (batches, request and reply files, the report, import and clean-up rules) | [`docs/formats.md`](docs/formats.md) section 5, `aiqueue.py`, `shared_tests/queue.json` | `core` `AiQueue` runs the same cases. |
| The instructions for any assistant | [`docs/AI_INSTRUCTIONS.md`](docs/AI_INSTRUCTIONS.md) | Copied into the app by the same Gradle task; both apps write it into the queue folder. |
| Shared details (`WildThing/user/`) and the sync rule | [`docs/formats.md`](docs/formats.md) section 6, `shared_details.py`, `shared_tests/shared_details.json` | `core` `SharedDetails` runs the same cases. |
| Shared postings (`WildThing/user/wildthing.db`) and the merge rule | [`docs/formats.md`](docs/formats.md) section 7, `shared_db.py`, `shared_tests/shared_db.json` | `core` `SharedDb` runs the same cases. |
| The career file (format, checks, the build request and the app's edits) | [`docs/formats.md`](docs/formats.md) section 9, `career.py`, `shared_tests/career.json` | `core` `Career` runs the same cases. |
| Tag keys and how avoided companies match | [`docs/formats.md`](docs/formats.md) section 8, `db.TAGS` | `core` `Marks` holds the same list. |

The fixtures in `shared_tests/` are written from the desktop code by `py -3 shared_tests/make_fixtures.py`. Run it only when you mean to change behavior, read the diff of the `.json` files, then make both test suites pass.

### Parity checklist

When you add or change a feature:

1. Change it in both versions, or write down here why one version does not have it.
2. If it changes scoring, gaps, requests, replies, duplicates or follow-ups, update the cases in `shared_tests/make_fixtures.py`, regenerate, and run both suites: `python -m unittest tests` and, in `android/`, `gradlew :core:test`.
3. If it changes a reply tag, a status or the export file, update [`docs/formats.md`](docs/formats.md) (and the export `version` when old files would no longer read correctly).
4. Keep both READMEs accurate.

Differences on purpose (and why):

- **Indeed and LinkedIn fetching (JobSpy)**: desktop only. Scraping from a phone app raises terms-of-service and blocking problems; on Android you share postings into the app from those apps instead.
- **Where the AI queue lives**: both can talk to the `WildThing` folder in Google Drive directly; the desktop can also use a folder on this computer instead. Same format. Android also has the share sheet.
- **Google Calendar**: Android writes interviews to it through the linked account; the desktop links Google for Drive only and keeps its Google Calendar links and `.ics` files.
- **Saving .md / .docx files to `output/`**: desktop only. On Android, saved AI work stays in the app and can be copied or shared.
- **Apply**: the desktop marks a posting Applied at once; Android opens the posting and asks "Did you apply?" when you come back.
- **Interview times**: Android stores a time zone with each one and can write to Google Calendar or the phone's calendar app; the desktop keeps local times and makes Google Calendar links and `.ics` files.
- **Reminders**: Android only (phone notifications).
- **Opening imports replies**: Android imports when the app opens; the desktop imports when you open the Queue page.
- **When postings sync**: the desktop at start, after Fetch and on Sync now; Android when it opens, after pull to refresh and on Sync now.

## License

Copyright (c) 2026 Willis Pearson. WildThing is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

You may use, change and share this app. If you share it, or run a changed version as a service others can use over a network, you must keep this credit and notice, publish your source code, and release it under the same license. The full terms are in the `LICENSE` file. The footer of every page links to the source, which is how a hosted copy meets that requirement.

The Android app's opening bite sound, "Chomp!" by CryptologyMedia from Pixabay (`android/app/src/main/res/raw/chomp.mp3`), is used under the Pixabay Content License and is not covered by the AGPL-3.0; see [CREDITS.md](CREDITS.md).
