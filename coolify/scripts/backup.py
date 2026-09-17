#!/usr/bin/env python3
"""Backup do DeskcommCRM no Coolify: dump do Supabase + snapshot do waha.
Roda NO HOST (cron diario as 03:00); `install-cron` despacha daqui via SSH.
Retencao por camadas: 7 mais novos + 1 por semana (4) + 1 por mes (2).
Tudo fica na mesma VPS; copia externa e manual. Stdlib only.
Uso no host: python3 backup.py run --env-file deskcomm.env --dir /data/coolify/backups-deskcomm/ [--waha-volume <vol>]
Daqui: python3 backup.py install-cron --ssh root@IP --file base.env [--waha-volume <vol>]
"""
import argparse
import gzip
import json
import os
import re
import subprocess
import sys
import time
from datetime import date

BACKUP_DIR = "/data/coolify/backups-deskcomm"

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def select_keep(names):
    dated = []
    for n in names:
        m = re.match(r"(\d{8})-\d{6}", n)
        if not m:
            continue
        s = m.group(1)
        dated.append((date(int(s[0:4]), int(s[4:6]), int(s[6:8])), n))
    dated.sort(reverse=True)
    keep = set()
    for _, n in dated[:7]:
        keep.add(n)
    weeks, months = set(), set()
    for d, n in dated:
        if n in keep:
            continue
        wk = (d.isocalendar()[0], d.isocalendar()[1])
        if len(weeks) < 4 and wk not in weeks:
            weeks.add(wk)
            keep.add(n)
            continue
        mo = (d.year, d.month)
        if len(months) < 2 and mo not in months:
            months.add(mo)
            keep.add(n)
    return sorted(keep), sorted({n for _, n in dated} - keep)


def read_env_file(path):
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k:
                env[k] = v.strip()
    return env


def prune(directory, prefix):
    names = [n for n in os.listdir(directory) if n.startswith(prefix)]
    keep, delete = select_keep(names)
    for n in delete:
        try:
            os.unlink(os.path.join(directory, n))
        except OSError:
            pass
    return keep, delete


def cmd_run(a):
    env = read_env_file(a.env_file)
    db_url = env.get("SUPABASE_DB_URL", "")
    if not db_url:
        print(json.dumps({"ok": False, "reason": "db_url_ausente"}))
        sys.exit(1)
    os.makedirs(a.dir, exist_ok=True)
    ts = time.strftime("%Y%m%d-%H%M%S")
    p = subprocess.run(["docker", "run", "--rm", "postgres:16-alpine",
                        "pg_dump", db_url, "--no-owner", "--no-privileges"],
                       capture_output=True, timeout=900)
    if p.returncode != 0:
        print(json.dumps({"ok": False, "reason": "pg_dump_falhou",
                          "stderr": p.stderr.decode("utf-8", "replace")[:200]}))
        sys.exit(1)
    db_file = "db-%s.sql.gz" % ts
    with gzip.open(os.path.join(a.dir, db_file), "wb") as f:
        f.write(p.stdout)
    waha_file = ""
    if a.waha_volume:
        waha_file = "waha-%s.tgz" % ts
        w = subprocess.run(["docker", "run", "--rm",
                            "-v", a.waha_volume + ":/data:ro",
                            "-v", a.dir + ":/out", "alpine:3.20",
                            "tar", "czf", "/out/" + waha_file, "-C", "/data", "."],
                           capture_output=True, timeout=900)
        if w.returncode != 0:
            waha_file = "snapshot_pulado"
    _, del_db = prune(a.dir, "db-")
    _, del_waha = prune(a.dir, "waha-")
    print(json.dumps({"ok": True, "db": db_file, "waha": waha_file,
                      "deleted": len(del_db) + len(del_waha)}))


def cmd_install_cron(a):
    from remote import put_file, run_script_file  # noqa: E402
    env = read_env_file(a.file)
    db_url = env.get("SUPABASE_DB_URL", "")
    if not db_url:
        print(json.dumps({"ok": False, "reason": "db_url_ausente"}))
        sys.exit(1)
    r = run_script_file(a.ssh, "set -euo pipefail\nmkdir -p " + BACKUP_DIR + "\n"
                        "echo '{\"dir_ok\":true}'\n")
    if not r["ok"]:
        print(json.dumps({"ok": False, "reason": "mkdir_falhou"}))
        sys.exit(1)
    env_path = BACKUP_DIR + "/deskcomm.env"
    with open(env_path + ".tmp", "w", encoding="utf-8", newline="\n") as f:
        f.write("SUPABASE_DB_URL=%s\n" % db_url)
    try:
        r = put_file(a.ssh, env_path + ".tmp", env_path, "600")
    finally:
        os.unlink(env_path + ".tmp")
    if not r["ok"]:
        print(json.dumps({"ok": False, "reason": "env_put_falhou"}))
        sys.exit(1)
    r = put_file(a.ssh, os.path.abspath(__file__),
                 BACKUP_DIR + "/backup.py", "600")
    if not r["ok"]:
        print(json.dumps({"ok": False, "reason": "script_put_falhou"}))
        sys.exit(1)
    cron = ("0 3 * * * python3 %s/backup.py run --env-file %s/deskcomm.env "
            "--dir %s/ --waha-volume %s >> %s/backup.log 2>&1"
            % (BACKUP_DIR, BACKUP_DIR, BACKUP_DIR, a.waha_volume, BACKUP_DIR))
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "(crontab -l 2>/dev/null | grep -v 'backups-deskcomm/backup.py' || true)\n"
        "((crontab -l 2>/dev/null | grep -v 'backups-deskcomm/backup.py' || true); "
        "echo '" + cron + "') | crontab -\n"
        "echo '{\"cron_ok\":true}'\n")
    print(json.dumps({"ok": r["ok"], "cron": cron if r["ok"] else ""}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    rr = sub.add_parser("run"); rr.add_argument("--env-file", required=True)
    rr.add_argument("--dir", required=True); rr.add_argument("--waha-volume", default="")
    ic = sub.add_parser("install-cron"); ic.add_argument("--ssh", required=True)
    ic.add_argument("--file", required=True); ic.add_argument("--waha-volume", default="")
    a = p.parse_args()
    if a.cmd == "run":
        cmd_run(a)
    elif a.cmd == "install-cron":
        cmd_install_cron(a)


if __name__ == "__main__":
    main()
