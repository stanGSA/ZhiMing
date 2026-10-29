#!/bin/bash
# Run only after the domain points exclusively to the new VPS.
set -euo pipefail
umask 077
test "$(dig +short A zhiming.mom | sort -u)" = 217.116.171.241
test -z "$(dig +short AAAA zhiming.mom)"
test "$(curl -fsS --max-time 20 http://zhiming.mom/.well-known/acme-challenge/deployment-check)" = zhiming-new-vps-ready
certbot certonly --webroot --webroot-path /var/lib/zhiming-acme --domain zhiming.mom --cert-name zhiming.mom --non-interactive --agree-tos --register-unsafely-without-email --keep-until-expiring
cp -a /etc/nginx/sites-available/zhiming-domain.conf /var/lib/zhiming-deployment/zhiming-domain-before-https.conf
install -m 0644 /etc/zhiming/zhiming-https.conf.pending /etc/nginx/sites-available/zhiming-domain.conf
nginx -t
python3 - <<'PY'
from pathlib import Path
import os
import tempfile
p=Path('/etc/zhiming/runtime.env')
lines=[line for line in p.read_text().splitlines() if not line.startswith('ZHIMING_PUBLIC_ORIGIN=')]
lines.append('ZHIMING_PUBLIC_ORIGIN="https://zhiming.mom"')
fd,name=tempfile.mkstemp(dir=p.parent,prefix='.https-runtime-')
with os.fdopen(fd,'w') as stream:
    stream.write('\n'.join(lines)+'\n')
    stream.flush()
    os.fsync(stream.fileno())
os.chmod(name,0o600)
os.replace(name,p)
PY
install -d -m 0755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/zhiming-nginx <<'HOOK'
#!/bin/sh
set -eu
nginx -t
systemctl reload nginx
HOOK
chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/zhiming-nginx
systemctl restart zhiming
systemctl reload nginx
systemctl enable --now certbot.timer
printf 'HTTPS_CONFIGURED_REQUIRES_END_TO_END_VERIFICATION\n'
