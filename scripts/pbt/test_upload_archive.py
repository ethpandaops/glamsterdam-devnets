"""Exercise the actual tar exclusions with native layouts and dummy credentials."""
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from upload import archive_command, validate_v3_head_proof


class ArchiveExclusions(unittest.TestCase):
    def test_nethermind_keystore_and_patricia_are_not_archived(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            private=['mainnet/keystore/node.key.plain','keystore/account.json',
                     'nodekey','jwtsecret','key','mainnet/state/old.sst']
            public=['mainnet/flat/part.sst','mainnet/blocks/part.sst']
            for name in private+public:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text('dummy fixture')
            data=subprocess.check_output(archive_command('nethermind',root))
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                names={m.name.removeprefix('./') for m in archive if m.isfile()}
            self.assertEqual(names,set(public))

    def test_erigon_temp_is_omitted_but_native_state_is_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ['temp/unfinished','nodekey','chaindata/mdbx.dat','snapshots/domain/state.kv']:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('dummy fixture')
            data=subprocess.check_output(archive_command('erigon',root))
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                names={m.name.removeprefix('./') for m in archive if m.isfile()}
            self.assertEqual(names,{'chaindata/mdbx.dat','snapshots/domain/state.kv'})

    def test_v3_source_omits_rollback_files_but_keeps_v3_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            kept={'chaindata/mdbx.dat','snapshots/domain/v3.0-commitment.0-1.kv',
                  'erigondb.toml','snapshots/erigondb.toml'}
            omitted={'snapshots/backup/domains/legacy.kv','snapshots/rebuild/domain/partial',
                     'snap/rebuild/domain/partial','jwtsecret','temp/unfinished'}
            for name in kept | omitted:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
            data=subprocess.check_output(archive_command('erigon',root,v3_source=True))
            with tarfile.open(fileobj=io.BytesIO(data)) as archive:
                names={m.name.removeprefix('./') for m in archive if m.isfile()}
            self.assertEqual(names,kept)


class V3HeadPublicationProof(unittest.TestCase):
    def setUp(self):
        jobs=Path(__file__).resolve().parents[2]/'ansible/inventories/pbt-1/files/qualification-jobs.json'
        self.proof=json.loads(jobs.read_text())['lighthouse-erigon-2']
        stopped={'Running':False,'OOMKilled':False,'ExitCode':0}
        self.proof.update(status='startup_checks_passed',native_reopen_verified=True,
                          v3_format_verified=True,cpus=8,network_mode='none',
                          missing_builder_contracts=[],first_stopped_state=dict(stopped),
                          stopped_state=dict(stopped))
        self.conversion={'source':'/data/pbt-1/erigon','target_block':24503958}

    def test_exact_h_with_two_v3_opens_accepted(self):
        validate_v3_head_proof(self.proof,self.conversion)

    def test_patched_conversion_provenance_must_match_reopen_proof(self):
        build={'binary_sha256':'candidate','patch_sha256':'reviewed-patch'}
        converted={**self.conversion,'converter_build':build}
        with self.assertRaises(AssertionError):
            validate_v3_head_proof(self.proof,converted)
        validate_v3_head_proof({**self.proof,'converter_build':build},converted)
        with self.assertRaises(AssertionError):
            validate_v3_head_proof({**self.proof,'converter_build':{'binary_sha256':'other'}},converted)

    def test_older_exporter_block_or_datadir_rejected(self):
        for conversion in [
            {'source':'/data/pbt-1/erigon','target_block':24452538},
            {'source':'/data/pbt-1/rehearsal-24453558/erigon','target_block':24503958}]:
            with self.subTest(conversion=conversion),self.assertRaises(AssertionError):
                validate_v3_head_proof(self.proof,conversion)

    def test_unverified_conversion_or_reopen_rejected(self):
        for field in ('native_reopen_verified','v3_format_verified'):
            with self.subTest(field=field),self.assertRaises(AssertionError):
                validate_v3_head_proof({**self.proof,field:False},self.conversion)

    def test_wrong_host_image_or_state_rejected(self):
        for field in ('host','image','head_hash','state_root'):
            with self.subTest(field=field),self.assertRaises(AssertionError):
                validate_v3_head_proof({**self.proof,field:'different'},self.conversion)

    def test_unclean_either_stop_rejected(self):
        for field in ('first_stopped_state','stopped_state'):
            with self.subTest(field=field),self.assertRaises(AssertionError):
                validate_v3_head_proof(
                    {**self.proof,field:{'Running':False,'OOMKilled':True,'ExitCode':137}},
                    self.conversion)


if __name__=='__main__':unittest.main()
