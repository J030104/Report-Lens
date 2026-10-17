"""Clickable location outline for an already marked LaTeX comparison."""
import re


HEADINGS = ("part", "chapter", "section", "subsection", "subsubsection", "paragraph", "subparagraph")


def braced(text, start):
    """Read a balanced LaTeX argument, including nested formatting commands."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] not in "{}":
            continue
        slashes = len(text[:i]) - len(text[:i].rstrip("\\"))
        if slashes % 2:
            continue
        depth += 1 if text[i] == "{" else -1
        if depth == 0:
            return text[start + 1:i], i + 1
    raise ValueError("Unbalanced LaTeX argument in comparison outline.")


def plain_title(text):
    # These are navigation labels, never executable copies of source commands.
    text = re.sub(r"\\(?:label|index)\{[^{}]*\}", "", text)
    text = re.sub(r"\\(?:[A-Za-z@]+)\*?", " ", text)
    text = re.sub(r"\\([%&#_$ {}])", r"\1", text)
    text = text.translate(str.maketrans({"{": "", "}": "", "~": " "}))
    return " ".join(text.split())


def tex_escape(text):
    escapes = {"\\": r"\textbackslash{}", "{": r"\{", "}": r"\}", "%": r"\%",
               "&": r"\&", "#": r"\#", "_": r"\_", "$": r"\$", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(escapes.get(c, c) for c in text)


def add_outline(marked, objects, mask_source, token_pattern):
    """Return marked source with section targets plus ordered clickable entries.

    Only actual latexdiff text markers and changed whole-object tokens qualify.
    Pagination shifts and unchanged headings/captions do not create entries.
    Whole-object targets are stored alongside the protected source for restoration.
    """
    mask = mask_source(marked)
    begin = re.search(r"\\begin\{document\}", mask)
    end = re.search(r"\\end\{document\}", mask)
    if not begin or not end:
        raise ValueError("The source must contain a complete LaTeX document environment.")
    heading_pattern = re.compile(r"\\(" + "|".join(HEADINGS) + r")\*?\s*(?:\[[^\]]*\]\s*)?\{")
    headings, parents = [], {}
    for match in heading_pattern.finditer(mask, begin.end(), end.start()):
        title, finish = braced(mask, match.end() - 1)
        level = HEADINGS.index(match.group(1))
        parents = {k: v for k, v in parents.items() if k < level}
        parents[level] = plain_title(title)
        headings.append({"start": match.start(), "end": finish,
                         "name": " / ".join(parents.values()), "kind": match.group(1).capitalize()})
    locations = {}
    visual_events = []
    change_pattern = re.compile(r"\\DIF(add|del)(?:FL)?\{")
    for match in change_pattern.finditer(mask, begin.end(), end.start()):
        content, finish = braced(mask, match.end() - 1)
        token = re.fullmatch(r"\s*(" + token_pattern + r")\s*", content)
        if token:
            key = token.group(1)
            side = "before" if match.group(1) == "del" else "after"
            info = objects[key].get(side)
            if info:
                caption = re.search(r"\\caption\*?\s*(?:\[[^\]]*\]\s*)?\{", mask_source(info["source"]))
                name = plain_title(braced(info["source"], caption.end() - 1)[0]) if caption else "Untitled object"
                kind = "Table" if info["kind"] in ("table", "table*", "tabular", "tabular*", "tabularx", "longtable") else "Figure"
                visual_events.append((match.start(), info, f"{kind} ({'before' if side == 'before' else 'after'}): {name}"))
            continue
        if not content.strip():
            continue
        # A changed block can contain multiple headings. Include each affected
        # named location, as well as the heading enclosing the block's start.
        preceding = [h for h in headings if h["start"] <= match.start()]
        affected = ([preceding[-1]] if preceding else []) + [h for h in headings if match.start() < h["start"] < finish]
        if not affected:
            locations.setdefault(begin.end(), (begin.end(), "Document opening"))
        for heading in affected:
            locations.setdefault(heading["start"], (heading["end"], f'{heading["kind"]}: {heading["name"]}'))
    events = [(pos, anchor_pos, name, None) for pos, (anchor_pos, name) in locations.items()]
    events += [(pos, None, name, info) for pos, info, name in visual_events]
    entries, inserts = [], []
    for i, (_, anchor_pos, name, info) in enumerate(sorted(events, key=lambda event: event[0])):
        anchor = f"reportlens-change-{i + 1}"
        entries.append((anchor, name))
        if info is not None:
            info["anchor"] = anchor
        else:
            inserts.append((anchor_pos, r"\hypertarget{" + anchor + "}{}"))
    for pos, insertion in sorted(inserts, reverse=True):
        marked = marked[:pos] + insertion + marked[pos:]
    return marked, entries


def front_matter(before, after, entries):
    lines = [r"\begingroup", r"\pagestyle{empty}\thispagestyle{empty}",
             r"\setcounter{ReportLensSavedPage}{\value{page}}",
             r"\renewcommand{\thepage}{RL-\arabic{page}}",
             r"{\LARGE\bfseries ReportLens comparison\par}\bigskip",
             r"Before: \texttt{" + before[:12] + r"}\par After: \texttt{" + after[:12] + r"}\par\medskip",
             r"\DIFdel{Red strikethrough: removed text.}\par\DIFadd{Green underline: added text.}\par\medskip",
             "Changed figures and tables retain complete old and new versions. "
             "This comparison uses the report's LaTeX class, fonts and layout settings. "
             "Additional review content can change pagination.\\par\\bigskip",
             r"{\Large\bfseries Changed places\par}\medskip",
             "Select a name below to jump to that location. Figure and table links "
             "identify the complete before or after version.\\par"]
    if entries:
        lines.append(r"\begin{enumerate}")
        lines.extend(r"\item\hyperlink{" + anchor + "}{" + tex_escape(name) + "}" for anchor, name in entries)
        lines.append(r"\end{enumerate}")
    else:
        lines.append("No inline text or whole-object changes were identified in the document body.\\par")
    lines.extend([r"\clearpage", r"\setcounter{page}{\value{ReportLensSavedPage}}", r"\endgroup", ""])
    return "\n".join(lines)
