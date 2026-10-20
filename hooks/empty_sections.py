"""Hide empty sections while keeping source placeholders and existing anchors."""
from html import escape
from html.parser import HTMLParser
import re


class Sections(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.lines = [0] + [m.end() for m in re.finditer('\n', source)]
        self.sections = []
        self.heading = False
        self.ignored = 0

    def position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        if tag == 'script' and dict(attrs).get('type', '').startswith('math/') and self.sections:
            self.sections[-1]['body'] = True
        if tag in {'style', 'script'}:
            self.ignored += 1
        if re.fullmatch(r'h[1-6]', tag):
            self.sections.append(dict(level=int(tag[1]), start=self.position(),
                                      id=dict(attrs).get('id'), body=False))
            self.heading = True
        elif not self.heading and not self.ignored and self.sections:
            if tag in {'img', 'object', 'embed', 'iframe', 'table', 'video', 'audio', 'svg', 'math'}:
                self.sections[-1]['body'] = True

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag):
        if re.fullmatch(r'h[1-6]', tag) and self.heading:
            self.sections[-1]['end'] = self.source.index('>', self.position()) + 1
            self.heading = False
        if tag in {'style', 'script'}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, data):
        if not self.heading and not self.ignored and self.sections and data.strip():
            self.sections[-1]['body'] = True


def hide_empty(source):
    parser = Sections(source)
    parser.feed(source)
    sections = parser.sections
    hidden = []
    for i, section in enumerate(sections):
        end = next((j for j in range(i + 1, len(sections))
                    if sections[j]['level'] <= section['level']), len(sections))
        if section['level'] > 1 and not any(s['body'] for s in sections[i:end]):
            hidden.append(section)
    for section in reversed(hidden):
        anchor = f'<span id="{escape(section["id"], quote=True)}" aria-hidden="true"></span>' if section['id'] else ''
        source = source[:section['start']] + anchor + source[section['end']:]
    return source, {s['id'] for s in hidden if s['id']}


def on_page_content(html, page, **kwargs):
    html, hidden = hide_empty(html)
    def retain(items):
        for item in items:
            item.children = retain(item.children)
        return [item for item in items if item.id not in hidden]
    page.toc.items = retain(page.toc.items)
    return html
