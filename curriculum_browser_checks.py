"""Browser assertions for authored exercises and intentional curriculum revisions."""
import json
from playwright.sync_api import expect
from curriculum_test_cases import implementations


def check_authored_exercises(page, root, run, open_ancestors, check):
    for pre in root.select('pre[data-validator]'):
        exercise = pre['data-exercise-id']
        wrap = page.locator(f'pre[data-exercise-id="{exercise}"]').locator('..')
        open_ancestors(wrap)
        if wrap.locator('.code-input').is_hidden():
            wrap.locator('.edit-code-btn').click()
        starter = pre.code.get_text()
        repair, mutations = implementations(exercise, starter)
        mistakes = mutations if pre.has_attr('data-python-packages') else mutations[:1]
        cases = [(starter, 'mismatch'), (repair, 'validated')] + [(source, 'mismatch') for source in mistakes]
        for source, expected in cases:
            wrap.locator('.code-input').fill(source)
            state = run(page, wrap, True)
            assert state == expected, (exercise, expected, state, wrap.locator('.run-output').inner_text())
        # Leave the published starter, not our solution, in this disposable profile.
        wrap.locator('.code-input').fill(starter)
        check(f'authored {exercise}: starter and {len(mistakes)} plausible mistake(s) rejected, repair validated')

    pre = root.select_one('[data-exercise-id="ed25519-message-verification"]')
    wrap = page.locator('[data-exercise-id="ed25519-message-verification"]').locator('..')
    open_ancestors(wrap)
    if wrap.locator('.code-input').is_hidden():
        wrap.locator('.edit-code-btn').click()
    source = pre.code.get_text()
    wrap.locator('.code-input').fill(source)
    assert run(page, wrap) == 'success'
    assert wrap.locator('.run-output').inner_text().splitlines() == [
        'Assinatura confere: falha de comunicação',
        'Assinatura não confere: Falha de comunicação']
    # Verify two identical messages with one key pair and signature.
    wrap.locator('.code-input').fill(source.replace('"Falha de comunicação"', 'mensagem_original'))
    assert run(page, wrap) == 'success'
    assert wrap.locator('.run-output').inner_text().splitlines() == [
        'Assinatura confere: falha de comunicação'] * 2
    wrap.locator('.code-input').fill(source)
    check('Ed25519: declared package loads; changed message rejected, identical messages accepted')


CODE_SNAPSHOT = '''() => Array.from(document.querySelectorAll('pre')).filter(p => p._studyEditor).map(p => {
    const id = p.getAttribute('data-validator'), validator = id && document.getElementById(id);
    return {
        descriptor: JSON.stringify([p.getAttribute('data-exercise-id'), p.getAttribute('data-progress-id'),
            p.querySelector('code').textContent, p.getAttribute('data-exercise-version') || '1',
            id, validator ? validator.textContent : null, p.getAttribute('data-python-package'), p.getAttribute('data-python-packages')]),
        key: p._studyEditor.storage.key,
        value: p._studyEditor.value(), result: p._studyEditor.result()
    };
})'''
RECORDS = '''() => Object.fromEntries(Object.entries(localStorage).filter(([key]) => key.startsWith('cardano-booklet.study.')))'''


def check_curriculum_migration(context, url, answer, check):
    # Dedicated context: synthetic stale passes exercise the actual revision guard,
    # without modifying or deleting any reader's records or the regular test profile.
    page = context.new_page()
    page.goto(url + '/before-curriculum', wait_until='domcontentloaded')
    before = page.evaluate(CODE_SNAPSHOT)
    old_by_descriptor = {entry['descriptor']: entry for entry in before}
    old_keys = {entry['key'] for entry in before}
    page.locator('pre').evaluate_all('''nodes => nodes.filter(p => p._studyEditor).forEach((p, i) => {
        const input = p.parentElement.querySelector('.code-input');
        input.value = 'historical draft ' + i;
        input.dispatchEvent(new Event('input', {bubbles:true}));
        p._studyEditor.setResult({status:'validated', output:'historical pass'});
    })''')
    quiz = page.locator('#quiz-aula-1-3-a1')
    answer(quiz)
    score = quiz.locator('.quiz-status').last.inner_text()
    records = page.evaluate(RECORDS)
    page.goto(url, wait_until='domcontentloaded')
    after = page.evaluate(CODE_SNAPSHOT)
    matched = revised = 0
    for entry in after:
        if entry['key'] in old_keys:
            saved = json.loads(records[entry['key']])['data']
            assert entry['value'] == saved['code']
            assert entry['result'] == saved['result']
            matched += 1
        else:
            assert not entry['value'].startswith('historical draft ')
            assert entry['result'] is None
            revised += 1
    # Assert every unchanged source still resolves to the old key, independently of
    # the retention checks above. A key accidentally changing must not escape as new.
    clean = context.browser.new_context()
    try:
        clean_page = clean.new_page()
        clean_page.goto(url, wait_until='domcontentloaded')
        for entry in clean_page.evaluate(CODE_SNAPSHOT):
            previous = old_by_descriptor.get(entry['descriptor'])
            if previous:
                assert entry['key'] == previous['key'], 'unchanged example lost its identity'
            else:
                assert entry['key'] not in old_keys, 'revised example inherited an obsolete identity'
    finally:
        clean.close()
    expect(page.locator('#quiz-aula-1-3-a1 .quiz-status').last).to_have_text(score)
    retained = page.evaluate(RECORDS)
    assert all(retained.get(key) == value for key, value in records.items()), 'old records were changed or deleted'
    assert matched > 0 and revised > 0
    check(f'curriculum migration: {matched} unchanged code blocks restore; {revised} revised/new blocks reject obsolete drafts/passes; {len(records)} old records intact; M1 quiz grade restored')
    page.close()
