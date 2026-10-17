"""Reflow extracted prose; keep complete visual bands as indivisible images.

PDFs have no reliable semantic figure/table boundaries. We group drawing geometry
in vertical bands across the full page width, including nearby captions. A page
with an unlocated caption falls back to its complete image. Originals remain in
the package for layout review; this export is a reading copy, not a facsimile.
"""
from collections import Counter
from difflib import SequenceMatcher
from io import BytesIO
from pathlib import Path
from statistics import median
from xml.sax.saxutils import escape
import hashlib
import re

import pdfplumber
import reportlab
from PIL import Image
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as PDFImage, KeepTogether

from .compare import normalize

CAPTION = re.compile(r"^(?:Figure|Fig\.|Table)\s+\d+(?:\.\d+)*(?:\s*:|\.\s+(?!(?:The|This|These|It)\b))", re.I)
RED, GREEN, INK = "#b52a3b", "#08774a", "#253b36"


def fonts():
    # ReportLab ships these fonts on every supported OS. Embed them so the
    # reading copy does not depend on the recipient's installed fonts.
    root = Path(reportlab.__file__).parent / "fonts"
    for name, filename in (("Lens", "Vera.ttf"), ("LensBold", "VeraBd.ttf")):
        if name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(name, str(root / filename)))


def lines_of(words):
    lines = []
    for word in sorted(words, key=lambda w: (round(w["top"] / 3), w["x0"])):
        if not lines or abs(word["top"] - lines[-1][0]["top"]) > 3:
            lines.append([])
        lines[-1].append(word)
    return lines


def line_text(line):
    return " ".join(w["text"] for w in line)


def visual_bands(page, lines):
    bands = []
    for obj in page.images + page.rects + page.curves + page.lines:
        top, bottom = max(0, obj["top"]), min(page.height, obj["bottom"])
        width = obj["x1"] - obj["x0"]
        # Ignore thin running-header/footer rules and full-bleed title panels.
        if bottom-top < 2 and (top < 90 or top > page.height-60):
            continue
        if (obj.get("object_type") == "rect" and top <= 1 and
                width >= page.width*.95 and bottom < page.height*.25):
            continue
        if width < 1 and bottom-top < 1:
            continue
        bands.append((max(0, top-7), min(page.height, bottom+7)))
    bands.sort()
    merged = []
    for top, bottom in bands:
        if merged and top <= merged[-1][1]+18:
            merged[-1] = (merged[-1][0], max(bottom, merged[-1][1]))
        else:
            merged.append((top, bottom))
    # Captions can sit well below a diagram. Associate the closest region only
    # when there is no intervening text, then include all caption continuation
    # lines so the crop never leaves the last line behind in the prose stream.
    for index, line in enumerate(lines):
        if not CAPTION.match(line_text(line)):
            continue
        top, bottom = min(w["top"] for w in line), max(w["bottom"] for w in line)
        size = bottom-top
        for continuation in lines[index+1:]:
            ct, cb = min(w["top"] for w in continuation), max(w["bottom"] for w in continuation)
            if ct-bottom > size*.7 or abs((cb-ct)-size) > 1.5 or CAPTION.match(line_text(continuation)):
                break
            bottom = cb
        candidates = []
        for i, (bt, bb) in enumerate(merged):
            gap = max(bt-bottom, top-bb, 0)
            intervening = any(min(w["top"] for w in other) > bb and
                              max(w["bottom"] for w in other) < top for other in lines)
            if gap <= 100 and not (bb < top and intervening):
                candidates.append((gap, i))
        if candidates:
            _, i = min(candidates)
            merged[i] = (min(top-4, merged[i][0]), max(bottom+4, merged[i][1]))
    # Expand through complete text lines crossing a band, including captions.
    for i, (top, bottom) in enumerate(merged):
        for line in lines:
            lt, lb = min(w["top"] for w in line), max(w["bottom"] for w in line)
            caption = bool(CAPTION.match(line_text(line)))
            if (lt < bottom and lb > top) or (caption and lt <= bottom+35 and lb >= top-35):
                top, bottom = min(top, lt-4), max(bottom, lb+4)
        merged[i] = (max(0, top), min(page.height, bottom))
    # Captions without reliable geometry may describe borderless tables or
    # text-only diagrams. Preserve that full page instead of guessing a crop.
    for line in lines:
        if CAPTION.match(line_text(line)) and not any(t <= line[0]["top"] <= b for t,b in merged):
            return [(0, page.height)]
    result = []
    for top, bottom in sorted(merged):
        if result and top <= result[-1][1]:
            result[-1] = (result[-1][0], max(bottom, result[-1][1]))
        else:
            result.append((top, bottom))
    return result


