import argparse
import json
from pathlib import Path
import sys

from .repository import Config
from .service import Service


def main():
    parser = argparse.ArgumentParser(prog="reportlens", description="Compare committed reports or PDF files without editing them.")
    sub = parser.add_subparsers(dest="action", required=True)
    gui = sub.add_parser("gui", help="Open the local read-only comparison GUI")
    gui.add_argument("package", nargs="?", help="A .reportlens file to open")
    gui.add_argument("--config", help="Trusted local repository configuration")
    gui.add_argument("--port", type=int, default=0)
    gui.add_argument("--no-browser", action="store_true")
    gui.add_argument("--no-watch", action="store_true")
    gui.add_argument("--output", default=".reportlens")
    compare = sub.add_parser("compare", help="Generate .reportlens and PDF outputs")
    compare.add_argument("--config")
    compare.add_argument("--before", help="Old Git revision")
    compare.add_argument("--after", help="New Git revision")
    compare.add_argument("--before-pdf")
    compare.add_argument("--after-pdf")
    compare.add_argument("--output", default=".reportlens")
    args = parser.parse_args()
    try:
        config = Config.load(args.config) if args.config else None
        output = config.output_directory if config else args.output
        service = Service(output, config)
        service.update = lambda message: print(message, flush=True)
        if args.action == "compare":
            if args.before_pdf or args.after_pdf:
                if not args.before_pdf or not args.after_pdf or args.before or args.after or config:
                    parser.error("Use both PDF inputs, without a repository configuration or revisions.")
                service.compare_files(args.before_pdf, args.after_pdf)
            elif config:
                if bool(args.before) != bool(args.after):
                    parser.error("Select both --before and --after, or omit both for the default pair.")
                service.compare_git(args.before, args.after)
            else:
                parser.error("Provide --config, or both --before-pdf and --after-pdf.")
            print(json.dumps(service.manifest["summary"], indent=2))
            print(f"Outputs: {service.root}")
        else:
            from .server import serve
            service.update = lambda message: service.state.update(message=message)
            if args.package:
                service.open_package(args.package)
            elif config:
                service.execute(service.compare_git)
            service.monitor = bool(config and not args.no_watch)
            if config:
                versions = service.repo.versions()
                service.monitor_seen = versions[0]["commit"] if versions else None
            serve(service, args.port, not args.no_browser)
    except (ValueError, RuntimeError, OSError) as error:
        print(f"ReportLens: {error}", file=sys.stderr)
        raise SystemExit(1)
