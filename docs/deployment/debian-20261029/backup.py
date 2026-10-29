"""Root-only local backup; never prints database contents or credentials."""

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tarfile
import tempfile
import time
from datetime import datetime, timezone


os.umask(0o077)
destination = Path('/var/backups/zhiming')
destination.mkdir(mode=0o700, parents=True, exist_ok=True)
stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
target = destination / f'zhiming-{stamp}.tar.gz'
pending = target.with_suffix('.partial')
source_db = Path('/opt/zhiming/data/app.db')

try:
    with tempfile.TemporaryDirectory(prefix='.stage-', dir=destination) as temporary:
        stage = Path(temporary)
        metadata = {'created_at_utc': stamp, 'retention_days': 7, 'database_present': source_db.exists()}
        if source_db.exists():
            snapshot = stage / 'app.db'
            source = sqlite3.connect(source_db.as_uri() + '?mode=ro', uri=True, timeout=30)
            copied = sqlite3.connect(snapshot)
            try:
                source.backup(copied, pages=256, sleep=0.1)
                if copied.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backup integrity check failed')
                metadata['schema_version'] = copied.execute('PRAGMA user_version').fetchone()[0]
            finally:
                copied.close()
                source.close()
        (stage / 'backup.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
        with tarfile.open(pending, 'w:gz') as archive:
            for path in stage.iterdir():
                archive.add(path, arcname=path.name)
            for relative in ('kb.sqlite', 'kb_versions', 'kb.coverage.json', 'kb.checks.json'):
                path = Path('/opt/zhiming/data') / relative
                if path.exists():
                    archive.add(path, arcname='data/' + relative)
            for absolute in (
                '/etc/zhiming',
                '/etc/systemd/system/zhiming.service',
                '/etc/systemd/system/zhiming-backup.service',
                '/etc/systemd/system/zhiming-backup.timer',
                '/etc/nginx/sites-available/zhiming-local.conf',
                '/etc/nginx/sites-available/zhiming-domain.conf',
                '/etc/letsencrypt/live/zhiming.mom',
                '/etc/letsencrypt/archive/zhiming.mom',
                '/etc/letsencrypt/renewal/zhiming.mom.conf',
                '/etc/letsencrypt/accounts/acme-v02.api.letsencrypt.org',
                '/etc/letsencrypt/renewal-hooks/deploy/zhiming-nginx',
                '/etc/logrotate.d/zhiming',
                '/etc/systemd/system/zhiming-trace-retention.service',
                '/etc/systemd/system/zhiming-trace-retention.timer',
                '/usr/local/lib/zhiming/backup.py',
                '/usr/local/lib/zhiming/launch.py',
                '/opt/zhiming/app/config.yaml',
                '/opt/zhiming/app/uv.lock',
                '/opt/zhiming/app/scripts/data_manifest.yaml',
            ):
                path = Path(absolute)
                if path.exists():
                    archive.add(path, arcname=absolute.lstrip('/'))
        pending.replace(target)
    # Validate that the archived SQLite can be independently opened after extraction.
    if source_db.exists():
        with tempfile.TemporaryDirectory(prefix='.verify-', dir=destination) as temporary:
            restored = Path(temporary) / 'restored.db'
            with tarfile.open(target, 'r:gz') as archive:
                stream = archive.extractfile('app.db')
                if stream is None:
                    raise RuntimeError('Database missing from archive')
                with stream, restored.open('wb') as output:
                    while block := stream.read(1024 * 1024):
                        output.write(block)
            check = sqlite3.connect(restored.as_uri() + '?mode=ro', uri=True)
            try:
                if check.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Restore verification failed')
            finally:
                check.close()
    with target.open('rb') as stream:
        checksum = hashlib.file_digest(stream, 'sha256').hexdigest()
    target.with_name(target.name + '.sha256').write_text(f'{checksum}  {target.name}\n', encoding='ascii')
    cutoff = time.time() - 7 * 86400
    for previous in destination.glob('zhiming-*.tar.gz'):
        if previous.is_file() and not previous.is_symlink() and previous.stat().st_mtime < cutoff:
            previous.unlink()
            previous.with_name(previous.name + '.sha256').unlink(missing_ok=True)
    print(json.dumps({'backup': target.name, 'integrity': 'ok', 'restore_verified': source_db.exists(), 'retention_days': 7}))
finally:
    pending.unlink(missing_ok=True)
