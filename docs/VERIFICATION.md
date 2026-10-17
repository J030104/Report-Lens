# Verification history

## Merged PDF default - 2026-10-17

- 34 local tests pass on Windows/Python 3.13, including selectable inline
  replacements/deletions, unchanged text and visuals appearing once, complete
  changed diagrams, multiline captions, and conservative borderless-table fallback.
- CLI tests exercise default merged export and `--pdf-layout pages`, including
  export from existing packages. Opening old packages regenerates the PDF in a
  local copy and leaves the input package byte-for-byte unchanged.
- The synthetic public example and a private multi-page report comparison were
  regenerated. PDF pages were rendered with Poppler and reviewed for readability,
  complete visuals, paragraph flow and caption clipping. The private report and
  its comparison artifacts remain excluded from this repository.
- The existing local GUI was restarted with the merged default. Original
  Before/After/Diff views remain available; PDF export uses the merged layout.
- Merged text uses embedded fonts at 12 points. This is a reflowed reading copy;
  original typography/pagination and visual-only formatting changes are reviewed
  through the GUI or the alternate `pages` export. See README for extraction limits.

## Initial release

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

Initial limitations included heuristic page matching and figure/table navigation,
rasterized diff PDF pages, no OCR, and monitoring only while the application
process is running. The merged export above supersedes the raster-only default.
