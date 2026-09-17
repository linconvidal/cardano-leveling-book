# /// script
# dependencies = [
#   "Jinja2==3.1.6", "PyYAML==6.0.3", "beautifulsoup4==4.14.3", "cryptography==50.0.1",
#   "pycardano==0.19.2", "cbor2==5.9.0", "cbor2pure==5.8.0",
#   "pynacl==1.6.2", "pydantic==2.12.5", "ogmios==1.4.3", "orjson==3.11.8",
# ]
# ///
"""Build checks; --baseline ZIP additionally audits the original manuscript."""
import argparse
from contextlib import contextmanager, redirect_stdout
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.dont_write_bytecode = True
import build
from bs4 import BeautifulSoup
import yaml
from test_curriculum import CurriculumTests
from test_sdk_examples import SDKExampleTests
from test_bilingual import BilingualTests, EnglishSDKTests

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--baseline', type=Path)
args, remaining = parser.parse_known_args()
PREFIX = 'content/pt-BR/'
# Structural/fail-closed tests deliberately start from a Portuguese-only fixture.
# The complete, real two-language curriculum is checked separately in test_bilingual.py.
SOURCES = {name: text for name, text in build.read_sources(build.ROOT).items()
           if name.startswith(('shared/', PREFIX))}


def english_fixture():
    """Synthetic locale, never written to the actual book sources or published."""
    data = {k: v for k, v in SOURCES.items() if k.startswith('shared/')}
    book = dict(language='en', title='English fixture', output='english.html',
                modules=[dict(id='0', title='Example module', summary='Fixture only.')])
    data['content/en/book.yaml'] = yaml.safe_dump(book)
    data['content/en/ui.json'] = json.dumps({key: 'EN / ' + key for key in json.loads(SOURCES[PREFIX + 'ui.json'])})
    data['content/en/intro.html'] = '<section id="capa"><h1>{{ book.title }}</h1></section>'
    data['content/en/references-0.html'] = '<section id="referencias-modulo-0">References</section>'
    data['content/en/aula-0-1.html'] = '---\ntitle: First lesson\nmap_title: First\nsummary: Example summary\n---\n<p>Literal {{ code_expression }} is not a template.</p>\n'
    return data


@contextmanager
def temporary_book(sources):
    root = Path(tempfile.mkdtemp(prefix='book-build-test-'))
    try:
        for name, text in sources.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        with patch.object(build, 'ROOT', root), redirect_stdout(io.StringIO()):
            yield root
    finally:
        subprocess.run(['gio', 'trash', str(root)], check=True)


