from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import os
import shutil
import subprocess
import unittest

import pdfplumber
from PIL import Image
from reportlens.export import export_pdf
from reportlens.latex import flatten, protect_visuals, restore_visuals, visual_spans, syntax_mask, TOKEN
from reportlens.outline import add_outline, front_matter
from reportlens.repository import Config, Repository
from reportlens.service import Service


class SourceTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory(); self.root=Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def test_nested_visuals_are_one_complete_object(self):
        source=r'Intro\begin{figure}\begin{tikzpicture}drawing\end{tikzpicture}\caption{Full}\end{figure}End'
        spans=visual_spans(source)
        self.assertEqual(len(spans),1)
        self.assertEqual(source[spans[0][0]:spans[0][1]],source[5:-3])
    def test_input_expansion_ignores_comments_and_verbatim(self):
        (self.root/'part.tex').write_text('Included text',encoding='utf-8')
        main=self.root/'main.tex'
        main.write_text('\\% literal % \\input{missing}\n\\input{part}\n\\begin{verbatim}\\input{absent}\\end{verbatim}',encoding='utf-8')
        text=flatten(self.root,main)
        self.assertIn('Included text',text)
        self.assertIn(r'\input{absent}',text)
    def test_subdirectory_main_can_include_other_committed_paths(self):
        folder=self.root/'document';folder.mkdir()
        main=folder/'main.tex'; main.write_text(r'\input{../section}',encoding='utf-8')
        (self.root/'section.tex').write_text('Section text\n\\endinput\nIgnored tail',encoding='utf-8')
        self.assertEqual(flatten(folder,main,boundary=self.root).strip(),'Section text')
    def test_recursive_or_escaping_input_rejected(self):
        source=self.root/'main.tex';source.write_text(r'\input{main}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'Recursive'):flatten(self.root,source)
        source.write_text(r'\input{../outside}',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'snapshot'):flatten(self.root,source)
    def test_changed_image_bytes_protect_both_whole_figures(self):
        a=self.root/'a';b=self.root/'b';a.mkdir();b.mkdir()
        Image.new('RGB',(20,20),'red').save(a/'plot.png')
        Image.new('RGB',(20,20),'green').save(b/'plot.png')
        source=r'\begin{figure}\includegraphics{plot.png}\caption{All content}\label{fig:one}\end{figure}'
        objects={};old=protect_visuals(source,a,'before',objects).strip();new=protect_visuals(source,b,'after',objects).strip()
        self.assertNotEqual(old,new)
        restored=restore_visuals(r'\DIFdel{'+old+'\n}'+r'\DIFadd{'+new+'\n}',objects)
        self.assertEqual(restored.count(r'\begin{figure}'),2)
        self.assertIn((a/'plot.png').resolve().as_posix(),restored)
        self.assertIn((b/'plot.png').resolve().as_posix(),restored)
        self.assertIn(r'\label{reportlens-old-',restored)
        self.assertIn(r'\setcounter{figure}{\value{ReportLensSavedFigure}}',restored)
    def test_unchanged_visual_is_not_duplicated(self):
        source=r'\begin{table}Whole table\end{table}';objects={}
        a=protect_visuals(source,self.root,'before',objects)
        b=protect_visuals(source,self.root,'after',objects)
        self.assertEqual(a,b)
        self.assertEqual(restore_visuals(a,objects).strip(),source)
    def test_preamble_macro_definitions_are_not_visual_objects(self):
        preamble=r'\documentclass{article}\newcommand{\legend}[1]{\begin{tabular}{l}#1\end{tabular}}'
        source=preamble+r'\begin{document}\begin{table}Displayed table\end{table}\end{document}'
        objects={}; protected=protect_visuals(source,self.root,'after',objects)
        self.assertTrue(protected.startswith(preamble))
        self.assertEqual(len(objects),1)
    def test_latex_is_selected_for_tex_and_not_for_pdf(self):
        with patch('reportlens.service.Repository'):
            self.assertEqual(Service(self.root/'tex',Config(str(self.root),source='main.tex')).pdf_layout,'latex')
            self.assertEqual(Service(self.root/'pdf',Config(str(self.root),source='main.pdf')).pdf_layout,'merged')
            self.assertEqual(Service(self.root/'forced',Config(str(self.root)),pdf_layout='pages').pdf_layout,'pages')
        with self.assertRaisesRegex(ValueError,'requires source'):
            Service(self.root/'no-source',pdf_layout='latex').compare_files('a.pdf','b.pdf')
    def test_export_cannot_invent_native_pdf_from_pdf_only_package(self):
        with self.assertRaisesRegex(ValueError,'no compiled LaTeX diff'):
            export_pdf(self.root,{},self.root/'out.pdf',layout='latex')
    def test_configured_native_viewer_can_still_open_legacy_packages(self):
        manifest={'pdf_export':{'layout':'merged','version':1}}
        with patch('reportlens.service.Repository'), patch('reportlens.service.load_package',return_value=manifest):
            service=Service(self.root/'configured',Config(str(self.root)))
            with patch.object(service,'write_pdf') as write:
                service.open_package('old.reportlens')
                self.assertEqual(write.call_args.kwargs,{'layout':'merged'})
            self.assertEqual(service.pdf_layout,'latex')

    def test_outline_names_changed_sections_and_ignores_unchanged_locations(self):
        source = (r'\documentclass{article}\begin{document}\section{Unchanged}Stable.'
                  r'\section{Methods \& \textbf{checks}}\DIFdel{old}\DIFadd{new}'
                  r'\subsection{Removed topic}\DIFdel{Removed paragraph}'
                  '\n% \\DIFadd{comment only}\n'
                  r'\section{Untouched}Stable.\end{document}')
        marked, entries = add_outline(source, {}, syntax_mask, TOKEN)
        self.assertEqual([name for _, name in entries], ['Section: Methods & checks', 'Subsection: Methods & checks / Removed topic'])
        self.assertEqual(marked.count(r'\hypertarget{'), 2)
        front = front_matter('a'*40, 'b'*40, entries)
        self.assertIn(r'\hyperlink{reportlens-change-1}{Section~\ref*{reportlens-change-1-number}: Methods \& checks', front)
        self.assertIn(r'\pageref*{reportlens-change-1-page}', front)
        self.assertNotIn('Untouched', front)

    def test_outline_visual_links_target_complete_versions(self):
        objects = {}
        old = protect_visuals(r'\begin{table}\caption{Readings \& checks}Old\end{table}', self.root, 'before', objects).strip()
        new = protect_visuals(r'\begin{table}\caption{Readings \& checks}New\end{table}', self.root, 'after', objects).strip()
        source = r'\begin{document}\section{Data}\DIFdel{'+old+r'}\DIFadd{'+new+r'}\end{document}'
        marked, entries = add_outline(source, objects, syntax_mask, TOKEN)
        restored = restore_visuals(marked, objects)
        self.assertEqual([name for _, name in entries], ['Table (before): Readings & checks', 'Table (after): Readings & checks'])
        for anchor, _ in entries:
            self.assertIn(r'\hypertarget{'+anchor+'}{}', restored)


@unittest.skipUnless(os.environ.get('REPORTLENS_TEST_LATEX')=='1','Set REPORTLENS_TEST_LATEX=1 with LaTeX/latexdiff installed')
class NativeIntegrationTests(unittest.TestCase):
    def test_native_prose_whole_tables_figures_and_portable_reopening(self):
        with TemporaryDirectory() as temp:
            root=Path(temp); repo=root/'repo';repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.STDOUT).decode().strip()
            git('init','-b','main');git('config','user.email','test@example.invalid');git('config','user.name','ReportLens test')
            base=r'''\documentclass[12pt]{article}
\usepackage[T1]{fontenc}\usepackage{lmodern}\usepackage{xcolor,graphicx,float,hyperref}
\begin{document}\section{Native typography}
The sample is WORD. Stable prose appears once.
\begin{figure}[H]\centering\includegraphics[width=20mm]{plot.png}\caption{Complete diagram}\label{fig:diagram}\end{figure}
\begin{table}[H]\centering\caption{Full observations}\label{tab:data}\begin{tabular}{ll}Bed & Value\\A & VALUE\\B & 20\end{tabular}\end{table}
Figure~\ref{fig:diagram} and Table~\ref{tab:data} retain their current numbering.
\end{document}'''
            for word,value,color in [('red','10','red'),('green','15','green')]:
                (repo/'main.tex').write_text(base.replace('WORD',word).replace('VALUE',value),encoding='utf-8')
                Image.new('RGB',(40,40),color).save(repo/'plot.png')
                git('add','.');git('commit','-m',word)
            dirty='Uncommitted work must remain untouched'
            (repo/'notes.txt').write_text(dirty)
            status=git('status','--porcelain')
            config=Config(str(repo),source='main.tex',output_directory=str(root/'output'))
            service=Service(root/'output',config);service.compare_git()
            self.assertEqual(service.manifest['pdf_export']['layout'],'latex')
            data=(service.current/'diff.pdf').read_bytes()
            with pdfplumber.open(service.current/'diff.pdf') as doc:
                text='\n'.join(p.extract_text() or '' for p in doc.pages)
                first = doc.pages[0].extract_text()
                self.assertIn('ReportLens comparison', first)
                self.assertIn('Changed places', first)
                self.assertIn('Section 1: Native typography', first)
                self.assertIn('Figure 1 (before): Complete diagram', first)
                self.assertIn('Table 1 (after): Full observations', first)
                self.assertIn('page 1', first)
                self.assertNotIn('ReportLens comparison', doc.pages[-1].extract_text())
                links = [a['data'].get('A', {}) for a in doc.pages[0].annots]
                targets = [a.get('D', b'') for a in links if isinstance(a, dict)]
                self.assertEqual(len([t for t in targets if isinstance(t, bytes) and t.startswith(b'reportlens-change-')]), 5)
                fonts={c['fontname'] for p in doc.pages for c in p.chars}
                self.assertTrue(any('LMRoman' in f for f in fonts))
                self.assertEqual(text.count('Stable prose appears once.'),1)
                self.assertEqual(text.count('BEFORE / removed - complete object'),2)
                self.assertEqual(text.count('AFTER / added - complete object'),2)
                self.assertIn('Figure 1 and Table 1 retain their current numbering.',text)
                self.assertNotIn('REPORTLENSOBJECT',text)
                self.assertNotIn('??',text)
            package=next((root/'output').glob('*.reportlens'))
            opened=Service(root/'opened');opened.open_package(package)
            self.assertEqual((opened.current/'diff.pdf').read_bytes(),data)
            export_pdf(opened.current,opened.manifest,root/'exported.pdf')
            self.assertEqual((root/'exported.pdf').read_bytes(),data)
            self.assertEqual(git('status','--porcelain'),status)
            self.assertEqual((repo/'notes.txt').read_text(),dirty)
            with patch('reportlens.latex.build_latex_diff',side_effect=AssertionError('cache should be used')):
                service.compare_git()


if __name__=='__main__':unittest.main()
