"""One folder the app reads and writes: a folder on this computer, or a folder in Google Drive (gdrive.py).

The AI queue and the shared details use only these few calls, so they work the same on either. Drive allows several
files with one name; reading takes the newest, and removing takes them all.
"""
import os
from datetime import datetime, timezone

MIME = {".db": "application/x-sqlite3", ".md": "text/markdown", ".json": "application/json", ".txt": "text/plain",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}


def mime(name):
    return MIME.get(os.path.splitext(name)[1].lower(), "application/octet-stream")


class LocalDir:
    def __init__(self, path):
        self.path = self.label = path

    def sub(self, name):
        return LocalDir(os.path.join(self.path, name))

    def ensure(self):
        os.makedirs(self.path, exist_ok=True)
        return self

    def files(self):
        """[{name, modified}] of the files in it (not folders), modified as an ISO time."""
        self.ensure()
        out = []
        for name in sorted(os.listdir(self.path)):
            p = os.path.join(self.path, name)
            if os.path.isfile(p):
                out.append({"name": name, "modified": datetime.fromtimestamp(os.path.getmtime(p), timezone.utc)
                           .isoformat(timespec="seconds")})
        return out

    def read(self, name):
        try:
            with open(os.path.join(self.path, name), "rb") as f:
                return f.read()
        except OSError:
            return None

    def write(self, name, data):
        self.ensure()
        with open(os.path.join(self.path, name), "wb") as f:
            f.write(data)

    def remove(self, name):
        try:
            os.remove(os.path.join(self.path, name))
        except OSError:
            pass

    def text(self, name):
        data = self.read(name)
        return None if data is None else data.decode("utf-8", errors="replace")

    def read_all(self, name):
        """Every copy of a file, newest first (a local folder has at most one)."""
        data = self.read(name)
        return [] if data is None else [data]

    def replace(self, name, data):
        """Writes a file and leaves exactly one copy of it."""
        self.write(name, data)


class DriveDir(LocalDir):
    """A folder in Google Drive, found (or made) by name the first time it is used. permanent: delete instead of
    moving to the Drive trash. Listings are kept until this object writes or removes something."""

    def __init__(self, drive, name, parent=None, permanent=False):
        self.drive, self.name, self.parent, self.permanent = drive, name, parent, permanent
        self.label = (parent.label + "/" if parent else "Google Drive: ") + name
        self._id, self._list = None, None

    @property
    def id(self):
        if self._id is None:
            self._id = self.drive.folder(self.parent.id if self.parent else "root", self.name)
        return self._id

    def sub(self, name):
        return DriveDir(self.drive, name, self, self.permanent)

    def ensure(self):
        _ = self.id
        return self

    def _all(self):
        if self._list is None:
            self._list = [f for f in self.drive.list(self.id) if not f["folder"]]
        return self._list

    def _named(self, name):
        return sorted((f for f in self._all() if f["name"] == name), key=lambda f: f["modified"], reverse=True)

    def files(self):
        return sorted(({"name": f["name"], "modified": f["modified"]} for f in self._all()), key=lambda f: f["name"])

    def read(self, name):
        found = self._named(name)
        return self.drive.download(found[0]["id"]) if found else None

    def write(self, name, data):
        found = self._named(name)
        if found:
            self.drive.update(found[0]["id"], data, mime(name))
        else:
            self.drive.create(self.id, name, data, mime(name))
        self._list = None

    def remove(self, name):
        for f in self._named(name):
            self.drive.remove(f["id"], self.permanent)
        self._list = None

    def read_all(self, name):
        return [self.drive.download(f["id"]) for f in self._named(name)]

    def replace(self, name, data):
        found = self._named(name)
        if found:
            self.drive.update(found[0]["id"], data, mime(name))
            for f in found[1:]:
                self.drive.remove(f["id"], self.permanent)
        else:
            self.drive.create(self.id, name, data, mime(name))
        self._list = None
