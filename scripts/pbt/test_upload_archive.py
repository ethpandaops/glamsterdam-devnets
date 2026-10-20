"""Exercise the actual tar exclusions with native layouts and dummy credentials."""
import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

from upload import archive_command


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


if __name__=='__main__':unittest.main()
