#!/bin/bash
# Install the monitor, alert timer and admin-console wiring on the Debian VPS. Idempotent.
# Run as root AFTER /opt/zhiming/app has been upgraded to a release that contains ops/.
# Prints no secrets. Usage:
#   bash install-ops.sh <admin account>[,<another admin account>]
# The admin accounts must already exist (register them on the site first). Rights are bound
# to their account ids, so a deleted admin's name registered again by someone else gets none;
# re-run this script to grant a new account explicitly.
set -euo pipefail
umask 077

APP=/opt/zhiming/app
SRC=$APP/docs/deployment/ops-20261030
ADMINS="${1:?usage: install-ops.sh <admin account>[,<more>]}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
SAVE=/var/lib/zhiming-deployment/ops-$STAMP

test "$(id -u)" = 0
test -f "$APP/ops/monitor.py"
test -f "$APP/ops/admin.py"
python3 -c 'import sys; assert sys.version_info >= (3, 11)'

# Names -> account ids, read-only and as the app user (root must not create WAL files).
IFS=',' read -r -a NAMES <<<"$ADMINS"
ADMIN_IDS=$(cd "$APP" && runuser -u zhiming -- "$APP/.venv/bin/python" -m ops.admin resolve \
  --db /opt/zhiming/data/app.db "${NAMES[@]}")

# Keep what is replaced, for rollback (see docs/operations.md).
install -d -m 0700 "$SAVE"
for path in /usr/local/lib/zhiming/launch.py /usr/local/lib/zhiming/backup.py \
  /etc/zhiming/runtime.env /etc/zhiming/monitor.env; do
  if [ -e "$path" ]; then cp -a "$path" "$SAVE/"; fi
done

install -m 0755 -o root -g root "$APP/ops/monitor.py" /usr/local/lib/zhiming/monitor.py
install -m 0644 -o root -g root "$SRC/launch.py" /usr/local/lib/zhiming/launch.py
install -m 0644 -o root -g root "$SRC/backup.py" /usr/local/lib/zhiming/backup.py
install -m 0644 -o root -g root "$SRC/zhiming-monitor.service" /etc/systemd/system/
install -m 0644 -o root -g root "$SRC/zhiming-monitor.timer" /etc/systemd/system/

# Admin ids into runtime.env; one random token shared by runtime.env and monitor.env.
python3 - "$ADMIN_IDS" "$SRC/monitor.env.example" <<'PY'
import os
import re
import secrets
import sys
import tempfile
from pathlib import Path

admins = [item.strip() for item in sys.argv[1].split(",") if item.strip()]
if not admins or not all(re.fullmatch(r"acct-[0-9a-f]{32}", item) for item in admins):
    sys.exit("invalid admin account id")


def read(path):
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def value(lines, key):
    for line in lines:
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


def write(path, lines, updates, drop=()):
    kept = [line for line in lines if line.split("=", 1)[0] not in {*updates, *drop}]
    kept += [f'{key}="{val}"' for key, val in updates.items()]
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".ops-")
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write("\n".join(kept) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(name, 0o600)
    os.replace(name, path)


runtime = Path("/etc/zhiming/runtime.env")
monitor = Path("/etc/zhiming/monitor.env")
runtime_lines = read(runtime)
monitor_lines = read(monitor) or read(Path(sys.argv[2]))
token = value(runtime_lines, "ZHIMING_MONITOR_TOKEN") or secrets.token_urlsafe(32)
write(
    runtime,
    runtime_lines,
    {"ZHIMING_ADMIN_IDS": ",".join(admins), "ZHIMING_MONITOR_TOKEN": token},
    drop=("ZHIMING_ADMIN_USERS",),
)
write(monitor, monitor_lines, {"ZHIMING_MONITOR_TOKEN": token})
print("runtime.env and monitor.env updated (values not shown)")
PY

systemctl daemon-reload
systemctl restart zhiming
for _ in $(seq 1 30); do
  if curl -fsS --max-time 5 http://127.0.0.1:8765/healthz >/dev/null; then break; fi
  sleep 2
done
curl -fsS --max-time 5 http://127.0.0.1:8765/healthz >/dev/null
systemctl enable --now zhiming-monitor.timer
systemctl start zhiming-monitor.service
test -s /var/lib/zhiming-monitor/status.json
printf 'OPS_INSTALLED backup=%s\n' "$SAVE"
printf 'Next: fill an alert channel in /etc/zhiming/monitor.env, then run\n'
printf '  python3 -I /usr/local/lib/zhiming/monitor.py --test-alert\n'
printf '(it reads /etc/zhiming/monitor.env itself), and open https://zhiming.mom/admin\n'
printf 'signed in as an admin account. Cost limits by amount stay off until unit prices\n'
printf 'and a daily cost budget are set there.\n'
