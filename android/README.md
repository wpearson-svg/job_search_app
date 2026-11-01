# WildThing for Android

The Android version of WildThing. It runs on the phone by itself: no PC, no server, no account. It needs the internet only to fetch postings and open them, and (optionally) a Google account to write interviews to Google Calendar.

It does what the desktop app does, on plain phone screens:

- **Postings**: one card per posting with its 0 to 100 match score, status chips, filters (status, profile, minimum score) and a sort sheet. **Pull down to Fetch.** Swipe right to Save, left to Dismiss; Undo appears for a few seconds. The **+** button pastes a posting.
- **A posting has two tabs, `[ Posting | You ]`.** *Posting* is about the posting: profile tags, why this score (matched skills, gaps split into required and preferred with an **I have this** button, warning flags), where else it was listed, the full text and **Open posting**. *You* is about you, for that posting: status, **Apply**, applied date, notes, the 14-day follow-up warning, interviews, and AI work (resume, cover letter, interview prep). The score and status stay visible above both tabs, and the app remembers which tab you were on.
- **Applications**, **Gap plan**, **Weekly** (with **Share**), and under **More**: Profiles, My resume, Paste a posting, Settings, About.

## Build it

You need a JDK 17 or newer (Android Studio's bundled one works) and the Android SDK with platform 36.

```bash
cd android
gradlew :core:test
gradlew :app:assembleRelease
```

- `:core:test` runs the shared behavior cases in `../shared_tests/` (the same ones the desktop tests run).
- The APK is `app/build/outputs/apk/release/app-release.apk`. A debug build (`gradlew :app:assembleDebug`) is larger and unminified.
- Tell Gradle where the SDK is with `local.properties` (`sdk.dir=C:/Users/<you>/AppData/Local/Android/Sdk`) or the `ANDROID_HOME` variable. Android Studio writes `local.properties` for you. It is gitignored.

### Signing

Without a keystore, the release APK is signed with this PC's debug key. That is fine for installing it on your own phone. To sign with your own key, create a keystore and an `android/keystore.properties` file (both gitignored, never commit them):

```
storeFile=../wildthing-release.jks
storePassword=...
keyAlias=wildthing
keyPassword=...
```

Keep the keystore safe: an update must be signed with the same key as the version already installed.

## Install it on the phone (sideloading)

Either:

- copy `app-release.apk` to the phone and open it (Android asks once to allow installs from that app), or
- turn on **Developer options > USB debugging** on the phone, connect it, and run `adb install -r app/build/outputs/apk/release/app-release.apk` (adb is in the SDK's `platform-tools`).

The app needs Android 13 or newer.

## What the phone shares with the desktop

| What | Source of truth | On Android |
|---|---|---|
| Skill list | `../skills.json` | Copied into `:core` by the `sharedResources` Gradle task at build time |
| Default settings | `../config.json` | Same task; your own settings are laid over them like `data/user_settings.json` on the desktop |
| Default instructions | `../default_instructions.md` | Same task |
| Scoring, gaps, duplicates, requests and replies, parsers, follow-up rules | `../shared_tests/*.json` | `core/src/test/.../SharedFixturesTest.kt` runs every case |
| Reply tags, statuses, export file | `../docs/formats.md` | `core` (`Replies`, `Tracking`, `ExportFormat`) |

`:core` is plain Kotlin (no Android code): `Matcher` (matcher.py), `Dedupe` (db.py helpers), `Gaps` (gaps.py), `Replies` and `Tracking` (writer.py, tracking.py), `Sources` (sources.py without JobSpy), `Docx` (resume.py), `ExportFormat` (exchange.py), `SharedDb` (shared_db.py), `Marks` (the tag list in db.py), `Career` (career.py). `:app` is the Compose UI, the SQLite database (same tables as `db.py`, plus a time zone on events) and the phone-only parts.

See the root README's **Parity checklist** for how to keep the two in line.

## How it works on a phone

### LinkedIn and Indeed: share them in
**Settings > Sources** switches each of the phone's sources on or off: RemoteOK, Remotive, USAJOBS (once its free key and email are saved under Keys), and the Greenhouse and Lever company boards you list. The choice stays on this phone.

The phone version does not scrape LinkedIn or Indeed. Instead, in the LinkedIn app, the Indeed app or a browser, tap **Share** on a posting and pick **WildThing**. It opens **Paste a posting** with the link (and any text) filled in. If only a link came through, tap **Open link**, copy the description, and paste it so it can be scored. RemoteOK, Remotive, Greenhouse, Lever, Adzuna and USAJOBS are fetched directly (the last two need their free keys in Settings).

### Working with an AI
WildThing never calls an AI itself and does not depend on any one assistant. Two ways to hand work over:

- **The AI queue (Google Drive).** With a Google account linked, each AI item on a posting's *You* tab (and the Gap plan) has **Send to queue**. The request goes into a batch in the `WildThing` folder of your Drive, with `AI_INSTRUCTIONS.md` beside it. Tell an assistant that can read and create files in that Drive: "Read AI_INSTRUCTIONS.md in the WildThing folder and process the pending batch." When you next open WildThing it imports the replies (or open **More > Queue** and pull down, or tap **Import replies**). After each reply is saved, its files are deleted (to the Drive trash by default; Settings can make it permanent), and when a batch is all in, its TODO files go too. Skipped or failed items stay, with the assistant's reason shown. The full guide is **How the AI queue works** (Settings > Google, or Help on the Queue screen); it works offline.
- **Share sheet and clipboard (any assistant, no Drive).** **Send request to...** opens the share sheet, **Copy** copies the request, and **Paste reply** fills from the clipboard. You can also share the assistant's reply back into WildThing from its share menu; WildThing files it with the posting you last opened (or the Gap plan, for a plan).

Both use the tagged reply format in `../docs/formats.md`, and the queue format there (section 5) is the same one the desktop uses, so a phone and a PC can share one `WildThing` folder (each imports only the batches it made).

### Shared details
With Google linked, your master resume, search settings and profiles, AI instructions, career file and "I have this" skills are kept in step with the desktop through `WildThing/user/` (on the desktop, link Google in Settings; the root README's "Google Drive on the desktop" says how). WildThing syncs when it opens and on **Settings > Google > Sync shared details**. If one of them changed on both devices since the last sync, it shows both and asks which to keep.

Your postings are shared the same way, through `WildThing/user/wildthing.db`: status, applied date, notes, interviews, saved AI work and gap plans. The phone merges with it when it opens, after pull to refresh and on **Settings > Google > Sync now**. The newer status wins, notes written on both devices are both kept, and a deleted posting goes on both. Keys, sources and reminders stay on the phone. Rules: `../docs/formats.md` section 7.

### Opening animation
On a cold start from the launcher, the crown fades in on forest green, two jaws bite shut over it with a "Chomp!", and they swing open to show your postings. It does not play when you come back to the app or share a posting in. With Android's animations switched off it is a short fade instead. The sound is never played on silent or vibrate, and **Settings > Opening** turns it off. The sound's credit is in `../CREDITS.md` and on the About screen.

### Apply
**Apply** opens the posting in the browser. When you come back, WildThing asks **Did you apply?** and marks it Applied (with today's date) only if you say yes.

### Career file
**More > Career file**: everything true about you in one file, built by your AI from your own documents. Choose your documents (Word, Markdown or text), make the request, then copy or share it to your AI, or send it to the Drive work folder. Bring the reply back from Drive or paste it; the app checks it and keeps it only when you accept it. It syncs with the desktop through `WildThing/user/career.json`. Once you have one, postings are scored against it instead of your resume, everything is re-scored when it changes, and "I have this" skills are kept in it as confirmed skills.

### Tags and companies you avoid
On a posting, tap the tag chips (AI interview, Possible scam, Ghost posting, No pay listed, Agency or recruiter, Unpaid test task) or add your own; the **Any tag** chip above the list filters by one. **Avoid** hides a company's postings; **Show avoided** brings them back, and Settings lists the companies you avoid. With Google linked, both sync with the desktop through `wildthing.db` (version 2 of the shared file, so update both apps together).

### Interviews, calendar and reminders
Interviews are saved with this phone's time zone. **Add to phone calendar** opens your calendar app with the event filled in (no sign-in, no permission). **Add to Google Calendar** appears once you link a Google account in Settings (below). Reminders: a notification when an application has waited 14 days with no change, and 1 day and 1 hour before each interview. Android asks once for permission to show notifications; you can switch reminders off in Settings.

### Your data
Everything lives in the app's private storage. Cloud backup is switched off on purpose (`allowBackup="false"` and backup rules that exclude everything), because your resume and notes are personal. **Settings > Data > Export data** saves one `.json` file with everything except your keys; **Import data** reads one back (from this phone or from the desktop's Export). Keys (Adzuna, USAJOBS) are encrypted with a key held in the Android Keystore.

## Setting up Google (Calendar and Drive, optional)

Linking a Google account needs an OAuth client in Google Cloud that matches this app's package name and the key it is signed with. Nothing secret goes in the app or the repo: Google Play services recognises the app by its package name and signing certificate. Never paste a client secret or token anywhere in this project.

1. Go to **console.cloud.google.com** and create a project (any name, for example "WildThing").
2. **APIs & Services > Library**: enable **Google Calendar API** and **Google Drive API**.
3. **APIs & Services > OAuth consent screen** (also called "Google Auth Platform"): choose **External**, fill in the app name and your email, and save. Under **Audience** (or **Test users**), add your own Google account. While the app is in "Testing", only test users can link it.
4. Under **Data access** (or **Scopes**), add `.../auth/calendar.events`, `.../auth/drive.file`, and, if you will use full Drive access, `.../auth/drive`.
5. Get the SHA-1 of the key your APK is signed with. In `android/`, run `gradlew :app:signingReport` and copy the **SHA1** line for the `release` variant (with no keystore, that is the debug key's).
6. **APIs & Services > Credentials > Create credentials > OAuth client ID**: application type **Android**, package name `io.github.wpearsonsvg.wildthing`, and the SHA-1 from step 5. Click **Create**. You do not need to download anything.
7. In the app: **Settings > Google > Link**, choose your account and allow access.

The desktop app needs its own client of type **Desktop app** in the same project; see the root README, "Google Drive on the desktop".

If you later sign with a different key (your own keystore, or another PC's debug key), add a second Android OAuth client with that SHA-1.

### Drive access: narrow or full
Settings > Google > **Drive access** has two choices:

- **Only files WildThing creates** (`drive.file`, the default). The least access, but Google only lets the app see files it created itself. Reply files that your AI (or your PC, through Drive for desktop) creates in the folder are then **probably invisible** to the app, so the queue and shared details may not work.
- **All of my Drive** (`drive`). The app can see what your AI and your PC create. `drive` is a restricted scope: while the Google Cloud project is in testing mode, Google shows an "unverified app" warning and asks you to allow access again about every 7 days.

**Check Drive access** lists every file the app can see in `WildThing/`, `requests/`, `replies/` and `user/`. Have your AI or your PC create any file in the folder, tap the button, and see whether it is listed. If not, switch to full access.

## Not verified yet

- The app has been **built and its shared tests pass**, but it has **not yet been run on a phone or an emulator** (this PC's emulator needs the Android Emulator hypervisor driver, which is not installed). Expect small layout or flow fixes after the first run.
- Live fetching from each source, the Google Calendar link and the Google Drive queue and sync (they need the OAuth client above) have not been tried against the real services. In particular, whether the narrow Drive access can see files your AI creates is unconfirmed; it most likely cannot (use **Check Drive access**).
- Whether a given assistant's Drive access can create a plain `.md` file with an exact name in a chosen folder, and whether that works from its phone app, depends on the assistant and has not been tested.
- Reading `.docx` uses the same simple reader as the desktop; unusual Word files may lose some text. PDF resumes are not read yet.
- The launcher icon is made from the 192 px crown; a 512 px or larger source image would make it sharper.
