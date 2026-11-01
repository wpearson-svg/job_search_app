"""Google sign-in and Google Drive for the desktop app, without Drive for desktop.

The app talks to the WildThing folder in your Drive directly, as the Android app does: the AI queue (requests/,
replies/) and the shared details (user/). Formats: docs/formats.md, sections 5 and 6.

Sign-in is Google's "installed app" flow: your browser opens Google's page, you allow access, and Google sends the
browser back to this app on 127.0.0.1 with a one-time code. The OAuth client id and secret you create in Google Cloud
are kept in keys.local.json; the token Google gives back is kept in data/google_token.json. Neither is ever committed.
"""
import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode

import requests

import settings

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/drive/v3"
UPLOAD = "https://www.googleapis.com/upload/drive/v3"
SCOPE_NARROW = "https://www.googleapis.com/auth/drive.file"      # only files WildThing created
SCOPE_FULL = "https://www.googleapis.com/auth/drive"             # all of your Drive
FOLDER_MIME = "application/vnd.google-apps.folder"
TOKEN_FILE = "google_token.json"                                  # in data/
TIMEOUT = 30


class DriveError(OSError):
    """Google said no, or could not be reached. The message is meant for the person."""


def scope(cfg):
    return SCOPE_FULL if cfg.get("drive_full") else SCOPE_NARROW


# ---- sign-in ----------------------------------------------------------------------------------------------------
def _token_path():
    return os.path.join(settings.DATA_DIR, TOKEN_FILE)


def load_token():
    try:
        with open(_token_path(), encoding="utf-8") as f:
            t = json.load(f)
    except (OSError, ValueError):
        return None
    return t if isinstance(t, dict) and t.get("refresh_token") else None


def _save_token(t):
    os.makedirs(settings.DATA_DIR, exist_ok=True)
    with open(_token_path(), "w", encoding="utf-8") as f:
        json.dump(t, f, indent=1)


def forget():
    try:
        os.remove(_token_path())
    except OSError:
        pass


def linked():
    return load_token() is not None


def granted(scope_url):
    t = load_token()
    return bool(t) and scope_url in (t.get("scope") or "").split()


def pkce():
    """(verifier, challenge): the proof that the code Google sends back was asked for by this app."""
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def auth_url(client_id, redirect_uri, scope_url, state, challenge):
    return AUTH_URL + "?" + urlencode({
        "client_id": client_id, "redirect_uri": redirect_uri, "response_type": "code", "scope": scope_url,
        "state": state, "code_challenge": challenge, "code_challenge_method": "S256",
        "access_type": "offline", "prompt": "consent"})


