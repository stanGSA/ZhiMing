"""Deployment launcher: bound graceful shutdown, single worker, optional exact HTTPS origin."""
import os
import sys

sys.path.insert(0, '/opt/zhiming/app')
import uvicorn
from web import create_web_app

origin = os.environ.get('ZHIMING_PUBLIC_ORIGIN')
uvicorn.run(
    create_web_app(public_origin=origin),
    host='127.0.0.1', port=8765, workers=1,
    proxy_headers=True, forwarded_allow_ips='127.0.0.1',
    timeout_graceful_shutdown=30,
)
