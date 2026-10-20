import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

spec = importlib.util.spec_from_file_location('sections', Path(__file__).resolve().parents[1] / 'hooks/empty_sections.py')
sections = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sections)


class EmptySectionsTests(unittest.TestCase):
    def test_empty_parent_and_children_hide_but_anchors_survive(self):
        source = '<h1>课程</h1><h2 id="empty">课程内容</h2><h3 id="outline">课程大纲</h3><!--填写区--><style>p{color:red}</style><h2 id="links">资料</h2><p><a href="/notes">笔记</a></p>'
        result, hidden = sections.hide_empty(source)
        self.assertEqual(hidden, {'empty', 'outline'})
        self.assertNotIn('<h2 id="empty">', result)
        self.assertIn('id="empty" aria-hidden', result)
        self.assertIn('<!--填写区-->', result)
        self.assertIn('<h2 id="links">资料</h2><p><a href="/notes">笔记</a></p>', result)

    def test_parent_with_child_and_nontext_material_are_kept(self):
        for content in ['<img src="a.png">', '<object data="a.pdf"></object>', '<table><tr><td>1</td></tr></table>', '<details><summary>大纲</summary>正文</details>', '<p>待补充，欢迎投稿</p>', '<script type="math/tex">x^2</script>']:
            source = '<h2 id="parent">课程资源</h2><h3 id="child">笔记</h3>' + content
            self.assertEqual(sections.hide_empty(source), (source, set()))

    def test_toc_removes_only_hidden_sections(self):
        empty = SimpleNamespace(id='empty', children=[])
        kept = SimpleNamespace(id='kept', children=[])
        page = SimpleNamespace(toc=SimpleNamespace(items=[empty, kept]))
        result = sections.on_page_content('<h2 id="empty">空栏</h2><h2 id="kept">资料</h2><p>原文</p>', page)
        self.assertEqual(page.toc.items, [kept])
        self.assertIn('原文', result)


if __name__ == '__main__':
    unittest.main()
