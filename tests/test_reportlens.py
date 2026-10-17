from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import hashlib
import json
import subprocess
import threading
import unittest
import zipfile

from reportlab.pdfgen import canvas
from reportlens.compare import create_comparison
from reportlens.export import export_pdf
from reportlens.package import load_package, save_package
from reportlens.repository import Config, Repository
from reportlens.server import make_server
from reportlens.service import Service


def pdf(path, pages):
    c=canvas.Canvas(str(path),invariant=1)
    for lines in pages:
        for index,line in enumerate(lines):c.drawString(60,740-index*25,line)
        c.showPage()
    c.save()


class ComparisonTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.a=self.root/'a.pdf';self.b=self.root/'b.pdf'
    def tearDown(self):self.temp.cleanup()
    def compare(self,a,b):
        pdf(self.a,a);pdf(self.b,b)
        return create_comparison(self.a,self.b,self.root/'result')
    def test_identical_has_no_changes(self):
        m=self.compare([['A consistent paragraph.']],[['A consistent paragraph.']])
        self.assertEqual(m['summary']['changed_pairs'],0)
        self.assertEqual(m['summary']['added_words'],0)
    def test_replacement_counts_and_retains_originals(self):
        m=self.compare([['The sample is red.']],[['The sample is green.']])
        self.assertEqual(m['summary']['added_words'],1)
        self.assertEqual(m['summary']['removed_words'],1)
        self.assertEqual((self.root/'result/before.pdf').read_bytes(),self.a.read_bytes())
        self.assertEqual(m['edits'][0]['removed'],'red.')
    def test_inserted_page_does_not_replace_later_text(self):
        m=self.compare([['Alpha stable content'],['Omega stable content']],[['Alpha stable content'],['Brand new middle page'],['Omega stable content']])
        self.assertEqual(m['summary']['removed_words'],0)
        self.assertEqual(m['summary']['added_words'],4)
        self.assertEqual([(p['before'],p['after']) for p in m['pairs']],[(1,1),(None,2),(2,3)])
    def test_reflow_is_not_a_text_edit(self):
        m=self.compare([['Alpha beta gamma delta'],['Epsilon zeta eta theta']],[['Alpha beta'],['gamma delta Epsilon zeta eta theta']])
        self.assertEqual(m['summary']['added_words'],0)
        self.assertEqual(m['summary']['removed_words'],0)
        self.assertGreater(m['summary']['changed_pairs'],0)
    def test_visual_only_change_detected(self):
        for path,x in ((self.a,60),(self.b,150)):
            c=canvas.Canvas(str(path),invariant=1);c.rect(x,300,100,80);c.showPage();c.save()
        m=create_comparison(self.a,self.b,self.root/'result')
        self.assertEqual(m['pairs'][0]['kind'],'visual / layout')
        self.assertEqual(m['summary']['added_words'],0)
    def test_deleted_page_alignment(self):
        m=self.compare([['Alpha stable content'],['Deleted material'],['Omega stable content']],[['Alpha stable content'],['Omega stable content']])
        self.assertEqual(m['summary']['removed_words'],2)
        self.assertEqual(m['pairs'][1]['after'],None)
    def test_complete_table_and_diagram_pages_kept(self):
        m=self.compare([['Table 1. Entire table','Alpha 10','Beta 20'],['Figure 1. Complete diagram','Input -> Output']],[['Table 1. Entire table','Alpha 15','Beta 20','Gamma 30'],['Figure 1. Complete diagram','Input -> Check -> Output']])
        self.assertIn('table',m['pairs'][0]['hints']);self.assertIn('figure',m['pairs'][1]['hints'])
        export_pdf(self.root/'result',m,self.root/'diff.pdf')
        import pdfplumber
        with pdfplumber.open(self.root/'diff.pdf') as document:self.assertEqual(len(document.pages),5)
    def test_package_round_trip(self):
        m=self.compare([['Original text']],[['Replacement text']])
        save_package(self.root/'result',self.root/'test.reportlens')
        actual=load_package(self.root/'test.reportlens',self.root/'opened')
        self.assertEqual(actual,m)
        self.assertEqual((self.root/'opened/after.pdf').read_bytes(),self.b.read_bytes())
    def test_zip_traversal_rejected_without_writes(self):
        with zipfile.ZipFile(self.root/'bad.reportlens','w') as archive:archive.writestr('../escape','bad')
        with self.assertRaises(ValueError):load_package(self.root/'bad.reportlens',self.root/'opened')
        self.assertFalse((self.root/'escape').exists())
    def test_corrupt_member_rejected(self):
        self.compare([['Old']],[['New']]);save_package(self.root/'result',self.root/'good.reportlens')
        with zipfile.ZipFile(self.root/'good.reportlens') as src,zipfile.ZipFile(self.root/'bad.reportlens','w') as out:
            for name in src.namelist():out.writestr(name,b'corrupted' if name=='before.pdf' else src.read(name))
        with self.assertRaisesRegex(ValueError,'checksum mismatch'):load_package(self.root/'bad.reportlens',self.root/'opened')
        self.assertFalse((self.root/'opened').exists())
    def test_invalid_page_reference_rejected_even_with_matching_checksum(self):
        self.compare([['Old']],[['New']]);save_package(self.root/'result',self.root/'good.reportlens')
        with zipfile.ZipFile(self.root/'good.reportlens') as src:
            entries={name:src.read(name) for name in src.namelist()}
        manifest=json.loads(entries['manifest.json']);manifest['pairs'][0]['after']=999
        entries['manifest.json']=json.dumps(manifest).encode()
        hashes=json.loads(entries['checksums.json']);hashes['manifest.json']=hashlib.sha256(entries['manifest.json']).hexdigest()
        entries['checksums.json']=json.dumps(hashes).encode()
        with zipfile.ZipFile(self.root/'bad.reportlens','w') as out:
            for name,data in entries.items():out.writestr(name,data)
        with self.assertRaisesRegex(ValueError,'page reference'):load_package(self.root/'bad.reportlens',self.root/'opened')


class GitTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.root=Path(self.temp.name)
        self.repo_path=self.root/'repo';self.repo_path.mkdir()
        self.git('init','-b','main');self.git('config','user.email','test@example.invalid');self.git('config','user.name','ReportLens test')
        pdf(self.repo_path/'report.pdf',[['Version one']]);self.commit('First report')
        self.first=self.git('rev-parse','HEAD').strip()
        (self.repo_path/'notes.md').write_text('Non-report update');self.commit('Notes only')
        pdf(self.repo_path/'report.pdf',[['Version two']]);self.commit('Second report')
        self.second=self.git('rev-parse','HEAD').strip()
        self.repository=Repository(Config(str(self.repo_path),source='report.pdf',tracked_paths=['report.pdf'],output_directory=str(self.root/'output')))
    def tearDown(self):self.temp.cleanup()
    def git(self,*args):
        return subprocess.check_output(['git','-C',str(self.repo_path),*args],stderr=subprocess.STDOUT).decode()
    def commit(self,message):self.git('add','.');self.git('commit','-m',message)
    def test_default_pair_skips_notes(self):
        self.assertEqual(self.repository.default_pair(),(self.first,self.second))
        self.assertEqual(len(self.repository.versions(False)),3)
    def test_snapshot_ignores_dirty_worktree_and_does_not_edit_it(self):
        dirty=b'Not the committed PDF';(self.repo_path/'report.pdf').write_bytes(dirty)
        before=self.git('status','--porcelain')
        result=self.repository.build(self.first)
        self.assertTrue(result.read_bytes().startswith(b'%PDF-'))
        self.assertEqual((self.repo_path/'report.pdf').read_bytes(),dirty)
        self.assertEqual(self.git('status','--porcelain'),before)
    def test_cached_build(self):
        first=self.repository.build(self.first)
        timestamp=first.stat().st_mtime_ns
        self.assertEqual(self.repository.build(self.first).stat().st_mtime_ns,timestamp)
    def test_autocrlf_does_not_alter_committed_pdf_bytes(self):
        self.git('config','core.autocrlf','true')
        expected=subprocess.check_output(['git','-C',str(self.repo_path),'show',self.first+':report.pdf'])
        self.assertEqual(self.repository.build(self.first).read_bytes(),expected)
    def test_reversed_targets_supported(self):
        service=Service(self.root/'comparisons',self.repository.config)
        service.compare_git(self.second,self.first)
        self.assertEqual(service.manifest['before']['commit'],self.second)
        self.assertTrue(list(service.root.glob('*.reportlens')))
        self.assertTrue(list(service.root.glob('*.pdf')))
    def test_config_rejects_escape(self):
        with self.assertRaises(ValueError):Config(str(self.repo_path),source='../report.tex').validate()
    def test_revision_option_injection_rejected(self):
        with self.assertRaises(RuntimeError):self.repository.resolve('--output=bad')
    def test_monitor_catches_two_new_commits(self):
        service=Service(self.root/'monitor',self.repository.config)
        service.monitor=True;service.monitor_seen=self.first
        pdf(self.repo_path/'report.pdf',[['Version three']]);self.commit('Third report')
        third=self.git('rev-parse','HEAD').strip()
        calls=[]
        service.compare_git=lambda a,b:calls.append((a,b))
        service.execute=lambda action:action()
        class OneIteration:
            count=0
            def wait(self,_):self.count+=1;return self.count>1
        service.stop=OneIteration();service.monitor_loop()
        self.assertEqual(calls,[(self.first,self.second),(self.second,third)])
        self.assertEqual(service.monitor_seen,third)


class ServerTests(TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.service=Service(self.temp.name)
        self.server=make_server(self.service);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=self.server.url.split('/?')[0];self.token=self.server.url.split('token=')[1]
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def test_local_gui_loads(self):
        with urlopen(self.server.url) as response:self.assertIn(b'ReportLens',response.read())
    def test_api_requires_capability(self):
        with self.assertRaises(HTTPError) as caught:urlopen(self.base+'/api/status')
        self.assertEqual(caught.exception.code,403)
    def test_external_origin_denied(self):
        request=Request(self.base+'/api/status?token='+self.token,headers={'Origin':'https://example.com'})
        with self.assertRaises(HTTPError) as caught:urlopen(request)
        self.assertEqual(caught.exception.code,403)
    def test_host_rebinding_denied(self):
        request=Request(self.base+'/api/status?token='+self.token,headers={'Host':'evil.example'})
        with self.assertRaises(HTTPError) as caught:urlopen(request)
        self.assertEqual(caught.exception.code,403)
    def test_asset_links_stay_bound_to_the_opened_version(self):
        root=Path(self.temp.name)
        for name,content in [('first',b'first image'),('second',b'second image')]:
            folder=root/name;(folder/'assets').mkdir(parents=True)
            (folder/'assets/before-1.png').write_bytes(content)
            self.service.activate(folder,{})
        with urlopen(self.base+'/assets/1/before-1.png?token='+self.token) as response:
            self.assertEqual(response.read(),b'first image')


if __name__=='__main__':unittest.main()
