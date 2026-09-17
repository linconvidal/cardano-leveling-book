"""Exercise the actual generated English book, never a synthetic translation."""
import json
from bs4 import BeautifulSoup
from playwright.sync_api import expect
from bilingual_test_cases import correspondence, renamed
from curriculum_test_cases import implementations


def check_real_translation(browser, url, portuguese, english_source, english_output,
                           run, open_ancestors, answer, check):
    english = BeautifulSoup(english_source, 'html.parser')
    ui = json.loads(english.select_one('#book-ui').string)
    assert english.html['lang'] == 'en'
    assert len(english.select('article.lesson')) == 21
    context = browser.new_context(viewport={'width': 1440, 'height': 1000})
    try:
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        lesson = 'aula-0-1'
        identity = 'utf8-encode-decode'
        code_selector = f'pre[data-exercise-id="{identity}"]'

        def editable():
            wrap = page.locator(code_selector).locator('..')
            open_ancestors(wrap)
            if wrap.locator('.code-input').is_hidden():
                wrap.locator('.edit-code-btn').click()
            return wrap.locator('.code-input')

        page.goto(url + '#' + lesson, wait_until='domcontentloaded')
        portuguese_draft = 'print("actual Portuguese draft")'
        english_draft = 'print("actual English draft")'
        editable().fill(portuguese_draft)
        pt_key = page.locator(code_selector).evaluate('p => p._studyEditor.storage.key')
        quiz_selector = '#quiz-aula-0-1-a1'
        answer(page.locator(quiz_selector))
        pt_score = page.locator(quiz_selector + ' .quiz-status').last.inner_text()
        page.wait_for_function('id => document.querySelector("#toc a.active")?.hash === "#" + id', arg=lesson)
        page.locator('#book-language').select_option('en')
        page.wait_for_url(url + '/' + english_output + '#' + lesson)
        expect(page.locator('html')).to_have_attribute('lang', 'en')
        assert editable().input_value() == english.select_one(code_selector).code.get_text()
        en_key = page.locator(code_selector).evaluate('p => p._studyEditor.storage.key')
        assert en_key != pt_key
        assert 'is-graded' not in (page.locator(quiz_selector).get_attribute('class') or '')
        editable().fill(english_draft)
        page.reload(wait_until='domcontentloaded')
        expect(editable()).to_have_value(english_draft)
        page.wait_for_function('id => document.querySelector("#toc a.active")?.hash === "#" + id', arg=lesson)
        page.locator('#book-language').select_option('pt-BR')
        page.wait_for_url(url + '/index.html#' + lesson)
        expect(editable()).to_have_value(portuguese_draft)
        expect(page.locator(quiz_selector + ' .quiz-status').last).to_have_text(pt_score)
        page.wait_for_function('id => document.querySelector("#toc a.active")?.hash === "#" + id', arg=lesson)
        page.locator('#book-language').select_option('en')
        page.wait_for_url(url + '/' + english_output + '#' + lesson)
        expect(editable()).to_have_value(english_draft)
        check('actual PT/EN exports preserve the lesson, restore separate drafts and isolate quiz grades')

        count = validators = quizzes = 0
        for pre in english.select('pre[data-exercise-id]'):
            exercise = pre['data-exercise-id']
            wrap = page.locator(f'pre[data-exercise-id="{exercise}"]').locator('..')
            open_ancestors(wrap)
            if wrap.locator('.code-input').is_hidden():
                wrap.locator('.edit-code-btn').click()
            starter = pre.code.get_text()
            wrap.locator('.code-input').fill(starter)
            expect(wrap.locator('.copy-btn')).to_have_accessible_name(ui['copy'])
            if pre.has_attr('data-validator'):
                pt = portuguese.select_one(f'pre[data-exercise-id="{exercise}"]').code.get_text()
                mapping = correspondence(pt, starter)
                repair, mutations = implementations(exercise, pt)
                cases = [(starter, 'mismatch'), (renamed(repair, mapping), 'validated')]
                cases += [(renamed(mutation, mapping), 'mismatch') for mutation in mutations]
                for source, expected in cases:
                    wrap.locator('.code-input').fill(source)
                    state = run(page, wrap, True)
                    assert state == expected, (exercise, expected, state, wrap.locator('.run-output').inner_text())
                validators += 1
                check(f'English {exercise}: starter and {len(mutations)} mistakes rejected; repair validated')
            else:
                assert run(page, wrap) == 'success', (exercise, wrap.locator('.run-output').inner_text())
            wrap.locator('.code-input').fill(starter)
            count += 1
        for form in page.locator('form.activity-quiz').all():
            answer(form)
            quizzes += 1
        assert not errors, errors
        check(f'actual English book: {count} Python examples, {validators} validators, {quizzes} quizzes; no browser errors')
    finally:
        context.close()
