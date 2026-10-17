"""Read-only Git snapshots and opt-in, locally configured PDF builds."""
from dataclasses import dataclass, field, asdict
from pathlib import Path, PurePosixPath
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import zipfile

DEFAULT_PATHS = ["*.tex", "*.bib", "*.sty", "*.cls", "*.png", "*.jpg", "*.jpeg", "*.pdf", "*.svg", "*.eps"]


def run(args, cwd=None, timeout=120, env=None):
    result = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, shell=False, env=env, creationflags=0x08000000 if os.name == "nt" else 0)
    if result.returncode:
        detail = (result.stderr or result.stdout).decode("utf-8", "replace")[-6000:]
        raise RuntimeError(f"{Path(args[0]).name} failed ({result.returncode}):\n{detail}")
    return result.stdout


@dataclass
class Config:
    repository: str
    source: str = "report.tex"
    ref: str = "HEAD"
    tracked_paths: list = field(default_factory=lambda: DEFAULT_PATHS.copy())
    build_command: list = field(default_factory=lambda: ["pdflatex", "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "{source}"])
    build_passes: int = 3
    output_pdf: str = ""
    output_directory: str = ".reportlens"
    poll_seconds: int = 15
    latexdiff_command: list = field(default_factory=list)

    @classmethod
    def load(cls, path):
        path = Path(path).resolve()
        data = json.loads(path.read_text(encoding="utf-8"))
        config = cls(**data)
        config.repository = str((path.parent / config.repository).resolve())
        config.output_directory = str((path.parent / config.output_directory).resolve())
        config.validate()
        return config

    def validate(self):
        for value in (self.source, self.output_pdf):
            if value and (Path(value).is_absolute() or ".." in PurePosixPath(value.replace("\\", "/")).parts):
                raise ValueError("Source and output PDF must be relative paths inside the snapshot.")
        if not 1 <= self.build_passes <= 5:
            raise ValueError("Build passes must be between 1 and 5.")
        if not isinstance(self.build_command, list) or not self.build_command or not all(isinstance(x, str) for x in self.build_command):
            raise ValueError("build_command must be a nonempty JSON argument array.")
        if not self.tracked_paths or not all(isinstance(x, str) and not x.startswith(":") for x in self.tracked_paths):
            raise ValueError("Provide ordinary tracked path patterns.")
        if self.poll_seconds < 5:
            raise ValueError("Polling interval must be at least 5 seconds.")
        if not isinstance(self.latexdiff_command, list) or not all(isinstance(x, str) and x for x in self.latexdiff_command):
            raise ValueError("latexdiff_command must be a JSON argument array.")


class Repository:
    def __init__(self, config):
        config.validate()
        self.config = config
        self.path = Path(config.repository).resolve()
        self.output = Path(config.output_directory).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        self.git("rev-parse", "--show-toplevel")

    def git(self, *args):
        return run(["git", "-C", str(self.path), *args])

    def resolve(self, ref):
        # --end-of-options prevents user-supplied revisions becoming git options.
        return self.git("rev-parse", "--verify", "--end-of-options", ref + "^{commit}").decode().strip()

    def info(self, ref):
        commit = self.resolve(ref)
        values = self.git("show", "-s", "--format=%H%x00%s%x00%cI", commit).decode("utf-8", "replace").strip().split("\x00")
        return {"commit": values[0], "label": values[1], "date": values[2]}

    def versions(self, relevant=True, limit=500):
        ref = self.resolve(self.config.ref)
        args = ["log", "--first-parent", f"--max-count={limit}", "--format=%H%x00%s%x00%cI", ref]
        if relevant:
            args += ["--", *self.config.tracked_paths]
        result = []
        for line in self.git(*args).decode("utf-8", "replace").splitlines():
            fields = line.split("\x00")
            if len(fields) == 3:
                result.append({"commit": fields[0], "label": fields[1], "date": fields[2]})
        return result

    def default_pair(self):
        versions = self.versions()
        if len(versions) < 2:
            raise ValueError("Two report-changing commits are needed. You can also compare two PDFs directly.")
        return versions[1]["commit"], versions[0]["commit"]

    def snapshot(self, commit, root):
        """Extract committed bytes only; never modify the working checkout."""
        archive_bytes = self.git("-c", "core.autocrlf=false", "archive", "--format=zip", commit)
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 2 * 1024 ** 3:
                raise ValueError("Git snapshot exceeds the 2 GB build limit.")
            for info in archive.infolist():
                parts = PurePosixPath(info.filename)
                if parts.is_absolute() or ".." in parts.parts or "\\" in info.filename or ":" in info.filename or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("Unsafe path or symlink in Git snapshot.")
            archive.extractall(root)

    def build(self, ref, progress=lambda _: None):
        commit = self.resolve(ref)
        identity = json.dumps({"commit": commit, "source": self.config.source,
                               "command": self.config.build_command, "passes": self.config.build_passes,
                               "output": self.config.output_pdf}, sort_keys=True).encode()
        cache = self.output / "cache" / hashlib.sha256(identity).hexdigest()
        result = cache / "report.pdf"
        if result.is_file():
            progress(f"Using cached PDF for {commit[:8]}")
            return result
        cache.mkdir(parents=True, exist_ok=True)
        progress(f"Preparing committed snapshot {commit[:8]}")
        # Git archive can apply autocrlf even to ASCII-heavy PDFs when a
        # repository has no binary attributes. Preserve committed byte streams.
        with tempfile.TemporaryDirectory(prefix="reportlens-build-") as temp:
            root = Path(temp)
            self.snapshot(commit, root)
            source = root / self.config.source
            if not source.is_file():
                raise ValueError(f"Source is absent in {commit[:8]}: {self.config.source}")
            if source.suffix.lower() == ".pdf":
                pdf = source
            else:
                command = [arg.replace("{source}", source.name) for arg in self.config.build_command]
                logs = []
                try:
                    for i in range(self.config.build_passes):
                        progress(f"Building {commit[:8]}: pass {i+1}/{self.config.build_passes}")
                        logs.append(run(command, cwd=source.parent, timeout=300).decode("utf-8", "replace"))
                except Exception as error:
                    logs.append(str(error)); raise
                finally:
                    (cache / "build.log").write_text("\n".join(logs), encoding="utf-8")
                pdf = root / self.config.output_pdf if self.config.output_pdf else source.with_suffix(".pdf")
            if not pdf.is_file() or not pdf.read_bytes().startswith(b"%PDF-"):
                raise RuntimeError("Build did not produce the configured PDF.")
            temporary = cache / "report.partial"
            shutil.copyfile(pdf, temporary)
            temporary.replace(result)
        (cache / "identity.json").write_text(json.dumps({**json.loads(identity), "pdf_sha256": hashlib.sha256(result.read_bytes()).hexdigest()}, indent=2), encoding="utf-8")
        return result