class BuildTests(unittest.TestCase):
    def test_deterministic_portable_output(self):
        first = build.render_book('pt-BR', SOURCES)
        self.assertEqual(first, build.render_book('pt-BR', SOURCES))
        name, data, count = first
        self.assertEqual((name, count), ('index.html', 21))
        self.assertTrue(build.is_generated(data))
        doc = BeautifulSoup(data, 'html.parser')
        self.assertEqual(len(doc.select('article.lesson')), count)
        self.assertIn(SOURCES['shared/app.js'], data.decode())
        self.assertIn(SOURCES['shared/styles.css'], data.decode())
        self.assertFalse(doc.select('script[src^="shared/"]'))

    def test_every_lesson_ends_with_takeaways_and_next_lesson(self):
        _, data, _ = build.render_book('pt-BR', SOURCES)
        lessons = BeautifulSoup(data, 'html.parser').select('article.lesson')
        for lesson in lessons:
            with self.subTest(lesson=lesson['id']):
                self.assertEqual(len(lesson.select(':scope > .closing')), 1)
                self.assertEqual(len(lesson.select(':scope > .bridge')), 1)
                closing, bridge = lesson.find_all(recursive=False)[-2:]
                self.assertIn('closing', closing.get('class', []))
                self.assertIn('bridge', bridge.get('class', []))
                self.assertEqual(closing.h3.get_text(strip=True), 'O que aprendemos')
                self.assertEqual(len(closing.select(':scope > ul')), 1)
                bullets = closing.select(':scope > ul > li')
                self.assertGreaterEqual(len(bullets), 2)
                self.assertTrue(all(item.get_text(strip=True) for item in bullets))
                expected_bridge = 'Para continuar' if lesson is lessons[-1] else 'Próxima aula'
                self.assertEqual(bridge.h3.get_text(strip=True), expected_bridge)
                self.assertTrue(bridge.select('p'))
        self.assertIn('Esta é a última aula do guia.', lessons[-1].select_one('.bridge').get_text())

    def test_each_module_opens_with_its_prose_summary(self):
        _, data, _ = build.render_book('pt-BR', SOURCES)
        doc = BeautifulSoup(data, 'html.parser')
        modules = build.book_config('pt-BR', SOURCES)['modules']
        self.assertEqual(len(doc.select('.module-divider > .module-opening')), len(modules))
        for module in modules:
            divider = doc.select_one('#modulo-' + str(module['id']))
            opening = divider.select_one(':scope > .module-opening')
            self.assertEqual(opening.get_text(), module['summary'])
            self.assertEqual(divider.h2.find_next_sibling(), opening)
            self.assertEqual(opening.find_next_sibling().name, 'nav')
            self.assertLessEqual(len(opening.get_text().split()), 65)
            self.assertFalse(opening.select('ul, ol, li'))

    def test_metadata_generates_all_navigation_views(self):
        sources = SOURCES.copy()
        sources[PREFIX + 'aula-0-1.html'] = sources[PREFIX + 'aula-0-1.html'].replace('Do texto aos bytes', 'Renamed lesson', 1)
        _, data, _ = build.render_book('pt-BR', sources)
        doc = BeautifulSoup(data, 'html.parser')
        self.assertEqual(doc.select_one('#aula-0-1 .lesson-title').get_text(), 'Renamed lesson')
        for selector in ('#toc a[href="#aula-0-1"]', '#sumario a[href="#aula-0-1"] strong'):
            self.assertIn('Renamed lesson', doc.select_one(selector).get_text())
        order = [el['id'] for el in doc.select('.lesson[data-module="1"]')]
        self.assertLess(order.index('aula-1-9'), order.index('aula-1-10'))

    def test_language_isolation_without_duplicate_runtime(self):
        sources = english_fixture()
        name, data, count = build.render_book('en', sources)
        self.assertEqual((name, count), ('english.html', 1))
        doc = BeautifulSoup(data, 'html.parser')
        self.assertEqual(doc.html['lang'], 'en')
        self.assertIn('{{ code_expression }}', doc.select_one('#aula-0-1').get_text())
        self.assertEqual(json.loads(doc.select_one('#book-ui').string), json.loads(sources['content/en/ui.json']))
        self.assertIn(SOURCES['shared/app.js'], data.decode())
        with self.assertRaises(ValueError):
            build.render_book('en', SOURCES)

    def test_language_selector_only_uses_current_build(self):
        with temporary_book(SOURCES) as root:
            (root / 'index-en.html').write_text('Legacy Portuguese artifact')
            self.assertEqual(build.main([]), 0)
            doc = BeautifulSoup((root / 'index.html').read_bytes(), 'html.parser')
            selector = doc.select_one('#toc > .toc-language #book-language')
            self.assertIsNotNone(selector)
            self.assertEqual(selector['aria-label'], 'Idioma da apostila')
            portuguese = selector.select_one('option[value="pt-BR"]')
            english = selector.select_one('option[value="en"]')
            self.assertTrue(portuguese.has_attr('selected'))
            self.assertEqual(portuguese['data-output'], 'index.html')
            self.assertTrue(english.has_attr('disabled'))
            self.assertFalse(english.has_attr('data-output'))
            self.assertIn('indisponível', english.get_text())
        sources = dict(SOURCES, **english_fixture())
        with temporary_book(sources) as root:
            self.assertEqual(build.main([]), 0)
            for language, output in (('pt-BR', 'index.html'), ('en', 'english.html')):
                doc = BeautifulSoup((root / output).read_bytes(), 'html.parser')
                selector = doc.select_one('#book-language')
                self.assertEqual(selector.select_one('option[selected]')['value'], language)
                self.assertFalse(selector.select('option[disabled]'))
                self.assertEqual({n['value']: n['data-output'] for n in selector.select('option')},
                                 {'pt-BR': 'index.html', 'en': 'english.html'})
                self.assertIn('aula-0-1', selector.select_one('option[value="en"]')['data-anchors'].split())
                self.assertNotIn('aula-1-1', selector.select_one('option[value="en"]')['data-anchors'].split())
            english_before = (root / 'english.html').read_bytes()
            self.assertEqual(build.main(['--lang', 'pt-BR']), 0)
            doc = BeautifulSoup((root / 'index.html').read_bytes(), 'html.parser')
            self.assertTrue(doc.select_one('#book-language option[value="en"]').has_attr('disabled'))
            self.assertEqual((root / 'english.html').read_bytes(), english_before)

    def test_metadata_and_catalog_are_escaped(self):
        sources = english_fixture()
        sources['content/en/aula-0-1.html'] = sources['content/en/aula-0-1.html'].replace('First lesson', '<img src=x onerror=alert(1)>')
        ui = json.loads(sources['content/en/ui.json']); ui['run'] = '</script><script>alert(1)</script>'
        sources['content/en/ui.json'] = json.dumps(ui)
        _, data, _ = build.render_book('en', sources)
        doc = BeautifulSoup(data, 'html.parser')
        self.assertFalse(doc.select('.lesson-title img'))
        self.assertEqual(json.loads(doc.select_one('#book-ui').string)['run'], ui['run'])

    def test_invalid_sources_fail_closed(self):
        base = english_fixture()
        lesson = 'content/en/aula-0-1.html'
        cases = {
            'duplicate metadata': (lesson, base[lesson].replace('title: First lesson', 'title: First\ntitle: Second')),
            'unknown metadata': (lesson, base[lesson].replace('title: First lesson', 'title: First\ntypo: Second')),
            'broken link': (lesson, base[lesson] + '<a href="#missing">Broken</a>'),
            'duplicate id': (lesson, base[lesson] + '<div id="capa"></div>'),
            'missing validator': (lesson, base[lesson] + '<pre data-validator="missing-checks"></pre>'),
            'missing catalog': ('content/en/ui.json', '{}'),
            'wrong catalog shape': ('content/en/ui.json', '[]'),
            'traversal output': ('content/en/book.yaml', base['content/en/book.yaml'].replace('english.html', '../index.html')),
            'locale mismatch': ('content/en/book.yaml', base['content/en/book.yaml'].replace('language: en', 'language: pt-BR')),
        }
        for label, (name, text) in cases.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                build.render_book('en', dict(base, **{name: text}))
        with self.assertRaises(KeyError):
            build.render_book('en', {k: v for k, v in base.items() if k != 'content/en/references-0.html'})
        with self.assertRaises(ValueError):
            build.render_book('en', dict(base, **{'content/en/draft.html': '<p>Unregistered lesson</p>'}))

    def test_cli_protects_legacy_and_manual_edits(self):
        with temporary_book(english_fixture()) as root:
            output = root / 'english.html'; output.write_bytes(b'legacy work')
            untouched = root / 'index-en.html'; untouched.write_bytes(b'untracked old file')
            with self.assertRaises(ValueError): build.main([])
            self.assertEqual(output.read_bytes(), b'legacy work')
            self.assertEqual(build.main(['--adopt', build.digest(b'legacy work')]), 0)
            self.assertEqual(build.main(['--check']), 0)
            generated = output.read_bytes(); stamp = output.stat().st_mtime_ns
            self.assertEqual(build.main([]), 0)
            self.assertEqual(output.stat().st_mtime_ns, stamp)
            output.write_bytes(generated + b'\nmanual edit')
            self.assertFalse(build.is_generated(output.read_bytes()))
            with self.assertRaises(ValueError): build.main([])
            self.assertTrue(output.read_bytes().endswith(b'manual edit'))
            self.assertEqual(build.main(['--check']), 1)
            self.assertEqual(untouched.read_bytes(), b'untracked old file')

    def test_atomic_write_checks_destination(self):
        with temporary_book({}) as root:
            output = root / 'test.html'; output.write_bytes(b'another writer')
            with self.assertRaises(ValueError): build.atomic_write(output, b'new', b'old')
            self.assertEqual(output.read_bytes(), b'another writer')

    def test_selected_language_tolerates_incomplete_other_content(self):
        sources = dict(SOURCES, **english_fixture())
        del sources['content/en/aula-0-1.html']
        with temporary_book(sources) as root:
            self.assertEqual(build.main(['--lang', 'pt-BR']), 0)
            self.assertFalse((root / 'english.html').exists())

    def test_output_collisions_are_rejected_even_when_selecting_one_language(self):
        sources = dict(SOURCES, **english_fixture())
        sources['content/en/book.yaml'] = sources['content/en/book.yaml'].replace('english.html', 'index.html')
        with temporary_book(sources), self.assertRaises(ValueError): build.main(['--lang', 'pt-BR'])

    def test_site_contains_only_fresh_configured_exports(self):
        sources = dict(SOURCES, **english_fixture())
        with temporary_book(sources) as root:
            legacy = {'index.html': b'manual preview', 'index-en.html': b'not a translation',
                      'notes.txt': b'private notes', 'backup.zip': b'backup'}
            for name, data in legacy.items(): (root / name).write_bytes(data)
            self.assertEqual(build.main(['--site']), 0)
            site = root / '_site'
            self.assertEqual({p.name for p in site.iterdir()}, {'index.html', 'english.html', '.nojekyll'})
            outputs = {'pt-BR': 'index.html', 'en': 'english.html'}
            for lang in ('pt-BR', 'en'):
                name, data, _ = build.render_book(lang, sources, outputs)
                self.assertEqual((site / name).read_bytes(), data)
            self.assertEqual((site / '.nojekyll').read_bytes(), b'')
            self.assertEqual(build.read_sources(root), sources)
            for name, data in legacy.items(): self.assertEqual((root / name).read_bytes(), data)

    def test_site_refuses_existing_directory_or_symlink(self):
        with temporary_book(SOURCES) as root:
            self.assertEqual(build.main(['--site']), 0)
            sentinel = root / '_site' / 'unexpected.txt'; sentinel.write_text('preserve')
            with self.assertRaisesRegex(ValueError, '_site already exists'): build.main(['--site'])
            self.assertEqual(sentinel.read_text(), 'preserve')
            (root / '_site').rename(root / 'previous-site')
            (root / '_site').symlink_to(root / 'missing-site', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, '_site already exists'): build.main(['--site'])
            self.assertFalse((root / 'missing-site').exists())

    def test_site_refuses_invalid_or_partial_publication(self):
        for flags in (['--lang', 'pt-BR'], ['--check'], ['--adopt', '0' * 64]):
            with temporary_book(SOURCES) as root, self.subTest(flags=flags):
                with self.assertRaisesRegex(ValueError, '--site builds all languages'):
                    build.main(['--site', *flags])
                self.assertFalse((root / '_site').exists())
        with temporary_book(english_fixture()) as root:
            with self.assertRaisesRegex(ValueError, 'configured index.html'): build.main(['--site'])
            self.assertFalse((root / '_site').exists())
        sources = dict(SOURCES, **english_fixture()); del sources['content/en/ui.json']
        with temporary_book(sources) as root:
            with self.assertRaises(ValueError): build.main(['--site'])
            self.assertFalse((root / '_site').exists())
        with temporary_book(SOURCES) as root, patch.object(build, 'read_sources', side_effect=[SOURCES, {}]):
            with self.assertRaisesRegex(ValueError, 'Sources changed'): build.main(['--site'])
            self.assertFalse((root / '_site').exists())

    def test_pages_workflow_limits_publication(self):
        workflow = yaml.load((build.ROOT / '.github/workflows/pages.yml').read_text(), Loader=yaml.BaseLoader)
        self.assertEqual(workflow['on']['push']['branches'], ['main'])
        self.assertEqual(workflow['on']['pull_request']['branches'], ['main'])
        self.assertIn('workflow_dispatch', workflow['on'])
        self.assertEqual(workflow['permissions'], {'contents': 'read'})
        build_job, deploy = workflow['jobs']['build'], workflow['jobs']['deploy']
        self.assertNotIn('permissions', build_job)
        steps = build_job['steps']
        commands = [step['run'] for step in steps if step.get('run', '').startswith('uv run ')]
        self.assertEqual(commands, ['uv run test-build.py', 'uv run build.py --site',
                                    'uv run test-learner-workspace.py --html _site/index.html'])
        upload = next(step for step in steps if step.get('uses', '').startswith('actions/upload-pages-artifact@'))
        self.assertEqual(upload['with']['path'], '_site')
        self.assertEqual(deploy['needs'], 'build')
        self.assertEqual(deploy['if'], "github.ref == 'refs/heads/main' && github.event_name != 'pull_request'")
        self.assertEqual(deploy['permissions'], {'pages': 'write', 'id-token': 'write'})
        self.assertEqual(deploy['environment']['name'], 'github-pages')
        self.assertEqual(deploy['concurrency']['cancel-in-progress'], 'false')

    @unittest.skipUnless(args.baseline, 'Pass --baseline ZIP to audit the original manuscript')
    def test_original_manuscript_preserved(self):
        with ZipFile(args.baseline) as archive: before = archive.read('index.html').decode()
        _, generated, _ = build.render_book('pt-BR', SOURCES)
        old, new = (BeautifulSoup(html, 'html.parser') for html in (before, generated))
        text = lambda element: ' '.join(element.stripped_strings)
        self.assertEqual(text(old.select_one('.main')), text(new.select_one('.main')))
        for selector in ('form', 'svg', 'pre > code', '.activity', 'details.answer', '.objectives', '.prereq'):
            self.assertEqual([str(x) for x in old.select(selector)], [str(x) for x in new.select(selector)], selector)
        self.assertEqual([(a['href'], text(a)) for a in old.select('a[href]')], [(a['href'], text(a)) for a in new.select('a[href]')])
        for name, source in SOURCES.items():
            if not name.startswith(PREFIX + 'aula-'): continue
            lesson = build.load_lesson(name, source)
            article = re.search(r'<article\b[^>]*\bid="' + lesson['id'] + r'"[^>]*>', before)
            start = before.index('</header>', article.end()) + len('</header>')
            end = before.index('</article>', start)
            self.assertEqual(lesson['body'], before[start:end], name)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
