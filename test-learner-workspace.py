# /// script
# dependencies = ["beautifulsoup4==4.14.3", "playwright==1.58.0"]
# ///
"""Run with: uv run test-learner-workspace.py

Uses an isolated Chrome profile, a loopback fixture server, and real Pyodide.
Requires google-chrome and network access to the pinned Pyodide CDN.
Never writes to the booklet or to an existing browser profile.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zipfile import ZipFile

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, expect
from curriculum_browser_checks import check_authored_exercises, check_curriculum_migration
from pycardano_browser_checks import check_pycardano_loading
from bilingual_browser_checks import check_real_translation

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--html', type=Path, default=Path(__file__).with_name('index.html'))
parser.add_argument('--baseline', type=Path, help='Optional pre-refactor ZIP for browser storage compatibility checks')
parser.add_argument('--curriculum-baseline', type=Path, help='Previous HTML for intentional curriculum revision/storage checks')
args = parser.parse_args()
SOURCE = args.html.read_text()
CURRICULUM_BASELINE = args.curriculum_baseline.read_bytes() if args.curriculum_baseline else None
BASELINE = None
if args.baseline:
    with ZipFile(args.baseline) as archive:
        BASELINE = archive.read('index.html')
ROOT = BeautifulSoup(SOURCE, 'html.parser')
ENGLISH_OPTION = ROOT.select_one('#book-language option[value="en"]:not([disabled])')
ENGLISH_OUTPUT = ENGLISH_OPTION['data-output'] if ENGLISH_OPTION else None
ENGLISH_SOURCE = (args.html.parent / ENGLISH_OUTPUT).read_text() if ENGLISH_OUTPUT else None
LINKED_CODE = 'pre[data-python-runner="true"][data-question]'
assert not ROOT.select('.selfcheck')
assert 'autoavaliação' not in ROOT.get_text().lower()
if not ROOT.select(LINKED_CODE):
    # Exercise the linked-question UI without imposing an activity on the curriculum.
    # This fixture exists only on the private test server, never in the published book.
    linked_fixture = BeautifulSoup('''
      <pre data-python-runner="true" data-exercise-id="workspace-linked-fixture"
           data-question="code-question-aula-workspace-fixture"><code class="language-python">print("workspace fixture")</code></pre>
      <form class="code-question" id="code-question-aula-workspace-fixture">
        <fieldset class="cq-fieldset"><legend>Questão de teste</legend><div class="cq-options">
          <label class="cq-option"><input type="radio" name="cq-aula-workspace-fixture" value="a"
            data-feedback="Alternativa incorreta."/><span class="cq-option-text">Alternativa incorreta</span></label>
          <label class="cq-option"><input type="radio" name="cq-aula-workspace-fixture" value="b"
            data-correct="true" data-feedback="Alternativa correta."/><span class="cq-option-text">Alternativa correta</span></label>
        </div></fieldset>
        <div class="cq-actions"><button type="submit" class="cq-check">Conferir resposta</button>
          <p class="cq-status" role="status"></p></div><p class="cq-feedback" aria-live="polite"></p>
      </form>
    ''', 'html.parser')
    ROOT.select_one('article.lesson').extend(list(linked_fixture.contents))
    SOURCE = str(ROOT)
LANGUAGE_LESSON = ROOT.select_one(LINKED_CODE).find_parent('article')['id']
FALLBACK_LESSON = next(article['id'] for article in ROOT.select('article.lesson') if article['id'] != LANGUAGE_LESSON)


def fixture(path):
    soup = BeautifulSoup(SOURCE, 'html.parser')
    pre = soup.select_one(LINKED_CODE)
    pre['data-exercise-id'] = 'test-addition'
    pre['data-exercise-version'] = '1'
    pre['data-validator'] = 'test-addition-checks'
    pre.code.string = 'def add(a, b):\n    return a - b\n'
    tests = [{'name': 'positive inputs', 'code': 'assert add(2, 3) == 5'},
             {'name': 'negative inputs', 'code': 'assert add(-2, 3) == 1'}]
    if 'revision=2' in path:
        tests.append({'name': 'zero', 'code': 'assert add(0, 0) == 0'})
    if 'invalid=1' in path:
        tests = []
    config = soup.new_tag('script', type='application/json', id='test-addition-checks')
    config.string = json.dumps({'version': 1, 'tests': tests})
    soup.head.append(config)
    if 'renumber=1' in path:
        for node in soup.find_all(True):
            for key in ('id', 'name', 'data-question', 'data-answer'):
                value = node.get(key)
                if value and 'aula-' in value:
                    node[key] = value.replace('aula-', 'moved-aula-')
    return str(soup).encode()


def language_fixture(path):
    """Synthetic browser pages only; never a published English translation."""
    soup = BeautifulSoup(SOURCE, 'html.parser')
    language = 'en' if path.startswith('/language/en.html') else 'pt-BR'
    soup.html['lang'] = language
    selector = soup.select_one('#book-language')
    for option in selector.select('option'):
        locale = option['value']
        option.attrs.pop('disabled', None)
        option.attrs.pop('selected', None)
        option['data-output'] = 'pt.html' if locale == 'pt-BR' else 'en.html'
        # A deliberately missing destination lesson exercises the contents fallback.
        anchors = [node['id'] for node in soup.select('[id]')
                   if locale != 'en' or node['id'] != FALLBACK_LESSON]
        option['data-anchors'] = ' '.join(anchors)
        option.string = 'PT' if locale == 'pt-BR' else 'EN'
        if locale == language:
            option['selected'] = ''
    if path.startswith('/language/unavailable.html'):
        option = selector.select_one('option[value="en"]')
        option['disabled'] = ''
        option.attrs.pop('data-output', None)
        option.attrs.pop('data-anchors', None)
        option.string = 'EN (indisponível)'
    if language == 'en':
        soup.select_one('#' + FALLBACK_LESSON).decompose()
        soup.select_one('#' + LANGUAGE_LESSON + ' .lesson-title').string = 'English selector test fixture'
    return str(soup).encode()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = fixture(self.path) if self.path.startswith('/fixture') else SOURCE.encode()
        if ENGLISH_SOURCE and self.path.split('?', 1)[0] == '/' + ENGLISH_OUTPUT:
            body = ENGLISH_SOURCE.encode()
        if self.path.startswith('/language/'):
            body = language_fixture(self.path)
        if self.path.startswith('/before-refactor') and BASELINE:
            body = BASELINE
        if self.path.startswith('/before-curriculum') and CURRICULUM_BASELINE:
            body = CURRICULUM_BASELINE
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def open_ancestors(locator):
    locator.evaluate('el => { for(let p=el.parentElement;p;p=p.parentElement) if(p.tagName === "DETAILS") p.open=true; }')


def editor(page):
    wrap = page.locator(LINKED_CODE).first.locator('..')
    open_ancestors(wrap)
    if wrap.locator('.code-input').is_hidden():
        wrap.locator('.edit-code-btn').click()
    return wrap


def run(page, wrap, validate=False):
    wrap.locator('.validate-code-btn' if validate else '.run-btn').click()
    expect(wrap.locator('.stop-code-btn')).to_be_hidden(timeout=75000)
    return wrap.locator('.run-status').get_attribute('data-state')


def answer(form):
    open_ancestors(form)
    for field in form.locator('input[data-correct="true"]').all():
        field.check()
    for field in form.locator('select.quiz-select').all():
        field.select_option(field.get_attribute('data-correct'))
    for field in form.locator('input.quiz-input').all():
        field.fill(field.get_attribute('data-accept').split('|')[0])
    form.locator('.quiz-check').last.click()
    expect(form).to_have_class('activity-quiz is-graded')
    assert form.locator('.is-incorrect').count() == 0


def check_icon_toolbar(page, wrap):
    open_ancestors(wrap)
    icons = wrap.locator('.code-tools .code-icon:visible')
    assert icons.count() == 4
    assert [b.get_attribute('aria-label') for b in icons.all()] == ['Copiar', 'Editar código', 'Restaurar original', 'Executar']
    icons.first.scroll_into_view_if_needed()
    bounds = [b.bounding_box() for b in icons.all()]
    assert max(b['y'] for b in bounds) - min(b['y'] for b in bounds) < .1
    assert all(abs(b['width'] - 36) < .1 and abs(b['height'] - 36) < .1 for b in bounds)
    assert all(abs(bounds[i+1]['x'] - bounds[i]['x'] - 40) < .1 for i in range(3))
    toolbar = wrap.locator('.code-tools')
    edge = toolbar.evaluate('el => { const s=getComputedStyle(el); return el.getBoundingClientRect().right-parseFloat(s.paddingRight)-parseFloat(s.borderRightWidth); }')
    assert abs(bounds[-1]['x'] + bounds[-1]['width'] - edge) < .1
    for icon in icons.all():
        assert icon.locator('svg[aria-hidden="true"]').count() == 1
        assert icon.evaluate('el => { const r=el.getBoundingClientRect(); return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2).closest("button")===el; }')
    copy = wrap.locator('.copy-btn')
    copy.hover()
    expect(copy.locator('.code-tooltip')).to_be_visible()
    copy.focus()
    page.keyboard.press('Tab')
    edit = wrap.locator('.edit-code-btn')
    expect(edit).to_be_focused()
    expect(edit.locator('.code-tooltip')).to_be_visible()
    assert edit.evaluate('el => getComputedStyle(el).outlineStyle') == 'solid'


def clear_output(page, wrap):
    field = wrap.locator('.code-input')
    draft = field.input_value()
    state = wrap.locator('.run-status').get_attribute('data-state')
    button = wrap.locator('.run-out .clear-output-btn')
    expect(button).to_have_accessible_name('Limpar saída')
    assert button.locator('svg[aria-hidden="true"]').count() == 1
    assert wrap.locator('.code-tools .clear-output-btn').count() == 0
    button.hover(); expect(button.locator('.code-tooltip')).to_be_visible()
    page.mouse.move(0, 0); button.focus()
    page.keyboard.press('Tab'); page.keyboard.press('Shift+Tab')
    expect(button).to_be_focused()
    expect(button.locator('.code-tooltip')).to_be_visible()
    assert button.evaluate('el=>getComputedStyle(el).outlineStyle') == 'solid'
    for width in (390, 320, 1440):
        page.set_viewport_size({'width': width, 'height': 1000})
        button.scroll_into_view_if_needed()
        box, label = button.bounding_box(), wrap.locator('.run-output-label').bounding_box()
        assert box['x'] > label['x'] + label['width']
        assert box['x'] + box['width'] <= width
        assert button.locator('svg').bounding_box()['width'] == 16
        assert button.evaluate('el=>{const r=el.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2).closest("button")===el}')
    button.focus(); button.press('Enter')
    expect(wrap.locator('.run-out')).to_be_hidden()
    expect(wrap.locator('.run-output')).to_have_text('')
    expect(wrap.locator('.run-btn')).to_be_focused()
    expect(field).to_have_value(draft)
    expect(wrap.locator('.run-status')).to_be_empty()
    expect(wrap.locator('.run-status')).to_be_hidden()
    result = wrap.locator('pre[data-python-runner]').evaluate('el=>JSON.parse(localStorage.getItem(el._studyEditor.storage.key)).data.result')
    assert result == {'status': state, 'output': ''}
    page.reload(wait_until='domcontentloaded')
    expect(wrap.locator('.run-out')).to_be_hidden()
    expect(wrap.locator('.clear-output-btn')).to_be_hidden()
    expect(field).to_have_value(draft)
    expect(wrap.locator('.run-status')).to_be_empty()
    expect(wrap.locator('.run-status')).to_be_hidden()
    assert wrap.locator('.run-status svg').count() == 0


def check_theme_control(page):
    button = page.locator('#theme-toggle')
    initial = page.evaluate('document.documentElement.dataset.theme')
    target = 'light' if initial == 'dark' else 'dark'
    expect(button).to_have_attribute('data-icon', 'sun' if initial == 'dark' else 'moon')
    expect(button).to_have_accessible_name('Ativar modo claro' if initial == 'dark' else 'Ativar modo escuro')
    assert button.locator('svg[aria-hidden="true"]').count() == 1
    assert page.locator('#toc #theme-toggle').count() == 0
    glyph = button.locator('svg').bounding_box()
    assert glyph['width'] == 16 and glyph['height'] == 16
    assert button.evaluate('el => getComputedStyle(el).borderTopWidth') == '0px'
    bounds = button.bounding_box()
    assert bounds['width'] == 44 and bounds['height'] == 44
    assert abs(bounds['y'] - 20) < .1
    assert abs(bounds['x'] + bounds['width'] - (page.viewport_size['width'] - 20)) < .1
    button.hover()
    expect(button.locator('.code-tooltip')).to_be_visible()
    button.click()
    assert page.evaluate('document.documentElement.dataset.theme') == target
    assert page.evaluate('localStorage.getItem("book-theme")') == target
    page.reload(wait_until='domcontentloaded')
    assert page.evaluate('document.documentElement.dataset.theme') == target
    expect(button).to_have_attribute('data-icon', 'sun' if target == 'dark' else 'moon')
    button.focus(); button.press('Enter')
    assert page.evaluate('document.documentElement.dataset.theme') == initial


def check_editor_highlight(page, wrap):
    field = wrap.locator('.code-input')
    surface = wrap.locator('.code-editor-surface')
    content = wrap.locator('.code-highlight-content')
    source = '# Acentuação\nimport hashlib\nprint("<img src=x onerror=alert(1)>")\n'
    field.fill(source)
    expect(surface).to_have_class('code-editor-surface is-highlighted')
    assert content.text_content() == source + '\u200b'
    assert content.locator('.token.keyword').count() > 0
    assert content.locator('.token.string').count() > 0
    assert content.locator('img').count() == 0
    assert field.evaluate('el => getComputedStyle(el).caretColor') != 'rgba(0, 0, 0, 0)'
    assert wrap.locator('.code-highlight').get_attribute('aria-hidden') == 'true'
    field.press('Control+End')
    page.keyboard.insert_text('# desfazer')
    field.press('Control+z')
    expect(field).to_have_value(source)
    field.dispatch_event('compositionstart')
    expect(surface).to_have_class('code-editor-surface')
    field.dispatch_event('compositionend')
    expect(surface).to_have_class('code-editor-surface is-highlighted')
    field.fill('\n'.join('print(' + repr('ç' * 180) + ')' for _ in range(100)) + '\n')
    for top, left in [(450, 150), (1000000, 1000000)]:
        field.evaluate('(el,p) => { el.scrollTop=p[0]; el.scrollLeft=p[1]; el.dispatchEvent(new Event("scroll")); }', [top, left])
        positions = wrap.evaluate('el => { const i=el.querySelector(".code-input"),v=el.querySelector(".code-highlight"),n=el.querySelector(".code-line-numbers"); return [[i.scrollTop,i.scrollLeft,i.clientWidth,i.clientHeight],[v.scrollTop,v.scrollLeft,v.clientWidth,v.clientHeight],n.scrollTop]; }')
        assert all(abs(a-b) <= 1 for a,b in zip(positions[0], positions[1])), positions
        assert abs(positions[0][0] - positions[2]) <= 1, positions
    page.emulate_media(forced_colors='active')
    expect(wrap.locator('.code-highlight')).to_be_hidden()
    assert field.evaluate('el => getComputedStyle(el).webkitTextFillColor') != 'rgba(0, 0, 0, 0)'
    page.emulate_media(forced_colors='none')


def check_language_selector(page):
    page.goto(url + '/language/unavailable.html', wait_until='domcontentloaded')
    selector = page.locator('#book-language')
    expect(selector).to_have_accessible_name('Idioma da apostila')
    expect(selector).to_have_value('pt-BR')
    assert selector.locator('option[value="en"]').is_disabled()
    assert selector.locator('option[value="en"]').get_attribute('data-output') is None
    before = page.url
    selector.evaluate('el=>{el.value="en";el.dispatchEvent(new Event("change",{bubbles:true}));}')
    assert page.url == before
    expect(selector).to_have_value('pt-BR')
    for width in (1440, 390, 320):
        page.set_viewport_size({'width': width, 'height': 1000})
        if width <= 1000 and page.locator('#toc-toggle').get_attribute('aria-expanded') != 'true':
            page.locator('#toc-toggle').click()
        for theme in ('light', 'dark'):
            page.evaluate('value=>document.documentElement.dataset.theme=value', theme)
            selector.scroll_into_view_if_needed()
            expect(selector).to_be_visible()
            geometry = selector.evaluate('''el=>{
                const footer=el.closest('.toc-language'), f=footer.getBoundingClientRect(), r=el.getBoundingClientRect();
                const last=footer.previousElementSibling.getBoundingClientRect();
                return {direct:footer.parentElement.id==='toc',outside:!el.closest('details'),
                    below:r.top>=last.bottom,center:Math.abs((r.left+r.right-f.left-f.right)/2),
                    width:r.width,height:r.height,radius:getComputedStyle(el).borderRadius};
            }''')
            assert geometry['direct'] and geometry['outside'] and geometry['below'], geometry
            assert geometry['center'] < 1 and geometry['width'] == 64 and geometry['height'] >= 36, geometry
            assert geometry['radius'] == '6px'
            page.mouse.move(0, 0)
            assert selector.evaluate('el=>getComputedStyle(el).backgroundColor') == 'rgba(0, 0, 0, 0)'
            assert selector.evaluate('el=>getComputedStyle(el).fontWeight') == '400'
            assert selector.locator('option:checked').inner_text() == 'PT'
            selector.focus(); page.keyboard.press('Shift+Tab'); page.keyboard.press('Tab')
            expect(selector).to_be_focused()
            assert selector.evaluate('el=>getComputedStyle(el).outlineStyle') == 'solid'
        page.emulate_media(media='print')
        expect(selector).to_be_hidden()
        page.emulate_media(media='screen')
    page.emulate_media(forced_colors='active')
    selector.scroll_into_view_if_needed()
    expect(selector).to_be_visible()
    page.emulate_media(forced_colors='none')
    page.set_viewport_size({'width': 1440, 'height': 1000})
    page.goto(url + '/language/pt.html#' + LANGUAGE_LESSON, wait_until='domcontentloaded')
    portuguese_draft = 'print("__portuguese_language_draft__")'
    english_draft = 'print("__english_language_draft__")'
    editor(page).locator('.code-input').fill(portuguese_draft)
    page.wait_for_function('id=>document.querySelector("#toc a.active")?.getAttribute("href")==="#"+id', arg=LANGUAGE_LESSON)
    page.locator('#book-language').select_option('en')
    page.wait_for_url(url + '/language/en.html#' + LANGUAGE_LESSON)
    expect(page.locator('html')).to_have_attribute('lang', 'en')
    expect(page.locator('#book-language')).to_have_value('en')
    expect(page.locator('#' + LANGUAGE_LESSON + ' .lesson-title')).to_have_text('English selector test fixture')
    assert editor(page).locator('.code-input').input_value() != portuguese_draft
    editor(page).locator('.code-input').fill(english_draft)
    page.locator('#book-language').select_option('pt-BR')
    page.wait_for_url(url + '/language/pt.html#' + LANGUAGE_LESSON)
    expect(editor(page).locator('.code-input')).to_have_value(portuguese_draft)
    page.go_back(wait_until='domcontentloaded')
    expect(page.locator('#book-language')).to_have_value('en')
    expect(editor(page).locator('.code-input')).to_have_value(english_draft)
    page.goto(url + '/language/pt.html#' + FALLBACK_LESSON, wait_until='domcontentloaded')
    page.wait_for_function('id=>document.querySelector("#toc a.active")?.getAttribute("href")==="#"+id', arg=FALLBACK_LESSON)
    page.locator('#book-language').select_option('en')
    page.wait_for_url(url + '/language/en.html#sumario')
    page.evaluate('localStorage.clear()')  # This test's private loopback origin only.
    browser = page.context.browser
    touch = browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
    try:
        mobile = touch.new_page()
        mobile.goto(url, wait_until='domcontentloaded')
        mobile.locator('#toc-toggle').click()
        control = mobile.locator('#book-language')
        control.scroll_into_view_if_needed()
        assert control.bounding_box()['height'] >= 44
    finally:
        touch.close()
    no_js = browser.new_context(java_script_enabled=False)
    try:
        plain = no_js.new_page()
        plain.goto(url, wait_until='domcontentloaded')
        expect(plain.locator('#book-language')).to_be_hidden()
    finally:
        no_js.close()
    check('language selector follows the chapters, is centered and accessible, disables missing English, switches valid pages and isolates drafts')


def check_migration(page):
    page.add_init_script('''
      const originalGet = Storage.prototype.getItem;
      window.__studyKeys = new Set();
      Storage.prototype.getItem = function(key) {
        if (String(key).startsWith('cardano-booklet.study.')) window.__studyKeys.add(key);
        return originalGet.call(this, key);
      };
    ''')
    page.goto(url + '/before-refactor', wait_until='domcontentloaded')
    before = editor(page)
    before.locator('.code-input').fill('print("migration draft")')
    assert run(page, before) == 'success'
    question_id = before.locator('pre[data-python-runner]').get_attribute('data-question')
    question = page.locator(f'form[id="{question_id}"]')
    question.locator('input[data-correct="true"]').check()
    question.locator('.cq-check').click()
    quiz = page.locator('form.activity-quiz').first
    answer(quiz)
    score = quiz.locator('.quiz-status').last.inner_text()
    keys = page.evaluate('Array.from(window.__studyKeys).sort()')
    records = page.evaluate('Object.fromEntries(Object.entries(localStorage).filter(([k]) => k.startsWith("cardano-booklet.study.")))')
    page.goto(url, wait_until='domcontentloaded')
    restored_keys = page.evaluate('Array.from(window.__studyKeys).sort()')
    assert restored_keys == keys, {
        'reason': 'Record identities changed. Check for editorial exercise revisions after the baseline.',
        'old_only': sorted(set(keys) - set(restored_keys)),
        'new_only': sorted(set(restored_keys) - set(keys)),
    }
    after = page.locator(LINKED_CODE).first.locator('..')
    expect(after.locator('.code-input')).to_be_visible()
    expect(after.locator('.code-input')).to_have_value('print("migration draft")')
    expect(after.locator('.run-output')).to_have_text('migration draft')
    assert 'is-correct' in page.locator(f'form[id="{question_id}"]').get_attribute('class')
    assert page.locator('form.activity-quiz').first.locator('.quiz-status').last.inner_text() == score
    assert page.evaluate('Object.fromEntries(Object.entries(localStorage).filter(([k]) => k.startsWith("cardano-booklet.study.")))') == records
    check(f'pre-refactor drafts, grades, outputs and activity expansion survive; all {len(keys)} record identities match')
    page.evaluate('localStorage.clear()')  # This test's private profile and loopback origin only.


def check(name):
    print('PASS:', name, flush=True)


server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
url = f'http://127.0.0.1:{server.server_port}'
profile = Path(tempfile.mkdtemp(prefix='booklet-study-test-'))
chrome = shutil.which('google-chrome')
assert chrome, 'google-chrome is required'
errors = []

with sync_playwright() as pw:
    def launch():
        ctx = pw.chromium.launch_persistent_context(str(profile), executable_path=chrome, headless=True,
            viewport={'width': 1440, 'height': 1000})
        ctx.on('page', lambda p: p.on('pageerror', lambda error: errors.append(str(error))))
        return ctx

    ctx = launch()
    try:
        page = ctx.pages[0]
        page.on('pageerror', lambda error: errors.append(str(error)))
        if BASELINE:
            check_migration(page)
        if CURRICULUM_BASELINE:
            migration_browser = pw.chromium.launch(executable_path=chrome, headless=True)
            try:
                migration_context = migration_browser.new_context(viewport={'width': 1440, 'height': 1000})
                check_curriculum_migration(migration_context, url, answer, check)
            finally:
                migration_browser.close()
        check_language_selector(page)
        page.goto(url, wait_until='domcontentloaded')
        check_theme_control(page)
        check('theme icon stays outside navigation, exposes its action and preserves the selected theme')
        assert page.locator('.edit-code-btn').count() == len(ROOT.select('pre code'))
        assert page.locator('.run-btn').count() == len(ROOT.select('pre > code.language-python'))
        assert page.locator('.study-save-status').evaluate_all('nodes => nodes.every(node => !node.textContent)')
        check_icon_toolbar(page, page.locator(LINKED_CODE).first.locator('..'))
        check('four SVG buttons align, never overlap, and expose hover and keyboard tooltips')
        for index, code in enumerate(ROOT.select('pre > code.language-python')):
            if code.parent.get('data-question'):
                continue
            lesson = code.find_parent('article')['id']
            sample = page.locator('.run-btn').nth(index).locator('../..')
            open_ancestors(sample)
            assert run(page, sample) == 'success', lesson
        check('all Python blocks expose Execute; standalone examples run successfully')
        check_authored_exercises(page, ROOT, run, open_ancestors, check)
        check_pycardano_loading(page, ROOT, run, open_ancestors, check)
        wrap = editor(page)
        check_editor_highlight(page, wrap)
        check('editing highlights safely with aligned scrolling, native undo, composition and high-contrast fallbacks')
        wrap.locator('.code-input').fill('print("draft <b>safe</b>")')
        expect(wrap.locator('.study-save-status')).to_have_text('')
        assert run(page, wrap) == 'success'
        expect(wrap.locator('.run-output')).to_have_text('draft <b>safe</b>')
        expect(wrap.locator('.run-status')).to_have_text('Execução concluída')
        assert wrap.locator('.run-status svg[aria-hidden="true"]').count() == 1
        assert wrap.locator('.run-output b').count() == 0
        question_id = wrap.locator('pre[data-python-runner]').get_attribute('data-question')
        cq = page.locator(f'form[id="{question_id}"]')
        cq.locator('input[data-correct="true"]').check()
        cq.locator('.cq-check').click()
        assert 'is-correct' in cq.get_attribute('class')
        quiz = page.locator('form.activity-quiz').first
        quiz_id = quiz.get_attribute('id')
        answer(quiz)
        score = quiz.locator('.quiz-status').last.inner_text()
        ctx.close()
        ctx = launch()
        page = ctx.pages[0]
        page.goto(url, wait_until='domcontentloaded')
        wrap = editor(page)
        expect(wrap.locator('.code-input')).to_have_value('print("draft <b>safe</b>")')
        expect(wrap.locator('.run-output')).to_have_text('draft <b>safe</b>')
        expect(page.locator(f'form[id="{quiz_id}"] .quiz-status').last).to_have_text(score)
        cq = page.locator(f'form[id="{question_id}"]')
        assert 'is-correct' in cq.get_attribute('class')
        check('browser restart restores drafts, outputs, quiz grades and linked code answers')
        clear_output(page, wrap)
        assert 'is-correct' in cq.get_attribute('class')
        expect(page.locator(f'form[id="{quiz_id}"] .quiz-status').last).to_have_text(score)
        assert run(page, wrap) == 'success'
        expect(wrap.locator('.run-output')).to_have_text('draft <b>safe</b>')
        expect(wrap.locator('.clear-output-btn')).to_be_visible()
        check('clearing removes output, status and checkmark across reload; code and quiz grades survive; rerun restores output')
        wrap.locator('.code-input').fill('print("changed")')
        assert 'is-locked' in cq.get_attribute('class')
        assert 'is-graded' not in cq.get_attribute('class')
        assert wrap.locator('.run-output').inner_text() == ''
        check('editing invalidates previous execution and linked answer grade')
        for form in page.locator('form.activity-quiz').all():
            answer(form)
        page.reload(wait_until='domcontentloaded')
        assert page.locator('form.activity-quiz.is-graded').count() == len(ROOT.select('form.activity-quiz'))
        assert page.locator('form.activity-quiz .quiz-question.is-incorrect').count() == 0
        quiz = page.locator('form.activity-quiz').first
        open_ancestors(quiz)
        wrong = quiz.locator('.quiz-question').first.locator('input:not([data-correct="true"])').first
        wrong.check()
        assert 'is-graded' not in quiz.get_attribute('class')
        page.reload(wait_until='domcontentloaded')
        quiz = page.locator('form.activity-quiz').first
        assert 'is-graded' not in quiz.get_attribute('class')
        expect(quiz.locator('.quiz-question').first.locator('input:not([data-correct="true"])').first).to_be_checked()
        check('all quiz kinds restore their grades; edited partial answers invalidate the old grade')

        page.goto(url + '/fixture', wait_until='domcontentloaded')
        wrap = editor(page)
        assert run(page, wrap, True) == 'mismatch'
        assert 'Falhou: positive inputs' in wrap.locator('.run-output').inner_text()
        wrap.locator('.code-input').fill('')
        assert run(page, wrap, True) == 'mismatch'
        wrap.locator('.code-input').fill('def add(a, b):\n    return a + b\n')
        assert run(page, wrap, True) == 'validated'
        check('separate authored tests reject wrong and empty solutions, accept correct solution')
        clear_output(page, wrap)
        check('clearing test output preserves the validated result across reload')
        page.reload(wait_until='domcontentloaded')
        wrap = editor(page)
        expect(wrap.locator('.run-status')).to_be_hidden()
        assert wrap.locator('pre[data-python-runner]').evaluate('el=>el._studyEditor.result().status') == 'validated'
        page.goto(url + '/fixture?renumber=1', wait_until='domcontentloaded')
        wrap = editor(page)
        expect(wrap.locator('.code-input')).to_have_value('def add(a, b):\n    return a + b\n')
        check('code identity survives lesson renumbering without relying on positional IDs')
        page.goto(url + '/fixture?revision=2', wait_until='domcontentloaded')
        wrap = editor(page)
        expect(wrap.locator('.code-input')).to_have_value('def add(a, b):\n    return a - b\n')
        assert wrap.locator('.run-status').get_attribute('data-state') == ''
        check('changed validator revision never inherits a stale pass or incompatible draft')
        page.goto(url + '/fixture?invalid=1', wait_until='domcontentloaded')
        wrap = editor(page)
        expect(wrap.locator('.validate-code-btn')).to_be_disabled()
        assert 'inválido' in wrap.locator('.run-status').inner_text()
        check('missing/empty validation configuration fails closed')
        page.goto(url + '/fixture', wait_until='domcontentloaded')
        wrap = editor(page)
        wrap.locator('.code-input').fill('if :')
        assert run(page, wrap) == 'error'
        clear_output(page, wrap)
        check('error output can be cleared without inventing a successful result')
        wrap.locator('.code-input').fill('while True:\n    pass')
        assert run(page, wrap) == 'timeout'
        wrap.locator('.code-input').fill('print("still responsive")')
        assert run(page, wrap) == 'success'
        check('syntax errors and infinite loops are bounded; a later run succeeds')
        wrap.locator('.run-btn').click()
        expect(wrap.locator('.clear-output-btn')).to_be_hidden()
        wrap.locator('.stop-code-btn').click()
        expect(wrap.locator('.run-status')).to_have_attribute('data-state', 'cancelled')
        wrap.locator('.run-btn').click()
        wrap.locator('.code-input').fill('print("new while loading")')
        expect(wrap.locator('.stop-code-btn')).to_be_hidden()
        assert wrap.locator('.run-output').inner_text() == ''
        check('cancel and edits during loading cannot publish a stale result')
        wrap.locator('.code-input').fill('print("saved from tab one")')
        other = ctx.new_page()
        other.goto(url + '/fixture', wait_until='domcontentloaded')
        other_wrap = editor(other)
        wrap.locator('.code-input').fill('print("newer tab one")')
        other_wrap.locator('.code-input').fill('print("tab two conflict")')
        expect(other_wrap.locator('.study-conflict')).to_be_visible()
        expect(wrap.locator('.code-input')).to_have_value('print("newer tab one")')
        other_wrap.get_by_role('button', name='Manter esta aba', exact=True).click()
        expect(wrap.locator('.study-conflict')).to_be_visible()
        wrap.get_by_role('button', name='Carregar versão salva', exact=True).click()
        expect(wrap.locator('.code-input')).to_have_value('print("tab two conflict")')
        other.close()
        check('two tabs require an explicit conflict choice instead of overwriting silently')
        ctx.grant_permissions(['clipboard-read', 'clipboard-write'], origin=url)
        page.bring_to_front()
        wrap.locator('.copy-btn').click()
        assert page.evaluate('navigator.clipboard.readText()') == 'print("tab two conflict")'
        page.once('dialog', lambda dialog: dialog.accept())
        wrap.locator('.reset-code-btn').click()
        expect(wrap.locator('.code-input')).to_have_value('def add(a, b):\n    return a - b\n')
        page.reload(wait_until='domcontentloaded')
        wrap = editor(page)
        expect(wrap.locator('.code-input')).to_have_value('def add(a, b):\n    return a - b\n')
        check('copy uses the draft; confirmed reset persists the original and invalidates results')

        page.set_viewport_size({'width':390,'height':844})
        wrap.locator('.code-input').fill('\n'.join('print(' + repr('x'*120) + ')' for _ in range(200)))
        assert wrap.locator('.code-editor-grid').bounding_box()['height'] < 900
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        wrap.screenshot(path=str(profile / 'mobile-editor.png'))
        wrap.locator('.code-input').fill('value = 1')
        wrap.locator('.code-input').press('Tab')
        expect(wrap.locator('.code-input')).to_have_value('value = 1')
        assert not wrap.locator('.code-input').evaluate('el => el === document.activeElement')
        wrap.locator('.code-input').focus()
        wrap.locator('.code-input').press('Shift+Tab')
        assert not wrap.locator('.code-input').evaluate('el => el === document.activeElement')
        expect(wrap.locator('.code-input')).to_have_value('value = 1')
        assert page.locator('.code-editor-hint').count() == 0
        check('mobile editor stays bounded; Tab and Shift+Tab navigate normally without changing code')

        browser2 = pw.chromium.launch(executable_path=chrome, headless=True)
        no_prism = browser2.new_context()
        no_prism.route('**/*prism*.js', lambda route: route.abort())
        p0 = no_prism.new_page(); p0.goto(url, wait_until='domcontentloaded')
        fallback = editor(p0)
        expect(fallback.locator('.code-editor-surface')).to_have_class('code-editor-surface')
        fallback.locator('.code-input').fill('print("sem CDN")')
        assert fallback.locator('.code-input').evaluate('el => getComputedStyle(el).color') != 'rgba(0, 0, 0, 0)'
        no_prism.close()
        check('unavailable syntax highlighter leaves the native editor readable and editable')
        blocked = browser2.new_context()
        blocked.add_init_script('Storage.prototype.setItem = function(){ throw new DOMException("blocked", "QuotaExceededError"); }')
        p2 = blocked.new_page(); p2.goto(url, wait_until='domcontentloaded')
        w2 = editor(p2); w2.locator('.code-input').fill('print("not saved")')
        assert 'Não foi possível salvar' in w2.locator('.study-save-status').inner_text()
        expect(w2.locator('.code-input')).to_have_value('print("not saved")')
        check('storage failure leaves work usable and visibly warns instead of claiming a save')
        blocked.close()
        corrupt = browser2.new_context()
        p3 = corrupt.new_page(); p3.goto(url + '/fixture', wait_until='domcontentloaded')
        w3 = editor(p3); w3.locator('.code-input').fill('print("before corruption")')
        key = p3.evaluate('Object.keys(localStorage).find(k => k.includes(":code:test-addition:"))')
        p3.evaluate('(key) => localStorage.setItem(key, "{")', key)
        p3.reload(wait_until='domcontentloaded')
        w3 = editor(p3)
        assert 'não pôde ser lido' in w3.locator('.study-save-status').inner_text()
        assert p3.evaluate('(key) => localStorage.getItem(key)',key) == '{'
        w3.locator('.code-input').fill('print("explicit replacement")')
        w3.get_by_role('button',name='Manter esta aba',exact=True).click()
        assert json.loads(p3.evaluate('(key) => localStorage.getItem(key)',key))['data']['code'] == 'print("explicit replacement")'
        check('malformed storage is preserved until explicit replacement')
        corrupt.close()
        if ENGLISH_SOURCE:
            check_real_translation(browser2, url, ROOT, ENGLISH_SOURCE, ENGLISH_OUTPUT,
                                   run, open_ancestors, answer, check)
        browser2.close()
        assert not errors, errors
        check('no uncaught JavaScript errors')
    finally:
        ctx.close()
        server.shutdown(); server.server_close()
        subprocess.run(['gio','trash',str(profile)],check=True)
print('All learner-workspace checks passed.')
