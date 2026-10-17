from pathlib import Path
from tempfile import TemporaryDirectory
import subprocess
import sys
import unittest

import pdfplumber
from reportlab.pdfgen import canvas
from reportlens.compare import create_comparison
from reportlens.export import export_pdf
from reportlens.merged import extract_blocks, fonts
from reportlens.package import save_package, load_package
from reportlens.service import Service


def make_pdf(path, lines, visual=False):
    c = canvas.Canvas(str(path), invariant=1)
    for i, text in enumerate(lines):
        c.drawString(60, 740-i*24, text)
    if visual:
        c.rect(60, 350, 400, 150)
        c.drawString(80, 460, "Complete diagram content")
        c.drawString(80, 370, "Bottom label must survive")
        c.drawString(60, 325, "Figure 1. Whole diagram")
    c.showPage(); c.save()


class MergedTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(); self.root = Path(self.temp.name)
        self.a, self.b = self.root/'old.pdf', self.root/'new.pdf'
    def tearDown(self):
        self.temp.cleanup()
    def compare(self, old, new, visual=False):
        make_pdf(self.a, old, visual); make_pdf(self.b, new, visual)
        self.directory = self.root/'comparison'
        self.manifest = create_comparison(self.a, self.b, self.directory)
        return self.manifest
    def test_default_merges_replacement_with_selectable_unchanged_text_once(self):
        m = self.compare(['Stable sentence.', 'The sample is red today.'],
                         ['Stable sentence.', 'The sample is green today.'])
        export_pdf(self.directory, m, self.root/'out.pdf')
        with pdfplumber.open(self.root/'out.pdf') as doc:
            text = '\n'.join(p.extract_text() for p in doc.pages)
            self.assertEqual(text.count('Stable sentence.'), 1)
            self.assertIn('The sample is red green today.', text)
            chars = [c for p in doc.pages for c in p.chars]
            colors = {tuple(c['non_stroking_color']) for c in chars}
            self.assertIn((round(181/255, 6), round(42/255, 6), round(59/255, 6)),
                          {tuple(round(v, 6) for v in color) for color in colors})
            self.assertTrue(any(p.lines for p in doc.pages))
    def test_insert_delete_and_reflow_do_not_duplicate_stable_text(self):
        m = self.compare(['Alpha beta gamma delta.', 'Remove this paragraph.'],
                         ['Alpha beta', 'gamma delta.', 'Add this paragraph.'])
        export_pdf(self.directory, m, self.root/'out.pdf')
        with pdfplumber.open(self.root/'out.pdf') as doc:
            text = '\n'.join(p.extract_text() for p in doc.pages)
            for word in ('Alpha', 'beta', 'gamma', 'delta.', 'Remove', 'Add'):
                self.assertEqual(text.split().count(word), 1)
    def test_inline_deletion_does_not_split_the_sentence(self):
        m = self.compare(['This is a very useful sentence.'], ['This is a useful sentence.'])
        export_pdf(self.directory, m, self.root/'out.pdf')
        with pdfplumber.open(self.root/'out.pdf') as doc:
            self.assertIn('This is a very useful sentence.', doc.pages[0].extract_text())
    def test_multiline_caption_stays_with_the_complete_visual(self):
        self.compare(['Introductory prose.'], ['Revised introductory prose.'], visual=True)
        c = canvas.Canvas(str(self.b), invariant=1)
        c.rect(60, 350, 400, 150)
        c.drawString(60, 310, 'Figure 1. A long caption')
        c.drawString(60, 296, 'continues on its second line.')
        c.drawString(60, 260, 'Separate prose follows.')
        c.showPage(); c.save()
        self.manifest = create_comparison(self.a, self.b, self.directory)
        fonts(); blocks = extract_blocks(self.directory, self.manifest, 'after')
        prose = ' '.join(w for b in blocks if b['type'] == 'text' for w in b['words'])
        self.assertEqual(prose, 'Separate prose follows.')
    def test_geometry_keeps_entire_diagram_and_caption(self):
        self.compare(['Introductory prose.'], ['Revised introductory prose.'], visual=True)
        fonts()
        blocks = extract_blocks(self.directory, self.manifest, 'after')
        visuals = [b for b in blocks if b['type'] == 'visual']
        self.assertEqual(len(visuals), 1)
        self.assertGreater(visuals[0]['height'], 175)
        prose = ' '.join(w for b in blocks if b['type'] == 'text' for w in b['words'])
        self.assertEqual(prose, 'Revised introductory prose.')
        export_pdf(self.directory, self.manifest, self.root/'out.pdf')
        with pdfplumber.open(self.root/'out.pdf') as doc:
            self.assertEqual(sum(len(p.images) for p in doc.pages), 1)
    def test_changed_diagram_keeps_both_complete_versions(self):
        self.compare(['Introductory prose.'], ['Introductory prose.'], visual=True)
        c = canvas.Canvas(str(self.b), invariant=1)
        c.drawString(60, 740, 'Introductory prose.')
        c.rect(60, 350, 400, 150)
        c.drawString(80, 460, 'Revised complete diagram content')
        c.drawString(80, 370, 'Bottom label must survive')
        c.drawString(60, 325, 'Figure 1. Whole diagram')
        c.showPage(); c.save()
        m = create_comparison(self.a, self.b, self.directory)
        export_pdf(self.directory, m, self.root/'out.pdf')
        with pdfplumber.open(self.root/'out.pdf') as doc:
            self.assertEqual(sum(len(p.images) for p in doc.pages), 2)
            text = '\n'.join(p.extract_text() or '' for p in doc.pages)
            self.assertEqual(text.count('Introductory prose.'), 1)
            self.assertIn('BEFORE / removed - complete visual region', text)
            self.assertIn('AFTER / added - complete visual region', text)
    def test_unlocated_table_uses_whole_page(self):
        self.compare(['Table 1. Borderless data', 'Alpha 10', 'Beta 20'],
                     ['Table 1. Borderless data', 'Alpha 15', 'Beta 20'])
        fonts()
        blocks = extract_blocks(self.directory, self.manifest, 'after')
        self.assertEqual(len(blocks), 1)
        self.assertTrue(blocks[0]['fallback'])
    def test_figure_references_in_prose_are_not_captions(self):
        self.compare(['Figure 2.4 shows the connections.', 'Figure 2.3. The power is separate.'],
                     ['Figure 2.4 shows the connections.', 'Figure 2.3. The power is separate.'])
        fonts(); blocks = extract_blocks(self.directory, self.manifest, 'after')
        self.assertTrue(all(b['type'] == 'text' for b in blocks))
    def test_old_package_opens_with_new_default_without_changing_input(self):
        self.compare(['Original prose'], ['Updated prose'])
        export_pdf(self.directory, self.manifest, self.directory/'diff.pdf', layout='pages')
        package = save_package(self.directory, self.root/'old.reportlens')
        original = package.read_bytes()
        service = Service(self.root/'opened')
        service.open_package(package)
        self.assertEqual(service.manifest['pdf_export']['layout'], 'merged')
        self.assertEqual(package.read_bytes(), original)
        with pdfplumber.open(service.current/'diff.pdf') as doc:
            self.assertIn('Original Updated prose', doc.pages[0].extract_text())
    def test_cli_alternative_export_and_new_package_metadata(self):
        make_pdf(self.a, ['Old prose']); make_pdf(self.b, ['New prose'])
        service = Service(self.root/'output', pdf_layout='pages')
        service.compare_files(self.a, self.b)
        package = self.root/'output/pdf-comparison-pages.reportlens'
        manifest = load_package(package, self.root/'check')
        self.assertEqual(manifest['pdf_export']['layout'], 'pages')
        subprocess.run([sys.executable, '-m', 'reportlens', 'export', str(package),
                        '--output', str(self.root/'merged.pdf')], check=True, capture_output=True)
        with pdfplumber.open(self.root/'merged.pdf') as doc:
            self.assertIn('Old New prose', doc.pages[0].extract_text())
        subprocess.run([sys.executable, '-m', 'reportlens', 'export', str(package),
                        '--output', str(self.root/'pages.pdf'), '--pdf-layout', 'pages'],
                       check=True, capture_output=True)
        with pdfplumber.open(self.root/'pages.pdf') as doc:
            self.assertEqual(len(doc.pages), 3)


if __name__ == '__main__':
    unittest.main()
