# WildThing

A local app that finds job postings, scores each one against your master resume, shows what each posting asks for that your resume does not, and helps you get a tailored resume, cover letter, interview prep and a skills plan from an AI assistant of your choice. It runs only on your computer at http://127.0.0.1:5050. Nothing is sent anywhere unless you copy it into an AI yourself or switch on an optional source.

The app never edits your resume and never makes up experience. Matching is a word list, not understanding (see Limits).

## Start it

Double-click `run.bat` (Windows). The first run sets itself up; it needs Python from python.org with the "py launcher" option ticked. A browser tab opens. To run the checks: `python -m unittest tests`.

## First run: Settings

Open **Settings** (top bar) and go top to bottom:

1. **Master resume.** Upload a .docx, .md or .txt. Every posting is scored against it, and the AI is told to use only facts from it. Uploading a new one re-scores everything.
2. **Your search.** The job titles you want, search keywords, the places that count as a match (your city, state, "remote"), and your main place to search.
3. **Sources.** Indeed and LinkedIn through JobSpy are on by default. Adzuna and USAJOBS turn on when you add their free keys.
4. **How the AI writes for you.** The app ships general resume-writing instructions. Replace them with your own if you have some.
5. **Keys** (optional). Saved on this computer and never shown again.

Until a master resume and target titles are set, a banner reminds you.

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
If a posting asks for something you have really done but your resume does not say, press **I have this**. It counts as a match from then on and postings are re-scored. It does not change your resume. If it is true and belongs on resumes, add it to your master resume.

### Duplicates
The same job found on two boards (or fetched twice) is detected by company, title and place. **Merge duplicates** keeps one posting, keeps your status and notes, and lists the other links under "Also listed at".

## Working with an AI assistant

The app does not call any AI by itself. It writes a request, you give it to the AI you use, and the answer comes back to the app. Any assistant that can follow written instructions works. There are two ways to hand things over; both do the same job.

### Way 1: copy and paste
On a posting, press a **Copy for Claude** button (the label says Claude, but the text works with any assistant): resume, resume and cover letter, or interview prep. On the Gap plan page, press **Copy for Claude: gap plan**. Paste it into your AI, then paste the whole reply into the box on the same page and press **Keep this reply** (or **Keep this prep**, **Keep this plan**). The app saves what it finds and warns about things like leftover [bracket markers] or a resume that runs long.

### Way 2: a work folder (for an AI that can read and write files)
Use the **Send to folder** buttons instead. Each one writes a request file and adds it to the **Queue** page. This is the layout, inside the app's folder:

```
requests/   one file per request, named like 003_prep_acme-co.md
replies/    the AI writes its answer here, using the same file name
TODO.md     the list of requests still waiting
```

**For an AI agent reading this:** open `TODO.md` in this folder. Each unchecked line names a file in `requests/` and the matching file to create in `replies/`. For each one, open the request file and follow it. It contains the instructions, the master resume (unless the person keeps those in your project), and the posting or data to work from. Write your answer to the reply file with the same name, using the tags the request asks for, and nothing else in the file. Skip any request whose reply file already exists. Use only facts from the master resume. Do not invent experience.

**For the person:** tell your AI "process the requests listed in TODO.md in this folder". If it works on its own copy of the folder, point it at this one. When it has written the replies, open the **Queue** page and press **Import replies**. Each reply is filed exactly as if you had pasted it. A reply that fails to import stays waiting and the page says why.

Reply tags, for reference (the request file repeats these, so the AI does not need this list):

| Request | Tags in the reply |
|---|---|
| Resume, or resume and cover letter | `<resume>`, `<cover_letter>`, `<review_notes>` |
| Interview prep | `<likely_questions>`, `<questions_to_ask>`, `<gap_prep>`, `<research>` |
| Gap plan | `<priorities>`, `<plan>`, `<proof>`, `<resume_changes>`, `<skip>`, `<questions>` |

A resume reply without `<resume>` tags is kept whole as the resume. Saved resumes and letters also go in `output/` as `.md` files.

### If your AI already holds your resume and instructions
Requests normally include your instructions and master resume, so they work in any new chat. If your assistant has a project or saved chat that already holds them, tick the box on the Settings page to stop repeating them.

### Optional: write through the Anthropic API
If you add an Anthropic API key (paid separately from a Claude subscription), a **Build with the API instead** button appears on the posting page. It sends your instructions as the system prompt and saves the same files. `.docx` copies are made if pandoc is installed.

## Fetching postings

**Fetch** pulls from every source that is switched on and reports each one's result, or why it was skipped. One source failing never stops the others. A posting whose location does not match your places (worldwide and "anywhere" do not count as a match) is skipped.

- **RemoteOK and Remotive:** always on, mostly remote jobs.
- **JobSpy** (Indeed and LinkedIn; on by default): the free [python-jobspy](https://github.com/speedyapply/JobSpy) library, installed by `run.bat`. No key or account. Indeed returns full descriptions. LinkedIn only returns descriptions when `jobspy.linkedin_fetch_description` is true, which costs one extra request per posting, and LinkedIn may rate-limit (HTTP 429) or block requests. Other boards (`zip_recruiter`, `glassdoor`) can be added to `jobspy.sites`. Other settings: `results_wanted`, `linkedin_results_wanted`, `hours_old` (168 is one week), `max_keywords`, `distance`.
- **LinkedIn through the npm package** ([linkedin-jobs-api](https://github.com/VishwaGauravIn/linkedin-jobs-api)): off by default; needs Node.js (`run.bat` runs `npm install` when Node is present).
- **Adzuna and USAJOBS:** need free keys. Adzuna gives only a short snippet of each description, so those scores are rough.
- **Company boards:** add Greenhouse board names or Lever company names in `config.json` (`greenhouse_boards`, `lever_companies`).

LinkedIn's and Indeed's terms restrict automated collection. Use them at your own judgment and keep the volume small.

## Your files and privacy

Everything personal stays on this computer and is listed in `.gitignore`, so sharing the code does not share your information:

- `data/`: your settings, master resume and instructions
- `keys.local.json`: your keys (copy `keys.local.example.json` to create it, or use the Settings page)
- `jobs.db`: postings, statuses and notes
- `output/`, `requests/`, `replies/`, `TODO.md`: generated resumes and the work folder

Defaults live in `config.json`; your own settings in `data/user_settings.json` are laid over them. `skills.json` is the word list the matching uses: add terms and aliases as you meet them in postings.

## Limits

- Matching is a word list. "Help desk" and "service desk" are both covered; wording not in `skills.json` is missed.
- Live job feeds and AI replies could not be tested from the build environment. If a source fails, the page says which and the rest still work.
- Calendar links carry local times only; there is no two-way calendar sync.

## License

Copyright (c) 2026 Willis Pearson. WildThing is licensed under the [GNU Affero General Public License v3.0](LICENSE) (AGPL-3.0).

You may use, change and share this app. If you share it, or run a changed version as a service others can use over a network, you must keep this credit and notice, publish your source code, and release it under the same license. The full terms are in the `LICENSE` file. The footer of every page links to the source, which is how a hosted copy meets that requirement.
