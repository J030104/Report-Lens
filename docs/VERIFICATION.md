# Initial release verification

Verified on Windows with Python 3.13 on 2026-10-17.

- 24 automated tests pass in the project's own virtual environment.
- An independent editable installation and the `reportlens` entry point work.
- `pip check`, Python compilation, JavaScript syntax, and staged whitespace checks pass.
- Browser review confirms Before, After, Diff, full-table navigation, fit-page
  display, rendered images, and opening a package without a repository. No browser
  warning/error messages were recorded during the final review.
- Synthetic diagram/table/prose outputs render correctly. Exported diff PDF pages
  retain complete original content and use readable consecutive Before/After sheets.
- A local multi-page LaTeX report was rebuilt from its two latest report-changing
  commits in temporary directories. The comparison package reopened with every
  checksum verified. Source reports and configuration are not part of this repository.
- Generated local output, nested demo caches, virtual environments, and personal
  configuration files are excluded from Git. Public examples contain invented data.

Regression coverage includes document-wide reflow, inserted/deleted pages,
visual-only edits, complete diagram/table context, package round trips, corrupt
payloads, invalid manifest references, ZIP traversal, read-only snapshots, default
commit selection, reverse comparisons, Windows Git line endings, monitoring
catch-up, immutable image-session links, and HTTP host/origin/token checks.

Windows is the locally tested platform. GitHub Actions is configured to check
Windows and Linux on Python 3.11 and 3.13; a configured workflow is not itself
evidence of a completed CI run. Review the Actions results for each commit.

Known limitations are documented in the README: heuristic page matching and
figure/table navigation, rasterized diff PDF pages, no OCR, and monitoring only
while the application process is running.
