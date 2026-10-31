from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/kaoyan-408'
SIX = ('kaoyan-408-tutor', 'kaoyan-error-loop-coach', 'kaoyan-mock-exam-coach',
       '408-error-diagnosis', '408-concept-followup', '408-calculation-check')
THREE = SIX[3:]
SHARED = ROOT / 'src/shared/references/knowledge-point-basis.md'
CONTRACT = PLUGIN / 'references/knowledge-point-basis-contract.md'
spec = importlib.util.spec_from_file_location('knowledge_cards_contract_test', ROOT / 'src/shared/calculation/knowledge_cards.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def contract_errors(text: str, kind: str) -> list[str]:
    """Checks explicitly written contract anchors, not the model's behavior."""
    errors = []
    if 'scripts/knowledge_cards.py --mode explain --id <已匹配ID>' not in text:
        errors.append('missing explain integration')
    if kind == 'shared':
        checks = {
            'protected modes': '仅提示、独立作答和冻结模考未交卷时',
            'no id': '不为当前保留答案查询或传递精确 ID',
            'no worked solutions': '不读取含例题解析的卡片',
            'safe no id': '且不传 `--id`',
            'unavailable is honest': '如实说明未取得脚本输出',
            'no fabricated success': '不声称读取或核验成功',
        }
    elif kind == 'contract':
        checks = {
            'protected modes': '仅提示、独立作答、未交卷时',
            'no id': '不得传入精确 ID',
            'no worked solutions': '读取含解析的卡',
            'safe no id': '不带 ID',
            'unavailable is honest': '诚实降级',
            'no fabricated success': '不能声称已读取卡或核验成功',
        }
    else:
        checks = {'unavailable is honest': '脚本不可用', 'contract handoff': '契约' if kind != 'new' else '依据规则说明降级'}
        if kind == 'mock':
            checks.update({'post-submit only': '明确交卷后', 'no id/solution': '未交卷不传 ID、不读取含解析卡'})
        elif kind == 'loop':
            checks.update({'completed question': '已完成题', 'no id/solution': '复测作答前不得传 ID 或读取含解析的卡'})
        else:
            checks.update({'protected': '仅提示、独立作答', 'no id/solution': '不得传' if kind == 'new' else '不得传 ID 或读取含解析的卡'})
        if kind == 'new':
            checks['no fabricated success'] = '不虚构已读或核验'
    errors.extend(label for label, marker in checks.items() if marker not in text)
    # Explicit unsafe calls or claims invalidate the contract even if a safe sentence remains.
    if re.search(r'--mode\s+(?:hint|independent|exam)\s+--id(?:\s|=)', text):
        errors.append('protected mode sends id')
    if re.search(r'未交卷时(?:仍|也)?(?:调用|读取).*?(?:--mode explain|含解析)', text):
        errors.append('exam reads solutions')
    if re.search(r'脚本不可用时(?:仍|也)?(?:声称|报告).*?(?:已读取|核验成功)', text):
        errors.append('unavailable claims success')
    return errors


class KnowledgeReaderContractTests(unittest.TestCase):
    def test_all_seventeen_entries_and_six_integrations(self):
        skills = {p.parent.name for p in (PLUGIN / 'skills').glob('*/SKILL.md')}
        self.assertEqual(len(skills), 17)
        self.assertTrue(set(SIX) <= skills)
        for skill in skills:
            text = (PLUGIN / 'skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
            findings = contract_errors(text, 'other')
            with self.subTest(all_entries=skill):
                self.assertNotIn('protected mode sends id', findings)
                self.assertNotIn('exam reads solutions', findings)
                self.assertNotIn('unavailable claims success', findings)
        for skill in SIX:
            text = (PLUGIN / 'skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
            kind = 'mock' if skill == SIX[2] else 'loop' if skill == SIX[1] else 'new' if skill in THREE else 'tutor'
            with self.subTest(skill=skill):
                self.assertEqual(contract_errors(text, kind), [])
        for skill in THREE:
            text = (ROOT / 'src/skills' / skill / 'SKILL.md').read_text(encoding='utf-8')
            with self.subTest(source=skill):
                self.assertEqual(contract_errors(text, 'new'), [])
        self.assertEqual(contract_errors(SHARED.read_text(encoding='utf-8'), 'shared'), [])
        self.assertEqual(contract_errors(CONTRACT.read_text(encoding='utf-8'), 'contract'), [])

    def test_contract_mutations_are_rejected(self):
        shared = SHARED.read_text(encoding='utf-8')
        cases = {
            'missing explain integration': shared.replace('scripts/knowledge_cards.py --mode explain --id <已匹配ID>', 'scripts/knowledge_cards.py'),
            'protected mode sends id': shared + '\n运行 --mode hint --id DS-ALG-001。\n',
            'exam reads solutions': shared + '\n未交卷时读取含解析的知识卡。\n',
            'unavailable claims success': shared + '\n脚本不可用时声称已读取卡并核验成功。\n',
        }
        for expected, mutant in cases.items():
            with self.subTest(mutant=expected):
                self.assertIn(expected, contract_errors(mutant, 'shared'))
        mock = (PLUGIN / 'skills/kaoyan-mock-exam-coach/SKILL.md').read_text(encoding='utf-8')
        self.assertIn('no id/solution', contract_errors(mock.replace('未交卷不传 ID、不读取含解析卡', '未交卷可读卡'), 'mock'))

    def test_protected_modes_cannot_touch_any_file(self):
        # Even a nonexistent or sensitive root cannot be probed in protected modes.
        with patch.object(Path, 'read_text', side_effect=AssertionError('read attempted')), \
             patch.object(Path, 'resolve', side_effect=AssertionError('resolve attempted')), \
             patch.object(Path, 'is_file', side_effect=AssertionError('stat attempted')), \
             patch.object(Path, 'is_symlink', side_effect=AssertionError('symlink check attempted')):
            for mode in ('hint', 'independent', 'exam'):
                with self.subTest(mode=mode):
                    result = reader.project(mode, None, Path('unavailable'))
                    self.assertEqual(result['status'], 'details-deferred')
                    with self.assertRaises(ValueError):
                        reader.project(mode, 'DS-ALG-001', Path('unavailable'))


if __name__ == '__main__':
    unittest.main()
