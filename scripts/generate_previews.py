"""Create PDF previews for Word materials while retaining their original files."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

from pypdf import PdfReader, PdfWriter

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / 'docs'
MANIFEST = ROOT / 'materials-previews.json'


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def generate():
    before = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    records, pending = {}, []
    originals = sorted(p for p in DOCS.rglob('*') if p.is_file() and p.suffix.lower() in {'.doc', '.docx'})
    for path in originals:
        relative, sha = path.relative_to(DOCS).as_posix(), digest(path)
        record = before.get(relative, {})
        preview = DOCS / record.get('preview', '_missing')
        if record.get('source_sha256') == sha and preview.is_file() and digest(preview) == record.get('preview_sha256'):
            records[relative] = record
        else:
            pending.append((path, relative, sha))
    if pending:
        if not shutil.which('soffice'):
            raise RuntimeError('Install LibreOffice to generate PDF previews before submitting Word materials')
        with tempfile.TemporaryDirectory() as folder:
            temp = Path(folder)
            inputs = []
            for path, relative, sha in pending:
                copy = temp / (sha + path.suffix.lower())
                shutil.copyfile(path, copy)
                inputs.append(str(copy))
            subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', str(temp), *inputs], check=True)
            for path, relative, sha in pending:
                converted = temp / (sha + '.pdf')
                reader = PdfReader(converted)
                assert len(reader.pages) > 0, relative
                writer = PdfWriter(clone_from=reader)
                writer.metadata = None
                writer.xmp_metadata = None
                writer.add_metadata({'/Author': 'bty', '/Creator': 'bty', '/Producer': 'bty', '/Title': path.stem})
                preview = DOCS / 'material-previews' / (sha + '.pdf')
                preview.parent.mkdir(exist_ok=True)
                with preview.open('wb') as output:
                    writer.write(output)
                assert digest(path) == sha, relative
                assert len(PdfReader(preview).pages) == len(reader.pages), relative
                records[relative] = dict(source_sha256=sha, preview=preview.relative_to(DOCS).as_posix(),
                                         preview_sha256=digest(preview), pages=len(reader.pages))
    MANIFEST.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'word_files': len(originals), 'generated': len(pending),
                      'preview_pages': sum(record['pages'] for record in records.values())}, ensure_ascii=False))


if __name__ == '__main__':
    generate()
