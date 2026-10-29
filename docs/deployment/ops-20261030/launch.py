"""Deployment launcher: bound graceful shutdown, single worker, optional exact HTTPS origin,
the admin console's account names and the monitor token (all from /etc/zhiming/runtime.env)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, '/opt/zhiming/app')
import uvicorn
from web import create_web_app

origin = os.environ.get('ZHIMING_PUBLIC_ORIGIN')
uvicorn.run(
    create_web_app(
        public_origin=origin,
        admin_users=os.environ.get('ZHIMING_ADMIN_USERS') or None,
        monitor_token=os.environ.get('ZHIMING_MONITOR_TOKEN') or None,
        monitor_status=Path('/var/lib/zhiming-monitor/status.json'),
        release_file=Path('/etc/zhiming/release.json'),
    ),
    host='127.0.0.1', port=8765, workers=1,
    proxy_headers=True, forwarded_allow_ips='127.0.0.1',
    timeout_graceful_shutdown=30,
)
