"""Reject incomplete or mismatched multipart evidence before completion."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location(
    'publisher', Path(__file__).with_name('publish-erigon-v3-head.py'))
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class PublicationEvidence(unittest.TestCase):
    def setUp(self):
        self.job = {'key': publisher.V3_HEAD_KEY, 'upload_id': 'fixture'}
        self.report = {
            **self.job, 'client': 'erigon', 'head': 24503958,
            'archive_bytes': publisher.PART_SIZE + 123, 'archive_sha256': 'a' * 64,
            'parts': [
                {'PartNumber': 1, 'ETag': '"one"', 'bytes': publisher.PART_SIZE,
                 'sha256': 'b' * 64},
                {'PartNumber': 2, 'ETag': '"two"', 'bytes': 123, 'sha256': 'c' * 64},
            ],
        }

    def test_complete_ordered_parts(self):
        self.assertEqual(publisher.validate_parts(self.report, self.job),
                         [{'PartNumber': 1, 'ETag': '"one"'},
                          {'PartNumber': 2, 'ETag': '"two"'}])

    def test_mismatched_head_key_upload_or_size(self):
        for field, value in [('head', 24452538), ('key', 'older-source'),
                             ('upload_id', 'other'), ('archive_bytes', 1),
                             ('archive_sha256', 'x' * 64)]:
            with self.subTest(field=field), self.assertRaises(AssertionError):
                publisher.validate_parts({**self.report, field: value}, self.job)

    def test_missing_reordered_empty_or_short_middle_parts(self):
        for parts in [[], self.report['parts'][1:], self.report['parts'][::-1],
                      [{**self.report['parts'][0], 'bytes': 123}, self.report['parts'][1]]]:
            report = copy.deepcopy(self.report)
            report['parts'] = parts
            with self.subTest(parts=parts), self.assertRaises(AssertionError):
                publisher.validate_parts(report, self.job)

    def test_failed_preflight_prevents_all_storage_calls(self):
        storage = Mock()
        with patch.object(publisher, 'ROOT') as root, patch.object(
                publisher, 'preflight', side_effect=RuntimeError('conversion pending')):
            root.__truediv__.return_value.exists.return_value = False
            with self.assertRaises(RuntimeError):
                publisher.authorize(storage)
        self.assertEqual(storage.mock_calls, [])

    def test_running_preparation_waits_and_stopped_preparation_requires_proofs(self):
        good={'ActiveState':'inactive','MainPID':'0','Result':'success'}
        observed={'units':{name:dict(good) for name in ('pbt-1-v3-head-upgrade','pbt-1-worker-qualification')},
                  'conversion':{},'conversion_complete':False,'qualification_complete':False}
        with self.assertRaises(AssertionError):
            publisher.workers_ready(observed)
        observed['units']['pbt-1-v3-head-upgrade'].update(ActiveState='active',MainPID='42')
        self.assertFalse(publisher.workers_ready(observed))
        observed['units']['pbt-1-v3-head-upgrade'].update(good)
        observed.update(conversion_complete=True,qualification_complete=True)
        self.assertTrue(publisher.workers_ready(observed))
        observed['units']['pbt-1-worker-qualification']['Result']='exit-code'
        with self.assertRaises(AssertionError):
            publisher.workers_ready(observed)

    def test_upload_completion_requires_retained_successful_exit_and_parts(self):
        unit={'ActiveState':'active','SubState':'running','MainPID':'42','Result':'success'}
        observed={'units':{publisher.UPLOAD_UNIT:unit},'upload':{},'upload_complete':False}
        self.assertFalse(publisher.upload_finished(observed))
        unit.update(MainPID='0',SubState='exited')
        with self.assertRaises(AssertionError):
            publisher.upload_finished(observed)
        observed['upload_complete']=True
        self.assertTrue(publisher.upload_finished(observed))
        unit['Result']='exit-code'
        with self.assertRaises(AssertionError):
            publisher.upload_finished(observed)

    def test_failed_wait_never_obtains_storage_client_or_starts_uploader(self):
        with patch.object(publisher,'ROOT') as root, \
                patch.object(publisher,'observe_until',side_effect=AssertionError('failed predecessor')), \
                patch.object(publisher,'client') as storage,patch.object(publisher,'ssh') as ssh:
            root.__truediv__.return_value.exists.return_value=False
            with self.assertRaises(AssertionError):
                publisher.automatic()
            storage.assert_not_called()
            ssh.assert_not_called()

    def test_observation_timeout_repolls_without_remote_restart(self):
        with patch.object(publisher,'observe',side_effect=[publisher.subprocess.TimeoutExpired('ssh',90),{'ready':True}]) as observe, \
                patch.object(publisher,'save'),patch.object(publisher.time,'sleep'), \
                patch.object(publisher,'ssh') as ssh:
            self.assertEqual(publisher.observe_until(lambda value:value['ready'],'waiting',float('inf')),{'ready':True})
            self.assertEqual(observe.call_count,2)
            ssh.assert_not_called()


if __name__ == '__main__':
    unittest.main()
