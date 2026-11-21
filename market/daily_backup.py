"""Daily logical snapshots: private Blob storage plus authenticated encryption."""
import gzip
import io
import json
import logging
import re
import tempfile
from datetime import timezone as datetime_timezone
from pathlib import Path

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone
from vercel.blob import BlobError, BlobNotFoundError
from vercel.blob import sync as blob

logger = logging.getLogger(__name__)
PREFIX = 'ushlm/daily/'
SUFFIX = '.backup.json.gz.fernet'
PATH_PATTERN = re.compile(r'^ushlm/daily/\d{4}-\d{2}-\d{2}\.backup\.json\.gz\.fernet$')
MAX_SNAPSHOT_BYTES = 32 * 1024 * 1024


def cipher():
    if not settings.BACKUP_ENCRYPTION_KEY:
        raise ValueError('Backup encryption key is missing.')
    return Fernet(settings.BACKUP_ENCRYPTION_KEY.encode('ascii'))


def decrypt_snapshot(content):
    compressed = cipher().decrypt(content)
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as stream:
        raw = stream.read(MAX_SNAPSHOT_BYTES + 1)
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise ValueError('Snapshot exceeds the supported size.')
    data = json.loads(raw)
    if not isinstance(data, list) or any(not isinstance(row, dict) or 'model' not in row or 'fields' not in row for row in data):
        raise ValueError('Invalid logical snapshot.')
    return raw


def snapshot_bytes():
    with tempfile.TemporaryDirectory(prefix='ushlm-backup-') as folder:
        destination = Path(folder) / 'snapshot.backup.json'
        call_command('backup_project', output=str(destination), stdout=io.StringIO())
        if destination.stat().st_size > MAX_SNAPSHOT_BYTES:
            raise ValueError('Snapshot exceeds the supported size.')
        raw = destination.read_bytes()
    return cipher().encrypt(gzip.compress(raw, mtime=0))


def verify_stored(pathname):
    result = blob.get_blob(pathname, access='private')
    decrypt_snapshot(result.body)
    return len(result.body)


def prune_snapshots(today):
    # Keep seven successful daily snapshots, even after missed days. Only the
    # dedicated path format is eligible; unrelated files and future dates stay.
    candidates = [item.pathname for item in blob.query_blobs(prefix=PREFIX)
                  if PATH_PATTERN.fullmatch(item.pathname) and item.pathname[len(PREFIX):len(PREFIX)+10] <= today]
    obsolete = sorted(set(candidates), reverse=True)[7:]
    if obsolete:
        blob.delete_blob(obsolete)
    return len(obsolete)


def run_daily_backup(now=None):
    # Preview never receives production credentials or permission to export data.
    if not settings.DAILY_BACKUP_ENABLED or settings.VERCEL_ENVIRONMENT != 'production':
        raise ValueError('Daily production backups are disabled.')
    if not settings.BLOB_STORE_ID:
        raise ValueError('Private Blob store is not configured.')
    cipher()  # Fail before touching storage or reading the database.
    today = (now or timezone.now()).astimezone(datetime_timezone.utc).date().isoformat()
    pathname = PREFIX + today + SUFFIX
    created = False
    try:
        blob.head_blob(pathname)
    except BlobNotFoundError:
        content = snapshot_bytes()
        try:
            blob.put_blob(pathname, content, access='private', content_type='application/octet-stream',
                          allow_overwrite=False, add_random_suffix=False)
            created = True
        except BlobError:
            # Another invocation may have completed the same immutable daily file.
            # Only accept that outcome after authenticated read-back succeeds.
            verify_stored(pathname)
        size = verify_stored(pathname)
    else:
        size = verify_stored(pathname)
    deleted = prune_snapshots(today)
    logger.info('Daily backup verified: date=%s created=%s size=%s pruned=%s', today, created, size, deleted)
    return {'ok': True, 'date_utc': today, 'created': created, 'encrypted_bytes': size, 'pruned': deleted, 'retained_days': 7}
