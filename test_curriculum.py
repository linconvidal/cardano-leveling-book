"""Curriculum checks loaded by test-build.py; no network or browser required."""
from contextlib import redirect_stdout
import hashlib
import io
import json
import re
import unittest

from bs4 import BeautifulSoup
import build
from curriculum_test_cases import REPAIRS, execute, implementations, validator_failures


class CurriculumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = build.read_sources(build.ROOT)
        _, html, _ = build.render_book('pt-BR', cls.sources)
        cls.doc = BeautifulSoup(html, 'html.parser')

    def test_approved_sequence_and_introduction(self):
        expected = [f'aula-{module}-{number}' for module, count in ((0, 4), (1, 13), (2, 4))
                    for number in range(1, count + 1)]
        self.assertEqual([lesson['id'] for lesson in self.doc.select('article.lesson')], expected)
        for module, count in ((0, 4), (1, 13), (2, 4)):
            paths = [p for p in self.sources if re.fullmatch(rf'content/pt-BR/aula-{module}-\d+\.html', p)]
            self.assertEqual(len(paths), count)
        for anchor, subject in [('aula-1-4', 'governança'), ('aula-1-5', 'Shelley'),
                                ('aula-1-8', 'CIP-30'), ('aula-1-12', 'Plutus'),
                                ('aula-1-13', 'CIP-68'), ('aula-2-1', 'Eventos'),
                                ('aula-2-2', 'Merkle'), ('aula-2-3', 'Hydra'), ('aula-2-4', 'Privacidade')]:
            self.assertIn(subject, self.doc.select_one(f'#{anchor} .lesson-title').get_text())
        self.assertIsNone(self.doc.select_one('#rotas-de-leitura'))
        self.assertIsNone(self.doc.select_one('a[href="#rotas-de-leitura"]'))
        introduction = self.doc.select_one('#capa .cover-how').get_text(' ', strip=True)
        self.assertIn('Sobre este guia', introduction)
        for topic in ('workshop', 'Pyodide', 'JavaScript', 'salvos localmente', 'PDF'):
            self.assertIn(topic, introduction)
        self.assertNotIn('Como usar este material', introduction)
        # Reused 2.1-2.4 numbers are not aliases to the old wallet/crypto lessons.
        for lesson in self.doc.select('article.lesson'):
            text = lesson.get_text(' ', strip=True)
            self.assertNotRegex(text, r'\bAula\s+2\.(?:[5-9]|1[0-4])\b')
        for number in range(1, 4):
            self.assertIn(f'Aula 2.{number + 1}', self.doc.select_one(f'#aula-2-{number} > .bridge').get_text())
        self.assertIn('eventos encadeados e checkpoints', self.doc.select_one('#aula-1-13 > .bridge').get_text())

    def test_authored_identity_and_reference_destinations(self):
        for attribute in ('data-exercise-id', 'data-progress-id'):
            values = [node[attribute] for node in self.doc.select(f'[{attribute}]')]
            self.assertEqual(len(values), len(set(values)), attribute)
        exercises = self.doc.select('pre[data-validator]')
        self.assertEqual({p['data-exercise-id'] for p in exercises}, set(REPAIRS))
        for pre in exercises:
            self.assertTrue(pre.get('data-exercise-version'))
            self.assertNotRegex(pre['data-exercise-id'], r'aula-\d')
            config = json.loads(self.doc.find(id=pre['data-validator']).string)
            self.assertGreater(len(config['tests']), 0)
            self.assertEqual(len(config['tests']), len({t['name'] for t in config['tests']}))
        refs = self.doc.select_one('#referencias-modulo-1')
        urls = {a['href'] for a in refs.select('a[href]')}
        for cip in ('0001', '1694', '0005', '0019', '1852', '0030', '0025', '0067', '0068', '0031', '0032', '0040'):
            self.assertIn('https://cips.cardano.org/cip/CIP-' + cip, urls)
        self.assertIn('https://www.rfc-editor.org/rfc/rfc8032', urls)
        self.assertIn('https://www.rfc-editor.org/rfc/rfc8785', urls)

    def test_final_editorial_cleanup_and_plutus_objects(self):
        policy = self.doc.select_one('#aula-1-3 .activity')
        self.assertNotIn('Escreva os estados', policy.get_text())
        self.assertIn('reconheça o estado', policy.select_one('.box-label').get_text())
        self.assertEqual(len(policy.select('input[type="radio"]')), 3)
        self.assertEqual(policy.select_one('input[data-correct="true"]')['value'], 'a')
        utxo = self.doc.select_one('#aula-1-7').get_text(' ', strip=True)
        self.assertNotIn('parâmetros vigentes, assunto da próxima aula', utxo)
        self.assertIn('Na próxima aula, calcularemos a taxa e definiremos a validade', utxo)
        prereq = self.doc.select_one('#aula-1-9 .prereq')
        self.assertEqual({a['href'] for a in prereq.select('a')}, {'#aula-0-2', '#aula-1-6'})
        for name in ('aula-1-13.html', 'references-1.html'):
            self.assertNotRegex(self.sources['content/pt-BR/' + name], r'\bprefixes\b')
        figure = self.doc.select_one('#fig-aula-1-12-proposta')
        self.assertEqual(len(figure.select('use[href="#u7-note"]')), 2)
        self.assertIsNotNone(self.doc.select_one('#u7-note .utxo-note-cardano-mark'))
        self.assertEqual([n.get_text() for n in figure.select('.u12-value')], ['2 ₳', '2 ₳'])
        references = [n.get_text() for n in figure.select('.u12-serial')]
        self.assertEqual(len(set(references)), 2)
        for reference in references:
            self.assertRegex(reference, r'^[0-9a-f]{12}…#0$')
        self.assertEqual([n.get_text() for n in figure.select('.u12-version')], ['versão = 3', 'versão = 4'])
        self.assertEqual(len(figure.select('[data-visual-asset="objects/datum-compact.svg"]')), 2)
        self.assertIn('Saída proposta', figure.get_text())
        self.assertIn('se a transação for validada e incluída', figure.figcaption.get_text())

    def test_identifiers_and_diagram_labels_in_both_languages(self):
        for language in ('pt-BR', 'en'):
            with self.subTest(language=language):
                _, html, _ = build.render_book(language, self.sources)
                doc = BeautifulSoup(html, 'html.parser')
                for number in ('1-7', '1-12', '1-13'):
                    lesson = doc.select_one('#aula-' + number)
                    self.assertNotRegex(str(lesson), r'\b[a-z](?:…)?#\d\b')
                    for text in lesson.select('svg text'):
                        value = text.get_text().strip()
                        if '#' in value:
                            self.assertRegex(value, r'^[0-9a-f]{12}…#\d+$')
                payment = doc.select_one('#fig-aula-1-7-pagamento')
                outputs = [n.get_text() for n in payment.select('.u7-outputs .u7-serial')]
                self.assertEqual([ref.split('#')[1] for ref in outputs], ['0', '1'])
                self.assertEqual(outputs[0].split('#')[0], outputs[1].split('#')[0])
                self.assertNotEqual(payment.select_one('.u7-input .u7-serial').get_text().split('#')[0],
                                    outputs[0].split('#')[0])
                self.assertEqual([n['value'] for n in doc.select('#aula-1-7 input[data-correct="true"]')],
                                 ['c', 'b'])
                notes = [n.get_text() for n in doc.select('#aula-1-13 .output-ref')]
                self.assertEqual(len(notes), 5)
                self.assertEqual(len(set(notes)), 3)
                self.assertEqual(notes[1:4], [notes[1]] * 3)
                assets = doc.select_one('#aula-1-10')
                self.assertNotRegex(assets.get_text(' ', strip=True), r'\bP[12]\b')
                for text in assets.select('svg text'):
                    self.assertNotRegex(text.get_text(), r'^(?:Ativo|Asset) [ABC]$')
                example = assets.select_one('[data-exercise-id="multiasset-policy-identity"] code').get_text()
                policy_ids = re.findall(r'ScriptHash\(bytes.fromhex\("([0-9a-f]{56})"\)\)', example)
                self.assertEqual(len(policy_ids), 2)
                headings = [n.get_text() for n in assets.select('svg text.cap')]
                self.assertEqual([heading.split()[-1] for heading in headings],
                                 [policy_id[:12] + '…' for policy_id in policy_ids])
                privacy = doc.select_one('#aula-2-4')
                labels = [n.get_text(' ', strip=True) for n in privacy.select('svg text')]
                self.assertFalse(set(labels) & {'D', 'N', 'C', 'C′'})
                expected = (('Compromisso recalculado', 'Compromisso publicado') if language == 'pt-BR'
                            else ('Recalculated commitment', 'Published commitment'))
                for label in expected:
                    self.assertIn(label, labels)

    def test_record_identifier_matches_the_cip68_name_bytes(self):
        for language in ('pt-BR', 'en'):
            with self.subTest(language=language):
                _, html, _ = build.render_book(language, self.sources)
                doc = BeautifulSoup(html, 'html.parser')
                for number in ('1-12', '1-13'):
                    source = self.sources[f'content/{language}/aula-{number}.html']
                    self.assertNotIn('R-42', source)
                    self.assertNotIn('r-42.svg', source)
                    self.assertNotIn('522d3432', source)
                    self.assertIn('REC-0042', source)
                lesson = doc.select_one('#aula-1-13')
                demo = lesson.select_one('[data-exercise-id="cip68-labeled-names-demo"] code')
                with redirect_stdout(io.StringIO()):
                    values = execute(demo.get_text(), 'cip68-record-id')
                self.assertEqual(values['base'], b'REC-0042')
                self.assertIn(b'REC-0042'.hex(), lesson.get_text())
                user_key, reference_key = (('usuario', 'referencia') if language == 'pt-BR'
                                           else ('user', 'reference'))
                self.assertEqual(values[user_key].hex(), '000de140' + b'REC-0042'.hex())
                self.assertEqual(values[reference_key].hex(), '000643b0' + b'REC-0042'.hex())
                starter = lesson.select_one('[data-exercise-id="cip68-reference-name"] code').get_text()
                self.assertIn(values[user_key].hex(), starter)
                self.assertIn(values[reference_key].hex(), lesson.select_one('.answer').get_text())

    def test_governance_and_shelley_lesson_scope(self):
        governance = self.doc.select_one('#aula-1-4')
        shelley = self.doc.select_one('#aula-1-5')
        self.assertNotRegex(governance.get_text(' ', strip=True), r'Academy|CBCA|ficha de fonte')
        self.assertNotRegex(shelley.get_text(' ', strip=True), r'Icarus|BIP-39|PBKDF2')
        self.assertIn('ratificada', governance.get_text())
        self.assertIn('entra em vigor', governance.get_text())
        self.assertEqual(len(governance.select('.activity')), 1)
        self.assertEqual(len(shelley.select('.activity')), 1)
        for lesson, answers in ((governance, ['c']), (shelley, ['b', 'c'])):
            self.assertEqual([i['value'] for i in lesson.select('input[data-correct="true"]')], answers)
            for question in lesson.select('.quiz-question'):
                self.assertEqual(len(question.select('input[type="radio"]')), 4)
        refs = self.doc.select_one('#referencias-modulo-1').get_text(' ', strip=True)
        self.assertNotRegex(refs, r'Academy|CBCA|Icarus|BIP-39')

    def test_hash_lesson_uses_the_message_example_throughout(self):
        lesson = self.doc.select_one('#aula-0-2')
        self.assertEqual(len(lesson.select('pre[data-python-runner]')), 1)
        self.assertEqual(len(lesson.select('.activity')), 1)
        self.assertEqual(len(lesson.select('figure')), 3)
        self.assertNotRegex(lesson.get_text(' ', strip=True),
                            r'(?i)resumo|REL-2026|20\.04|20\.40|400 bytes|canônic|Argon2|PBKDF2|scrypt')
        example = lesson.select_one('[data-exercise-id="sha256-message-comparison"] code')
        output = io.StringIO()
        with redirect_stdout(output):
            values = execute(example.get_text(), 'hash-message-example')
        self.assertEqual(output.getvalue().splitlines(), [
            'falha de comunicação\td3b2d6009b1e4b0a06d8c7f213afcacce38aec7d16a8cc6866100b4c92457a67',
            'Falha de comunicação\ta7c21cccec0718c76999e1e77093840bb67b4d3ebcb28bf670a00eab3890448d'])
        self.assertEqual(sum(a != b for a, b in zip(values['hash_original'], values['hash_alterado'])), 61)
        quiz = lesson.select_one('#quiz-aula-0-2-a2')
        self.assertEqual(len(quiz.select('input[type="radio"]')), 4)
        self.assertEqual([item['value'] for item in quiz.select('[data-correct="true"]')], ['c'])
        self.assertIsNotNone(lesson.select_one('#atividade-aula-0-2-a2'))
        self.assertIn('atividade da Aula 0.2', self.doc.select_one('#aula-0-4 .closing').get_text())

    def test_signature_example_uses_real_verification(self):
        lesson = self.doc.select_one('#aula-0-4')
        self.assertEqual(len(lesson.select('pre[data-python-runner]')), 1)
        self.assertEqual(len(lesson.select('.activity')), 1)
        pre = lesson.select_one('[data-exercise-id="ed25519-message-verification"]')
        self.assertEqual(pre['data-python-package'], 'cryptography')
        output = io.StringIO()
        with redirect_stdout(output):
            values = execute(pre.code.get_text(), 'signature-example')
        self.assertEqual(output.getvalue().splitlines(), [
            'Assinatura confere: falha de comunicação',
            'Assinatura não confere: Falha de comunicação'])
        signature = values['assinatura']
        public_key = values['chave_publica']
        message = values['mensagem_original'].encode('utf-8')
        self.assertIsInstance(signature, bytes)
        self.assertEqual(len(signature), 64)
        public_key.verify(signature, message)
        other_key = values['ed25519'].Ed25519PrivateKey.generate().public_key()
        bad_signature = bytes([signature[0] ^ 1]) + signature[1:]
        for key, sig, data in [(public_key, signature, b'changed'),
                               (other_key, signature, message),
                               (public_key, bad_signature, message)]:
            with self.assertRaises(values['InvalidSignature']):
                key.verify(sig, data)

    def test_pycardano_demonstrations_prepare_the_activity(self):
        lesson = self.doc.select_one('#aula-1-6')
        examples = lesson.select('pre[data-python-packages]')
        self.assertEqual([pre['data-exercise-id'] for pre in examples], [
            'body-cbor-sdk-demo', 'body-hash-bytes-demo', 'body-hash-witness-message'])
        for demonstration in examples[:2]:
            self.assertIsNone(demonstration.find_parent(class_='activity'))
        self.assertIsNotNone(examples[2].find_parent(class_='activity'))
        self.assertNotRegex(examples[2].code.get_text(),
                            r'Address|TransactionInput|TransactionOutput|TransactionWitnessSet')
        self.assertNotRegex(lesson.get_text(' ', strip=True),
                            r'(?i)Pyodide|micropip|fixtures|provider|piloto|314\.0\.7|0\.19\.2')
        with redirect_stdout(io.StringIO()):
            build_example, hash_example, activity = [
                execute(pre.code.get_text(), pre['data-exercise-id']) for pre in examples]
        # Each independent example must use the same actual SDK-serialized body.
        cbor = build_example['corpo'].to_cbor()
        self.assertEqual(hash_example['corpo'].to_cbor(), cbor)
        self.assertEqual(activity['corpo_exemplo'].to_cbor(), cbor)
        self.assertEqual(hash_example['digest'], build_example['corpo'].hash())

    def test_every_runnable_example(self):
        examples = self.doc.select('pre > code.language-python')
        self.assertTrue(examples)
        for index, code in enumerate(examples):
            if code.parent.get('data-python-runner') == 'false':
                continue
            name = code.find_parent('article')['id'] + f':example-{index}'
            with self.subTest(example=name), redirect_stdout(io.StringIO()):
                execute(code.get_text(), name)

    def test_authored_validators_accept_repairs_and_reject_mistakes(self):
        for pre in self.doc.select('pre[data-validator]'):
            name = pre['data-exercise-id']
            tests = json.loads(self.doc.find(id=pre['data-validator']).string)['tests']
            starter = pre.code.get_text()
            repair, mutations = implementations(name, starter)
            with self.subTest(exercise=name), redirect_stdout(io.StringIO()):
                self.assertTrue(validator_failures(starter, tests, name), 'starter must not pass')
                self.assertEqual(validator_failures(repair, tests, name), [])
                for index, mutation in enumerate(mutations):
                    self.assertTrue(validator_failures(mutation, tests, name), f'mutation {index} must not pass')

    def test_fixed_merkle_reference(self):
        with redirect_stdout(io.StringIO()):
            merkle = execute(self.doc.select_one('[data-exercise-id="merkle-four-leaf-demo"] code').get_text(), 'merkle')
        self.assertEqual(merkle['raiz_publicada'].hex(), '2da39bbe8eb68096f77d903e70fb6b88b3d8d55ad8b4e8efa5f6f092c673163a')
        self.assertEqual(merkle['recalculada'], merkle['raiz_publicada'])
        for data in [b'', b'\x00', 'revisão'.encode('utf-8'), bytes(range(256))]:
            self.assertEqual(merkle['folha'](data), hashlib.sha256(b'\x00' + data).digest())
        left, right = merkle['A'], merkle['B']
        self.assertNotEqual(merkle['folha'](left + right), merkle['no'](left, right))

    def test_merkle_validators_require_the_index_path_even_for_identical_files(self):
        pre = self.doc.select_one('[data-exercise-id="merkle-sibling-order"]')
        tests = json.loads(self.doc.find(id=pre['data-validator']).string)['tests']
        repair, _ = implementations('merkle-sibling-order', pre.code.get_text())
        mistakes = [
            repair.replace('if lado != lado_esperado:', 'if lado not in ("E", "D"):'),
            repair.replace('        posicao //= 2\n', ''),
        ]
        with redirect_stdout(io.StringIO()):
            self.assertEqual(validator_failures(repair, tests, 'merkle'), [])
            for mistake in mistakes:
                self.assertNotEqual(mistake, repair)
                self.assertTrue(validator_failures(mistake, tests, 'merkle-index-path'))
