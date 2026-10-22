"""Protect the original H producer when preparing its local v3 conversion."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    'upgrade_head', Path(__file__).with_name('upgrade-erigon-head-v3.py'))
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)
spec = importlib.util.spec_from_file_location('worker', Path(__file__).with_name('qualify-worker.py'))
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)


class PreservedHead(unittest.TestCase):
    def setUp(self):
        self.proof = {
            'client': 'erigon', 'stopped': True, 'verified_bal_bodies': 51420,
            'image': 'fixture-pinned-image',
            'head': {'number': hex(24503958),
                     'hash': '0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216',
                     'stateRoot': '0x8cab6f81e370f341e67e66d2333cdf3e6074861f861aa3e490b9411460ad7f22'}}
        self.container = {
            'State': {'Running': False, 'OOMKilled': False, 'ExitCode': 0},
            'Config': {'Image': 'fixture-pinned-image'},
            'Mounts': [{'Source': '/data/pbt-1/erigon', 'Destination': '/data'}]}

    def test_stopped_h_producer_accepted(self):
        upgrade.validate_preserved_head(self.proof, self.container)

    def test_old_exporter_or_wrong_root_rejected(self):
        for field, value in [('number', hex(24452538)), ('hash', 'other'),
                             ('stateRoot', 'other')]:
            proof = copy.deepcopy(self.proof)
            proof['head'][field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                upgrade.validate_preserved_head(proof, self.container)

    def test_wrong_datadir_or_running_container_rejected(self):
        container = copy.deepcopy(self.container)
        container['Mounts'][0]['Source'] = '/data/pbt-1/rehearsal-24453558/erigon'
        with self.assertRaises(AssertionError):
            upgrade.validate_preserved_head(self.proof, container)
        container = copy.deepcopy(self.container)
        container['State']['Running'] = True
        with self.assertRaises(AssertionError):
            upgrade.validate_preserved_head(self.proof, container)

    def test_partial_bal_audit_rejected(self):
        with self.assertRaises(AssertionError):
            upgrade.validate_preserved_head({**self.proof, 'verified_bal_bodies': 3},
                                            self.container)


class OptimizedHandoff(unittest.TestCase):
    def peer(self):
        build = {'base_commit': upgrade.COMMIT, 'patch_sha256': upgrade.PATCH_SHA,
                 'binary_sha256': upgrade.CANDIDATE_SHA,
                 'independent_verifier_sha256': upgrade.EXPECTED['integration']}
        proof = {'host': 'lighthouse-erigon-2', 'client': 'erigon', 'status': 'startup_checks_passed',
                 'head': upgrade.TARGET,
                 'head_hash': '0x47c3596789c3d65824cb157d470e558266242bf2415b900ab81299c022a2d216',
                 'state_root': '0x8cab6f81e370f341e67e66d2333cdf3e6074861f861aa3e490b9411460ad7f22',
                 'commit': upgrade.COMMIT,
                 'image': 'registry-1.docker.io/ethpandaops/erigon@sha256:4aec40c643590ec9496c982b22f0efb04835ff071233e92c418f9380cc84db69',
                 'memory_gib': 16, 'cpus': 8, 'network_mode': 'none',
                 'native_reopen_verified': True, 'v3_format_verified': True,
                 'missing_builder_contracts': [], 'converter_build': build,
                 'first_stopped_state': {'Running': False, 'OOMKilled': False, 'ExitCode': 0},
                 'stopped_state': {'Running': False, 'OOMKilled': False, 'ExitCode': 0}}
        phases = {}
        for name in ('convert-v3', 'verify-v3-files', 'restore-head-block', 'verify-v3-state'):
            args = ['stage_exec', '--block=24503958'] if name == 'restore-head-block' else [
                'commitment', 'convert' if name == 'convert-v3' else 'verify']
            phases[name] = {'exit_code': 0, 'binary_sha256': upgrade.EXPECTED['integration'],
                            'command': ['binary', *args, '--datadir=' + str(upgrade.SOURCE)], 'no_prune_env': 'true'}
        phases['convert-v3'].update(binary_sha256=upgrade.CANDIDATE_SHA, converter_build=build)
        return {'proof': proof, 'conversion': {'source': str(upgrade.SOURCE), 'target_block': upgrade.TARGET,
                                              'converter_build': build}, 'phases': phases}

    def test_completed_peer_requires_reopens_and_original_verifiers(self):
        peer = self.peer()
        upgrade.validate_peer_qualification(peer, qualifier)
        for key, value in [('native_reopen_verified', False), ('v3_format_verified', False),
                           ('host', 'lighthouse-erigon-1'), ('head', 24452538),
                           ('state_root', 'wrong'), ('status', 'starting')]:
            changed = copy.deepcopy(peer)
            changed['proof'][key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                upgrade.validate_peer_qualification(changed, qualifier)
        for name in ('verify-v3-files', 'restore-head-block', 'verify-v3-state'):
            changed = copy.deepcopy(peer)
            changed['phases'][name]['binary_sha256'] = upgrade.CANDIDATE_SHA
            with self.subTest(phase=name), self.assertRaises(AssertionError):
                upgrade.validate_peer_qualification(changed, qualifier)

    def test_peer_must_restore_H_with_BAL_retention(self):
        for key, value in [('command', ['binary', 'stage_exec', '--block=24452538', '--datadir=' + str(upgrade.SOURCE)]),
                           ('no_prune_env', None), ('exit_code', 1)]:
            peer = self.peer()
            peer['phases']['restore-head-block'][key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                upgrade.validate_peer_qualification(peer, qualifier)

    def test_changed_peer_proof_prevents_file_selection(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(upgrade, 'ROOT', Path(directory)), \
                patch.object(upgrade, 'bounded_review', return_value=({}, [], 'changed')):
            with self.assertRaises(AssertionError):
                upgrade.select_bounded_fragments('lighthouse-erigon-1', 'original')
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_selection_preserves_merged_files_and_unrelated_data(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source'
            domain = source / 'snapshots/domain'
            domain.mkdir(parents=True)
            names = ['merged.kv', 'merged.bt', 'merged.kvei']
            for name in names:
                (domain / name).write_text(name)
            (domain / 'retained-fragment.kv').write_text('preserved')
            (source / 'chaindata').mkdir()
            with patch.object(upgrade, 'ROOT', root), patch.object(upgrade, 'SOURCE', source), \
                    patch.object(upgrade, 'bounded_review', return_value=({}, [{'name': n} for n in names], 'proof')):
                upgrade.select_bounded_fragments('lighthouse-erigon-1', 'proof')
            for name in names:
                self.assertEqual((root / 'bounded-selection/hidden-domain-files' / name).read_text(), name)
                self.assertFalse((domain / name).exists())
            self.assertEqual((domain / 'retained-fragment.kv').read_text(), 'preserved')
            self.assertTrue((source / 'chaindata').is_dir())


if __name__ == '__main__':
    unittest.main()
