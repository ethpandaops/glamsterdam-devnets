"""Early replay upload must preserve input identity and the four-client delivery gate."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

from bundle_records import index_records, index_digest, stream_archive

spec=importlib.util.spec_from_file_location('publisher',Path(__file__).with_name('publish-bundle.py'))
publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'blocks').mkdir()
        self.staging=self.root/'staging';self.staging.mkdir()
        for n in range(1,4):(self.root/f'blocks/{n:08d}.json.gz').write_bytes(bytes([n])*100)

    def test_index_detects_gap_and_changed_producer_bytes(self):
        entries=index_records(self.root,1,3);original=index_digest(entries)
        (self.root/'blocks/00000002.json.gz').write_bytes(b'changed')
        self.assertNotEqual(original,index_digest(index_records(self.root,1,3)))
        (self.root/'blocks/00000002.json.gz').unlink()
        with self.assertRaises(AssertionError):index_records(self.root,1,3)

    def test_stream_preserves_indexed_bytes_and_rejects_changes_after_indexing(self):
        entries=index_records(self.root,1,3)
        manifest={'records':entries,'artifacts':[]}
        (self.staging/'manifest.json').write_text(json.dumps(manifest))
        out=io.BytesIO();stream_archive(self.root,self.staging,out);out.seek(0)
        with tarfile.open(fileobj=out) as archive:
            for entry in entries:
                self.assertEqual(hashlib.sha256(archive.extractfile(entry['file']).read()).hexdigest(),entry['sha256'])
        (self.root/'blocks/00000003.json.gz').write_bytes(b'changed')
        with self.assertRaisesRegex(AssertionError,'Changed input'):
            stream_archive(self.root,self.staging,io.BytesIO())

    def test_remote_readback_rejects_same_length_corruption_and_replacement(self):
        class S3:
            body=b'good'
            calls=0
            replace=False
            def head_object(s,**kwargs):
                s.calls+=1
                return {'ContentLength':4,'ETag':str(s.calls if s.replace else 1)}
            def get_object(s,**kwargs):return {'Body':io.BytesIO(s.body)}
        s3=S3();sha=hashlib.sha256(b'good').hexdigest()
        self.assertEqual(publisher.verify_archive(s3,'key',4,sha)['verification'],'full remote readback')
        s3.body=b'evil'
        with self.assertRaises(AssertionError):publisher.verify_archive(s3,'key',4,sha)
        s3.body=b'good';s3.replace=True
        with self.assertRaises(AssertionError):publisher.verify_archive(s3,'key',4,sha)

    def test_final_gate_requires_every_client_and_exact_bundle_commitments(self):
        commitments={'head_hash':'h','state_root':'s','bal_hash':'b'}
        manifest={'head':100,'expected_commitments':commitments}
        ready={'phase':'replay_bundle_verified','head':100,'replay_bundle':{
            'key':publisher.PREFIX+'replay/snapshot.tar.zst','verification':'full remote readback'}}
        snapshots={c:{'phase':'snapshot_uploaded_verified','head':100,**commitments} for c in publisher.HOSTS}
        publisher.validate_delivery(manifest,ready,snapshots)
        for client in snapshots:
            missing=copy.deepcopy(snapshots);missing.pop(client)
            with self.assertRaises(AssertionError):publisher.validate_delivery(manifest,ready,missing)
            for field in ('head','head_hash','state_root','bal_hash','phase'):
                bad=copy.deepcopy(snapshots);bad[client][field]='wrong'
                with self.assertRaises(AssertionError):publisher.validate_delivery(manifest,ready,bad)
        pending=copy.deepcopy(ready);pending['phase']='uploaded'
        with self.assertRaises(AssertionError):publisher.validate_delivery(manifest,pending,snapshots)

    def test_prepare_only_returns_without_final_publication(self):
        with patch.object(publisher,'ROOT',self.root), patch.object(publisher,'client'), \
             patch.object(publisher,'prepare_bundle') as prepare, \
             patch.object(publisher,'validate_delivery') as validate, \
             patch('sys.argv',['publish-bundle.py','--prepare-only']):
            publisher.main()
            prepare.assert_called_once();validate.assert_not_called()
            self.assertFalse((self.root/'delivery-complete.json').exists())


if __name__=='__main__':unittest.main()
