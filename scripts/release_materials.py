"""Archive originals in Releases and link verified Pages copies for reading."""
import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import quote, unquote, urlencode, urljoin, urlsplit

REPO = 'ZJUSUEE/ZJUSUEE.github.io'
TAG = 'learning-materials-2026-10-15'
BASE = f'https://github.com/{REPO}/releases/download/{TAG}/'
DOCUMENT_TYPES = {'.pdf', '.doc', '.docx'}
BUDGET = 500_000_000
ORIGIN = 'https://zjusuee.github.io/'
SOURCE = Path(__file__).resolve().parents[1]
BOILER_PATH = 'courses/routes/Thermal/Route/能源转化（锅炉原理）/热能锅炉原理复习笔记.-klx.pdf'
BOILER_URL = BASE + 'boiler-review-notes-klx.pdf'
ATTRIBUTE = re.compile(r'\b(href|src|data)\s*=\s*([\"\'])(.*?)\2', re.I | re.S)


def viewer_url(asset):
    name = Path(asset['path']).with_suffix('.pdf').name
    return '/assets/pdfjs/web/viewer.html?' + urlencode({'file': asset['preview_url'], 'filename': name}) + '#zoom=page-width'


def boiler_asset(revision):
    return dict(path=BOILER_PATH, url=BOILER_URL, size=133976746,
                preview_url=f'https://media.githubusercontent.com/media/{REPO}/{revision}/docs/' + quote(BOILER_PATH))


class Links(HTMLParser):
    def __init__(self, page, assets):
        super().__init__(convert_charrefs=False)
        self.page, self.assets = page, assets
        self.output, self.fallback = [], []
        self.skip_object = False
        self.anchor_asset = None

    def feed(self, data):
        self.source = data
        self.line_starts = [0] + [match.end() for match in re.finditer('\n', data)]
        super().feed(data)

    def asset(self, url):
        parsed = urlsplit(urljoin(ORIGIN + self.page, html.unescape(url)))
        if parsed._replace(fragment='').geturl() == BOILER_URL:
            return self.assets.get(BOILER_PATH) or boiler_asset(next(iter(self.assets.values()))['revision'])
        if parsed.netloc != 'zjusuee.github.io':
            return None
        return self.assets.get(unquote(parsed.path).lstrip('/'))

    def download(self, asset):
        name = html.escape(Path(asset['path']).name)
        filename = html.escape(Path(asset['path']).name, quote=True)
        preview = html.escape(viewer_url(asset), quote=True)
        download = html.escape(asset['url'], quote=True)
        self.output.append(f'<p>{name} · <a href="{preview}" target="_blank" rel="noopener">预览</a> · '
                           f'<a href="{download}" download="{filename}">下载原文件</a></p>')
        self.output.append(
            f'<iframe class="course-pdf-preview" src="{html.escape(viewer_url(asset), quote=True)}" '
            f'title="{html.escape(Path(asset["path"]).name, quote=True)} 在线预览" loading="lazy" '
            'style="width:100%;height:75vh;min-height:360px;border:0"></iframe>')

    def handle_starttag(self, tag, attrs):
        if self.skip_object:
            if tag == 'object':
                raise ValueError('Nested PDF objects need review before migration')
            return
        values = dict(attrs)
        if tag == 'a':
            self.anchor_asset = self.asset(values.get('href', ''))
        asset = self.asset(values.get('data' if tag == 'object' else 'src', ''))
        if tag in {'object', 'embed'} and asset:
            self.download(asset)
            if tag == 'object':
                self.skip_object = True
                self.fallback = []
            return
        raw = self.get_starttag_text()
        def replace(match):
            asset = self.asset(match[3])
            if not asset:
                return match[0]
            fragment = urlsplit(html.unescape(match[3])).fragment
            url = viewer_url(asset) if match[1].lower() == 'href' else asset['url']
            if fragment and match[1].lower() == 'href':
                url = url.split('#', 1)[0] + '#' + fragment
            return f'{match[1]}={match[2]}{html.escape(url, quote=True)}{match[2]}'
        self.output.append(ATTRIBUTE.sub(replace, raw))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if self.skip_object:
            if tag == 'object':
                fallback = ' '.join(''.join(self.fallback).split())
                if fallback not in {'', 'Your browser does not support PDFs 下载笔记',
                                    'Your browser does not support PDFs 下载',
                                    'Your browser does not support PDFs 下载飞跃手册'}:
                    raise ValueError(f'PDF fallback contains additional content in {self.page}')
                self.skip_object = False
            return
        # embed is a void element; existing documents sometimes include its end tag.
        if tag != 'embed':
            self.output.append(f'</{tag}>')
        if tag == 'a' and self.anchor_asset:
            url = html.escape(self.anchor_asset['url'], quote=True)
            filename = html.escape(Path(self.anchor_asset['path']).name, quote=True)
            self.output.append(f' <a href="{url}" download="{filename}">下载原文件</a>')
            self.anchor_asset = None

    def handle_data(self, data):
        if self.anchor_asset and not self.skip_object:
            data = re.sub(r'^(\s*)下载', r'\1预览', data)
        (self.fallback if self.skip_object else self.output).append(data)

    def handle_entityref(self, name):
        self.reference('&' + name)

    def handle_charref(self, name):
        self.reference('&#' + name)

    def reference(self, prefix):
        line, column = self.getpos()
        start = self.line_starts[line - 1] + column
        end = start + len(prefix)
        self.handle_data(self.source[start:end + (self.source[end:end + 1] == ';')])

    def handle_comment(self, data):
        if not self.skip_object:
            self.output.append('<!--' + data + '-->')

    def handle_decl(self, decl):
        self.output.append('<!' + decl + '>')


