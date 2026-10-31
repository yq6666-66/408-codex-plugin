"""Contract tests for the active 2027 third-party outline mappings."""
import copy
import json
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]

class CurrentMappingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = json.loads((ROOT / 'src/shared/references/kp-408.json').read_text(encoding='utf8'))
        schema = json.loads((ROOT / 'schemas/kp-408.schema.json').read_text(encoding='utf8'))
        cls.validator = Draft202012Validator(schema, format_checker=FormatChecker())

    def test_sixty_stable_points_and_scope_are_explicit(self):
        self.validator.validate(self.index)
        points = self.index['knowledgePoints']
        self.assertEqual(len(points), 60)
        self.assertEqual(len({p['id'] for p in points}), 60)
        self.assertEqual(sum(p['mappingStatus'] == 'direct' for p in points), 9)
        self.assertEqual(sum(p['mappingStatus'] == 'upper-topic' for p in points), 51)
        for p in points:
            self.assertEqual(p['basisYear'], '2027')
            self.assertEqual(p['source']['kind'], 'third-party-outline')
            self.assertEqual(p['source']['sha256Scope'], 'normalized-article-text-v1')
            self.assertEqual(p['knowledgeCard'], 'knowledge-cards/' + p['id'] + '.json')
            self.assertTrue(p['mappingNote'])

    def test_scope_source_and_card_escape_are_rejected(self):
        for change in ({'mappingStatus': 'upper-topic', 'verified': False},
                       {'mappingStatus': 'direct', 'source': None},
                       {'knowledgeCard': '../private.json'}, {'mappingNote': ' '}):
            with self.subTest(change=change):
                data = copy.deepcopy(self.index)
                data['knowledgePoints'][0].update(change)
                self.assertFalse(self.validator.is_valid(data))
        data = copy.deepcopy(self.index)
        del data['knowledgePoints'][0]['source']['sha256Scope']
        self.assertFalse(self.validator.is_valid(data))
        data = copy.deepcopy(self.index)
        data['knowledgePoints'][0]['source']['kind'] = 'exam-authority'
        self.assertFalse(self.validator.is_valid(data))
        for url in ('https://www.csgraduates.com/study_methods/outline/2027/?view=full',
                    'https://WWW.CSGRADUATES.COM/study_methods/outline/2027/#section',
                    'https://other.example.edu/independent-syllabus'):
            for kind in ('exam-authority', 'official-repost'):
                with self.subTest(url=url, kind=kind):
                    data = copy.deepcopy(self.index)
                    data['knowledgePoints'][0]['source'].update({'reference': url, 'kind': kind})
                    self.assertFalse(self.validator.is_valid(data))

if __name__ == '__main__':
    unittest.main()
