"""Job sources that allow programmatic use: open APIs and the public boards companies publish themselves.

Each fetch_* returns a list of dicts: source, ext_id, title, company, location, url, description (plain text), posted.
LinkedIn (via the linkedin-jobs-api npm package) and Indeed/LinkedIn (via the python-jobspy library) are included too.
Both services' own terms restrict automated collection; each has an `enabled` switch in config.json.
The parsing below follows each service's documented response format; the functions named parse_* take the already
downloaded data, so they can be tested without a network.
"""
import html
import json
import os
import re
import shutil
import subprocess
import time

import requests

UA = {"User-Agent": "job-search-app/1.0 (personal use)"}
TIMEOUT = 25


def strip_html(text):
    text = html.unescape(text or "")
    text = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def title_wanted(title, target_titles):
    t = (title or "").lower()
    return any(p.lower() in t for p in target_titles)


# ---- RemoteOK (no key) -------------------------------------------------------
def parse_remoteok(data):
    out = []
    for j in data:
        if not isinstance(j, dict) or "position" not in j:
            continue  # the first element is a legal notice
        out.append({"source": "remoteok", "ext_id": str(j.get("id")), "title": j.get("position", ""),
                    "company": j.get("company", ""), "location": j.get("location") or "Remote",
                    "url": j.get("url", ""), "description": strip_html(j.get("description", "")),
                    "posted": j.get("date", "")})
    return out


