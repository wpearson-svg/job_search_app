# Job search app

A local app that finds job postings, scores each against your master resume, turns the gaps into one plan, and helps you build a tailored resume and cover letter through your resume builder project. It runs only on your computer (http://127.0.0.1:5050).

## Start it
Double-click `run.bat`. The first run sets itself up (needs Python from python.org, with "py launcher" ticked). A browser tab opens.

## What each page does
- **Postings:** every posting with a 0 to 100 match score; the status filter covers all statuses. "Fetch from open sources" pulls new ones. Click a title to see what it matches, what it asks for that your resume does not show, and to build documents.
- **Paste a posting:** copy the full description from LinkedIn, Indeed or anywhere and paste it. Pasting always works, even with the LinkedIn and Indeed fetchers below switched off.
- **Applications:** every posting you have applied for, with a status dropdown (Applied, Phone screen, Interview, Offer, Rejected, No response, Withdrawn), the applied date, a notes box and a count per status. A posting still at "Applied" after 14 days is marked for a follow-up. You can log an application made somewhere else with the form at the bottom. The same status dropdown is on each posting; the first time you set an applied status, today's date is filled in, and you can change it.
- **Gap plan:** the gaps across all postings that are not dismissed, ranked by how often they appear and how often they are listed as required, grouped into two-week blocks with advice by kind (certification, tool, skill, method).
- **My resume:** the skills the app found in your master resume (uploaded on the Settings page), and anything you marked "I have this".

## "I have this"
If a posting asks for something you have done but the resume does not say, press "I have this". It counts as a match from then on and the postings are re-scored. It does not change the resume and is not sent to Claude. If it is true and belongs on resumes, add it to your master resume first.

## Building a resume (through your Claude project)
On a posting, under "Resume and cover letter":
1. Press **Copy for Claude: resume** (or **resume and cover letter**). The text copied is the posting with a one-line request, in the form your builder prompt expects.
2. Paste it into your resume builder project chat in Claude.
3. Paste Claude's whole reply into the box on the posting and press **Keep this reply**. The app saves it in `output/` as `.md` files (resume, cover letter, review notes), shows it with the posting, and warns if the resume has a bracket marker, "managed a team", "2.5", or runs long.

If the project answers without the `<resume>` tags, the whole reply is kept as the resume.

**Optional: build through the API instead.** If you add an Anthropic API key (paid separately from a Claude subscription), a "Build with the API instead" button appears. It sends your resume-writing instructions (from Settings) as the system prompt, with the same checks and saved files. `.docx` copies are made if pandoc is installed.

Nothing from "I have this" is put in the copied text. If a new fact is true and belongs on resumes, add it to your master resume first.

## Keys (copy `keys.local.example.json` to `keys.local.json`; that file is never committed)
- `anthropic_api_key`: optional, only for "Build with the API instead". Or set the ANTHROPIC_API_KEY environment variable.
- Adzuna (`adzuna_app_id`, `adzuna_app_key`) and USAJOBS (`usajobs_key`, `usajobs_email`): optional extra sources. Without them those two are skipped.

## Settings you can edit
- `config.json`: target titles, search words, your areas, Greenhouse boards and Lever companies to watch (add the company's board name), the model.
- `skills.json`: the skills list the matching uses. Add terms and aliases as you meet them in postings.

## Honest limits
- Matching is a word list, not understanding. A posting that says "help desk" and one that says "service desk" are both covered; wording not in the list is missed. Add terms to `skills.json`.
- The open sources are mostly remote jobs. Jobs near you come from Adzuna, USAJOBS, company boards you add, and your pasted postings.
- Adzuna gives only a short snippet of each description, so scores on those are rough.
- Tested here with sample data only; the live job feeds and the optional Claude API call were not reachable from the build environment. If a source fails, the page says which and the rest still work.


## LinkedIn and Indeed fetching

Switched on or off in `config.json` (`jobspy.enabled`, `linkedin.enabled`). Both services' terms restrict automated collection, so use them at your own judgment and keep the volume small.

- **JobSpy** (on by default) uses the free [python-jobspy](https://github.com/speedyapply/JobSpy) library, which `run.bat` installs. No key or account is needed. `jobspy.sites` picks the boards (`indeed`, `linkedin`, and also `zip_recruiter` or `glassdoor` if you want them). Indeed returns full descriptions. LinkedIn only gives descriptions when `jobspy.linkedin_fetch_description` is true, which costs one extra request per posting, and LinkedIn may answer with a rate-limit error (HTTP 429) or block the request; each Fetch report says when that happens. Settings: `results_wanted`, `linkedin_results_wanted`, `hours_old` (168 = last week), `max_keywords` (how many of a profile's keywords are searched), `location` and `distance`.
- **LinkedIn through the npm package** ([linkedin-jobs-api](https://github.com/VishwaGauravIn/linkedin-jobs-api)) is off by default now, since JobSpy covers LinkedIn. It needs Node.js; `run.bat` runs `npm install` when Node is present.
- Each source reports its own result (or why it was skipped) after a Fetch, and a failure in one never stops the others. Profiles (Profiles page) change the keywords, titles and place for each run.


## Setting it up for yourself (first run)

Open **Settings** (top bar) and fill in, top to bottom:

1. **Master resume.** Upload your resume (.docx, .md or .txt). Every posting is scored against it and Claude only uses facts from it.
2. **Your search.** Job titles you want, search keywords, places that count as a match, and your main place to search.
3. **Sources.** Indeed/LinkedIn (JobSpy) is on by default. Adzuna and USAJOBS turn on when you add their free keys.
4. **How Claude writes for you.** The app ships general resume-writing instructions. Replace them with your own if you have some. Every request you copy to Claude includes the instructions and your resume, so it works in any chat. If your Claude project already holds them, tick the box to stop repeating them.
5. **Keys** (optional). Saved in `keys.local.json` on this computer and never shown again.

Your personal files live in the `data/` folder and `keys.local.json`, plus the `requests/`, `replies/`, `output/` folders and the database. All of them are in `.gitignore`, so sharing the code does not share your information.
