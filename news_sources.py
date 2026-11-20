"""Source-specific parsing for public news transports; no article-body crawling."""
import re
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit


def publisher_matches(url: str, domain: str) -> bool:
    """Check publisher metadata by hostname, never by title or substring."""
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower()
        return (parsed.scheme == 'https' and not parsed.username and not parsed.password
                and parsed.port in (None, 443)
                and (host == domain or host.endswith('.' + domain)))
    except (TypeError, ValueError):
        return False


class TreasuryPressParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_main = False
        self.divs = []
        self.headline = False
        self.current = None
        self.entries = []
        self.seen = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'main':
            self.in_main = True
        if not self.in_main:
            return
        if tag == 'div':
            self.divs.append({'published': None})
        elif tag == 'time' and self.divs:
            value = attrs.get('datetime', '')
            try:
                parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
                self.divs[-1]['published'] = value if parsed.tzinfo is not None else None
            except ValueError:
                self.divs[-1]['published'] = None
        elif tag == 'h3':
            self.headline = 'featured-stories__headline' in (attrs.get('class') or '').split()
        elif tag == 'a' and self.headline and self.divs:
            url = urljoin('https://home.treasury.gov', attrs.get('href') or '')
            try:
                parsed = urlsplit(url)
                valid = (parsed.hostname == 'home.treasury.gov'
                         and publisher_matches(url, 'home.treasury.gov')
                         and re.fullmatch(r'/news/press-releases/(?!statements-remarks/?$)[a-zA-Z0-9][a-zA-Z0-9-]*/?', parsed.path))
            except ValueError:
                valid = False
            if valid and self.divs[-1]['published']:
                self.current = {'link': 'https://home.treasury.gov' + parsed.path.rstrip('/'),
                                'published': self.divs[-1]['published'], 'parts': []}

    def handle_data(self, data):
        if self.current is not None:
            self.current['parts'].append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.current is not None:
            item = self.current
            title = ' '.join(''.join(item['parts']).split())
            if title and item['link'] not in self.seen:
                self.entries.append({'title': title, 'summary': '', 'link': item['link'],
                                     'published': item['published']})
                self.seen.add(item['link'])
            self.current = None
        elif tag == 'h3':
            self.headline = False
            self.current = None
        elif tag == 'div' and self.divs:
            self.divs.pop()
        elif tag == 'main':
            self.in_main = False
            self.current = None
            self.divs.clear()


def treasury_entries(payload: bytes) -> list[dict]:
    parser = TreasuryPressParser()
    parser.feed(payload.decode('utf-8-sig'))
    parser.close()
    if not parser.entries:
        raise ValueError('Treasury press-release listing not found or missing publication dates')
    return parser.entries
