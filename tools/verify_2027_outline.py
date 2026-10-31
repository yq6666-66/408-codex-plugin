"""Recheck the 2027 third-party outline mapping against actual article text.

Use --html for a saved source file or --fetch for a live read. No source text is
persisted or republished. Hash normalization: td-content data nodes excluding
script/style, collapse each node's whitespace, omit empty nodes, join with LF,
UTF-8 encode, then SHA-256. Navigation outside td-content is excluded.
"""
from __future__ import annotations
import argparse
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unicodedata
from urllib.request import urlopen

URL = 'https://www.csgraduates.com/study_methods/outline/2027/'
ROOT = Path(__file__).resolve().parents[1]
SUBJECTS = {'数据结构', '计算机组成原理', '操作系统', '计算机网络'}

class OutlineParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.skip = False
        self.heading = None
        self.subject = None
        self.chapter = None
        self.parts = []
        self.entries = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'div' and not self.depth and attrs.get('class') == 'td-content':
            self.depth = 1
        elif self.depth and tag == 'div':
            self.depth += 1
        if self.depth and tag in ('script', 'style'):
            self.skip = True
        if self.depth and tag in ('h3', 'h4'):
            self.heading = tag

    def handle_endtag(self, tag):
        if tag == self.heading:
            self.heading = None
        if tag in ('script', 'style'):
            self.skip = False
        if self.depth and tag == 'div':
            self.depth -= 1

    def handle_data(self, value):
        if not self.depth or self.skip or not value.strip():
            return
        value = ' '.join(value.split())
        self.parts.append(value)
        if self.heading == 'h3' and value in SUBJECTS:
            self.subject, self.chapter = value, None
        if self.heading == 'h4':
            self.chapter = value
        self.entries.append((self.subject, self.chapter, value))


def normalize_match(value):
    return re.sub(r'[^\w\u4e00-\u9fff]+', '', unicodedata.normalize('NFKC', value)).casefold()


def verify(html, index):
    parser = OutlineParser()
    parser.feed(html)
    if not parser.parts:
        raise ValueError('outline article was not found')
    digest = hashlib.sha256('\n'.join(parser.parts).encode('utf-8')).hexdigest()
    errors = []
    for point in index['knowledgePoints']:
        if not point['verified']:
            continue
        source = point['source']
        if source['kind'] != 'third-party-outline' or source['sha256Scope'] != 'normalized-article-text-v1':
            errors.append(point['id'] + ': unexpected source scope')
            continue
        if source['sha256'] != digest:
            errors.append(point['id'] + ': article digest differs')
        subject, chapter, topic = point['syllabusPath']
        if point['id'] == 'CN-TRANS-001' and (point['syllabusPath'] != ['计算机网络', '五、传输层', 'UDP 数据报']
                or point.get('mappingStatus') != 'upper-topic' or source.get('mappingScope') != 'upper-topic'):
            errors.append(point['id'] + ': expected the UDP datagram partial-topic locator')
        if source['locator'] != f'{subject} / {chapter} / {topic}' or point['subject'] != subject:
            errors.append(point['id'] + ': inconsistent locator')
        if not any(s == subject and c == chapter and normalize_match(topic) in normalize_match(text)
                   for s, c, text in parser.entries):
            errors.append(point['id'] + ': locator not present in article')
    return {'valid': not errors, 'sourceKind': 'third-party-outline', 'sha256Scope': 'normalized-article-text-v1',
            'articleSha256': digest, 'entries': len(index['knowledgePoints']), 'errors': errors}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    source = cli.add_mutually_exclusive_group(required=True)
    source.add_argument('--html', type=Path)
    source.add_argument('--fetch', action='store_true')
    args = cli.parse_args()
    html = urlopen(URL, timeout=30).read().decode('utf-8') if args.fetch else args.html.read_text(encoding='utf-8')
    index = json.loads((ROOT / 'src/shared/references/kp-408.json').read_text(encoding='utf-8'))
    result = verify(html, index)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['valid'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
