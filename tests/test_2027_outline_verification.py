"""Check third-party outline provenance without a network dependency."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('verify_2027_outline', ROOT / 'tools/verify_2027_outline.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class OutlineVerificationTests(unittest.TestCase):
    def setUp(self):
        self.body = '<div class="td-content"><h3>数据结构</h3><h4>六、查找</h4><p>折半查找法</p></div>'
        parser = module.OutlineParser()
        parser.feed(self.body)
        digest = hashlib.sha256('\n'.join(parser.parts).encode('utf8')).hexdigest()
        self.index = {'knowledgePoints': [{'id': 'DS-SEARCH-003', 'subject': '数据结构',
            'verified': True, 'syllabusPath': ['数据结构', '六、查找', '折半查找法'],
            'source': {'kind': 'third-party-outline', 'sha256Scope': 'normalized-article-text-v1',
                       'sha256': digest, 'locator': '数据结构 / 六、查找 / 折半查找法'}}]}

    def test_navigation_changes_do_not_change_article_digest(self):
        a = module.verify('<nav>old</nav>' + self.body, self.index)
        b = module.verify('<nav>completely different</nav>' + self.body, self.index)
        self.assertTrue(a['valid'])
        self.assertTrue(b['valid'])
        self.assertEqual(a['articleSha256'], b['articleSha256'])

    def test_changed_body_or_locator_is_not_promoted_to_verified(self):
        changed = module.verify(self.body.replace('折半查找法', '顺序查找法'), self.index)
        self.assertFalse(changed['valid'])
        bad = copy.deepcopy(self.index)
        bad['knowledgePoints'][0]['syllabusPath'][2] = '未列出内容'
        bad['knowledgePoints'][0]['source']['locator'] = '数据结构 / 六、查找 / 未列出内容'
        self.assertFalse(module.verify(self.body, bad)['valid'])

    def test_transport_mapping_requires_udp_datagram_partial_locator(self):
        body = '<div class="td-content"><h3>计算机网络</h3><h4>五、传输层</h4><p>传输层提供的服务</p><p>UDP 数据报</p></div>'
        parser = module.OutlineParser()
        parser.feed(body)
        digest = hashlib.sha256('\n'.join(parser.parts).encode('utf8')).hexdigest()
        point = {'id': 'CN-TRANS-001', 'subject': '计算机网络', 'verified': True,
            'syllabusPath': ['计算机网络', '五、传输层', 'UDP 数据报'],
            'mappingStatus': 'upper-topic', 'source': {'kind': 'third-party-outline',
            'sha256Scope': 'normalized-article-text-v1', 'sha256': digest,
            'locator': '计算机网络 / 五、传输层 / UDP 数据报', 'mappingScope': 'upper-topic'}}
        self.assertTrue(module.verify(body, {'knowledgePoints': [point]})['valid'])
        previous = copy.deepcopy(point)
        previous['syllabusPath'][2] = '传输层提供的服务'
        previous['source']['locator'] = '计算机网络 / 五、传输层 / 传输层提供的服务'
        self.assertFalse(module.verify(body, {'knowledgePoints': [previous]})['valid'])
        promoted = copy.deepcopy(point)
        promoted['mappingStatus'] = 'direct'
        self.assertFalse(module.verify(body, {'knowledgePoints': [promoted]})['valid'])

if __name__ == '__main__':
    unittest.main()
