"""Cross-language coverage and byte/behavior parity, loaded by test-build.py.

Identifier correspondence is inferred from the actual Python ASTs, not trusted
from a translation report. Only display strings may differ beyond identifiers.
"""
from collections import Counter
from contextlib import redirect_stdout
import io
import json
import re
import unittest

from bs4 import BeautifulSoup
import build
from curriculum_test_cases import execute, implementations, validator_failures
from test_sdk_examples import SDKExampleTests


from bilingual_test_cases import correspondence, renamed


def documents():
    sources = build.read_sources(build.ROOT)
    outputs = {'pt-BR': 'index.html', 'en': 'index-en.html'}
    docs = {locale: BeautifulSoup(build.render_book(locale, sources, outputs)[1], 'html.parser')
            for locale in outputs}
    return sources, docs


class BilingualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources, cls.docs = documents()

    def test_complete_matching_curriculum_and_navigation(self):
        pt, en = self.docs['pt-BR'], self.docs['en']
        self.assertEqual(en.html['lang'], 'en')
        expected = [f'aula-{m}-{n}' for m, count in ((0, 4), (1, 13), (2, 4)) for n in range(1, count + 1)]
        for doc in (pt, en):
            self.assertEqual([a['id'] for a in doc.select('article.lesson')], expected)
            self.assertEqual(len(doc.select('.module-references')), 3)
            self.assertEqual(len(doc.select('.module-divider > .module-opening')), 3)
            self.assertEqual([o['value'] for o in doc.select('#book-language option:not([disabled])')], ['pt-BR', 'en'])
        for attribute in ('id', 'data-exercise-id', 'data-progress-id', 'data-validator', 'data-question'):
            self.assertEqual(Counter(n[attribute] for n in pt.select(f'[{attribute}]')),
                             Counter(n[attribute] for n in en.select(f'[{attribute}]')), attribute)
        for selector in ('article.lesson', '.module-references'):
            for p, e in zip(pt.select(selector), en.select(selector)):
                with self.subTest(section=p['id']):
                    for child in ('h3', 'h4', 'li', 'table tr', 'figure', 'figcaption',
                                  '.activity', '.answer', '.quiz-question', '.quiz-option',
                                  'svg text', 'svg tspan', 'svg title', 'svg desc', 'pre'):
                        self.assertEqual(len(p.select(child)), len(e.select(child)), child)
                    self.assertEqual([a['href'] for a in p.select('a[href]')],
                                     [a['href'] for a in e.select('a[href]')])
                    for q, r in zip(p.select('input, select, option'), e.select('input, select, option')):
                        for key in ('type', 'value', 'data-correct', 'data-accept', 'name', 'multiple'):
                            self.assertEqual(q.get(key), r.get(key), key)

    def test_diagram_geometry_and_runtime_are_shared(self):
        pt, en = self.docs['pt-BR'], self.docs['en']
        def geometry(doc):
            return [(el.name, {key: value for key, value in el.attrs.items()
                              if key not in ('aria-label', 'title')})
                    for svg in doc.select('article.lesson svg') for el in [svg, *svg.find_all(True)]]
        self.assertEqual(geometry(pt), geometry(en))
        for source in ('shared/app.js', 'shared/styles.css'):
            for locale, doc in self.docs.items():
                self.assertIn(self.sources[source], str(doc), (source, locale))

    def test_ui_dictionary_and_module_openings(self):
        pt = json.loads(self.sources['content/pt-BR/ui.json'])
        en = json.loads(self.sources['content/en/ui.json'])
        self.assertEqual(pt.keys(), en.keys())
        self.assertTrue(all(isinstance(v, str) and v.strip() for v in en.values()))
        for locale, doc in self.docs.items():
            self.assertEqual(json.loads(doc.select_one('#book-ui').string),
                             json.loads(self.sources[f'content/{locale}/ui.json']))
            for module in build.book_config(locale, self.sources)['modules']:
                divider = doc.select_one('#modulo-' + str(module['id']))
                opening = divider.select_one('.module-opening')
                self.assertEqual(opening.get_text(), module['summary'])
                self.assertLessEqual(len(opening.get_text().split()), 65)
                self.assertFalse(opening.select('li, ul, ol'))
                self.assertEqual(divider.h2.find_next_sibling(), opening)
                self.assertEqual(opening.find_next_sibling().name, 'nav')

    def test_english_lesson_closings_and_editorial_cleanup(self):
        en = self.docs['en']
        for article in en.select('article.lesson'):
            closing, bridge = article.select_one('.closing'), article.select_one('.bridge')
            self.assertEqual(closing.h3.get_text(), 'What we learned')
            self.assertEqual(bridge.h3.get_text(), 'To continue' if article['id'] == 'aula-2-4' else 'Next lesson')
        markers = re.compile(r'\b(?:(?-i:TODO)|FIXME|meta[- ]?instructions?|meta[- ]?instruções|translate this|as an AI|como uma IA)\b', re.I)
        for locale, original in self.docs.items():
            doc = BeautifulSoup(str(original), 'html.parser')
            for node in doc.select('script, style'):
                node.decompose()
            text = doc.get_text(' ', strip=True)
            self.assertIsNone(markers.search(text), locale)
            self.assertNotIn('\u2014', text, locale)

    def test_all_python_and_validator_semantics_preserve_data(self):
        pt, en = self.docs['pt-BR'], self.docs['en']
        for p in pt.select('pre[data-exercise-id]'):
            identity = p['data-exercise-id']
            e = en.select_one(f'pre[data-exercise-id="{identity}"]')
            with self.subTest(exercise=identity), redirect_stdout(io.StringIO()):
                for attribute in ('data-exercise-version', 'data-python-runner',
                                  'data-python-package', 'data-python-packages'):
                    self.assertEqual(p.get(attribute), e.get(attribute), attribute)
                mapping = correspondence(p.code.get_text(), e.code.get_text())
                execute(e.code.get_text(), 'en:' + identity)
                if p.get('data-validator'):
                    pt_tests = json.loads(pt.find(id=p['data-validator']).string)['tests']
                    en_tests = json.loads(en.find(id=e['data-validator']).string)['tests']
                    self.assertEqual(len(pt_tests), len(en_tests))
                    for a, b in zip(pt_tests, en_tests):
                        correspondence(a['code'], b['code'], mapping)
                    repair, mutations = implementations(identity, p.code.get_text())
                    self.assertTrue(validator_failures(e.code.get_text(), en_tests, identity), 'broken starter passed')
                    self.assertEqual(validator_failures(renamed(repair, mapping), en_tests, identity), [])
                    for mutation in mutations:
                        self.assertTrue(validator_failures(renamed(mutation, mapping), en_tests, identity),
                                        'incorrect repair passed')


