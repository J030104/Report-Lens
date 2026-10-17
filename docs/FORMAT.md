# ReportLens package format, version 1

A `.reportlens` file is a ZIP archive. No repository, commands, scripts, or local
configuration are included. Required entries: `manifest.json`, `checksums.json`,
`before.pdf`, `after.pdf`, and all images referenced by the manifest. `diff.pdf`
is included by the writer and optional for readers.

Images use `assets/before-N.png`, `assets/after-N.png`, and corresponding
`before-N-diff.png` / `after-N-diff.png` names. N is one-based. Originals show full
pages; diff images add red strikethrough highlights or green underlines. No image
is an isolated changed diagram fragment or table cell.

The manifest contains `format: "reportlens"`, `version: 1`, `before`/`after`
metadata (label, optional full commit and date), page dimensions, aligned `pairs`,
document-wide text `edits`, summary counts, and comparison caveats. Pair IDs are
zero-based. Missing sides of inserted/deleted pages are null. Text edit page
references and page numbers are one-based. Width and height use PDF points.

New writers add optional `pdf_export: {"layout": "merged", "version": 2}`
metadata (`layout` may also be `pages`). This describes `diff.pdf`, not the
package format version. Older packages remain readable; the viewer regenerates
the selected layout in its local extracted copy when needed. The original
package is unchanged. Cropped visual regions are embedded in the exported PDF;
the package continues to retain full original page images and both input PDFs.

`checksums.json` maps every other entry to its SHA-256 hash. A valid reader rejects
missing/unlisted/duplicate entries, path traversal, symlinks, unknown filenames,
unsupported format versions, invalid image/page references, and checksum failures.
No files are written until all checksums pass. Integrity checks are not signatures.

Limits: 512 MB compressed input; 2 GB expanded; 5,000 entries; 32 MB manifest;
2 MB checksum inventory; 500 pages per side; 1,000 aligned pairs.

The format deliberately includes all source PDF pages. A shared package discloses
unchanged content as well as changes. It contains no original LaTeX or repository
directory, but source PDFs can themselves contain metadata or attachments.