def extract_blocks(directory, manifest, side):
    blocks = []
    with pdfplumber.open(directory / f"{side}.pdf") as doc:
        all_words = [p.extract_words(x_tolerance=2, y_tolerance=3) for p in doc.pages]
        margins = Counter()
        for page, words in zip(doc.pages, all_words):
            margins.update({re.sub(r"\d+", "#", line_text(line)) for line in lines_of(words)
                            if max(w["bottom"] for w in line) < 80 or
                            min(w["top"] for w in line) > page.height-85})
        for number, (page, words) in enumerate(zip(doc.pages, all_words), 1):
            lines = lines_of(words)
            bands = visual_bands(page, lines)
            # Image-only pages and missing embedded font glyphs retain their
            # original appearance rather than silently losing their content.
            glyphs = pdfmetrics.getFont("Lens").face.charToGlyph
            if not words:
                bands = [(0, page.height)]
            else:
                for line in lines:
                    top, bottom = min(w["top"] for w in line), max(w["bottom"] for w in line)
                    if (not any(top < b and bottom > t for t,b in bands) and
                            any(ord(c) not in glyphs for w in line for c in normalize(w["text"]))):
                        bands.append((max(0, top-3), min(page.height, bottom+3)))
                joined = []
                for top, bottom in sorted(bands):
                    if joined and top <= joined[-1][1]:
                        joined[-1] = (joined[-1][0], max(bottom, joined[-1][1]))
                    else:
                        joined.append((top, bottom))
                bands = joined
            parts = []
            for index, (top, bottom) in enumerate(bands):
                with Image.open(directory / manifest["pages"][side][number-1]["image"]) as image:
                    crop = image.crop((0, int(top/page.height*image.height), image.width,
                                       min(image.height, int(bottom/page.height*image.height)+1)))
                    stream = BytesIO(); crop.save(stream, format="PNG")
                    digest = hashlib.sha256(crop.tobytes()+str(crop.size).encode()).hexdigest()
                parts.append({"type": "visual", "top": top, "bottom": bottom,
                              "image": stream.getvalue(), "digest": digest,
                              "width": page.width, "height": bottom-top,
                              "page": number, "index": index, "side": side,
                              "fallback": top == 0 and bottom == page.height})
            paragraph = None
            for line in lines:
                top, bottom = min(w["top"] for w in line), max(w["bottom"] for w in line)
                if any(top < b and bottom > t for t,b in bands):
                    paragraph = None
                    continue
                marginal = bottom < 80 or top > page.height-85
                text = line_text(line)
                page_number = bool(re.fullmatch(r"\d+|[ivxlcdm]+", text, re.I))
                if marginal and (page_number or margins[re.sub(r"\d+", "#", text)] >= 3):
                    continue
                size = median(w["bottom"]-w["top"] for w in line)
                if (paragraph is None or top-paragraph["bottom"] > size*.65 or
                        abs(size-paragraph["size"]) > 1.5 or
                        abs(line[0]["x0"]-paragraph["left"]) > 14):
                    paragraph = {"type": "text", "top": top, "bottom": bottom,
                                 "words": [], "page": number, "size": size,
                                 "left": line[0]["x0"], "side": side}
                    parts.append(paragraph)
                paragraph["words"].extend(normalize(w["text"]) for w in line)
                paragraph["bottom"] = bottom
            blocks.extend(sorted(parts, key=lambda b: b["top"]))
    return blocks


def tokens_for(blocks, manifest, side):
    pairs = {p[side]: p["id"] for p in manifest["pairs"] if p[side] is not None}
    tokens = []
    for index, block in enumerate(blocks):
        block["block"] = (side, index)
        if block["type"] == "visual":
            key = ("visual", pairs[block["page"]], block["index"])
            tokens.append((key, block))
        else:
            tokens.extend((("word", word), block) for word in block["words"])
    return tokens


def merged_events(before, after):
    matcher = SequenceMatcher(None, [t[0] for t in before], [t[0] for t in after], autojunk=False)
    for op, a0, a1, b0, b1 in matcher.get_opcodes():
        if op == "equal":
            for old, new in zip(before[a0:a1], after[b0:b1]):
                if new[0][0] == "visual" and old[1]["digest"] != new[1]["digest"]:
                    yield "removed", old
                    yield "added", new
                else:
                    yield "equal", new
        else:
            for old in before[a0:a1]:
                yield "removed", old
            for new in after[b0:b1]:
                yield "added", new


