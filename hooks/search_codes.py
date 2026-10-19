import json
import re
from pathlib import Path


def on_post_build(config):
    path = Path(config['site_dir']) / 'search/search_index.json'
    index = json.loads(path.read_text())
    for entry in index['docs']:
        if entry['location'].endswith('#course-information'):
            codes = dict.fromkeys(re.findall(r'[A-Z]{2,8}\d{4}[A-Z]{1,3}\d?', entry['text']))
            entry['text'] = ' '.join(codes) + ' ' + entry['text']
    path.write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')))