def fetch_remoteok(cfg):
    r = requests.get("https://remoteok.com/api", headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return [j for j in parse_remoteok(r.json()) if title_wanted(j["title"], cfg["target_titles"])]


# ---- Remotive (no key) -------------------------------------------------------
def parse_remotive(data):
    out = []
    for j in data.get("jobs", []):
        out.append({"source": "remotive", "ext_id": str(j.get("id")), "title": j.get("title", ""),
                    "company": j.get("company_name", ""), "location": j.get("candidate_required_location") or "Remote",
                    "url": j.get("url", ""), "description": strip_html(j.get("description", "")),
                    "posted": j.get("publication_date", "")})
    return out


def fetch_remotive(cfg):
    found = {}
    for kw in cfg["search_keywords"]:
        r = requests.get("https://remotive.com/api/remote-jobs", params={"search": kw}, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        for j in parse_remotive(r.json()):
            found[j["ext_id"]] = j
    return list(found.values())


# ---- Greenhouse boards (no key; you list the company board names) -------------
def parse_greenhouse(data, board):
    out = []
    for j in data.get("jobs", []):
        out.append({"source": f"greenhouse:{board}", "ext_id": str(j.get("id")), "title": j.get("title", ""),
                    "company": board, "location": (j.get("location") or {}).get("name", ""),
                    "url": j.get("absolute_url", ""), "description": strip_html(j.get("content", "")),
                    "posted": j.get("updated_at", "")})
    return out


def fetch_greenhouse(cfg):
    out = []
    for board in cfg.get("greenhouse_boards", []):
        r = requests.get(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs", params={"content": "true"},
                         headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        out += [j for j in parse_greenhouse(r.json(), board) if title_wanted(j["title"], cfg["target_titles"])]
    return out


# ---- Lever postings (no key; you list the company names) ---------------------
def parse_lever(data, company):
    out = []
    for j in data:
        extra = "\n".join(strip_html(x.get("text", "") + "\n" + x.get("content", "")) for x in j.get("lists", []))
        out.append({"source": f"lever:{company}", "ext_id": str(j.get("id")), "title": j.get("text", ""),
                    "company": company, "location": (j.get("categories") or {}).get("location", ""),
                    "url": j.get("hostedUrl", ""), "description": (j.get("descriptionPlain", "") + "\n" + extra).strip(),
                    "posted": str(j.get("createdAt", ""))})
    return out


def fetch_lever(cfg):
    out = []
    for company in cfg.get("lever_companies", []):
        r = requests.get(f"https://api.lever.co/v0/postings/{company}", params={"mode": "json"},
                         headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        out += [j for j in parse_lever(r.json(), company) if title_wanted(j["title"], cfg["target_titles"])]
    return out


# ---- Adzuna (free key). The API gives a short snippet, not the full description. ----
def parse_adzuna(data):
    out = []
    for j in data.get("results", []):
        out.append({"source": "adzuna", "ext_id": str(j.get("id")), "title": j.get("title", ""),
                    "company": (j.get("company") or {}).get("display_name", ""),
                    "location": (j.get("location") or {}).get("display_name", ""),
                    "url": j.get("redirect_url", ""), "description": strip_html(j.get("description", "")),
                    "posted": j.get("created", "")})
    return out


def fetch_adzuna(cfg, keys):
    if not (keys.get("adzuna_app_id") and keys.get("adzuna_app_key")):
        raise RuntimeError("no Adzuna key in keys.local.json (skipped)")
    a = cfg.get("adzuna", {})
    found = {}
    for kw in cfg["search_keywords"]:
        r = requests.get(f"https://api.adzuna.com/v1/api/jobs/{a.get('country', 'us')}/search/1",
                         params={"app_id": keys["adzuna_app_id"], "app_key": keys["adzuna_app_key"], "what": kw,
                                 "where": a.get("where", ""), "results_per_page": 30,
                                 "content-type": "application/json"}, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        for j in parse_adzuna(r.json()):
            found[j["ext_id"]] = j
    return list(found.values())


# ---- USAJOBS (free key) ------------------------------------------------------
def parse_usajobs(data):
    out = []
    for item in data.get("SearchResult", {}).get("SearchResultItems", []):
        d = item.get("MatchedObjectDescriptor", {})
        det = (d.get("UserArea") or {}).get("Details", {})
        text = (det.get("JobSummary", "") + "\n" + d.get("QualificationSummary", "")).strip()
        out.append({"source": "usajobs", "ext_id": str(item.get("MatchedObjectId")), "title": d.get("PositionTitle", ""),
                    "company": d.get("OrganizationName", ""), "location": d.get("PositionLocationDisplay", ""),
                    "url": d.get("PositionURI", ""), "description": strip_html(text),
                    "posted": d.get("PublicationStartDate", "")})
    return out


def fetch_usajobs(cfg, keys):
    if not (keys.get("usajobs_key") and keys.get("usajobs_email")):
        raise RuntimeError("no USAJOBS key in keys.local.json (skipped)")
    found = {}
    for kw in cfg["search_keywords"]:
        r = requests.get("https://data.usajobs.gov/api/search",
                         params={"Keyword": kw, "LocationName": cfg.get("usajobs", {}).get("location", ""),
                                 "ResultsPerPage": 25},
                         headers={"Host": "data.usajobs.gov", "User-Agent": keys["usajobs_email"],
                                  "Authorization-Key": keys["usajobs_key"]}, timeout=TIMEOUT)
        r.raise_for_status()
        for j in parse_usajobs(r.json()):
            found[j["ext_id"]] = j
    return list(found.values())


# ---- LinkedIn (npm package linkedin-jobs-api, run through Node) ---------------
HERE = os.path.dirname(os.path.abspath(__file__))


def _linkedin_id(url):
    m = re.search(r"-(\d{6,})(?:[/?]|$)", url or "") or re.search(r"/view/(\d{6,})", url or "")
    return m.group(1) if m else ""


def parse_linkedin(items):
    out = []
    for j in items or []:
        url = j.get("jobUrl", "")
        ext = _linkedin_id(url) or url
        if not (ext and j.get("position")):
            continue
        out.append({"source": "linkedin", "ext_id": ext, "title": j.get("position", ""), "company": j.get("company", ""),
                    "location": j.get("location", ""), "url": url, "description": "",
                    "posted": j.get("date") or j.get("agoTime", "")})
    return out


def parse_linkedin_description(page_html):
    """The public job page keeps the description in div.show-more-less-html__markup."""
    m = re.search(r'show-more-less-html__markup[^>]*>(.*?)</div>', page_html or "", re.S)
    return strip_html(m.group(1)) if m else ""


def _run_linkedin_query(options):
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node.js is not installed (needed for LinkedIn). Install it from nodejs.org, then run again.")
    if not os.path.isdir(os.path.join(HERE, "node_modules", "linkedin-jobs-api")):
        raise RuntimeError("linkedin-jobs-api is not installed. Run `npm install` in the app folder (run.bat does this).")
    p = subprocess.run([node, os.path.join(HERE, "linkedin_bridge.js"), json.dumps(options)],
                       capture_output=True, text=True, timeout=120, cwd=HERE, encoding="utf-8", errors="replace")
    m = re.search(r"@@JSON@@(.*?)@@END@@", p.stdout or "", re.S)
    problems = [ln.strip() for ln in (p.stderr or "").splitlines() if "status code" in ln or "Rate limit" in ln or "Error" in ln]
    if p.returncode != 0 or not m:
        raise RuntimeError("LinkedIn query failed: " + (problems[-1] if problems else (p.stderr.strip() or "no message"))[:160])
    jobs = json.loads(m.group(1))
    if not jobs and problems:                    # the package swallows HTTP errors and returns an empty list
        raise RuntimeError("LinkedIn did not return results: " + problems[-1][:140])
    return jobs


def fetch_linkedin(cfg):
    c = cfg.get("linkedin", {})
    if not c.get("enabled"):
        raise RuntimeError("LinkedIn is off (set linkedin.enabled to true in config.json)")
    found = {}
    for kw in cfg["search_keywords"][: c.get("max_keywords", 3)]:
        opts = {"keyword": kw, "location": c.get("location", ""), "dateSincePosted": c.get("dateSincePosted", "past week"),
                "limit": str(c.get("limit", 25)), "sortBy": "recent"}
        for key in ("jobType", "remoteFilter", "experienceLevel"):
            if c.get(key):
                opts[key] = c[key]
        for j in parse_linkedin(_run_linkedin_query(opts)):
            found.setdefault(j["ext_id"], j)
        time.sleep(1.5)                                     # be gentle: one query at a time
    jobs = [j for j in found.values() if title_wanted(j["title"], cfg["target_titles"])]
    # The package returns the listing only. Fetch each posting's public page so it can be scored.
    for j in jobs[: c.get("max_descriptions", 25)]:
        try:
            r = requests.get("https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/" + j["ext_id"], headers=UA, timeout=TIMEOUT)
            if r.ok:
                j["description"] = parse_linkedin_description(r.text)
        except requests.RequestException:
            pass
        time.sleep(1.5)
    for j in jobs:
        if not j["description"]:
            j["description"] = "(Description not retrieved. Open the posting and paste it here to score it.)"
    return jobs


# ---- JobSpy (python-jobspy: Indeed, LinkedIn, ZipRecruiter, Glassdoor; no key) ------------------------------
def _clean(v):
    """pandas leaves NaN/None in empty cells; treat both as blank."""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip()


def parse_jobspy(rows):
    """rows: list of dicts (one per row of JobSpy's dataframe)."""
    out = []
    for r in rows or []:
        site = _clean(r.get("site")) or "jobspy"
        url = _clean(r.get("job_url"))
        ext = _clean(r.get("id")) or url
        title = _clean(r.get("title"))
        if not (ext and title):
            continue
        pay = ""
        lo, hi = _clean(r.get("min_amount")), _clean(r.get("max_amount"))
        if lo or hi:
            pay = "Salary: " + " to ".join(x for x in (lo, hi) if x) + (" " + _clean(r.get("interval")) if _clean(r.get("interval")) else "")
        kind = _clean(r.get("job_type"))
        text = "\n".join(x for x in (_clean(r.get("description")), pay, ("Type: " + kind) if kind else "") if x)
        out.append({"source": site, "ext_id": ext, "title": title, "company": _clean(r.get("company")),
                    "location": _clean(r.get("location")), "url": url, "description": text,
                    "posted": _clean(r.get("date_posted"))})
    return out


def _scrape(scrape_jobs, **kw):
    """Calls JobSpy; copes with the old and new name of the 'fetch the full description' option."""
    fetch = kw.pop("fetch_description", None)
    try:
        df = scrape_jobs(**kw, **({} if fetch is None else {"fetch_description": fetch}))
    except TypeError as e:
        if fetch is None or "fetch_description" not in str(e):
            raise
        df = scrape_jobs(**kw, linkedin_fetch_description=fetch)
    errors = getattr(df, "attrs", {}).get("errors") if hasattr(df, "attrs") else None
    return df.to_dict("records"), errors


def fetch_jobspy(cfg):
    c = cfg.get("jobspy", {})
    if not c.get("enabled"):
        raise RuntimeError("JobSpy is off (set jobspy.enabled to true in config.json)")
    try:
        from jobspy import scrape_jobs
    except ImportError:
        raise RuntimeError("python-jobspy is not installed. Run `pip install python-jobspy` (run.bat does this).")
    found, problems = {}, []
    for kw in cfg["search_keywords"][: c.get("max_keywords", 3)]:
        for site in c.get("sites", ["indeed", "linkedin"]):
            opts = dict(site_name=[site], search_term=kw, location=c.get("location", ""), distance=c.get("distance", 25),
                        results_wanted=c.get("linkedin_results_wanted", 15) if site == "linkedin" else c.get("results_wanted", 25),
                        hours_old=c.get("hours_old", 168), country_indeed=c.get("country_indeed", "USA"), verbose=0)
            if site == "linkedin":
                opts["fetch_description"] = c.get("linkedin_fetch_description", True)
            try:
                rows, errs = _scrape(scrape_jobs, **opts)
            except Exception as e:                      # one site failing must not stop the others
                problems.append(f"{site}: {str(e)[:100]}")
                continue
            if errs:
                problems.append(f"{site}: {str(errs)[:100]}")
            for j in parse_jobspy(rows):
                found.setdefault((j["source"], j["ext_id"]), j)
            time.sleep(c.get("pause_seconds", 3))
    jobs = [j for j in found.values() if title_wanted(j["title"], cfg["target_titles"])]
    if not jobs and problems:
        raise RuntimeError("; ".join(problems[:3]))
    return jobs


def fetch_all(cfg, keys):
    """Runs every source. Returns (jobs, report) where report lists each source's result or error."""
    jobs, report = [], []
    runners = [("RemoteOK", lambda: fetch_remoteok(cfg)), ("Remotive", lambda: fetch_remotive(cfg)),
               ("Greenhouse boards", lambda: fetch_greenhouse(cfg)), ("Lever companies", lambda: fetch_lever(cfg)),
               ("Adzuna", lambda: fetch_adzuna(cfg, keys)), ("USAJOBS", lambda: fetch_usajobs(cfg, keys)),
               ("LinkedIn (npm package)", lambda: fetch_linkedin(cfg)), ("JobSpy (Indeed, LinkedIn)", lambda: fetch_jobspy(cfg))]
    cap = cfg.get("max_jobs_per_source", 60)
    for name, run in runners:
        try:
            got = run()[:cap]
            jobs += got
            report.append((name, len(got), ""))
        except Exception as e:  # one source failing must not stop the others
            report.append((name, 0, str(e)[:160]))
    return jobs, report
