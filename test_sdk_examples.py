"""Offline SDK evidence checks, loaded by test-build.py. Browser checks are separate."""
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path
import hashlib
import io
import json
import unittest

from bs4 import BeautifulSoup
from nacl.signing import VerifyKey
from nacl.exceptions import BadSignatureError
from pycardano.exception import InvalidArgumentException
from pycardano import (
    Transaction, TransactionBody, TransactionWitnessSet, PaymentVerificationKey,
    ScriptPubkey, Metadata, AuxiliaryData, NativeScript, MultiAsset, Address, PaymentSigningKey,
)
import build
from curriculum_test_cases import execute, implementations

SDK_IDS = {
    'shelley-address-components', 'body-cbor-sdk-demo', 'body-hash-bytes-demo', 'body-hash-witness-message',
    'serialized-publication-fee', 'key-witness-sign-verify', 'cip30-witness-merge',
    'metadata-auxiliary-commitment', 'multiasset-policy-identity',
    'native-policy-cbor', 'native-multisig-window',
}


class SDKExampleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, html, _ = build.render_book('pt-BR', build.read_sources(build.ROOT))
        cls.doc = BeautifulSoup(html, 'html.parser')
        cls.fixture = json.loads((build.ROOT/'sdk_example_fixtures.json').read_text())

    def example(self, identity, repair=False):
        source = self.doc.select_one(f'pre[data-exercise-id="{identity}"] code').get_text()
        if repair:
            source, _ = implementations(identity, source)
        with redirect_stdout(io.StringIO()):
            return execute(source, identity)

    def test_sdk_scope_and_teaching_sequence(self):
        self.assertEqual({p['data-exercise-id'] for p in self.doc.select('pre[data-python-packages]')}, SDK_IDS)
        for identity in SDK_IDS:
            pre = self.doc.select_one(f'[data-exercise-id="{identity}"]')
            self.assertEqual(pre['data-python-packages'], 'pycardano-workshop-0.19.2-pyodide-314.0.7-v1')
        for lesson in ('aula-1-5', 'aula-1-8', 'aula-1-9', 'aula-1-10'):
            self.assertNotRegex(self.doc.select_one('#'+lesson).get_text(' ',strip=True),
                                r'Pyodide|micropip|314\.0\.7|0\.19\.2|TransacaoDidatica|sig-A|sig-B')
        for demo, exercise in [('key-witness-sign-verify','cip30-witness-merge'),
                               ('native-policy-cbor','native-multisig-window')]:
            pre = self.doc.select_one(f'[data-exercise-id="{demo}"]')
            self.assertIsNone(pre.find_parent(class_='activity'))
            self.assertIn(self.doc.select_one(f'[data-exercise-id="{exercise}"]'), list(pre.find_all_next('pre')))
        for lesson in ('aula-1-12', 'aula-1-13'):
            self.assertFalse(self.doc.select_one('#'+lesson).select('[data-python-packages]'))

    def test_shelley_address_components_match_cip19_vectors(self):
        pre = self.doc.select_one('pre[data-exercise-id="shelley-address-components"]')
        output = io.StringIO()
        with redirect_stdout(output):
            values = execute(pre.code.get_text(), 'shelley-address-components')
        self.assertEqual(output.getvalue().splitlines(), [
            'Rede: TESTNET', 'Base: 57 bytes', 'Enterprise: 29 bytes', 'Reward: 29 bytes'])
        base = values['endereco_base']
        enterprise = values['endereco_enterprise']
        reward = values['endereco_reward']
        # CIP-19 Test Vectors, testnet type-06 and type-14.
        self.assertEqual(enterprise.encode(),
                         'addr_test1vz2fxv2umyhttkxyxp8x0dlpdt3k6cwng5pxj3jhsydzerspjrlsz')
        self.assertEqual(reward.encode(),
                         'stake_test1uqehkck0lajq8gr28t9uxnuvgcqrc6070x3k9r8048z8y5gssrtvn')
        self.assertEqual(base.payment_part, enterprise.payment_part)
        self.assertEqual(base.staking_part, reward.staking_part)
        self.assertIsNone(enterprise.staking_part)
        self.assertIsNone(reward.payment_part)
        for address, header, size in ((base, 0x00, 57), (enterprise, 0x60, 29), (reward, 0xe0, 29)):
            self.assertEqual(bytes(address)[0], header)
            self.assertEqual(len(bytes(address)), size)
            self.assertEqual(address.network.name, 'TESTNET')
            self.assertEqual(Address.from_primitive(address.encode()), address)

    def test_publication_size_fee_and_batch_use_one_measurement(self):
        values = self.example('serialized-publication-fee')
        tx = values['publicacao']
        self.assertEqual(tx.to_cbor_hex(), self.fixture['publication_tx_cbor'])
        self.assertEqual(len(tx.to_cbor()), 306)
        self.assertEqual(len(values['sem_assinatura'].to_cbor()), 203)
        params = self.fixture['protocol_source']['protocol_parameters']
        self.assertEqual((values['a'], values['b']), (params['txFeePerByte'],params['txFeeFixed']))
        self.assertEqual(44*len(tx.to_cbor())+155381, self.fixture['minimum_fee'])
        self.assertEqual(self.fixture['minimum_fee'],168845)
        self.assertGreaterEqual(tx.transaction_body.fee, self.fixture['minimum_fee'])
        batch = self.example('batch-cost-window-demo')
        activity = self.example('batch-publication-count',repair=True)
        self.assertEqual(batch['bytes_por_transacao'],len(tx.to_cbor()))
        self.assertEqual(batch['taxa'],self.fixture['minimum_fee'])
        self.assertEqual(activity['publicacoes'],3)
        self.assertEqual(tx.auxiliary_data.data.metadata[1001]['root'].hex(),self.fixture['merkle_root'])
        self.assertEqual(self.example('merkle-four-leaf-demo')['raiz_publicada'].hex(),self.fixture['merkle_root'])
        self.assertEqual(tx.transaction_body.auxiliary_data_hash,tx.auxiliary_data.hash())
        for w in tx.transaction_witness_set.vkey_witnesses:
            VerifyKey(w.vkey.payload).verify(tx.transaction_body.hash(),w.signature)

    def test_publication_witnesses_are_reproducible_with_public_teaching_keys(self):
        # Public deterministic examples only. These keys must never hold funds.
        keys = [PaymentSigningKey(hashlib.sha256(f'cardano-booklet-public-example-{i}'.encode()).digest())
                for i in range(3)]
        self.assertEqual([k.to_verification_key().payload.hex() for k in keys], self.fixture['verification_keys'])
        message = bytes.fromhex(self.fixture['publication_body_hash'])
        for field, key in zip(('existing_witnesses_cbor', 'received_witnesses_cbor'), keys):
            package = TransactionWitnessSet.from_cbor(self.fixture[field])
            self.assertEqual(package.vkey_witnesses[0].signature, key.sign(message))

    def test_signature_is_real_and_changed_message_fails(self):
        values = self.example('key-witness-sign-verify')
        w = values['witness']; message = values['mensagem']
        self.assertEqual(message.hex(),self.fixture['publication_body_hash'])
        self.assertEqual(len(w.vkey.payload),32); self.assertEqual(len(w.signature),64)
        VerifyKey(w.vkey.payload).verify(message,w.signature)
        with self.assertRaises(BadSignatureError):
            VerifyKey(w.vkey.payload).verify(bytes([message[0]^1])+message[1:],w.signature)
        with self.assertRaises(BadSignatureError):
            VerifyKey(w.vkey.payload).verify(message,bytes([w.signature[0]^1])+w.signature[1:])

    def test_merged_witnesses_preserve_body_and_auxiliary_data(self):
        values = self.example('cip30-witness-merge',repair=True)
        tx = Transaction.from_cbor(self.fixture['publication_tx_cbor'])
        before = tx.transaction_body.to_cbor(),tx.auxiliary_data.to_cbor(),tx.valid
        tx.transaction_witness_set = values['resultado']
        decoded = Transaction.from_cbor(tx.to_cbor())
        self.assertEqual((decoded.transaction_body.to_cbor(),decoded.auxiliary_data.to_cbor(),decoded.valid),before)
        self.assertEqual(len(decoded.transaction_witness_set.vkey_witnesses),2)
        for w in decoded.transaction_witness_set.vkey_witnesses:
            VerifyKey(w.vkey.payload).verify(decoded.transaction_body.hash(),w.signature)
        changed = deepcopy(decoded.transaction_body); changed.fee += 1
        with self.assertRaises(BadSignatureError):
            w = decoded.transaction_witness_set.vkey_witnesses[0]
            VerifyKey(w.vkey.payload).verify(changed.hash(),w.signature)

    def test_metadata_types_commitment_and_size_limit(self):
        values = self.example('metadata-auxiliary-commitment')
        aux = values['anexo']
        decoded = AuxiliaryData.from_cbor(aux.to_cbor())
        self.assertEqual(decoded.to_cbor(),aux.to_cbor())
        self.assertEqual(values['dados'][1001], {'mensagem': 'Olá, Cardano!'})
        self.assertEqual(aux.hash().payload.hex(),'87d9d63d8d5fe36c17a8a815384228371bf3b26b9126be041939e146e9911e62')
        changed = deepcopy(aux)
        changed.data.metadata[1001]['mensagem'] = 'Olá, Ada!'
        self.assertNotEqual(changed.hash(),aux.hash())
        changed.data.metadata[1001]['mensagem'] = 'Olá, Cardano!'
        self.assertEqual(changed.hash(),aux.hash())
        for invalid in [{'1001': 'wrong label'}, {1001: 'é'*33}, {1001: bytes(65)}]:
            with self.assertRaises(InvalidArgumentException):
                Metadata(invalid)

    def test_asset_identity_and_policy_origins(self):
        values = self.example('multiasset-policy-identity')
        saldo = MultiAsset.from_cbor(values['saldo'].to_cbor())
        self.assertEqual(len(saldo),2)
        self.assertEqual(saldo[values['p1']][values['nome']],50)
        self.assertEqual(saldo[values['p2']][values['nome']],7)
        self.assertEqual(saldo[values['p1']][values['minusculo']],3)
        for public, key_hash, policy_id in zip(self.fixture['verification_keys'], self.fixture['key_hashes'],self.fixture['policy_ids']):
            key = PaymentVerificationKey.from_primitive(bytes.fromhex(public))
            self.assertEqual(key.hash().payload.hex(),key_hash)
            self.assertEqual(ScriptPubkey(key.hash()).hash().payload.hex(),policy_id)

    def test_native_policy_demo_and_repair_agree(self):
        demo = self.example('native-policy-cbor')
        activity = self.example('native-multisig-window',repair=True)
        original = self.example('native-multisig-window')
        self.assertEqual(demo['politica'].to_cbor(),activity['politica'].to_cbor())
        self.assertNotEqual(original['politica'].hash(),activity['politica'].hash())
        self.assertEqual(NativeScript.from_cbor(demo['politica'].to_cbor()).hash(),demo['politica'].hash())
        self.assertEqual(demo['politica'].hash().payload.hex(),'5e279f8b3de340b354a78d4ba334b8b25d2079d15448099c78a268b4')
