"""Analytics must remain optional for every page feature."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/javascripts/web-analytics.js'


class WebAnalyticsTests(unittest.TestCase):
    def test_public_site_token_is_configured(self):
        token = re.search(r'const token = "([^"]*)";', SOURCE.read_text()).group(1)
        self.assertRegex(token, r'^[a-f0-9]{32}$')

    @unittest.skipUnless(shutil.which('node'), 'Node.js is required for JavaScript checks')
    def test_delayed_loading_preview_isolation_and_failure(self):
        result = subprocess.run(['node', '-e', r'''
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const code = fs.readFileSync(process.argv[1], 'utf8')
  .replace(/const token = "[^"]*";/, 'const token = "0123456789abcdef0123456789abcdef";');
function page(hostname, readyState) {
  const scripts = [], events = [], body = {content:'course content'};
  const context = {location:{hostname}, document:{readyState, body,
    createElement:tag => ({tag, dataset:{}, remove(){this.removed=true;}}),
    head:{appendChild:script => scripts.push(script)}},
    window:{addEventListener:(type, callback, options) => events.push({type,callback,options})}};
  vm.runInNewContext(code, context);
  return {scripts,events,body};
}
for (const hostname of ['localhost','127.0.0.1','example.org','zjusuee.github.io.example.org']) {
  const preview = page(hostname, 'complete');
  assert.equal(preview.scripts.length,0);
  assert.equal(preview.events.length,0);
}
const loading = page('zjusuee.github.io','loading');
assert.equal(loading.scripts.length,0);
assert.equal(loading.events.length,1);
assert.equal(loading.events[0].type,'load');
assert.equal(loading.events[0].options.once,true);
loading.events[0].callback();
const beacon = loading.scripts[0];
assert.equal(beacon.type,'module');
assert.equal(beacon.async,true);
assert.equal(beacon.src,'https://static.cloudflareinsights.com/beacon.min.js');
assert.equal(JSON.parse(beacon.dataset.cfBeacon).token,'0123456789abcdef0123456789abcdef');
beacon.onerror();
assert.equal(beacon.removed,true);
assert.deepEqual(loading.body,{content:'course content'});
const loaded = page('zjusuee.github.io','complete');
assert.equal(loaded.scripts.length,1);
assert.equal(loaded.events.length,0);
''', str(SOURCE)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
