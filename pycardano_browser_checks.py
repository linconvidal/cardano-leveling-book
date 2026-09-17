"""Browser regressions for the opt-in PyCardano examples; never bundled."""
from playwright.sync_api import expect


PILOT = 'pre[data-exercise-id="body-hash-witness-message"]'
VANILLA = 'pre[data-exercise-id="hex-base64-roundtrip"]'


def check_pycardano_loading(page, root, run, open_ancestors, check):
    def editor(selector):
        wrap = page.locator(selector).locator('..')
        open_ancestors(wrap)
        if wrap.locator('.code-input').is_hidden():
            wrap.locator('.edit-code-btn').click()
        return wrap

    pilot = editor(PILOT)
    starter = root.select_one(PILOT).code.get_text()
    boundary = ('from js import globalThis\n'
                'assert globalThis.fetch is None\n'
                'assert globalThis.XMLHttpRequest is None\n')
    pilot.locator('.code-input').fill(boundary + 'from pycardano import TransactionBody\nprint("SDK ready, network disabled")')
    assert run(page, pilot) == 'success'
    expect(pilot.locator('.run-output')).to_have_text('SDK ready, network disabled')

    requests = []
    capture = lambda request: requests.append(request.url)
    page.on('request', capture)
    package_url = '**/pycardano-0.19.2-py3-none-any.whl'
    page.context.route(package_url, lambda route: route.abort())
    try:
        assert run(page, pilot) == 'error'
        assert 'não pôde ser carregado' in pilot.locator('.run-output').inner_text()
        assert any('pycardano-0.19.2-py3-none-any.whl' in url for url in requests)
    finally:
        page.context.unroute(package_url)
    check('PyCardano loads before the network cutoff; genuine package-download failure terminates cleanly')

    for action in ('cancel', 'edit'):
        pilot.locator('.code-input').fill('print("must not execute")')
        pilot.locator('.run-btn').click()
        expect(pilot.locator('.clear-output-btn')).to_be_hidden()
        if action == 'cancel':
            pilot.locator('.stop-code-btn').click()
            expect(pilot.locator('.run-status')).to_have_attribute('data-state', 'cancelled')
        else:
            pilot.locator('.code-input').fill('print("new draft while installing")')
            expect(pilot.locator('.run-output')).to_have_text('')
        expect(pilot.locator('.stop-code-btn')).to_be_hidden()
    check('cancel/edit during SDK loading terminate the run without publishing a stale result')

    requests.clear()
    vanilla = editor(VANILLA)
    vanilla.locator('.code-input').fill(boundary + 'import importlib.util\nassert importlib.util.find_spec("pycardano") is None\nprint(6 * 7)')
    assert run(page, vanilla) == 'success'
    expect(vanilla.locator('.run-output')).to_have_text('42')
    assert not any('.whl' in url or 'pypi.org/' in url for url in requests), requests
    page.remove_listener('request', capture)
    check('subsequent vanilla Worker succeeds without SDK leakage or any package requests')

    # Exercise unknown AND empty declarations before runtime initialization.
    declaration = 'data-python-packages="pycardano-workshop-0.19.2-pyodide-314.0.7-v1"'
    html = str(root)
    assert html.count(declaration) == 11
    original_url = page.url
    fixture_url = original_url.split('#')[0].split('?')[0].rstrip('/') + '/package-declaration'
    for value in ('unknown-package', ''):
        fixture = html.replace(declaration, 'data-python-packages="' + value + '"')
        page.route(fixture_url, lambda route: route.fulfill(status=200, content_type='text/html', body=fixture))
        try:
            page.goto(fixture_url, wait_until='domcontentloaded')
            invalid = editor(PILOT)
            assert run(page, invalid) == 'error'
            assert 'não pôde ser carregado' in invalid.locator('.run-output').inner_text()
        finally:
            page.unroute(fixture_url)
    page.goto(original_url, wait_until='domcontentloaded')
    editor(PILOT).locator('.code-input').fill(starter)
    editor(VANILLA).locator('.code-input').fill(root.select_one(VANILLA).code.get_text())
    check('unknown/empty package declarations fail closed; published starters restored in the test profile')

    expected_outputs = {
        'shelley-address-components': ['Rede: TESTNET', 'Base: 57 bytes', 'Enterprise: 29 bytes', 'Reward: 29 bytes'],
        'serialized-publication-fee': ['306 bytes; mínimo: 168845', '203 bytes; conta incompleta: 164313'],
        'metadata-auxiliary-commitment': ['87d9d63d8d5fe36c17a8a815384228371bf3b26b9126be041939e146e9911e62', 'mensagem: Olá, Cardano!'],
        'multiasset-policy-identity': ['544f4b454e 50', '544f4b454e 7', '746f6b656e 3'],
        'native-policy-cbor': ['5e279f8b3de340b354a78d4ba334b8b25d2079d15448099c78a268b4'],
        'key-witness-sign-verify': ['chave pública: 32 bytes', 'assinatura: 64 bytes'],
    }
    for identity, expected in expected_outputs.items():
        selector = f'pre[data-exercise-id="{identity}"]'
        source = root.select_one(selector).code.get_text()
        wrap = editor(selector)
        wrap.locator('.code-input').fill(source)
        assert run(page, wrap) == 'success', identity
        output = wrap.locator('.run-output').inner_text()
        assert all(fragment in output for fragment in expected), (identity, output)
        if identity == 'key-witness-sign-verify':
            wrong = source.replace('.verify(mensagem, witness.signature)', '.verify(bytes(32), witness.signature)')
            assert wrong != source
            wrap.locator('.code-input').fill(wrong)
            assert run(page, wrap) == 'error'
            assert 'BadSignatureError' in wrap.locator('.run-output').inner_text()
        elif identity == 'metadata-auxiliary-commitment':
            wrap.locator('.code-input').fill(source.replace('Olá, Cardano!', 'Olá, Ada!'))
            assert run(page, wrap) == 'success'
            assert expected[0] not in wrap.locator('.run-output').inner_text()
        elif identity == 'native-policy-cbor':
            wrap.locator('.code-input').fill(source.replace('InvalidHereAfter(200)', 'InvalidHereAfter(201)'))
            assert run(page, wrap) == 'success'
            assert expected[0] not in wrap.locator('.run-output').inner_text()
        wrap.locator('.code-input').fill(source)
        check(f'SDK {identity}: genuine browser output matches; published starter restored')
