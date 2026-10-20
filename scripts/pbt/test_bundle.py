"""Early replay upload must preserve input identity and the four-client delivery gate."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
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

    def test_native_archive_recheck_rejects_replacement_and_truncation(self):
        snapshots={c:{'key':publisher.PREFIX+f'{c}/100/snapshot.tar.zst',
                      'archive_bytes':123} for c in publisher.HOSTS}
        completions={c:{'etag':f'"{c}-1"'} for c in snapshots}
        class S3:
            changed=None
            truncate=False
            def head_object(s,**kwargs):
                c=next(c for c,v in snapshots.items() if v['key']==kwargs['Key'])
                return {'ContentLength':122 if s.truncate and c==s.changed else 123,
                        'ETag':'"replaced"' if not s.truncate and c==s.changed else completions[c]['etag']}
        s3=S3()
        result=publisher.verify_native_archives(s3,snapshots,completions)
        self.assertEqual(set(result),set(snapshots))
        for c in snapshots:
            for truncate in (False,True):
                s3.changed=c;s3.truncate=truncate
                with self.assertRaises(AssertionError):
                    publisher.verify_native_archives(s3,snapshots,completions)

    def test_public_archive_requires_exact_status_length_and_etag(self):
        expected={'bytes':123,'etag':'"archive-4"'}
        headers='HTTP/2 200\r\nContent-Length: 123\r\nETag: "archive-4"\r\n\r\n'
        publisher.verify_public_headers(headers,expected)
        publisher.verify_public_headers('HTTP/1.1 200 Connection established\r\n\r\n'+headers,expected)
        for changed in [
            headers.replace('200','206'),
            headers.replace('123','122'),
            headers.replace('"archive-4"','"replacement-4"'),
            headers.replace('Content-Length: 123\r\n',''),
            headers.replace('ETag: "archive-4"\r\n',''),
            'HTTP/2 200\r\nContent-Type: text/html\r\n\r\n',
        ]:
            with self.assertRaises(AssertionError):
                publisher.verify_public_headers(changed,expected)

    def test_failed_archive_identity_prevents_final_metadata_and_completion(self):
        commitments={'head_hash':'h','state_root':'s','bal_hash':'b'}
        manifest={'head':100,'expected_commitments':commitments,'workload':{},
                  'records':[],'manifest_kind':'replay_artifact','delivery_complete':False}
        manifest_bytes=json.dumps(manifest).encode()
        (self.root/'replay-bundle-input').mkdir()
        (self.root/'replay-bundle-input/manifest.json').write_bytes(manifest_bytes)
        replay_key=publisher.PREFIX+'replay/snapshot.tar.zst'
        ready={'phase':'replay_bundle_verified','head':100,
               'manifest_sha256':hashlib.sha256(manifest_bytes).hexdigest(),
               'replay_bundle':{'key':replay_key,'bytes':4,'etag':'"verified"',
                                'verification':'full remote readback'}}
        (self.root/'replay-bundle-ready.json').write_text(json.dumps(ready))
        (self.root/'workload.json').write_text('{}')
        for c in publisher.HOSTS:
            snapshot={'phase':'snapshot_uploaded_verified','head':100,**commitments,
                      'key':publisher.PREFIX+f'{c}/100/snapshot.tar.zst','archive_bytes':4}
            (self.root/f'published-{c}.json').write_text(json.dumps(snapshot))
            (self.root/f'upload-{c}-completed.json').write_text('{"etag":"\\"verified\\""}')
        for failure in ('storage','public'):
            with self.subTest(failure=failure), patch.object(publisher,'ROOT',self.root), \
                 patch.object(publisher,'client') as client, \
                 patch.object(publisher.subprocess,'check_output',
                              return_value='HTTP/2 200\r\nContent-Length: 3\r\nETag: "verified"\r\n\r\n'):
                s3=client.return_value
                s3.head_object.side_effect=lambda **kw: {
                    'ContentLength':4,
                    'ETag':'"replaced"' if failure=='storage' and kw['Key']!=replay_key else '"verified"'}
                with self.assertRaises(AssertionError):
                    publisher.publish(SimpleNamespace(prepare_only=False))
                s3.put_object.assert_not_called()
                self.assertFalse((self.root/'delivery-complete.json').exists())


if __name__=='__main__':unittest.main()