def plan(site):
    revision = os.environ.get('GITHUB_SHA') or subprocess.check_output(
        ['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    if not re.fullmatch(r'[a-fA-F0-9]{40}', revision):
        raise ValueError('A full source commit SHA is required for stable previews')
    previews_path = SOURCE / 'materials-previews.json'
    previews = json.loads(previews_path.read_text()) if previews_path.exists() else {}
    assets = {}
    for path in sorted(p for p in site.rglob('*') if p.is_file() and p.suffix.lower() in DOCUMENT_TYPES):
        if path.suffix.lower() == '.pdf':
            with path.open('rb') as source:
                if not source.read(1024).lstrip().startswith(b'%PDF-'):
                    raise ValueError(f'Not a PDF: {path}')
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
        name = f'material-{digest}{path.suffix.lower()}'
        relative = path.relative_to(site).as_posix()
        preview_path = relative
        if path.suffix.lower() != '.pdf':
            record = previews.get(relative, {})
            preview_path = record.get('preview')
            if not preview_path or record.get('source_sha256') != digest or not (site / preview_path).is_file():
                raise ValueError(f'Generate and save an updated PDF preview before publishing: {relative}')
            with (site / preview_path).open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != record['preview_sha256']:
                    raise ValueError(f'PDF preview hash mismatch: {relative}')
        preview_digest = digest if preview_path == relative else previews[relative]['preview_sha256']
        asset = dict(path=relative, size=path.stat().st_size, sha256=digest,
                                name=name, url=BASE + name, revision=revision, preview_path=preview_path,
                                source_preview_path=preview_path, preview_sha256=preview_digest, mode='pdf',
                                full_preview_url=f'https://raw.githubusercontent.com/{REPO}/{revision}/docs/' + quote(preview_path))
        asset['preview_url'] = asset['full_preview_url']
        assets[relative] = asset
    pages_path = SOURCE / 'materials-pages.json'
    if pages_path.exists():
        routes = json.loads(pages_path.read_text())
        if BOILER_PATH in routes:
            asset = boiler_asset(revision)
            asset.update(name='boiler-review-notes-klx.pdf',
                         sha256='507eb96f7afb419db4541a771c2f53ad936b28a9e276e427f7c8fefe1c8e18d2',
                         external=True, revision=revision, source_preview_path=BOILER_PATH)
            assets[BOILER_PATH] = asset
        for asset in assets.values():
            original = routes.get(asset['path'], {})
            preview = routes.get(asset['source_preview_path'], {})
            if (original.get('sha256') != asset['sha256']
                    or preview.get('sha256') != asset.get('preview_sha256', asset['sha256'])):
                raise ValueError(f'Publish updated Pages copies before deploying: {asset["path"]}')
            for source_path, record in [(asset['path'], original), (asset['source_preview_path'], preview)]:
                if not re.fullmatch(r'/materials-(?:basic|major)/(?:material-[a-f0-9]{64}|boiler-review-notes-klx)\.(?:pdf|docx?)', record.get('url', '')):
                    raise ValueError('Invalid Pages material URL')
                expected = 'boiler-review-notes-klx.pdf' if source_path == BOILER_PATH else f'material-{record["sha256"]}{Path(source_path).suffix.lower()}'
                if record['url'].rsplit('/', 1)[-1] != expected:
                    raise ValueError('Pages material URL does not match its verified file')
            if not preview['url'].endswith('.pdf'):
                raise ValueError('Pages preview must be a PDF')
            asset.update(mode='pdf', url=original['url'], preview_url=preview['url'],
                         full_preview_url=preview['url'], pages_mirror=True)
    if not assets:
        raise ValueError('No documents found; build a fresh site before preparing materials')
    return assets


def gh(*args):
    return json.loads(subprocess.check_output(['gh', 'api', *args], text=True))


def upload(site, assets):
    release = gh(f'repos/{REPO}/releases/tags/{TAG}')
    def remote_assets():
        pages = gh(f'repos/{REPO}/releases/{release["id"]}/assets?per_page=100', '--paginate', '--slurp')
        return {asset['name']: asset for page in pages for asset in page}
    remote = remote_assets()
    with tempfile.TemporaryDirectory() as folder:
        for asset in {a['name']: a for a in assets.values()}.values():
            if asset['name'] not in remote:
                if asset.get('external'):
                    raise ValueError('Restore the published boiler asset before deploying')
                if release.get('immutable'):
                    raise ValueError('The materials release is immutable; use a new release before publishing')
                target = Path(folder) / asset['name']
                shutil.copyfile(site / asset['path'], target)
                subprocess.run(['gh', 'release', 'upload', TAG, str(target), '--repo', REPO], check=True)
                target.unlink()
    remote = remote_assets()
    for asset in assets.values():
        published = remote.get(asset['name'], {})
        if (published.get('size'), published.get('digest')) != (asset['size'], 'sha256:' + asset['sha256']):
            raise ValueError(f'Release asset verification failed: {asset["path"]}')


def prepare(site, assets, publish=False, local_files=None):
    if local_files:
        if publish:
            raise ValueError('Local preview URLs cannot be published')
        local_files = local_files.resolve()
        if local_files.is_relative_to(site.resolve()) or site.resolve().is_relative_to(local_files):
            raise ValueError('Use separate directories for original files and the local review build')
        for asset in assets.values():
            for path in [asset['path'], asset['source_preview_path']]:
                if not (local_files / path).is_file():
                    raise ValueError(f'Local preview file missing: {path}')
            asset['preview_url'] = '/__local-materials/' + quote(asset['source_preview_path'])
            asset['url'] = '/__local-materials/' + quote(asset['path'])
    pages = {}
    for path in site.rglob('*.html'):
        parser = Links(path.relative_to(site).as_posix(), assets)
        parser.feed(path.read_text())
        parser.close()
        if parser.skip_object:
            raise ValueError(f'Unclosed PDF object: {path}')
        pages[path] = ''.join(parser.output)
    redirects = {}
    redirect_assets = {BOILER_PATH: boiler_asset(next(iter(assets.values()))['revision']), **assets}
    for relative, asset in redirect_assets.items():
        url, name = html.escape(asset['url'], quote=True), html.escape(Path(relative).name)
        preview = html.escape(viewer_url(asset), quote=True)
        redirects[site / relative / 'index.html'] = (
            '<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            f'<title>{name}</title><meta http-equiv="refresh" content="0; url={preview}">'
            f'<p><a href="{preview}">在线预览 {name}</a> · <a href="{url}" download="{html.escape(Path(relative).name, quote=True)}">下载原文件</a></p></html>')
    before = sum(p.stat().st_size for p in site.rglob('*') if p.is_file())
    after = before - sum(a['size'] for a in assets.values() if not a.get('external'))
    after += sum(len(text.encode()) - path.stat().st_size for path, text in pages.items())
    after += sum(len(text.encode()) for text in redirects.values())
    if after > BUDGET:
        raise ValueError(f'Prepared site is {after} bytes; limit is {BUDGET}. Move more materials before publishing')
    if publish:
        upload(site, assets)
    # Only generated files change, after validation and (for deployment) verified uploads.
    for path, text in pages.items():
        path.write_text(text)
    for relative, asset in assets.items():
        if asset.get('external'):
            continue
        path = site / relative
        path.unlink()
        path.mkdir()
    for path, text in redirects.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    if local_files:
        (site / '__local-materials').symlink_to(local_files, target_is_directory=True)
    return {'document_count': len(assets), 'before_bytes': before, 'after_bytes': after,
            'reserved_bytes': 1_000_000_000 - after, 'budget_bytes': BUDGET,
            'uploaded': publish, 'local_preview': bool(local_files), 'assets': list(assets.values())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('site', type=Path)
    parser.add_argument('--upload', action='store_true', help='Upload and verify assets before preparing the deployment')
    parser.add_argument('--local-preview-files', type=Path, help='Use local original files for a review build; cannot be deployed')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.site, plan(args.site), args.upload, args.local_preview_files)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != 'assets'}, ensure_ascii=False))
