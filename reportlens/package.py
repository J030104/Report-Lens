"""Portable, non-executable ZIP packages with bounded, validated extraction."""
from pathlib import Path, PurePosixPath
import hashlib
import json
import re
import zipfile

MAX_PACKAGE = 512 * 1024 * 1024
MAX_EXPANDED = 2 * 1024 * 1024 * 1024
ALLOWED = re.compile(r"(?:manifest\.json|checksums\.json|before\.pdf|after\.pdf|diff\.pdf|assets/(?:before|after)-\d+(?:-diff)?\.png)\Z")


def save_package(directory, target):
    directory, target = Path(directory), Path(target)
    files = [p for p in directory.rglob("*") if p.is_file() and ALLOWED.fullmatch(p.relative_to(directory).as_posix()) and p.name != "checksums.json"]
    checksums = {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".partial")
    with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
        for p in files: archive.write(p, p.relative_to(directory).as_posix())
        archive.writestr("checksums.json", json.dumps(checksums))
    temporary.replace(target)
    return target


def load_package(source, destination):
    source, destination = Path(source), Path(destination)
    if source.stat().st_size > MAX_PACKAGE:
        raise ValueError("Package exceeds the 512 MB limit.")
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        names = [i.filename for i in infos]
        if len(names) > 5000 or len(names) != len(set(names)):
            raise ValueError("Package has too many or duplicate entries.")
        if sum(i.file_size for i in infos) > MAX_EXPANDED:
            raise ValueError("Expanded package exceeds 2 GB.")
        for info in infos:
            if not ALLOWED.fullmatch(info.filename) or info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Unsafe or unsupported package entry.")
        if not {"manifest.json", "checksums.json", "before.pdf", "after.pdf"} <= set(names):
            raise ValueError("Required package entries are missing.")
        if archive.getinfo("manifest.json").file_size > 32_000_000 or archive.getinfo("checksums.json").file_size > 2_000_000:
            raise ValueError("Package metadata is too large.")
        checksums = json.loads(archive.read("checksums.json"))
        if set(checksums) != set(names) - {"checksums.json"}:
            raise ValueError("Package checksum inventory does not match.")
        manifest = json.loads(archive.read("manifest.json"))
        validate_manifest(manifest, set(names))
        # Verify all members before writing any file.
        for name, expected in checksums.items():
            if hashlib.sha256(archive.read(name)).hexdigest() != expected:
                raise ValueError(f"Package checksum mismatch: {name}")
        destination.mkdir(parents=True, exist_ok=True)
        for name in names:
            path = destination / PurePosixPath(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as src, path.open("wb") as out:
                import shutil
                shutil.copyfileobj(src, out)
    return manifest


def validate_manifest(data, names):
    try:
        if data["format"] != "reportlens" or data["version"] != 1:
            raise ValueError("Unsupported ReportLens package version.")
        if len(data["pairs"]) > 1000:
            raise ValueError("Too many page pairs.")
        for index, pair in enumerate(data["pairs"]):
            if pair["id"] != index or not isinstance(pair["title"], str) or not isinstance(pair["kind"], str) or type(pair["changed"]) is not bool:
                raise ValueError("Invalid page pair metadata.")
            if not isinstance(pair["hints"], list) or not all(h in ("figure", "table") for h in pair["hints"]):
                raise ValueError("Invalid page hints.")
            if pair["before"] is None and pair["after"] is None:
                raise ValueError("Empty page pair.")
            if any(type(pair[k]) is not int or pair[k] < 0 for k in ("added", "removed")):
                raise ValueError("Invalid word counts.")
        for side in ("before", "after"):
            if not isinstance(data[side]["label"], str) or not isinstance(data[side].get("commit", ""), str):
                raise ValueError("Invalid version metadata.")
            pages = data["pages"][side]
            if not 1 <= len(pages) <= 500:
                raise ValueError("Invalid page count.")
            for index, page in enumerate(pages, 1):
                if page["number"] != index:
                    raise ValueError("Invalid page number.")
                if any(type(page[k]) not in (int, float) or not 0 < page[k] < 100_000 for k in ("width", "height")):
                    raise ValueError("Invalid page dimensions.")
                for key, suffix in (("image", ""), ("diff_image", "-diff")):
                    expected = f"assets/{side}-{index}{suffix}.png"
                    if page[key] != expected or expected not in names:
                        raise ValueError("Missing or invalid page image.")
            for pair in data["pairs"]:
                value = pair[side]
                if value is not None and (type(value) is not int or not 1 <= value <= len(pages)):
                    raise ValueError("Invalid page reference.")
            references = [p[side] for p in data["pairs"] if p[side] is not None]
            if sorted(references) != list(range(1, len(pages)+1)):
                raise ValueError("Every original page must appear exactly once.")
        if not isinstance(data["edits"], list) or not isinstance(data["summary"], dict):
            raise ValueError("Invalid comparison data.")
        for edit in data["edits"]:
            if not all(isinstance(edit[k], str) for k in ("added", "removed")):
                raise ValueError("Invalid text edit.")
            for side in ("before", "after"):
                if not isinstance(edit[side+"_pages"], list) or any(type(p) is not int or not 1 <= p <= len(data["pages"][side]) for p in edit[side+"_pages"]):
                    raise ValueError("Invalid edit page reference.")
        for key in ("added_words", "removed_words", "changed_pairs", "page_pairs"):
            if type(data["summary"][key]) is not int or data["summary"][key] < 0:
                raise ValueError("Invalid summary count.")
        if not isinstance(data["notes"], list) or not all(isinstance(n, str) for n in data["notes"]):
            raise ValueError("Invalid comparison notes.")
    except (KeyError, TypeError) as error:
        raise ValueError("Malformed comparison manifest.") from error
