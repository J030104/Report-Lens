# Verification history

## Numbered outline references - 2026-10-17

- The linked native outline includes compiled section, figure and table numbers
  and printed report page numbers. References resolve through LaTeX labels;
  starred headings and captionless objects are marked unnumbered.
- The private report shows subsections 2.2.1 / 2.2.2 on printed pages 6 / 7 and
  figure 2.3 on page 7. All three links resolve to the expected PDF destinations.
  The public demo verifies old/new figure 1.1 on page 1 and table 1.1 on page 2.
  Both first pages were rendered and visually reviewed; no unresolved references
  remain. The native regression also checks numbering, page references and links.
- All 48 local tests pass with native LaTeX integration enabled. The refreshed
  GUI downloads a byte-identical copy of the reviewed PDF.

## Linked change outline - 2026-10-17

- The native comparison key now precedes the source cover. Its numbered
  **Changed places** outline links to affected source headings and complete
  before/after figures and tables, using their names and captions.
- 48 local tests pass with native integration enabled. The compiled PDF test
  verifies the outline is on the first page, names the changed locations, has
  five internal links, and no longer has the comparison key at the end.
- Section targets follow their headings; visual targets sit inside their
  complete objects. The front matter restores the report's page counter and
  uses a separate page-anchor prefix to avoid conflicting PDF destinations.
- The 53-page report example has three named destinations: its two changed
  sections on PDF pages 16/17 and its added figure on page 17. All destinations
  resolve, and extracted text on every original body page matches the previous
  native export. The new first page and following cover were rendered and reviewed.
- Previous CI failures were traced to a missing TeX Live `ulem` dependency
  (`texlive-plain-generic`) and a Windows test's short-path expectation. The
  dependency list and test path normalization are corrected.

## Native LaTeX default - 2026-10-17

The owner rejected the reflowed PDF's appearance. The default for `.tex`
repositories now compiles a source diff with the report's own class, fonts,
headings, margins, headers and captions. `merged` remains an explicit alternative;
`pages` retains the original consecutive-page layout.

- 46 local tests pass with native integration enabled. The native test compiles
  a real committed LaTeX pair, including a changed image under the same filename,
  a changed whole table, inline prose and cross-references. It verifies Latin
  Modern fonts, whole old/new visuals, stable current numbering, package reopening,
  byte-identical default PDF export, caching and an untouched dirty source checkout.
- The existing report's latest comparison compiled in three LaTeX passes to a
  53-page PDF. Final-pass references resolved; the retained epstopdf shell-escape
  advisory is nonfatal. Original source files were not changed.
- The public `latex-review` example uses only an invented garden report. It
  includes the two source files, a native comparison PDF and portable package.
- LaTeX source parsing, recursive/path-escaping input rejection, complete nested
  visuals, image-byte changes, PDF-only error messages and legacy package opening
  are also covered without requiring a compiler.
- GitHub Actions now includes a separate native LaTeX integration job. Local
  verification is distinct from the status of any particular CI run.

## Merged PDF default - 2026-10-17

- 35 local tests pass on Windows/Python 3.13, including selectable inline
  replacements/deletions, unchanged text and visuals appearing once, complete
  changed diagrams (including disconnected panels), multiline captions, and
  conservative borderless-table fallback.
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
