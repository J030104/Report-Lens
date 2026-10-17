"""Export embedded native LaTeX, reflowed prose, or original-page comparisons."""
from pathlib import Path
import shutil
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4


def wrapped(canvas_, text, x, y, width, font="Helvetica", size=10, leading=15):
    canvas_.setFont(font, size)
    words, line = str(text).split(), ""
    for word in words:
        candidate = (line + " " + word).strip()
        if canvas_.stringWidth(candidate, font, size) > width and line:
            canvas_.drawString(x, y, line); y -= leading; line = word
        else:
            line = candidate
    if line:
        canvas_.drawString(x, y, line); y -= leading
    return y


PDF_EXPORT_VERSION = 4


def export_pdf(directory, manifest, target, layout="auto"):
    if layout == "auto":
        layout = "latex" if manifest.get("pdf_export", {}).get("layout") == "latex" else "merged"
    if layout == "latex":
        source = Path(directory) / "diff.pdf"
        if manifest.get("pdf_export", {}).get("layout") != "latex" or not source.is_file():
            raise ValueError("This package has no compiled LaTeX diff. Compare the source repository with --pdf-layout latex first.")
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != target.resolve():
            temporary = target.with_suffix(".partial")
            shutil.copyfile(source, temporary)
            temporary.replace(target)
        return target
    if layout == "merged":
        from .merged import export_merged
        return export_merged(directory, manifest, target)
    if layout == "pages":
        return export_pages(directory, manifest, target)
    raise ValueError("PDF layout must be auto, latex, merged or pages.")


def export_pages(directory, manifest, target):
    directory, target = Path(directory), Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".partial")
    c = canvas.Canvas(str(temporary), pagesize=A4, pageCompression=1)
    c.setTitle("ReportLens - report comparison")
    c.setAuthor("ReportLens")
    w, h = A4
    c.setFillColor(HexColor("#17302b")); c.rect(0, h-230, w, 230, fill=1, stroke=0)
    c.setFillColor(HexColor("#a4e5bb")); c.setFont("Helvetica-Bold", 12); c.drawString(42, h-54, "REPORTLENS / COMPARISON")
    c.setFillColor(HexColor("#ffffff")); c.setFont("Helvetica-Bold", 31); c.drawString(42, h-111, "See what changed.")
    c.setFont("Helvetica", 12); c.drawString(42, h-144, "A read-only review of two report versions")
    c.setFillColor(HexColor("#253b36"))
    y = h-274
    for side, title in (("before", "BEFORE"), ("after", "AFTER")):
        info = manifest[side]
        c.setFont("Helvetica-Bold", 10); c.drawString(42, y, title); y -= 22
        y = wrapped(c, info.get("label", side), 42, y, w-84, size=12)
        y = wrapped(c, info.get("commit", "PDF file comparison"), 42, y-4, w-84, size=8)
        y -= 24
    s = manifest["summary"]
    y = wrapped(c, f"{s['changed_pairs']} changed page pairs   /   +{s['added_words']} added words   /   -{s['removed_words']} removed words", 42, y, w-84, size=11)
    y -= 25
    for color, label in (("#08774a", "Green underline / highlight: added text"), ("#b52a3b", "Red strikethrough / highlight: removed text")):
        c.setFillColor(HexColor(color)); y = wrapped(c, label, 42, y, w-84)
    c.setFillColor(HexColor("#485a55")); y -= 15
    for note in manifest["notes"]:
        y = wrapped(c, note, 42, y, w-84, size=9, leading=14) - 9
    c.showPage()
    changed = [p for p in manifest["pairs"] if p["changed"]]
    for pair in changed:
        for side in ("before", "after"):
            number = pair[side]
            if number is None:
                continue
            page = manifest["pages"][side][number-1]
            # Preserve the complete page, on consecutive sheets for readability.
            pw, ph = max(420, page["width"]), max(595, page["height"])
            c.setPageSize((pw, ph+66))
            color = "#b52a3b" if side == "before" else "#08774a"
            c.setFillColor(HexColor(color)); c.rect(0, ph+22, pw, 44, fill=1, stroke=0)
            c.setFillColor(HexColor("#ffffff")); c.setFont("Helvetica-Bold", 11)
            c.drawString(20, ph+47, f"{side.upper()}  /  page {number}  /  {pair['kind']}")
            c.setFont("Helvetica", 8)
            c.drawString(20, ph+32, f"Comparison {pair['id']+1}  |  full page: diagrams and tables retained")
            image = ImageReader(str(directory / page["diff_image"]))
            iw, ih = image.getSize(); ratio = min((pw-28)/iw, (ph-14)/ih)
            dw, dh = iw*ratio, ih*ratio
            c.drawImage(image, (pw-dw)/2, 18+(ph-14-dh)/2, width=dw, height=dh)
            c.setFillColor(HexColor("#53635e")); c.setFont("Helvetica", 7)
            commit = manifest[side].get("commit", "PDF input")
            c.drawString(14, 8, f"ReportLens  |  {commit}  |  read-only comparison")
            c.showPage()
    c.save()
    temporary.replace(target)
    return target
