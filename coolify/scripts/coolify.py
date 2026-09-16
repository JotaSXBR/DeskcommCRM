#!/usr/bin/env python3
"""DeskcommCRM no Coolify via SSH root + API. Stdlib only, WSL/Linux.
Segredo nunca no output: token Sanctum <id>|<token> só em arquivo 0600 e header HTTP.
Payload remoto sempre via arquivo (remote.py), nunca inline. Compose raw sempre base64.
Uso: python3 coolify.py <comando> --ssh root@IP [opções]"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remote import run_script_file, run_lines  # noqa: E402


def read_token(token_file):
    with open(token_file, "r", encoding="utf-8") as f:
        return f.read().strip()


def api_req(base_url, token_file, method, path, body=None):
    token = read_token(token_file)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        code = getattr(getattr(e, "fp", None), "status", 0) or 0
        return code, str(e)


def cmd_heal_localhost(a):
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "f=/root/.ssh/authorized_keys\n"
        "test -f \"$f\" || { echo '{\"reachable\":false,\"reason\":\"no_authorized_keys\"}'; exit 0; }\n"
        "awk 'length{print}' \"$f\" > \"$f.tmp\" && printf '\\n' >> \"$f.tmp\"\n"
        "PUB=$(docker exec coolify cat /root/.ssh/id*.pub 2>/dev/null | head -n1)\n"
        "grep -qxF \"$PUB\" \"$f.tmp\" 2>/dev/null || printf '%s\\n' \"$PUB\" >> \"$f.tmp\"\n"
        "cat \"$f.tmp\" > \"$f\" && chmod 600 \"$f\" && rm -f \"$f.tmp\"\n"
        "docker exec coolify ssh -o BatchMode=yes -o ConnectTimeout=5 root@host.docker.internal hostname >/dev/null 2>&1 "
        "&& echo '{\"reachable\":true}' || echo '{\"reachable\":false}'\n")
    print(r["stdout"].strip() or json.dumps(r))


def cmd_wait_admin(a):
    for _ in range(1, a.attempts + 1):
        r = run_lines(a.ssh, "docker exec -i coolify-db psql -U coolify -d coolify -tAc \"SELECT count(*) FROM users;\"")
        n = (r["stdout"] or "").strip().split("\n")[-1].strip() if r["ok"] else ""
        if n.isdigit() and int(n) > 0:
            print(json.dumps({"ok": True, "users": int(n)}))
            return
        time.sleep(5)
    print(json.dumps({"ok": False, "reason": "timeout_criar_admin_no_browser"}))


def cmd_enable_api(a):
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "docker exec -i coolify-db psql -U coolify -d coolify -v ON_ERROR_STOP=1 -c "
        "\"UPDATE instance_settings SET is_api_enabled=true;\"\n"
        "echo '{\"api_enabled\":true}'\n")
    print(r["stdout"].strip() or json.dumps(r))


def api_list(base_url, token_file, path):
    s, b = api_req(base_url, token_file, "GET", path)
    try:
        data = json.loads(b)
    except Exception:
        return s, []
    if isinstance(data, dict):
        for k in ("data", "items", "projects", "services", "environments"):
            if isinstance(data.get(k), list):
                return s, data[k]
        return s, [data]
    return s, data if isinstance(data, list) else []


def find_by_name(items, name):
    for it in items:
        if isinstance(it, dict) and it.get("name") == name:
            return it
    return None


def cmd_token(a):
    if a.base_url and os.path.exists(a.out):
        s, _ = api_req(a.base_url, a.out, "GET", "/servers")
        if s == 200:
            print(json.dumps({"ok": True, "reused": True, "out": a.out}))
            return
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "docker exec -i coolify php artisan tinker --execute=\""
        "$u=\\App\\Models\\User::first(); $t=$u->teams()->first(); "
        "if($t){$u->current_team_id=$t->id; $u->save();} "
        "echo $u->createToken('deskcomm-install',['*'])->plainTextToken;\"\n")
    token = (r["stdout"] or "").strip().split("\n")[-1].strip()
    if "|" not in token:
        print(json.dumps({"ok": False, "reason": "token_nao_gerado"}))
        sys.exit(1)
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    os.chmod(a.out, 0o600)
    print(json.dumps({"ok": True, "out": a.out}))


def cmd_create_project(a):
    _, items = api_list(a.base_url, a.token_file, "/projects")
    found = find_by_name(items, "DeskcommCRM")
    if found and found.get("uuid"):
        print(json.dumps({"action": "reused", "uuid": found["uuid"]}))
        return
    status, body = api_req(a.base_url, a.token_file, "POST", "/projects",
                           {"name": "DeskcommCRM"})
    uuid = ""
    try:
        uuid = json.loads(body).get("uuid", "")
    except Exception:
        pass
    print(json.dumps({"action": "created", "status": status,
                      "uuid": uuid, "body": body[:500]}))


def cmd_ensure_service(a):
    _, items = api_list(a.base_url, a.token_file, "/services")
    found = find_by_name(items, a.name)
    if found and found.get("uuid"):
        print(json.dumps({"action": "reused", "uuid": found["uuid"]}))
        return
    server_uuid = a.server_uuid
    if not server_uuid:
        _, servers = api_list(a.base_url, a.token_file, "/servers")
        if len(servers) == 1 and servers[0].get("uuid"):
            server_uuid = servers[0]["uuid"]
    if not server_uuid:
        print(json.dumps({"action": "need_server_uuid",
                          "reason": "service ausente e servidor ambiguo"}))
        sys.exit(1)
    with open(a.compose_file, "rb") as f:
        raw_b64 = base64.b64encode(f.read()).decode("ascii")
    status, body = api_req(a.base_url, a.token_file, "POST", "/services",
                           {"project_uuid": a.project_uuid,
                            "server_uuid": server_uuid,
                            "environment_name": a.environment or "production",
                            "docker_compose_raw": raw_b64,
                            "name": a.name, "instant_deploy": False})
    uuid = ""
    try:
        uuid = json.loads(body).get("uuid", "")
    except Exception:
        pass
    print(json.dumps({"action": "created", "status": status,
                      "uuid": uuid, "body": body[:500]}))


def cmd_sync_compose(a):
    with open(a.compose_file, "rb") as f:
        raw_b64 = base64.b64encode(f.read()).decode("ascii")
    s, b = api_req(a.base_url, a.token_file, "PUT",
                   "/services/" + a.service_uuid,
                   {"docker_compose_raw": raw_b64})
    print(json.dumps({"status": s, "body": b[:2000]}))


def cmd_instance_domain(a):
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "docker exec -i coolify-db psql -U coolify -d coolify -tAc "
        "\"SELECT fqdn FROM instance_settings LIMIT 1;\"\n")
    print(json.dumps({"ok": r["ok"],
                      "fqdn": (r["stdout"] or "").strip()}))


def parse_env_file(path):
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


def cmd_env_sync(a):
    env = parse_env_file(a.file)
    if a.app_fqdn:
        base = "https://" + a.app_fqdn
        env["DOMAIN"] = a.app_fqdn
        env["WAHA_WEBHOOK_BASE_URL"] = base
        env["NEXT_PUBLIC_APP_URL"] = base
        env["NEXT_PUBLIC_ADMIN_URL"] = base
    results = []
    for k, v in env.items():
        s, b = api_req(a.base_url, a.token_file, "PATCH",
                       "/services/" + a.service_uuid + "/envs",
                       {"key": k, "value": v})
        action = "patched"
        if s == 404:
            s, b = api_req(a.base_url, a.token_file, "POST",
                           "/services/" + a.service_uuid + "/env",
                           {"key": k, "value": v})
            action = "created"
        results.append({"key": k, "status": s, "action": action,
                        "ok": s in (200, 201), "body": b[:200]})
    print(json.dumps({"synced": sum(1 for r in results if r["ok"]),
                      "total": len(results), "results": results}))


def cmd_set_fqdn(a):
    fqdn = a.fqdn.replace("'", "''")
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "docker exec -i coolify-db psql -U coolify -d coolify -v ON_ERROR_STOP=1 -c "
        "\"UPDATE service_applications SET fqdn='https://" + fqdn + "' "
        "WHERE id=" + str(a.app_id) + ";\"\n"
        "echo '{\"fqdn_set\":true}'\n")
    print(r["stdout"].strip() or json.dumps(r))


def cmd_restart(a):
    s, b = api_req(a.base_url, a.token_file, "POST",
                   "/services/" + a.service_uuid + "/restart")
    print(json.dumps({"status": s, "body": b[:2000]}))


def cmd_poll_tls(a):
    for i in range(1, a.attempts + 1):
        try:
            with urllib.request.urlopen(a.url, timeout=15) as r:
                if r.status in (200, 302):
                    print(json.dumps({"ok": True, "tries": i, "status": r.status}))
                    return
        except Exception as e:
            last = str(e)[:200]
        time.sleep(5)
    print(json.dumps({"ok": False, "reason": last}))


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("heal-localhost"); h.add_argument("--ssh", required=True)
    w = sub.add_parser("wait-admin"); w.add_argument("--ssh", required=True)
    w.add_argument("--attempts", type=int, default=120)
    e = sub.add_parser("enable-api"); e.add_argument("--ssh", required=True)
    t = sub.add_parser("token"); t.add_argument("--ssh", required=True)
    t.add_argument("--out", required=True); t.add_argument("--base-url", default="")
    cp = sub.add_parser("create-project"); cp.add_argument("--base-url", required=True)
    cp.add_argument("--token-file", required=True)
    cs = sub.add_parser("ensure-service"); cs.add_argument("--base-url", required=True)
    cs.add_argument("--token-file", required=True); cs.add_argument("--project-uuid", required=True)
    cs.add_argument("--name", default="deskcommcrm"); cs.add_argument("--server-uuid", default="")
    cs.add_argument("--compose-file", required=True)
    cs.add_argument("--environment", default="production")
    sc = sub.add_parser("sync-compose"); sc.add_argument("--base-url", required=True)
    sc.add_argument("--token-file", required=True); sc.add_argument("--service-uuid", required=True)
    sc.add_argument("--compose-file", required=True)
    idd = sub.add_parser("instance-domain"); idd.add_argument("--ssh", required=True)
    g = sub.add_parser("api-get"); g.add_argument("--base-url", required=True)
    g.add_argument("--token-file", required=True); g.add_argument("--path", required=True)
    es = sub.add_parser("env-sync"); es.add_argument("--base-url", required=True)
    es.add_argument("--token-file", required=True); es.add_argument("--service-uuid", required=True)
    es.add_argument("--file", required=True); es.add_argument("--app-fqdn", default="")
    sf = sub.add_parser("set-fqdn"); sf.add_argument("--ssh", required=True)
    sf.add_argument("--app-id", required=True); sf.add_argument("--fqdn", required=True)
    rs = sub.add_parser("restart"); rs.add_argument("--base-url", required=True)
    rs.add_argument("--token-file", required=True); rs.add_argument("--service-uuid", required=True)
    pt = sub.add_parser("poll-tls"); pt.add_argument("--url", required=True)
    pt.add_argument("--attempts", type=int, default=18)
    a = p.parse_args()
    if a.cmd == "heal-localhost":
        cmd_heal_localhost(a)
    elif a.cmd == "wait-admin":
        cmd_wait_admin(a)
    elif a.cmd == "enable-api":
        cmd_enable_api(a)
    elif a.cmd == "token":
        cmd_token(a)
    elif a.cmd == "create-project":
        cmd_create_project(a)
    elif a.cmd == "ensure-service":
        cmd_ensure_service(a)
    elif a.cmd == "sync-compose":
        cmd_sync_compose(a)
    elif a.cmd == "instance-domain":
        cmd_instance_domain(a)
    elif a.cmd == "api-get":
        s, b = api_req(a.base_url, a.token_file, "GET", a.path)
        print(json.dumps({"status": s, "body": b[:2000]}))
    elif a.cmd == "env-sync":
        cmd_env_sync(a)
    elif a.cmd == "set-fqdn":
        cmd_set_fqdn(a)
    elif a.cmd == "restart":
        cmd_restart(a)
    elif a.cmd == "poll-tls":
        cmd_poll_tls(a)


if __name__ == "__main__":
    main()
