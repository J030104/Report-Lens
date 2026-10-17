from pathlib import Path
import hashlib
import json
import shutil
import threading
import time
import uuid

from .compare import create_comparison
from .export import export_pdf, PDF_EXPORT_VERSION
from .package import load_package, save_package
from .repository import Repository


class Service:
    def __init__(self, directory, config=None, pdf_layout="auto"):
        if pdf_layout not in ("auto", "latex", "merged", "pages"):
            raise ValueError("PDF layout must be auto, latex, merged or pages.")
        self.requested_layout = pdf_layout
        self.pdf_layout = ("latex" if config and Path(config.source).suffix.lower() == ".tex" else "merged") if pdf_layout == "auto" else pdf_layout
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.repo = Repository(config) if config else None
        self.current = None
        self.manifest = None
        self.sessions = {}
        self.lock = threading.Lock()
        self.state = {"busy": False, "message": "Ready", "error": None, "generation": 0}
        self.monitor = False
        self.stop = threading.Event()
        self.monitor_seen = None

    def update(self, message):
        self.state["message"] = message

    def activate(self, directory, manifest):
        self.current, self.manifest = Path(directory), manifest
        self.state["generation"] += 1
        self.sessions[self.state["generation"]] = (self.current, manifest)

    def execute(self, action):
        if not self.lock.acquire(blocking=False):
            raise ValueError("Another comparison is already running.")
        self.state.update(busy=True, error=None)
        def work():
            try:
                action()
                self.update("Comparison ready")
            except Exception as error:
                self.state.update(error=str(error), message="Could not finish comparison")
            finally:
                self.state["busy"] = False
                self.lock.release()
        thread = threading.Thread(target=work, daemon=True)
        thread.start()
        return thread

    def compare_git(self, before=None, after=None):
        if not self.repo:
            raise ValueError("Launch with a repository configuration to compare commits.")
        if before is None or after is None:
            before, after = self.repo.default_pair()
        before, after = self.repo.resolve(before), self.repo.resolve(after)
        a = self.repo.build(before, self.update)
        b = self.repo.build(after, self.update)
        # Build identities separate changed compiler/config caches.
        digest = hashlib.sha256(a.read_bytes()+b.read_bytes()).hexdigest()[:12]
        name = f"{before[:8]}--{after[:8]}-{digest}-{self.pdf_layout}-v{PDF_EXPORT_VERSION}"
        if self.pdf_layout == "latex":
            from .latex import ENGINE_VERSION
            name += f"-source{ENGINE_VERSION}"
        destination = self.root / "comparisons" / name
        package = self.root / f"{name}.reportlens"
        if package.is_file():
            manifest = load_package(package, destination)
        else:
            prepared_pdf = None
            if self.pdf_layout == "latex":
                if Path(self.repo.config.source).suffix.lower() != ".tex":
                    raise ValueError("LaTeX layout requires a configured .tex source repository.")
                from .latex import build_latex_diff
                prepared_pdf = build_latex_diff(self.repo, before, after, self.update)
            manifest = create_comparison(a, b, destination, self.repo.info(before), self.repo.info(after), self.update)
            self.finish(destination, manifest, name, prepared_pdf)
        self.record_latest(name)
        self.activate(destination, manifest)

    def compare_files(self, before, after, name="pdf-comparison"):
        if self.pdf_layout == "latex":
            raise ValueError("LaTeX layout requires source files; use --config with a .tex repository, or --pdf-layout merged/pages for PDF inputs.")
        if self.pdf_layout != "merged":
            name += "-" + self.pdf_layout
        destination = self.root / "comparisons" / (name + "-" + uuid.uuid4().hex[:8])
        manifest = create_comparison(before, after, destination, progress=self.update)
        self.finish(destination, manifest, name)
        self.activate(destination, manifest)

    def finish(self, directory, manifest, name, prepared_pdf=None):
        self.update("Writing diff PDF and portable comparison package")
        if prepared_pdf:
            shutil.copyfile(prepared_pdf, directory / "diff.pdf")
            manifest["pdf_export"] = {"layout": "latex", "version": PDF_EXPORT_VERSION, "engine": "latexdiff"}
            self.write_manifest(directory, manifest)
        else:
            self.write_pdf(directory, manifest)
        save_package(directory, self.root / f"{name}.reportlens")
        shutil.copyfile(directory / "diff.pdf", self.root / f"{name}.pdf")
        self.record_latest(name)

    def record_latest(self, name):
        (self.root / "latest.json").write_text(json.dumps({"package": f"{name}.reportlens", "pdf": f"{name}.pdf"}), encoding="utf-8")

    def open_package(self, path):
        destination = self.root / "opened" / uuid.uuid4().hex
        manifest = load_package(path, destination)
        embedded_latex = manifest.get("pdf_export", {}).get("layout") == "latex" and (destination/"diff.pdf").is_file()
        package_layout = ("latex" if embedded_latex else "merged") if self.requested_layout == "auto" else self.requested_layout
        if embedded_latex and self.requested_layout in ("auto", "latex"):
            pass  # Portable native PDF needs no compiler or source repository.
        elif manifest.get("pdf_export") != {"layout": package_layout, "version": PDF_EXPORT_VERSION}:
            self.write_pdf(destination, manifest, layout=package_layout)
        self.activate(destination, manifest)

    def write_pdf(self, directory, manifest, layout=None):
        layout = layout or self.pdf_layout
        export_pdf(directory, manifest, directory / "diff.pdf", layout=layout)
        manifest["pdf_export"] = {"layout": layout, "version": PDF_EXPORT_VERSION}
        self.write_manifest(directory, manifest)

    @staticmethod
    def write_manifest(directory, manifest):
        (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    def monitor_loop(self):
        while not self.stop.wait(self.repo.config.poll_seconds if self.repo else 15):
            if not self.monitor or not self.repo or self.state["busy"]:
                continue
            try:
                versions = self.repo.versions()
                if len(versions) < 2:
                    continue
                newest = versions[0]["commit"]
                if self.monitor_seen == newest:
                    continue
                hashes = [v["commit"] for v in versions]
                # Queue every newly observed report commit, oldest first.
                cutoff = hashes.index(self.monitor_seen) if self.monitor_seen in hashes else 1
                pairs = [(hashes[i+1], hashes[i]) for i in reversed(range(min(cutoff, len(hashes)-1)))]
                def batch(pairs=pairs, newest=newest):
                    for old, new in pairs:
                        self.compare_git(old, new)
                    self.monitor_seen = newest
                self.execute(batch)
            except Exception as error:
                self.state.update(error=str(error), message="Monitoring needs attention")
