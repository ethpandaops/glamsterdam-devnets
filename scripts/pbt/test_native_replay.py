"""Failure-path checks for the native replay driver; no live RPC or database."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import subprocess

spec = importlib.util.spec_from_file_location('native_replay', Path(__file__).with_name('replay-erigon-native.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReplayChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        for name in ('ROOT', 'RUN', 'RAW'):
            directory = root/name
            directory.mkdir()
            p = patch.object(module, name, directory)
            p.start()
            self.addCleanup(p.stop)
        (module.ROOT/'blocks').mkdir()
        self.base = module.ANCHOR+1020
        self.end = self.base+20
        self.head = self.header(self.base)
        self.calls = []
        self.bad_header = False
        self.invalid_payload = False
        module.save(module.RUN/'before.json', {'head': self.head})
        module.save(module.RUN/'request.json', {'start': self.base+1, 'end': self.end, 'batch_size': 64})
        module.save(module.RAW/'request.json', {'start': self.base+1, 'end': self.end, 'chunk_size': 256})
        self.chunk = module.RAW/f'{self.base+1:08d}'
        self.chunk.mkdir()
        entries = []
        for n in range(self.base+1, self.end+1):
            name = f'{n:08d}.json.gz'
            item = {'number': n, 'hash': str(n), 'state_root': 'state'+str(n), 'bal_hash': 'bal'+str(n),
                    'new_payload': [{'blockNumber': hex(n), 'parentHash': str(n-1), 'blockAccessList': '0xc0'}],
                    'forkchoice': [{'headBlockHash': str(n)}]}
            (module.ROOT/'blocks'/name).write_bytes(gzip.compress(json.dumps(item).encode()))
            data = gzip.compress(json.dumps({'number': n, 'hash': str(n), 'raw': hex(n)}).encode())
            (self.chunk/name).write_bytes(data)
            entries.append({'name': name, 'sha256': hashlib.sha256(data).hexdigest()})
        module.save(self.chunk/'manifest.json', {'start': self.base+1, 'end': self.end, 'files': entries})
        rpc = SimpleNamespace(head=lambda: self.head, call=self.call)
        for target, value in [('RPC', lambda: rpc), ('persist_fence', self.fence)]:
            p = patch.object(module, target, value)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(module.shutil, 'disk_usage', return_value=SimpleNamespace(free=500*10**9))
        p.start()
        self.addCleanup(p.stop)

    def header(self, n):
        return {'number': hex(n), 'hash': str(n), 'stateRoot': 'state'+str(n), 'blockAccessListHash': 'bal'+str(n)}

    def fence(self, head_before):
        self.calls.append(('persist', head_before))

    def call(self, method, params, engine=False):
        self.calls.append((method, params))
        if method == 'testing_insertRawBlocksV2':
            return [str(int(value, 16)) for value in params[1]]
        if method == 'testing_insertRawBlocksV1':
            return [str(int(value, 16)) for value in params[0]]
        if method == 'engine_forkchoiceUpdatedV3':
            self.head = self.header(int(params[0]['headBlockHash']))
            return {'payloadStatus': {'status': 'VALID', 'latestValidHash': self.head['hash']}}
        if method == 'engine_newPayloadV5':
            return {'status': 'INVALID' if self.invalid_payload else 'VALID',
                    'latestValidHash': str(int(params[0]['blockNumber'], 16))}
        if method == 'eth_getBlockByNumber':
            result = self.header(int(params[0], 16))
            if self.bad_header:
                result['stateRoot'] = 'wrong'
            return result
        raise AssertionError(method)

    def test_stages_small_requests_then_validates_every_block_and_persistence(self):
        module.replay()
        methods = [name for name, _ in self.calls]
        self.assertEqual(methods[:3], ['testing_insertRawBlocksV2']*2+['engine_forkchoiceUpdatedV3'])
        self.assertEqual(methods.count('engine_newPayloadV5'), 20)
        self.assertEqual(methods.count('eth_getBlockByNumber'), 20)
        self.assertEqual(self.calls[-1], ('persist', self.base))
        result = json.loads((module.RUN/'replay-complete.json').read_text())
        self.assertTrue(result['final_persistence_verified'])
        self.assertEqual(result['head'], self.end)

    def test_corrupt_raw_input_rejected_before_staging(self):
        (self.chunk/f'{self.base+20:08d}.json.gz').write_bytes(b'corrupt')
        with self.assertRaises(AssertionError):
            module.replay()
        self.assertEqual(self.calls, [])

    def test_bounded_prefix_of_full_raw_stream(self):
        module.save(module.RUN/'request.json', {'start': self.base+1, 'end': self.base+12,
                    'batch_size': 64, 'record_batch_timings': True})
        module.replay()
        result = json.loads((module.RUN/'replay-complete.json').read_text())
        self.assertEqual(result['head'], self.base+12)
        self.assertEqual(sum(name == 'engine_newPayloadV5' for name, _ in self.calls), 12)
        timings = json.loads((module.RUN/'batch-timings.json').read_text())
        self.assertEqual(timings[0]['validated_blocks'], 12)

    def test_trial_warmup_waits_for_persistence_before_next_batch(self):
        module.save(module.RUN/'request.json', {'start': self.base+1, 'end': self.end,
                    'batch_size': 16, 'record_batch_timings': True})
        module.replay()
        fences = [i for i, (name, _) in enumerate(self.calls) if name == 'persist']
        self.assertEqual(len(fences), 2)
        self.assertEqual(sum(name == 'engine_newPayloadV5' for name, _ in self.calls[:fences[0]]), 16)
        self.assertEqual(sum(name == 'engine_newPayloadV5' for name, _ in self.calls[fences[0]+1:]), 4)
        self.assertEqual(self.calls[-1], ('persist', self.base+16))

    def test_wrong_intermediate_commitment_prevents_completion(self):
        self.bad_header = True
        with self.assertRaises(AssertionError):
            module.replay()
        self.assertFalse((module.RUN/'replay-complete.json').exists())

    def test_invalid_payload_prevents_completion(self):
        self.invalid_payload = True
        with self.assertRaises(AssertionError):
            module.replay()
        self.assertFalse((module.RUN/'replay-complete.json').exists())


class ServiceChecks(unittest.TestCase):
    def test_absent_old_driver_does_not_block_startup(self):
        with patch.object(module, 'command', return_value='not-found'), patch.object(module.subprocess, 'run') as run:
            module.stop_previous_driver()
            run.assert_not_called()

    def test_existing_driver_stop_failure_remains_fatal(self):
        with patch.object(module, 'command', return_value='loaded'), patch.object(module.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'systemctl')):
            with self.assertRaises(subprocess.CalledProcessError):
                module.stop_previous_driver()


if __name__ == '__main__':
    unittest.main()