def _token_call(data):
    try:
        r = requests.post(TOKEN_URL, data=data, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise DriveError(f"Could not reach Google: {e}") from None
    try:
        body = r.json()
    except ValueError:
        body = {}
    if r.status_code >= 400:
        raise DriveError(body.get("error_description") or body.get("error") or f"Google said {r.status_code}.")
    return body


def _store(body, refresh_token=None):
    t = {"access_token": body["access_token"], "expires_at": time.time() + int(body.get("expires_in", 3600)) - 60,
         "refresh_token": body.get("refresh_token") or refresh_token, "scope": body.get("scope", "")}
    _save_token(t)
    return t


def exchange(code, client_id, client_secret, verifier, redirect_uri):
    """Trades the one-time code for a token and keeps it in data/google_token.json."""
    body = _token_call({"code": code, "client_id": client_id, "client_secret": client_secret, "code_verifier": verifier,
                        "redirect_uri": redirect_uri, "grant_type": "authorization_code"})
    if not body.get("refresh_token"):
        raise DriveError("Google did not send a long-lived token. Unlink, then link again.")
    return _store(body)


def revoke():
    t = load_token()
    if t:
        try:
            requests.post(REVOKE_URL, data={"token": t["refresh_token"]}, timeout=TIMEOUT)
        except requests.RequestException:
            pass
    forget()


class Auth:
    """Hands out a current access token, refreshing it with the saved refresh token when it has run out."""

    def __init__(self, client_id, client_secret):
        self.client_id, self.client_secret = client_id, client_secret

    def __call__(self):
        t = load_token()
        if not t:
            raise DriveError("Google is not linked on this computer. Link it in Settings.")
        if t.get("access_token") and t.get("expires_at", 0) > time.time():
            return t["access_token"]
        try:
            body = _token_call({"client_id": self.client_id, "client_secret": self.client_secret,
                                "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})
        except DriveError as e:
            if "invalid_grant" in str(e) or "expired" in str(e).lower() or "revoked" in str(e).lower():
                forget()
                raise DriveError("Google access has run out (in testing mode Google asks again about every 7 days). "
                                 "Link Google again in Settings.") from None
            raise
        return _store(body, t["refresh_token"])["access_token"]


# ---- Drive ------------------------------------------------------------------------------------------------------
class Drive:
    """The few Drive v3 calls WildThing needs. token: a function returning a current access token."""

    def __init__(self, token, http=None):
        self.token, self.http = token, http or requests.Session()

    def _call(self, method, url, **kw):
        headers = kw.pop("headers", {})
        headers["Authorization"] = "Bearer " + self.token()
        try:
            r = self.http.request(method, url, headers=headers, timeout=TIMEOUT, **kw)
        except requests.RequestException as e:
            raise DriveError(f"Could not reach Google Drive: {e}") from None
        if r.status_code >= 400:
            try:
                msg = r.json()["error"]["message"]
            except (ValueError, KeyError, TypeError):
                msg = f"error {r.status_code}"
            raise DriveError(f"Google Drive said: {msg}")
        return r

    def list(self, parent):
        """Everything directly in a folder: [{id, name, folder, modified}]."""
        out, page = [], None
        while True:
            params = {"q": f"'{parent}' in parents and trashed=false", "pageSize": 1000,
                      "fields": "nextPageToken,files(id,name,mimeType,modifiedTime)"}
            if page:
                params["pageToken"] = page
            body = self._call("GET", API + "/files", params=params).json()
            out += [{"id": f["id"], "name": f["name"], "folder": f.get("mimeType") == FOLDER_MIME,
                     "modified": f.get("modifiedTime", "")} for f in body.get("files", [])]
            page = body.get("nextPageToken")
            if not page:
                return out

    def folder(self, parent, name):
        """The id of a folder by name inside parent ("root" for My Drive), made when it is not there."""
        found = sorted((f for f in self.list(parent) if f["folder"] and f["name"] == name), key=lambda f: f["modified"])
        if found:
            return found[0]["id"]
        body = self._call("POST", API + "/files", params={"fields": "id"},
                          json={"name": name, "mimeType": FOLDER_MIME, "parents": [parent]}).json()
        return body["id"]

    def download(self, file_id):
        return self._call("GET", f"{API}/files/{file_id}", params={"alt": "media"}).content

    def create(self, parent, name, data, mime):
        boundary = "wildthing-" + secrets.token_hex(8)
        meta = json.dumps({"name": name, "parents": [parent]}).encode()
        body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n".encode() + meta +
                f"\r\n--{boundary}\r\nContent-Type: {mime}\r\n\r\n".encode() + data + f"\r\n--{boundary}--".encode())
        return self._call("POST", UPLOAD + "/files", params={"uploadType": "multipart", "fields": "id"}, data=body,
                          headers={"Content-Type": f"multipart/related; boundary={boundary}"}).json()["id"]

    def update(self, file_id, data, mime):
        self._call("PATCH", f"{UPLOAD}/files/{file_id}", params={"uploadType": "media"}, data=data,
                   headers={"Content-Type": mime})

    def remove(self, file_id, permanent=False):
        """To the Drive trash, or gone for good."""
        if permanent:
            self._call("DELETE", f"{API}/files/{file_id}")
        else:
            self._call("PATCH", f"{API}/files/{file_id}", json={"trashed": True})
