"""PDF extraction, document-wide text matching and monotonic page alignment.

No OCR is inferred. Original full pages are always retained, including every
table cell and diagram element; detected object labels are navigation hints.
"""
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import hashlib
import json
import re
import shutil
import threading
import unicodedata

import pdfplumber
import pypdfium2 as pdfium
from PIL import Image, ImageChops, ImageDraw

PDF_LOCK = threading.RLock()  # PDFium must not be called concurrently.
SCALE = 1.6


def normalize(text):
    return unicodedata.normalize("NFKC", text).replace("\u00ad", "")


def extract(path):
    pages = []
    with pdfplumber.open(path) as doc:
        for number, page in enumerate(doc.pages):
            if number >= 500:
                raise ValueError("The comparison limit is 500 pages per PDF.")
            if page.width * page.height * SCALE ** 2 > 30_000_000:
                raise ValueError("A PDF page exceeds the 30 megapixel render limit.")
            words = [{"text": w["text"], "key": normalize(w["text"]),
                      "box": [w["x0"], w["top"], w["x1"], w["bottom"]], "page": number}
                     for w in page.extract_words(x_tolerance=2, y_tolerance=3)]
            text = " ".join(w["text"] for w in words)
            hints = []
            if re.search(r"\b(?:Figure|Fig\.)\s+\d", text, re.I) or page.images:
                hints.append("figure")
            if re.search(r"\bTable\s+\d", text, re.I):
                hints.append("table")
            # Ruled tables also work without English captions.
            if len(page.edges) >= 6 and page.find_tables():
                if "table" not in hints:
                    hints.append("table")
            pages.append({"number": number + 1, "width": page.width, "height": page.height,
                          "words": words, "hints": hints,
                          "title": text[:100] or "Image / drawing page"})
    if not pages:
        raise ValueError("The PDF has no pages.")
    # Repeated running headers/footers are not substantive text edits. Rendered
    # differences still remain visible and are classified separately.
    marginal = Counter()
    for page in pages:
        keys = set()
        for w in page["words"]:
            if w["box"][1] < 40 or w["box"][3] > page["height"] - 40:
                keys.add(re.sub(r"\d+", "#", w["key"]))
        marginal.update(keys)
    for page in pages:
        for w in page["words"]:
            edge = w["box"][1] < 40 or w["box"][3] > page["height"] - 40
            key = re.sub(r"\d+", "#", w["key"])
            w["ignored"] = bool(edge and (w["key"].isdigit() or marginal[key] >= max(3, len(pages) * .6)))
    return pages


