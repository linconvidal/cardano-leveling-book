"""Test-only repairs and plausible mistakes for the book's authored validators.

These transform the real starters; tests remain the JSON authored in each lesson.
Nothing in this module is bundled into the book or used to grade learners.
"""
# exercise ID: (exact starter fragment, repair, incorrect replacement repairs)
REPAIRS = {
    'utf8-byte-roundtrip': (
        'mensagem_recuperada = mensagem_em_base64',
        'mensagem_recuperada = base64.b64decode(mensagem_em_base64).decode("utf-8")',
        ['mensagem_recuperada = base64.b64decode(mensagem_em_base64)',
         'mensagem_recuperada = base64.b64decode(mensagem_em_base64).decode("latin-1")']),
    'secret-length-log': (
        'registro = segredo.hex()',
        'registro = len(segredo)',
        ['registro = len(segredo.hex())', 'registro = segredo']),
    'body-hash-witness-message': (
        'corpo.ttl = nova_taxa\n    return corpo.to_cbor_hex(), corpo.hash()',
        'corpo.fee = nova_taxa\n    return corpo.to_cbor_hex(), corpo.hash()',
        ['corpo.fee = nova_taxa\n    return corpo.to_cbor_hex(), TransactionBody.from_cbor(body_cbor_hex).hash()',
         'corpo.fee = nova_taxa\n    import hashlib\n'
         '    from pycardano import Transaction, TransactionWitnessSet\n'
         '    envelope = Transaction(transaction_body=corpo, transaction_witness_set=TransactionWitnessSet())\n'
         '    return corpo.to_cbor_hex(), hashlib.blake2b(envelope.to_cbor(), digest_size=32).digest()']),
    'cip30-witness-merge': (
        'resultado.vkey_witnesses = unir(None, recebidas.vkey_witnesses)',
        'resultado.vkey_witnesses = unir(existentes.vkey_witnesses, recebidas.vkey_witnesses)',
        ['resultado.vkey_witnesses = unir(existentes.vkey_witnesses, None)',
         'resultado = existentes\n    resultado.vkey_witnesses = unir(existentes.vkey_witnesses, recebidas.vkey_witnesses)']),
    'native-multisig-window': (
        'ScriptPubkey(chaves[0]), ScriptPubkey(chaves[0]), ScriptPubkey(chaves[2])',
        'ScriptPubkey(chaves[0]), ScriptPubkey(chaves[1]), ScriptPubkey(chaves[2])',
        ['ScriptPubkey(chaves[0]), ScriptPubkey(chaves[1]), ScriptPubkey(chaves[1])',
         'ScriptPubkey(chaves[0]), ScriptPubkey(chaves[1])']),
    'plutus-successor-effects': (
        'return redeemer == "Incrementar"',
        'if redeemer != "Incrementar" or len(sucessoras) != 1:\n        return False\n'
        '    nova = sucessoras[0]\n'
        '    return (nova["script"] == anterior["script"] and nova["valor"] == anterior["valor"]\n'
        '            and nova["versao"] == anterior["versao"] + 1)',
        ['return len(sucessoras) == 1 and sucessoras[0]["versao"] == anterior["versao"] + 1',
         'return redeemer == "Incrementar" and any(s["versao"] == anterior["versao"] + 1 for s in sucessoras)']),
    'cip68-reference-name': (
        'return nome_usuario',
        'if not 4 <= len(nome_usuario) <= 32 or nome_usuario[:4].hex() not in ("000de140", "0014df10", "001bc280"):\n'
        '        raise ValueError("nome inválido")\n'
        '    return bytes.fromhex("000643b0") + nome_usuario[4:]',
        ['return bytes.fromhex("000643b0") + nome_usuario[4:]',
         'if not 4 <= len(nome_usuario) <= 32 or nome_usuario[:4].hex() != "000de140":\n'
         '        raise ValueError("nome inválido")\n'
         '    return bytes.fromhex("000643b0") + nome_usuario[4:]']),
    'event-checkpoint-prefix': (
        '    return True\n\ncadeia = []',
        '    if len(cadeia) < quantidade:\n        return False\n'
        '    return hash_evento(cadeia[quantidade - 1]) == cabeca\n\ncadeia = []',
        ['    return bool(cadeia) and hash_evento(cadeia[-1]) == cabeca\n\ncadeia = []',
         '    return len(cadeia) >= quantidade\n\ncadeia = []']),
    'merkle-sibling-order': (
        'atual = no(atual, irmao)',
        'atual = no(irmao, atual) if lado == "E" else no(atual, irmao)',
        ['atual = no(irmao, atual)', 'atual = no(*sorted((atual, irmao)))']),
    'batch-publication-count': (
        'return len(grupos)', 'return len(set(grupos))',
        ['return len(set(instantes))', 'return max(instantes) // janela + 1 if instantes else 0']),
    'nonce-opening-verifier': (
        'return comprometer(dados, bytes(16)) == esperado',
        'return comprometer(dados, nonce) == esperado',
        ['return len(esperado) == 32', 'return comprometer(dados, nonce) == comprometer(dados, nonce)']),
}


def implementations(exercise_id, starter):
    old, repair, mutations = REPAIRS[exercise_id]
    assert starter.count(old) == 1, f'{exercise_id}: starter changed; review the repair fixture'
    return starter.replace(old, repair), [starter.replace(old, mutation) for mutation in mutations]


def execute(source, name, namespace=None):
    namespace = {} if namespace is None else namespace
    exec(compile(source, name, 'exec'), namespace)
    return namespace


def validator_failures(source, tests, name):
    namespace = execute(source, name)
    failures = []
    for test in tests:
        try:
            execute(test['code'], name + ':' + test['name'], namespace)
        except Exception as error:
            failures.append((test['name'], type(error).__name__, str(error)))
    return failures
