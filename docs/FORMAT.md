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

New writers add optional `pdf_export: {"layout": "latex", "version": 4,
"engine": "latexdiff"}` metadata (`layout` may also be `merged` or `pages`,
without an engine field). This describes `diff.pdf`, not the
package format version. Older packages remain readable; the viewer regenerates
the selected layout in its local extracted copy when needed. The original
package is unchanged. Native LaTeX PDFs are preserved on opening and default
export, even without the original source or compiler. `merged`/`pages` can be
regenerated from the embedded originals; native LaTeX cannot be reconstructed
from PDF-only inputs. The package contains no TeX source or build commands.
Reflowed visual crops are embedded in `merged` PDFs; full original page images
and both input PDFs remain in every package.

`checksums.json` maps every other entry to its SHA-256 hash. A valid reader rejects
missing/unlisted/duplicate entries, path traversal, symlinks, unknown filenames,
unsupported format versions, invalid image/page references, and checksum failures.
No files are written until all checksums pass. Integrity checks are not signatures.

Limits: 512 MB compressed input; 2 GB expanded; 5,000 entries; 32 MB manifest;
2 MB checksum inventory; 500 pages per side; 1,000 aligned pairs.

The format deliberately includes all source PDF pages. A shared package discloses
unchanged content as well as changes. It contains no original LaTeX or repository
directory, but source PDFs can themselves contain metadata or attachments.