def export_merged(directory, manifest, target):
    directory, target = Path(directory), Path(target)
    fonts()
    before = tokens_for(extract_blocks(directory, manifest, "before"), manifest, "before")
    after = tokens_for(extract_blocks(directory, manifest, "after"), manifest, "after")
    body = ParagraphStyle("Body", fontName="Lens", fontSize=12, leading=18,
                          textColor=HexColor(INK), spaceAfter=10, splitLongWords=True)
    small = ParagraphStyle("Small", parent=body, fontSize=9, leading=13, spaceAfter=8)
    heading = ParagraphStyle("Heading", parent=body, fontName="LensBold", fontSize=20, leading=26, spaceAfter=16)
    story = [Paragraph("ReportLens / Merged comparison", heading)]
    for side in ("before", "after"):
        info = manifest[side]
        label = escape(str(info.get("label", side)))
        commit = escape(str(info.get("commit", "PDF input")))
        story.append(Paragraph(f"{side.upper()}: {label}<br/>{commit}", small))
    summary = manifest["summary"]
    story.append(Paragraph(f"+{summary['added_words']} added words / -{summary['removed_words']} removed words / "
                           f"{summary['changed_pairs']} changed page pairs", body))
    story.append(Paragraph(f'<font color="{RED}"><strike>Removed text</strike></font> and '
                           f'<font color="{GREEN}"><u>added text</u></font> appear together. '
                           'Unchanged text appears once.', body))
    story.append(Paragraph("Reading copy: prose is reflowed; source pagination and styling are not retained. "
                           "Complete visual regions appear below in old/new order when changed. "
                           "Uncertain boundaries use complete pages; unsupported glyphs retain original line images. "
                           "Use Before/After in the viewer, or --pdf-layout pages, to inspect original layout changes.", small))
    story.append(Spacer(1, 14))
    pending, block_id, after_block_id, paragraph_size = [], None, None, 12

    def flush():
        nonlocal pending
        if pending:
            style = body
            if paragraph_size >= 15:
                style = ParagraphStyle("SourceHeading", parent=body, fontName="LensBold",
                                       fontSize=min(20, paragraph_size), leading=min(26, paragraph_size+6))
            story.append(Paragraph(" ".join(pending), style))
            pending = []

    for kind, (key, block) in merged_events(before, after):
        if key[0] == "visual":
            flush(); block_id = after_block_id = None
            color = RED if kind == "removed" else GREEN if kind == "added" else INK
            label = {"removed": "BEFORE / removed", "added": "AFTER / added", "equal": "UNCHANGED"}[kind]
            context = "complete source page" if block["fallback"] else "complete visual region"
            caption = Paragraph(f'<font color="{color}">{label} - {context} - '
                                f'{block["side"]} page {block["page"]}</font>', small)
            width = A4[0]-88
            ratio = min(width/block["width"], (A4[1]-150)/block["height"])
            image = PDFImage(BytesIO(block["image"]), width=block["width"]*ratio,
                             height=block["height"]*ratio)
            story.append(KeepTogether([caption, image, Spacer(1, 14)]))
            continue
        # Old replacement words stay in the surrounding paragraph. A new
        # after paragraph starts a fresh block; pure deletions keep old breaks.
        boundary = ((block["side"] == "after" and after_block_id is not None and
                     after_block_id != block["block"]) or
                    (block["side"] == "before" and after_block_id is None and
                     block_id is not None and block_id != block["block"]))
        if pending and boundary:
            flush()
        if not pending:
            paragraph_size = block["size"]
        block_id = block["block"]
        if block["side"] == "after":
            after_block_id = block_id
        word = escape(key[1])
        if kind == "removed":
            word = f'<font color="{RED}"><strike>{word}</strike></font>'
        elif kind == "added":
            word = f'<font color="{GREEN}"><u>{word}</u></font>'
        pending.append(word)
    flush()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".partial")
    def footer(c, doc):
        c.setFont("Lens", 8); c.setFillColor(HexColor("#53635e"))
        c.drawString(44, 24, "ReportLens / merged reading copy")
        c.drawRightString(A4[0]-44, 24, str(doc.page))
    SimpleDocTemplate(str(temporary), pagesize=A4, rightMargin=44, leftMargin=44,
                      topMargin=42, bottomMargin=46, title="ReportLens - merged comparison",
                      author="ReportLens").build(story, onFirstPage=footer, onLaterPages=footer)
    temporary.replace(target)
    return target
