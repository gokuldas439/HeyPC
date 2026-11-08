"""Finds files using the Windows search index, falling back to a limited walk of your main folders."""
import os
import re
import subprocess
import time
from pathlib import Path

HOME = Path.home()
KINDS = {
    "pdf": (".pdf",),
    "word": (".doc", ".docx"),
    "document": (".pdf", ".doc", ".docx", ".txt", ".rtf"),
    "excel": (".xls", ".xlsx", ".csv"),
    "spreadsheet": (".xls", ".xlsx", ".csv"),
    "csv": (".csv",),
    "presentation": (".ppt", ".pptx"),
    "powerpoint": (".ppt", ".pptx"),
    "image": (".png", ".jpg", ".jpeg", ".webp", ".gif"),
    "photo": (".png", ".jpg", ".jpeg", ".webp", ".heic"),
    "picture": (".png", ".jpg", ".jpeg", ".webp", ".gif"),
    "video": (".mp4", ".mkv", ".mov", ".avi", ".webm"),
}
EXTRA_WORDS = {"file", "files", "the", "my", "a", "an", "called", "named", "latest", "last", "newest", "recent", "most"}
# Never launched by voice, because one misheard word could run a program. These are shown in their folder instead.
DO_NOT_RUN = {
    ".exe", ".msi", ".bat", ".cmd", ".com", ".scr", ".ps1", ".vbs", ".vbe", ".js", ".jse", ".wsf", ".wsh", ".lnk", ".reg", ".hta", ".jar", ".pif", ".cpl",
}
NOT_FINISHED = {".crdownload", ".tmp", ".part", ".partial"}
WALK_FOLDERS = ("Downloads", "Documents", "Desktop", "OneDrive")
SKIP_FOLDERS = {"node_modules", "appdata", ".git", "__pycache__", ".venv", "dist", "build"}
WALK_SECONDS = 3.0
IMAGE_TYPES = {".png", ".jpg", ".jpeg"}
NO_WINDOW = 0x08000000


def split_query(spoken: str) -> tuple[list[str], tuple]:
    """("the invoice pdf") becomes (["invoice"], (".pdf",))."""
    words = [word for word in re.findall(r"[a-z0-9]+", spoken.lower()) if word not in EXTRA_WORDS]
    types: tuple = ()
    for word in list(words):
        kind = KINDS.get(word) or KINDS.get(word.rstrip("s"))
        if kind:
            types += kind
            words.remove(word)
    return words, types


def _from_index(words: list[str], types: tuple, limit: int) -> list[str]:
    import win32com.client

    conditions = [f"SCOPE='file:{HOME.as_posix()}'", "System.ItemType <> 'Directory'", "NOT System.ItemPathDisplay LIKE '%\\AppData\\%'", "NOT System.ItemPathDisplay LIKE '%node_modules%'"]
    conditions += [f"System.FileName LIKE '%{word}%'" for word in words]  # words are letters and digits only
    if types:
        conditions.append("(" + " OR ".join(f"System.FileExtension = '{extension}'" for extension in types) + ")")
    query = f"SELECT TOP {limit} System.ItemPathDisplay FROM SystemIndex WHERE {' AND '.join(conditions)} ORDER BY System.DateModified DESC"
    connection = win32com.client.Dispatch("ADODB.Connection")
    connection.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows';")
    records = win32com.client.Dispatch("ADODB.Recordset")
    found = []
    try:
        records.Open(query, connection)
        while not records.EOF:
            found.append(records.Fields.Item("System.ItemPathDisplay").Value)
            records.MoveNext()
        records.Close()
    finally:
        connection.Close()
    return [path for path in found if path and Path(path).is_file()]


def _by_walking(words: list[str], types: tuple, limit: int) -> list[str]:
    deadline = time.monotonic() + WALK_SECONDS
    found: list[tuple[float, str]] = []
    for name in WALK_FOLDERS:
        for folder, subfolders, filenames in os.walk(HOME / name):
            subfolders[:] = [sub for sub in subfolders if sub.lower() not in SKIP_FOLDERS and not sub.startswith(".")]
            if time.monotonic() > deadline:
                break
            for filename in filenames:
                lowered = filename.lower()
                if all(word in lowered for word in words) and (not types or lowered.endswith(types)):
                    path = os.path.join(folder, filename)
                    try:
                        found.append((os.path.getmtime(path), path))
                    except OSError:
                        pass
    return [path for _, path in sorted(found, reverse=True)[:limit]]


def search(words: list[str], types: tuple, limit: int = 5) -> list[str]:
    """Newest first."""
    try:
        return _from_index(words, types, limit)
    except Exception as error:
        print(f"   file index unavailable, searching folders instead: {error!r}")
        return _by_walking(words, types, limit)


def _newest(folders: list[Path], keep) -> str | None:
    newest: tuple[float, str] | None = None
    for folder in folders:
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for entry in entries:
            if entry.is_file() and keep(Path(entry.name)):
                modified = entry.stat().st_mtime
                if newest is None or modified > newest[0]:
                    newest = (modified, entry.path)
    return newest[1] if newest else None


def latest(kind: str) -> str | None:
    if kind == "screenshot":
        folders = [HOME / "Pictures" / "Screenshots", HOME / "OneDrive" / "Pictures" / "Screenshots"]
        return _newest(folders, lambda path: path.suffix.lower() in IMAGE_TYPES)
    return _newest([HOME / "Downloads"], lambda path: path.suffix.lower() not in NOT_FINISHED and not path.name.startswith(("~", ".")))


def spoken_name(path: str) -> str:
    return " ".join(re.sub(r"[-_.]+", " ", Path(path).stem).split()[:8])


def show_in_folder(path: str) -> None:
    subprocess.Popen(f'explorer.exe /select,"{path}"', creationflags=NO_WINDOW)


def can_open(path: str) -> bool:
    return Path(path).suffix.lower() not in DO_NOT_RUN