def align_pages(before, after, votes):
    """Global sequence alignment permits inserted/deleted pages without index drift."""
    n, m = len(before), len(after)
    score = [[0.] * (m + 1) for _ in range(n + 1)]
    step = [[None] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        score[i][0], step[i][0] = -i * .4, "delete"
    for j in range(1, m + 1):
        score[0][j], step[0][j] = -j * .4, "insert"
    counts_a = [Counter(w["key"] for w in p["words"] if not w["ignored"]) for p in before]
    counts_b = [Counter(w["key"] for w in p["words"] if not w["ignored"]) for p in after]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            a, b = counts_a[i - 1], counts_b[j - 1]
            denom = max(sum(a.values()), sum(b.values()), 1)
            overlap = sum((a & b).values()) / denom
            similarity = max(overlap, votes.get((i - 1, j - 1), 0) / denom)
            if not a and not b:
                similarity = .5  # Image-only pages: retain positional pairing.
            options = [(score[i-1][j-1] + similarity * 1.6 - .45, "pair"),
                       (score[i-1][j] - .4, "delete"), (score[i][j-1] - .4, "insert")]
            score[i][j], step[i][j] = max(options, key=lambda x: x[0])
    result = []
    i, j = n, m
    while i or j:
        action = step[i][j]
        if action == "pair":
            result.append((i-1, j-1)); i -= 1; j -= 1
        elif action == "delete":
            result.append((i-1, None)); i -= 1
        else:
            result.append((None, j-1)); j -= 1
    return list(reversed(result))


def render(path, pages, directory, side, changed):
    hashes = []
    with PDF_LOCK, pdfium.PdfDocument(str(path)) as doc:
        for i, metadata in enumerate(pages):
            page = doc[i]
            bitmap = page.render(scale=SCALE)
            image = bitmap.to_pil().convert("RGB")
            bitmap.close(); page.close()
            raw_name = f"assets/{side}-{i+1}.png"
            image.save(directory / raw_name)
            hashes.append(hashlib.sha256(image.tobytes() + str(image.size).encode()).hexdigest())
            overlay = Image.new("RGBA", image.size)
            draw = ImageDraw.Draw(overlay)
            color = (209, 44, 65, 76) if side == "before" else (0, 153, 91, 76)
            for index in changed.get(i, []):
                x0, y0, x1, y1 = metadata["words"][index]["box"]
                rect = (x0*SCALE-1, y0*SCALE-1, x1*SCALE+1, y1*SCALE+1)
                draw.rectangle(rect, fill=color)
                if side == "before":
                    draw.line((rect[0], (rect[1]+rect[3])/2, rect[2], (rect[1]+rect[3])/2),
                              fill=(177, 29, 50, 190), width=1)
                else:
                    draw.line((rect[0], rect[3], rect[2], rect[3]), fill=(0, 123, 72, 220), width=2)
            marked = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
            marked.save(directory / f"assets/{side}-{i+1}-diff.png")
            metadata["image"], metadata["diff_image"] = raw_name, f"assets/{side}-{i+1}-diff.png"
    return hashes


def create_comparison(before_pdf, after_pdf, destination, before_info=None, after_info=None, progress=lambda _: None):
    destination = Path(destination)
    (destination / "assets").mkdir(parents=True, exist_ok=True)
    before_pdf, after_pdf = Path(before_pdf), Path(after_pdf)
    progress("Reading PDF text and page structure")
    before, after = extract(before_pdf), extract(after_pdf)
    a = [(pi, wi, w) for pi, p in enumerate(before) for wi, w in enumerate(p["words"]) if not w["ignored"]]
    b = [(pi, wi, w) for pi, p in enumerate(after) for wi, w in enumerate(p["words"]) if not w["ignored"]]
    if len(a) + len(b) > 300_000:
        raise ValueError("The comparison limit is 300,000 extracted words.")
    progress("Matching text across the whole document")
    matcher = SequenceMatcher(None, [w[2]["key"] for w in a], [w[2]["key"] for w in b], autojunk=False)
    removed, added, votes = defaultdict(list), defaultdict(list), Counter()
    edits = []
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            for x, y in zip(a[a0:a1], b[b0:b1]):
                votes[(x[0], y[0])] += 1
            continue
        for pi, wi, _ in a[a0:a1]: removed[pi].append(wi)
        for pi, wi, _ in b[b0:b1]: added[pi].append(wi)
        edits.append({"removed": " ".join(x[2]["text"] for x in a[a0:a1]),
                      "added": " ".join(x[2]["text"] for x in b[b0:b1]),
                      "before_pages": sorted({x[0]+1 for x in a[a0:a1]}),
                      "after_pages": sorted({x[0]+1 for x in b[b0:b1]})})
    progress("Rendering complete pages and change highlights")
    ah = render(before_pdf, before, destination, "before", removed)
    bh = render(after_pdf, after, destination, "after", added)
    pairs = []
    for index, (i, j) in enumerate(align_pages(before, after, votes)):
        text_change = bool(removed.get(i) or added.get(j))
        visual_change = i is None or j is None or ah[i] != bh[j]
        kind = "added page" if i is None else "removed page" if j is None else "text change" if text_change else "visual / layout" if visual_change else "unchanged"
        hints = sorted(set((before[i]["hints"] if i is not None else []) + (after[j]["hints"] if j is not None else [])))
        pairs.append({"id": index, "before": i+1 if i is not None else None,
                      "after": j+1 if j is not None else None, "kind": kind,
                      "changed": text_change or visual_change, "hints": hints,
                      "title": (after[j] if j is not None else before[i])["title"],
                      "removed": len(removed.get(i, [])), "added": len(added.get(j, []))})
    for pages in (before, after):
        for page in pages:
            page.pop("words")
    shutil.copyfile(before_pdf, destination / "before.pdf")
    shutil.copyfile(after_pdf, destination / "after.pdf")
    manifest = {"format": "reportlens", "version": 1,
                "before": before_info or {"label": before_pdf.name},
                "after": after_info or {"label": after_pdf.name},
                "pages": {"before": before, "after": after}, "pairs": pairs, "edits": edits,
                "summary": {"added_words": sum(map(len, added.values())), "removed_words": sum(map(len, removed.values())),
                            "changed_pairs": sum(p["changed"] for p in pairs), "page_pairs": len(pairs)},
                "notes": ["Text is matched across the document; page pairing is heuristic when content reflows.",
                          "Figures and tables are shown in full page context, never as isolated changed fragments.",
                          "Visual / layout includes diagram, table, formatting, page-number and reflow changes.",
                          "Caption/object labels are navigation hints, not guaranteed object detection. No OCR is performed."]}
    (destination / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest
