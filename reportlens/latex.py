"""Compile source-aware comparisons using the report's own LaTeX document.

latexdiff handles prose/math. Whole figures and tables are protected from inline
markup, including changed external image bytes. Only committed snapshots enter
the compiler. No TeX source or build commands are added to portable packages.
"""
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import tempfile

from .repository import run
from .outline import add_outline, front_matter

ENGINE_VERSION = 4
VISUALS = {"figure", "figure*", "table", "table*", "longtable", "tikzpicture",
           "tabular", "tabular*", "tabularx"}
TOKEN = r"REPORTLENSOBJECT[a-f0-9]{40}"
INPUT = re.compile(r"\\(input|include)\s*\{([^{}]+)\}")
GRAPHIC = re.compile(r"\\includegraphics\*?(?:\s*\[[^\]]*\])?\s*\{([^{}]+)\}")
ENV = re.compile(r"\\(begin|end)\s*\{([^{}]+)\}")


def syntax_mask(text):
    """Keep offsets while ignoring comments and literal-code environments."""
    masked = list(text)
    for m in re.finditer(r"\\begin\{(verbatim\*?|lstlisting|minted)\}.*?\\end\{\1\}", text, re.S):
        masked[m.start():m.end()] = ["\n" if c == "\n" else " " for c in m.group()]
    visible = "".join(masked)
    for m in re.finditer(r"%", visible):
        slash = len(visible[:m.start()])-len(visible[:m.start()].rstrip("\\"))
        if slash % 2 == 0:
            end = visible.find("\n", m.start())
            if end == -1:
                end = len(visible)
            masked[m.start():end] = " " * (end-m.start())
    return "".join(masked)


def inside(root, path):
    path = path.resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("LaTeX input must stay inside its committed snapshot.")
    return path


def flatten(root, source, stack=(), boundary=None):
    """Expand ordinary braced input/include; fail clearly on dynamic paths."""
    boundary = boundary or root
    source = inside(boundary, source)
    if source in stack or len(stack) >= 40:
        raise ValueError("Recursive or excessively nested LaTeX input.")
    text = source.read_text(encoding="utf-8-sig")
    mask = syntax_mask(text)
    endinput = re.search(r"\\endinput\b", mask)
    if stack and endinput:
        text, mask = text[:endinput.start()], mask[:endinput.start()]
    if re.search(r"\\(?:includeonly|subfile|import|subimport)\b", mask):
        raise ValueError("This LaTeX include mechanism is not supported by the source diff. Use ordinary input/include or --pdf-layout pages.")
    matches = list(INPUT.finditer(mask))
    if len(matches) != len(re.findall(r"\\(?:input|include)\b", mask)):
        raise ValueError("Use literal, braced LaTeX input/include paths for source comparison.")
    for match in reversed(matches):
        name = match.group(2)
        if any(c in name for c in "\\#$"):
            raise ValueError("Dynamic LaTeX input paths are not supported by source comparison.")
        relative = Path(name)
        if not relative.suffix:
            relative = relative.with_suffix(".tex")
        # TeX resolves paths from the main compilation directory, not each
        # included file's directory. Root here is that main source directory.
        child = inside(boundary, root / relative)
        content = flatten(root, child, (*stack, source), boundary)
        if match.group(1) == "include":
            content = "\\clearpage\n" + content + "\n\\clearpage\n"
        text = text[:match.start()] + content + text[match.end():]
    return text


def visual_spans(text):
    result, depth, start, kind = [], 0, None, None
    for match in ENV.finditer(syntax_mask(text)):
        if match.group(2) not in VISUALS:
            continue
        if match.group(1) == "begin":
            if depth == 0:
                start, kind = match.start(), match.group(2)
            depth += 1
        else:
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced visual environment in LaTeX source.")
            if depth == 0:
                result.append((start, match.end(), kind))
    if depth:
        raise ValueError("Unbalanced visual environment in LaTeX source.")
    return result


def graphics_paths(text):
    match = re.search(r"\\graphicspath\s*\{((?:\s*\{[^{}]*\}\s*)+)\}", syntax_mask(text))
    return re.findall(r"\{([^{}]*)\}", match.group(1)) if match else []


def rewrite_graphics(text, root, search_paths, boundary=None):
    replacements, hashes = [], []
    for match in GRAPHIC.finditer(syntax_mask(text)):
        name = match.group(1)
        if any(c in name for c in "\\#$"):
            raise ValueError("Dynamic includegraphics paths need a literal path for whole-object comparison.")
        found = None
        for prefix in ["", *search_paths]:
            path = inside(boundary or root, root / prefix / name)
            for candidate in [path] if path.suffix else [path.with_suffix(e) for e in (".pdf", ".png", ".jpg", ".jpeg", ".eps")]:
                if candidate.is_file():
                    found = candidate; break
            if found:
                break
        if found is None:
            raise ValueError(f"Committed graphic not found: {name}")
        hashes.append(hashlib.sha256(found.read_bytes()).hexdigest())
        replacements.append((match.start(1), match.end(1), found.as_posix()))
    for start, end, replacement in reversed(replacements):
        text = text[:start] + replacement + text[end:]
    return text, hashes


