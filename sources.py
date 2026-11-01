"""Job sources that allow programmatic use: open APIs and the public boards companies publish themselves.

Each fetch_* returns a list of dicts: source, ext_id, title, company, location, url, description (plain text), posted.
Indeed, LinkedIn, ZipRecruiter, Glassdoor and Google Jobs come through the python-jobspy library; those sites' own
terms restrict automated collection. Each source can be switched on or off in Settings (SOURCES below).
The parsing below follows each service's documented response format; the functions named parse_* take the already
downloaded data, so they can be tested without a network.
"""
import html
import re
import time

import requests

UA = {"User-Agent": "job-search-app/1.0 (personal use)"}
TIMEOUT = 25

# Every source: key, name, what it is, on by default. Settings saves {key: on} as "sources"; this computer only.
# The phone runs the same keys less the JobSpy ones (wildthing.core.Sources.PHONE).
JOBSPY_SITES = ("indeed", "linkedin", "zip_recruiter", "glassdoor", "google")
SOURCES = (
    ("remoteok", "RemoteOK", "Remote jobs. No key needed.", True),
    ("remotive", "Remotive", "Remote jobs. No key needed.", True),
    ("indeed", "Indeed", "Through JobSpy. Full descriptions.", True),
    ("linkedin", "LinkedIn", "Through JobSpy. Slower, and LinkedIn may rate-limit it.", True),
    ("zip_recruiter", "ZipRecruiter", "Through JobSpy. US and Canada; often blocked.", False),
    ("glassdoor", "Glassdoor", "Through JobSpy. Often blocked.", False),
    ("google", "Google Jobs", "Through JobSpy. Postings Google gathers from many boards.", False),
    ("usajobs", "USAJOBS", "US federal jobs. Needs your free key and email (section 6).", True),
    ("greenhouse", "Greenhouse boards", "The company boards listed below.", True),
    ("lever", "Lever companies", "The companies listed below.", True),
)
LABEL = {k: label for k, label, _, _ in SOURCES}


def enabled(cfg):
    """The keys of the sources that are on, in SOURCES order: Settings' choices over each source's default."""
    chosen = cfg.get("sources") or {}
    return [k for k, _, _, default in SOURCES if chosen.get(k, default)]


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
        raise RuntimeError("no USAJOBS key yet: add it in Settings, section 6 (skipped)")
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


# ---- JobSpy (python-jobspy: Indeed, LinkedIn, ZipRecruiter, Glassdoor, Google Jobs; no key) -----------------
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


def fetch_jobspy(cfg, site):
    """One JobSpy site (a key in JOBSPY_SITES), searched for each keyword."""
    c = cfg.get("jobspy", {})
    try:
        from jobspy import scrape_jobs
    except ImportError:
        raise RuntimeError("python-jobspy is not installed. Run `pip install python-jobspy` (run.bat does this).")
    place = c.get("location", "")
    found, problems = {}, []
    for kw in cfg["search_keywords"][: c.get("max_keywords", 3)]:
        opts = dict(site_name=[site], search_term=kw, location=place, distance=c.get("distance", 25),
                    results_wanted=c.get("linkedin_results_wanted", 15) if site == "linkedin" else c.get("results_wanted", 25),
                    hours_old=c.get("hours_old", 168), country_indeed=c.get("country_indeed", "USA"), verbose=0)
        if site == "linkedin":
            opts["fetch_description"] = c.get("linkedin_fetch_description", True)
        if site == "google":                            # Google Jobs reads its own wording, not search_term
            opts["google_search_term"] = f"{kw} jobs near {place}" if place else f"{kw} jobs"
        try:
            rows, errs = _scrape(scrape_jobs, **opts)
        except Exception as e:                          # one keyword failing must not stop the others
            problems.append(str(e)[:100])
            continue
        if errs:
            problems.append(str(errs)[:100])
        for j in parse_jobspy(rows):
            found.setdefault(j["ext_id"], j)
        time.sleep(c.get("pause_seconds", 3))
    jobs = [j for j in found.values() if title_wanted(j["title"], cfg["target_titles"])]
    if not jobs and problems:
        raise RuntimeError("; ".join(problems[:3]))
    return jobs


def fetch_all(cfg, keys):
    """Runs every source that is on. Returns (jobs, report) where report lists each source's result or error."""
    jobs, report = [], []
    runners = {"remoteok": lambda: fetch_remoteok(cfg), "remotive": lambda: fetch_remotive(cfg),
               "greenhouse": lambda: fetch_greenhouse(cfg), "lever": lambda: fetch_lever(cfg),
               "usajobs": lambda: fetch_usajobs(cfg, keys)}
    for site in JOBSPY_SITES:
        runners[site] = lambda site=site: fetch_jobspy(cfg, site)
    cap = cfg.get("max_jobs_per_source", 60)
    for key in enabled(cfg):
        try:
            got = runners[key]()[:cap]
            jobs += got
            report.append((LABEL[key], len(got), ""))
        except Exception as e:  # one source failing must not stop the others
            report.append((LABEL[key], 0, str(e)[:160]))
    return jobs, report