class EnglishSDKTests(SDKExampleTests):
    """Run the SDK's semantic evidence checks against the actual English code."""
    @classmethod
    def setUpClass(cls):
        cls.sources, docs = documents()
        cls.doc, cls.portuguese = docs['en'], docs['pt-BR']
        cls.fixture = json.loads((build.ROOT / 'sdk_example_fixtures.json').read_text())

    def example(self, identity, repair=False):
        pt = self.portuguese.select_one(f'pre[data-exercise-id="{identity}"] code').get_text()
        en = self.doc.select_one(f'pre[data-exercise-id="{identity}"] code').get_text()
        mapping = correspondence(pt, en)
        source = renamed(implementations(identity, pt)[0], mapping) if repair else en
        with redirect_stdout(io.StringIO()):
            namespace = execute(source, 'en:' + identity)
        # Test-only aliases allow the existing SDK assertions to inspect the
        # translated variables. These aliases are never shipped to the learner.
        return {**namespace, **{old: namespace[new] for old, new in mapping.items() if new in namespace}}

    def test_shelley_address_components_match_cip19_vectors(self):
        values = self.example('shelley-address-components')
        base, enterprise, reward = (values[k] for k in ('endereco_base', 'endereco_enterprise', 'endereco_reward'))
        self.assertEqual(enterprise.encode(), 'addr_test1vz2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzerspjrlsz')
        self.assertEqual(reward.encode(), 'stake_test1uqehkck0lajq8gr28t9uxnuvgcqrc6070x3k9r8048z8y5gssrtvn')
        self.assertEqual(base.payment_part, enterprise.payment_part)
        self.assertEqual(base.staking_part, reward.staking_part)
        self.assertIsNone(enterprise.staking_part)
        self.assertIsNone(reward.payment_part)
        for address, header, size in ((base, 0x00, 57), (enterprise, 0x60, 29), (reward, 0xe0, 29)):
            self.assertEqual((bytes(address)[0], len(bytes(address)), address.network.name), (header, size, 'TESTNET'))