def protect_visuals(text, root, side, objects, boundary=None):
    paths = graphics_paths(text)
    document = re.search(r"\\begin\{document\}", syntax_mask(text))
    for start, end, kind in reversed(visual_spans(text)):
        if document and start < document.end():
            continue  # Preamble macro definitions are not displayed objects.
        original = text[start:end]
        content, hashes = rewrite_graphics(original, root, paths, boundary)
        # Ignore snapshot directory names when identifying unchanged objects.
        digest = hashlib.sha1((original + json.dumps(hashes)).encode()).hexdigest()
        token = "REPORTLENSOBJECT" + digest
        objects.setdefault(token, {})[side] = {"source": content, "kind": kind}
        text = text[:start] + "\n\n" + token + "\n\n" + text[end:]
    # Standalone image commands are unsupported: never silently use new bytes
    # for an old image when the file kept its name.
    mask = syntax_mask(text)
    document = re.search(r"\\begin\{document\}", mask)
    if GRAPHIC.search(mask[document.end():] if document else mask):
        raise ValueError("Place includegraphics inside a figure environment for source comparison.")
    return text


def visual_source(token, kind, objects):
    info = objects[token].get("before" if kind == "del" else "after")
    if info is None:
        info = next(iter(objects[token].values()))
    source, environment = info["source"], info["kind"]
    if kind == "equal":
        return source
    label = "BEFORE / removed" if kind == "del" else "AFTER / added"
    color = "ReportLensRemoved" if kind == "del" else "ReportLensAdded"
    heading = r"{\small\color{" + color + r"}\textbf{" + label + r" - complete object}\par}\smallskip" + "\n"
    if info.get("anchor"):
        heading = r"\hypertarget{" + info["anchor"] + "}{}" + heading
    if environment.rstrip("*") in ("figure", "table"):
        start = re.match(r"\\begin\{[^{}]+\}(?:\s*\[[^\]]*\])?", source)
        # Keep complete versions in document order; each is still typeset by
        # the report's class and packages, with its native fonts and graphics.
        source = "\\begin{" + environment + "}[H]\n" + heading + source[start.end():]
    else:
        source = heading + source
    if kind == "del":
        source = re.sub(r"\\label\{([^{}]+)\}", lambda m: r"\label{reportlens-old-" + token[-12:] + "-" + m.group(1) + "}", source)
        # Deleted captions must not shift current figure/table numbering, add
        # old entries to lists, or create duplicate PDF anchor destinations.
        source = (r"\begingroup" + "\n" +
                  r"\setcounter{ReportLensSavedFigure}{\value{figure}}" + "\n" +
                  r"\setcounter{ReportLensSavedTable}{\value{table}}" + "\n" +
                  r"\renewcommand{\addcontentsline}[3]{}" + "\n" +
                  r"\ifdefined\theHfigure\renewcommand{\theHfigure}{reportlens-old-" + token[-12:] + r"}\fi" + "\n" +
                  r"\ifdefined\theHtable\renewcommand{\theHtable}{reportlens-old-" + token[-12:] + r"}\fi" + "\n" + source + "\n" +
                  r"\setcounter{figure}{\value{ReportLensSavedFigure}}" + "\n" +
                  r"\setcounter{table}{\value{ReportLensSavedTable}}" + "\n" + r"\endgroup")
    return "\n" + source + "\n"


def restore_visuals(text, objects):
    pattern = re.compile(r"\\DIF(add|del)(?:FL)?\{\s*(" + TOKEN + r")\s*\}")
    text = pattern.sub(lambda m: visual_source(m.group(2), m.group(1), objects), text)
    # Equal objects occur as ordinary text. Remaining tokens nested in markup
    # would be unsafe for floats; refuse rather than producing clipped output.
    for token in re.findall(TOKEN, text):
        if re.search(r"\\DIF(?:add|del)(?:FL)?\{[^{}]*" + token, text):
            raise ValueError("latexdiff nested a visual placeholder in text markup; the source diff cannot safely restore this object.")
        text = text.replace(token, visual_source(token, "equal", objects), 1)
    return text


