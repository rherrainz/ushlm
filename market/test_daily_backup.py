import gzip
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch
from cryptography.fernet import Fernet, InvalidToken
from django.test import SimpleTestCase, override_settings
from market.daily_backup import (PREFIX, SUFFIX, decrypt_snapshot, run_daily_backup)
from vercel.blob import BlobNotFoundError

KEY = Fernet.generate_key().decode()
RAW = b'[{"model":"market.category","pk":1,"fields":{"kind":"tour"}}]'
TODAY = datetime(2026, 11, 21, 6, tzinfo=timezone.utc)
PATH = PREFIX + '2026-11-21' + SUFFIX

@override_settings(DAILY_BACKUP_ENABLED=True, VERCEL_ENVIRONMENT='production', BLOB_STORE_ID='test-store', BACKUP_ENCRYPTION_KEY=KEY, CRON_SECRET='test-cron-secret')
class DailyBackupTests(SimpleTestCase):
    def ciphertext(self):
        return Fernet(KEY.encode()).encrypt(gzip.compress(RAW))

    @patch('market.daily_backup.blob')
    @patch('market.daily_backup.snapshot_bytes')
    def test_created_private_read_back_before_retention_and_retry_is_idempotent(self, snapshot, blob):
        encrypted = self.ciphertext()
        snapshot.return_value = encrypted
        blob.head_blob.side_effect = [BlobNotFoundError('missing'), SimpleNamespace()]
        blob.get_blob.return_value = SimpleNamespace(body=encrypted)
        paths = [PREFIX+f'2026-11-{day:02d}'+SUFFIX for day in range(12,22)]
        blob.query_blobs.return_value = [SimpleNamespace(pathname=path) for path in paths]+[SimpleNamespace(pathname='unrelated.txt')]
        first = run_daily_backup(TODAY)
        self.assertTrue(first['created'])
        self.assertEqual(first['pruned'], 3)
        self.assertEqual(blob.put_blob.call_args.kwargs['access'], 'private')
        self.assertFalse(blob.put_blob.call_args.kwargs['allow_overwrite'])
        self.assertNotIn(b'category', blob.put_blob.call_args.args[1])
        self.assertEqual(blob.delete_blob.call_args.args[0], sorted(paths, reverse=True)[7:])
        calls = [item[0] for item in blob.mock_calls]
        self.assertLess(calls.index('get_blob'), calls.index('delete_blob'))
        second = run_daily_backup(TODAY)
        self.assertFalse(second['created'])
        self.assertEqual(snapshot.call_count, 1)
        self.assertEqual(blob.put_blob.call_count, 1)

    @patch('market.daily_backup.blob')
    @patch('market.daily_backup.snapshot_bytes')
    def test_bad_read_back_never_prunes(self, snapshot, blob):
        blob.head_blob.side_effect = BlobNotFoundError('missing')
        snapshot.return_value = self.ciphertext()
        blob.get_blob.return_value = SimpleNamespace(body=b'corrupted')
        with self.assertRaises(InvalidToken): run_daily_backup(TODAY)
        blob.delete_blob.assert_not_called()
        blob.query_blobs.assert_not_called()

    @patch('market.daily_backup.blob')
    def test_missing_key_and_preview_fail_before_database_or_storage(self, blob):
        with override_settings(BACKUP_ENCRYPTION_KEY=''):
            with self.assertRaises(ValueError): run_daily_backup(TODAY)
        with override_settings(VERCEL_ENVIRONMENT='preview'):
            with self.assertRaises(ValueError): run_daily_backup(TODAY)
        self.assertEqual(blob.mock_calls, [])

    def test_cipher_round_trip_wrong_key_and_tampering(self):
        encrypted = self.ciphertext()
        self.assertEqual(decrypt_snapshot(encrypted), RAW)
        with override_settings(BACKUP_ENCRYPTION_KEY=Fernet.generate_key().decode()):
            with self.assertRaises(InvalidToken): decrypt_snapshot(encrypted)
        with self.assertRaises(InvalidToken): decrypt_snapshot(encrypted[:-5]+b'wrong')

    @patch('market.views.run_daily_backup')
    def test_cron_auth_method_and_no_cache(self, run):
        url = '/internal/cron/daily-backup/'
        self.assertEqual(self.client.get(url).status_code, 401)
        self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION='Bearer incorrect').status_code, 401)
        with override_settings(CRON_SECRET=''):
            self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION='Bearer ').status_code, 401)
        self.assertEqual(self.client.post(url, HTTP_AUTHORIZATION='Bearer test-cron-secret').status_code, 405)
        run.assert_not_called()
        run.return_value = {'ok':True, 'created':True}
        response = self.client.get(url, HTTP_AUTHORIZATION='Bearer test-cron-secret')
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])

    @patch('market.views.run_daily_backup')
    def test_disabled_and_failures_do_not_expose_details(self, run):
        url = '/internal/cron/daily-backup/'
        with override_settings(VERCEL_ENVIRONMENT='preview'):
            self.assertEqual(self.client.get(url, HTTP_AUTHORIZATION='Bearer test-cron-secret').status_code, 503)
        run.assert_not_called()
        run.side_effect = RuntimeError('credential and personal information MUST NOT LEAK')
        with self.assertLogs('market.views', level='ERROR') as logs:
            response = self.client.get(url, HTTP_AUTHORIZATION='Bearer test-cron-secret')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(b'MUST NOT LEAK', response.content)
        self.assertNotIn('MUST NOT LEAK', str(logs.output))

    @patch('market.daily_backup.blob')
    def test_retention_keeps_old_snapshots_when_fewer_than_seven(self, blob):
        from market.daily_backup import prune_snapshots
        blob.query_blobs.return_value = [SimpleNamespace(pathname=PREFIX+'2020-01-01'+SUFFIX), SimpleNamespace(pathname=PREFIX+'2099-01-01'+SUFFIX), SimpleNamespace(pathname=PREFIX+'notes.txt')]
        self.assertEqual(prune_snapshots('2026-11-21'), 0)
        blob.delete_blob.assert_not_called()
