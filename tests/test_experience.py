"""Prevent restoring excluded references or an explicitly anonymous byline."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ExperiencePermissionsTests(unittest.TestCase):
    def test_excluded_references_are_not_published(self):
        excluded = ('5571498', '5739793', '5800325', '5873243', '5935779',
                    '5940420', '5959808', '6135930', '6226730', '6301566',
                    '6623542', '6625464', '6635907')
        pattern = re.compile(r'cc98\.org/topic/(?:' + '|'.join(excluded) + r')(?!\d)')
        for page in (ROOT / 'docs').rglob('*.md'):
            self.assertIsNone(pattern.search(page.read_text()), str(page))

    def test_anonymous_credit_keeps_only_the_original_post_link(self):
        page = ROOT / 'docs/experience/posts/6152341.md'
        text = page.read_text()
        self.assertIn('匿名作者', text)
        self.assertIn('https://www.cc98.org/topic/6152341', text)
        for source in (ROOT / 'docs/experience').rglob('*.md'):
            self.assertNotIn('Baryouu', source.read_text(), str(source))


if __name__ == '__main__':
    unittest.main()