MARKUP = r"""
% ReportLens: retain the source document class, fonts and page geometry.
\usepackage{xcolor}
\usepackage{float}
\usepackage{hyperref}
\definecolor{ReportLensAdded}{HTML}{08774A}
\definecolor{ReportLensRemoved}{HTML}{B52A3B}
\renewcommand{\DIFadd}[1]{{\protect\color{ReportLensAdded}\uline{#1}}}
\renewcommand{\DIFdel}[1]{{\protect\color{ReportLensRemoved}\sout{#1}}}
\newcommand{\ReportLensGap}{\ifhmode\unskip\hspace{0.15em}\fi}
\renewcommand{\DIFdelbegin}{\ReportLensGap}
\renewcommand{\DIFdelend}{\ReportLensGap}
\newcounter{ReportLensSavedFigure}
\newcounter{ReportLensSavedTable}
\newcounter{ReportLensSavedPage}
"""


def command_for(config):
    if config.latexdiff_command:
        return config.latexdiff_command
    executable = shutil.which("latexdiff-so") or shutil.which("latexdiff")
    if not executable:
        raise ValueError("LaTeX comparison needs latexdiff and Perl. Install them or choose --pdf-layout pages (or merged for reflowed text).")
    if os.name == "nt":
        # Git for Windows already includes Perl. Use MiKTeX's standalone
        # script when available, avoiding an extra CPAN module dependency.
        git = shutil.which("git")
        perl = shutil.which("perl")
        if not perl and git:
            candidate = Path(git).parent.parent / "usr/bin/perl.exe"
            if candidate.is_file():
                perl = str(candidate)
        script = Path(executable).parents[3] / "scripts/latexdiff/latexdiff-so"
        if perl and script.is_file():
            return [perl, str(script)]
    return [executable]


def build_latex_diff(repo, before, after, progress=lambda _: None):
    command = command_for(repo.config)
    identity = {"before": before, "after": after, "config": asdict(repo.config),
                "engine": ENGINE_VERSION, "latexdiff": command}
    cache = repo.output / "latex-cache" / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    result = cache / "diff.pdf"
    if result.is_file():
        progress("Using cached LaTeX comparison")
        return result
    cache.mkdir(parents=True, exist_ok=True)
    logs = []
    with tempfile.TemporaryDirectory(prefix="reportlens-latex-") as temp:
        root = Path(temp)
        old, new = root/"before", root/"after"
        repo.snapshot(before, old); repo.snapshot(after, new)
        old_source, new_source = old/repo.config.source, new/repo.config.source
        objects = {}
        a = protect_visuals(flatten(old_source.parent, old_source, boundary=old), old_source.parent, "before", objects, old)
        b = protect_visuals(flatten(new_source.parent, new_source, boundary=new), new_source.parent, "after", objects, new)
        (root/"before.tex").write_text(a, encoding="utf-8")
        (root/"after.tex").write_text(b, encoding="utf-8")
        progress("Marking LaTeX prose and preserving complete figures/tables")
        try:
            marked = run([*command, "--encoding=utf8", "--graphics-markup=none", "--math-markup=whole",
                          "--type=UNDERLINE", "--disable-citation-markup", str(root/"before.tex"), str(root/"after.tex")],
                         cwd=new_source.parent, timeout=300).decode("utf-8")
            marked, entries = add_outline(marked, objects, syntax_mask, TOKEN)
            marked = restore_visuals(marked, objects)
            start = re.search(r"\\begin\{document\}", syntax_mask(marked))
            if not start:
                raise ValueError("The source must contain a LaTeX document environment.")
            marked = (marked[:start.start()] + MARKUP + marked[start.start():start.end()] + "\n" +
                      front_matter(before, after, entries) + marked[start.end():])
            new_source.write_text(marked, encoding="utf-8")
            (cache/"diff.tex").write_text(marked, encoding="utf-8")
            args = [arg.replace("{source}", new_source.name) for arg in repo.config.build_command]
            for i in range(repo.config.build_passes):
                progress(f"Typesetting LaTeX comparison: pass {i+1}/{repo.config.build_passes}")
                logs.append(run(args, cwd=new_source.parent, timeout=300).decode("utf-8", "replace"))
            pdf = new/repo.config.output_pdf if repo.config.output_pdf else new_source.with_suffix(".pdf")
            if not pdf.is_file() or not pdf.read_bytes().startswith(b"%PDF-"):
                raise RuntimeError("LaTeX diff build did not produce the configured PDF.")
            shutil.copyfile(pdf, cache/"diff.partial")
            (cache/"diff.partial").replace(result)
            (cache/"identity.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
        except Exception as error:
            logs.append(str(error))
            raise RuntimeError(f"LaTeX comparison failed; see {cache/'build.log'}. "
                               "Use --pdf-layout pages for an original-page comparison.\n" + str(error)) from error
        finally:
            (cache/"build.log").write_text("\n".join(logs), encoding="utf-8")
    return result
