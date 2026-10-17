# Contributing

Please open an issue with a small, public or synthetic PDF pair, the expected
comparison, what actually appeared, and your operating system/Python version.
Do not upload private reports, credentials, or personal configuration files.

For pull requests, keep the viewer read-only and local, preserve complete visual
context, and add regression tests for matching or package-handling changes.
Run `python -m unittest discover -s tests -v`. The UI uses plain HTML/CSS/JavaScript;
it needs no JavaScript build tool or internet connection. Check keyboard navigation,
Before/After/Diff, an opened package without a repository, and a narrow window.

Ideas for future contributions: better reflow alignment, reliable semantic object
extraction, selectable text in exported PDFs, desktop packaging, and explicit
versioned schemas. Keep known limits visible rather than hiding uncertainty.
