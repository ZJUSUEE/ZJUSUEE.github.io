import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


materials = module('materials', 'scripts/release_materials.py')
search = module('search', 'hooks/search_codes.py')


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.site = Path(self.directory.name)
        self.pdf = self.site / 'courses/笔记 + &.pdf'
        self.pdf.parent.mkdir()
        self.pdf.write_bytes(b'%PDF-1.4\n' + b'x' * 40)
        self.page = self.site / 'courses/index.html'
        self.page.write_text('<!DOCTYPE html><p>作者：同学</p>'
            '<object data="%E7%AC%94%E8%AE%B0%20+%20%26.pdf" type="application/pdf">'
            '<embed src="笔记 + &amp;.pdf" />'
            '<p>Your browser does not support PDFs <a href="笔记 + &amp;.pdf">下载笔记</a></p>'
            '</object><a href="笔记 + &amp;.pdf#page=3">复习资料</a>'
            '<a href="笔记 + &amp;.pdf">下载笔记</a>')
        revision = patch.dict(materials.os.environ, {'GITHUB_SHA': 'a' * 40})
        revision.start()
        self.addCleanup(revision.stop)
        source = patch.object(materials, 'SOURCE', self.site)
        source.start()
        self.addCleanup(source.stop)

    def test_download_redirect_and_duplicate_names_keep_file_identity(self):
        other = self.site / 'other/笔记 + &.pdf'
        other.parent.mkdir()
        other.write_bytes(b'%PDF-1.4\n' + b'y' * 40)
        small = self.site / 'small.pdf'
        small.write_bytes(b'%PDF-1.4\n')
        assets = materials.plan(self.site)
        self.assertNotEqual(assets['courses/笔记 + &.pdf']['url'], assets['other/笔记 + &.pdf']['url'])
        result = materials.prepare(self.site, assets)
        text = self.page.read_text()
        self.assertIn('作者：同学', text)
        self.assertNotIn('<object', text)
        self.assertNotIn('<embed', text)
        self.assertIn('class="course-pdf-preview"', text)
        self.assertIn('/assets/pdfjs/web/viewer.html?file=', text)
        self.assertIn('raw.githubusercontent.com', assets['courses/笔记 + &.pdf']['preview_url'])
        self.assertIn('在线预览', text)
        self.assertIn(materials.viewer_url(assets['courses/笔记 + &.pdf']).split('#')[0] + '#page=3', materials.html.unescape(text))
        self.assertIn('复习资料', text)
        self.assertIn('预览笔记</a>', text)
        self.assertTrue((self.pdf / 'index.html').is_file())
        self.assertTrue((small / 'index.html').is_file())
        legacy_boiler = (self.site / materials.BOILER_PATH / 'index.html').read_text()
        self.assertIn(materials.BOILER_URL, legacy_boiler)
        self.assertIn('media.githubusercontent.com', legacy_boiler)
        actual = sum(p.stat().st_size for p in self.site.rglob('*') if p.is_file())
        self.assertEqual(result['after_bytes'], actual)
        self.assertFalse(result['uploaded'])

    def test_additional_fallback_content_blocks_migration_without_edits(self):
        self.page.write_text(self.page.read_text().replace('下载笔记</a>', '下载笔记</a>额外说明'))
        original = self.page.read_bytes()
        with self.assertRaisesRegex(ValueError, 'additional content'):
            materials.prepare(self.site, materials.plan(self.site))
        self.assertEqual(self.page.read_bytes(), original)
        self.assertTrue(self.pdf.is_file())

    def test_literal_ampersands_and_escaped_examples_keep_their_original_text(self):
        text = '<p>数理方法 I&II\n&amp; &lt;script&gt; &#65; &#65中文</p>'
        parser = materials.Links('index.html', {})
        parser.feed(text)
        parser.close()
        self.assertEqual(''.join(parser.output), text)

    def test_budget_failure_happens_before_upload_or_edits(self):
        original = self.page.read_bytes()
        with patch.object(materials, 'BUDGET', 1), patch.object(materials, 'upload') as upload:
            with self.assertRaisesRegex(ValueError, 'limit'):
                materials.prepare(self.site, materials.plan(self.site), publish=True)
            upload.assert_not_called()
        self.assertEqual(self.page.read_bytes(), original)
        self.assertTrue(self.pdf.is_file())

    def test_remote_digest_mismatch_blocks_preparation_without_overwriting(self):
        assets = materials.plan(self.site)
        item = next(iter(assets.values()))
        remote = [[dict(name=item['name'], size=item['size'], digest='sha256:wrong')]]
        original = self.page.read_bytes()
        with patch.object(materials, 'gh', side_effect=[{'id': 1}, remote, remote]), patch.object(materials.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'verification failed'):
                materials.prepare(self.site, assets, publish=True)
            run.assert_not_called()
        self.assertEqual(self.page.read_bytes(), original)
        self.assertTrue(self.pdf.is_file())

    def test_fake_pdf_is_rejected(self):
        self.pdf.write_bytes(b'version https://git-lfs.github.com/spec/v1')
        with self.assertRaisesRegex(ValueError, 'Not a PDF'):
            materials.plan(self.site)

    def test_identical_files_are_uploaded_once_and_verified(self):
        duplicate = self.site / 'duplicate.pdf'
        duplicate.write_bytes(self.pdf.read_bytes())
        assets = materials.plan(self.site)
        item = next(iter(assets.values()))
        remote = [[dict(name=item['name'], size=item['size'], digest='sha256:' + item['sha256'])]]
        with patch.object(materials, 'gh', side_effect=[{'id': 1}, [[]], remote]), patch.object(materials.subprocess, 'run') as run:
            result = materials.prepare(self.site, assets, publish=True)
            self.assertEqual(run.call_count, 1)
            self.assertNotIn('--clobber', run.call_args.args[0])
        self.assertTrue(result['uploaded'])
        self.assertEqual(result['document_count'], 2)

    def test_word_preview_must_match_its_original(self):
        word = self.site / 'notes.docx'
        word.write_bytes(b'PKword-original')
        sha = materials.hashlib.sha256(word.read_bytes()).hexdigest()
        preview = self.site / 'material-previews/word.pdf'
        preview.parent.mkdir()
        preview.write_bytes(b'%PDF-1.4\n')
        record = {'notes.docx': dict(source_sha256=sha, preview='material-previews/word.pdf',
                                     preview_sha256=materials.hashlib.sha256(preview.read_bytes()).hexdigest())}
        (self.site / 'materials-previews.json').write_text(json.dumps(record))
        with patch.object(materials, 'SOURCE', self.site):
            assets = materials.plan(self.site)
            self.assertTrue(assets['notes.docx']['preview_url'].endswith('/material-previews/word.pdf'))
            word.write_bytes(b'PKchanged-original')
            with self.assertRaisesRegex(ValueError, 'updated PDF preview'):
                materials.plan(self.site)

    def test_local_preview_cannot_publish(self):
        with self.assertRaisesRegex(ValueError, 'cannot be published'):
            materials.prepare(self.site, materials.plan(self.site), publish=True, local_files=self.site)

    def test_pages_copy_uses_original_pdf_and_preserves_page_link(self):
        first = materials.plan(self.site)['courses/笔记 + &.pdf']
        url = '/materials-basic/' + first['name']
        routes = {first['path']: dict(sha256=first['sha256'], url=url)}
        (self.site / 'materials-pages.json').write_text(json.dumps(routes))
        assets = materials.plan(self.site)
        asset = assets[first['path']]
        self.assertEqual(asset['mode'], 'pdf')
        self.assertEqual(asset['url'], url)
        self.assertEqual(asset['preview_url'], url)
        self.assertNotIn('material-viewer', materials.viewer_url(asset))
        result = materials.prepare(self.site, assets)
        self.assertIn(url, self.page.read_text())
        self.assertIn('download="笔记 + &amp;.pdf"', self.page.read_text())
        self.assertIn('#page=3', self.page.read_text())
        self.assertFalse((self.site / 'document-previews').exists())
        self.assertEqual(result['after_bytes'], sum(p.stat().st_size for p in self.site.rglob('*') if p.is_file()))

    def test_pages_copy_hash_or_url_mismatch_blocks_edits(self):
        asset = materials.plan(self.site)['courses/笔记 + &.pdf']
        original = self.page.read_bytes()
        for changes in [dict(sha256='0'*64), dict(url='https://example.com/file.pdf'),
                        dict(url='/materials-basic/material-'+'0'*64+'.pdf')]:
            routes = {asset['path']: dict(sha256=asset['sha256'], url='/materials-basic/'+asset['name'])}
            routes[asset['path']].update(changes)
            (self.site / 'materials-pages.json').write_text(json.dumps(routes))
            with self.assertRaises(ValueError):
                materials.plan(self.site)
            self.assertEqual(self.page.read_bytes(), original)

    def test_external_boiler_uses_verified_pages_copy_without_local_pdf(self):
        first = materials.plan(self.site)['courses/笔记 + &.pdf']
        boiler = '/materials-major/boiler-review-notes-klx.pdf'
        routes = {first['path']: dict(sha256=first['sha256'], url='/materials-basic/'+first['name']),
                  materials.BOILER_PATH: dict(sha256='507eb96f7afb419db4541a771c2f53ad936b28a9e276e427f7c8fefe1c8e18d2', url=boiler)}
        (self.site / 'materials-pages.json').write_text(json.dumps(routes))
        self.page.write_text(self.page.read_text()+f'<a href="{materials.BOILER_URL}#page=2">锅炉笔记</a>')
        assets = materials.plan(self.site)
        self.assertTrue(assets[materials.BOILER_PATH]['external'])
        result = materials.prepare(self.site, assets)
        self.assertIn('file=%2Fmaterials-major%2Fboiler-review-notes-klx.pdf', self.page.read_text())
        self.assertIn('#page=2', self.page.read_text())
        self.assertIn(boiler, (self.site / materials.BOILER_PATH / 'index.html').read_text())
        self.assertEqual(result['after_bytes'], sum(p.stat().st_size for p in self.site.rglob('*') if p.is_file()))

    def test_immutable_release_blocks_new_uploads(self):
        assets = materials.plan(self.site)
        with patch.object(materials, 'gh', side_effect=[{'id': 1, 'immutable': True}, [[]]]), patch.object(materials.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'immutable'):
                materials.prepare(self.site, assets, publish=True)
            run.assert_not_called()
        self.assertTrue(self.pdf.is_file())

    def test_search_codes_are_independent_without_changing_course_content(self):
        folder = self.site / 'search'
        folder.mkdir()
        entries = [{'location': 'courses/catalog/CSE2001M/#course-information', 'title': '课程信息',
                    'text': '自动控制理论（甲）CSE2001M 毕业设计ENER4016M1ENER4016M'},
                   {'location': 'other/', 'title': '其他', 'text': '保持原文'}]
        path = folder / 'search_index.json'
        path.write_text(json.dumps({'docs': entries}))
        search.on_post_build({'site_dir': str(self.site)})
        result = json.loads(path.read_text())['docs']
        for code in ['CSE2001M', 'ENER4016M1', 'ENER4016M']:
            self.assertIn(code, result[0]['text'].split())
        self.assertTrue(result[0]['text'].endswith(entries[0]['text']))
        self.assertEqual(result[1], entries[1])


if __name__ == '__main__':
    unittest.main()
