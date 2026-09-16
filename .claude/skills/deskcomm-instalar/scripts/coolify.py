#!/usr/bin/env python3
"""Operações do Coolify para o caminho Deskcomm, sem segredo em log ou repo.

O token Sanctum `id|segredo` é lido de arquivo 0600 e viaja só no header
HTTP em memória; nunca é impresso. Uso:
  python3 coolify.py enable-api --ssh root@HOST
  python3 coolify.py token --ssh root@HOST --out coolify.token
  python3 coolify.py api-get --base-url http://HOST:8000 --token-file coolify.token --path /servers
  python3 coolify.py api-post --base-url ... --token-file ... --path /services/UUID/start --json-file body.json
  python3 coolify.py create-service --base-url ... --token-file ... --name deskcommcrm --compose-file templates/docker-compose.coolify.yml --fqdn https://crm.exemplo.com
  python3 coolify.py set-fqdn --ssh root@HOST --app-id <id> --fqdn https://crm.exemplo.com
  python3 coolify.py heal-localhost --ssh root@HOST
  python3 coolify.py wait-admin --ssh root@HOST --attempts 120
"""
import argparse
import base64
import json
import os
import stat
import subprocess
import sys
import time
import urllib.request

PSQL_COOLIFY_DB = ["docker", "exec", "-i", "coolify-db", "psql", "-U", "coolify", "-d", "coolify", "-tA"]


def ssh_run(ssh: str, remote: list[str], ssh_opts: str = "", input: bytes | None = None) -> subprocess.CompletedProcess:
    import shlex
    cmd = ["ssh"]
    if ssh_opts:
        cmd += shlex.split(ssh_opts)
    return subprocess.run(cmd + [ssh] + remote, capture_output=True, input=input)


def read_token(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def api(base_url: str, token_file: str, method: str, path: str, data: object = None) -> tuple[int, str]:
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(base_url + path, data=body, method=method)
    req.add_header("Authorization", "Bearer " + read_token(token_file))
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def cmd_enable_api(args) -> int:
    sql = "UPDATE settings SET api_enabled = true WHERE id = 1;"
    p = ssh_run(args.ssh, PSQL_COOLIFY_DB + ["-c", sql], args.ssh_opts)
    sys.stdout.write(p.stdout.decode("utf-8", "replace"))
    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode("utf-8", "replace"))
    return p.returncode


def cmd_token(args) -> int:
    seed = (
        "cope = User::where('id', 0)->first();"
        "$team = $cope ? $cope->currentTeam() : \\App\\Models\\Team::first();"
        "if (!$team) { fwrite(STDERR, 'no-team'); exit(1); }"
        "$cope->current_team_id = $team->id; $cope->save();"
        "$t = $cope->createToken('opencode', ['*']); echo $t->accessToken->id . '|' . $t->plainTextToken;"
    )
    helper = (
        "cat > /tmp/coolify-token.php <<'PHPEOF'\n<?php\nrequire '/var/www/html/vendor/autoload.php';\n"
        "$app = require '/var/www/html/bootstrap/app.php';\n$app->make('Illuminate\\Contracts\\Console\\Kernel')->bootstrap();\n"
        + seed + "\nPHPEOF\n"
        "docker exec -i coolify php /tmp/coolify-token.php"
    )
    p = ssh_run(args.ssh, ["bash", "-s"], args.ssh_opts, input=helper.encode("utf-8"))
    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode("utf-8", "replace"))
        return p.returncode
    out = p.stdout.decode("utf-8", "replace")
    tok = next((part.strip() for part in out.split() if "|" in part), "")
    if not tok:
        sys.stderr.write("token não encontrado na saída remota\n")
        return 1
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(tok + "\n")
    os.chmod(args.out, 0o600)
    return 0


def cmd_api_get(args) -> int:
    status, body = api(args.base_url, args.token_file, "GET", args.path)
    print(json.dumps({"status": status, "body": body[:4000]}, ensure_ascii=False))
    return 0 if status < 400 else 1


def cmd_api_post(args) -> int:
    data = None
    if args.json_file:
        with open(args.json_file, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    status, body = api(args.base_url, args.token_file, "POST", args.path, data)
    print(json.dumps({"status": status, "body": body[:4000]}, ensure_ascii=False))
    return 0 if status < 400 else 1


def cmd_create_service(args) -> int:
    with open(args.compose_file, "rb") as f:
        raw = base64.b64encode(f.read()).decode("ascii")
    payload = {"name": args.name, "docker_compose_raw": raw}
    if args.fqdn:
        payload["fqdn"] = args.fqdn
    status, body = api(args.base_url, args.token_file, "POST", "/api/v1/services", payload)
    print(json.dumps({"status": status, "body": body[:4000]}, ensure_ascii=False))
    if status >= 400:
        sys.stderr.write("falha ao criar service; confira versão da API e ajuste o payload com a resposta acima\n")
        return 1
    return 0


def cmd_set_fqdn(args) -> int:
    sql = (
        "UPDATE service_applications SET fqdn = '%s' WHERE id = '%s';"
        % (args.fqdn.replace("'", "''"), args.app_id.replace("'", "''"))
    )
    p = ssh_run(args.ssh, PSQL_COOLIFY_DB + ["-c", sql], args.ssh_opts)
    sys.stdout.write(p.stdout.decode("utf-8", "replace"))
    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode("utf-8", "replace"))
    return p.returncode


def cmd_heal_localhost(args) -> int:
    script = (
        "set -e\n"
        "f=/root/.ssh/authorized_keys\n"
        "awk 'length{print}' \"$f\" > \"$f.tmp\" && mv \"$f.tmp\" \"$f\"\n"
        "tail -c1 \"$f\" | read -r _ || echo >> \"$f\"\n"
        "chmod 600 \"$f\"\n"
        "docker exec coolify ssh -o BatchMode=yes -o ConnectTimeout=5 root@host.docker.internal true "
        "&& echo '{\"reachable\":true}' || echo '{\"reachable\":false}'\n"
    )
    p = ssh_run(args.ssh, ["bash", "-s"], args.ssh_opts, input=script.encode("utf-8"))
    out = p.stdout.decode("utf-8", "replace")
    sys.stdout.write(out if out else "")
    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode("utf-8", "replace"))
        return p.returncode
    if '"reachable":true' not in out:
        return 1
    return 0


def cmd_wait_admin(args) -> int:
    for i in range(1, args.attempts + 1):
        p = ssh_run(args.ssh, PSQL_COOLIFY_DB + ["-c", "SELECT count(*) FROM users;"], args.ssh_opts)
        n = p.stdout.decode("utf-8", "replace").strip()
        if p.returncode == 0 and n.isdigit() and int(n) > 0:
            print(json.dumps({"ok": True, "users": int(n)}))
            return 0
        time.sleep(5)
    print(json.dumps({"ok": False}))
    return 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssh", default="")
    ap.add_argument("--ssh-opts", default="")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--token-file", default="")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("enable-api")
    t = sub.add_parser("token")
    t.add_argument("--out", required=True)
    g = sub.add_parser("api-get")
    g.add_argument("--path", required=True)
    p = sub.add_parser("api-post")
    p.add_argument("--path", required=True)
    p.add_argument("--json-file", default="")
    c = sub.add_parser("create-service")
    c.add_argument("--name", required=True)
    c.add_argument("--compose-file", required=True)
    c.add_argument("--fqdn", default="")
    s = sub.add_parser("set-fqdn")
    s.add_argument("--app-id", required=True)
    s.add_argument("--fqdn", required=True)
    sub.add_parser("heal-localhost")
    w = sub.add_parser("wait-admin")
    w.add_argument("--attempts", type=int, default=120)
    args = ap.parse_args()

    os.umask(0o077)
    if args.cmd == "enable-api":
        return cmd_enable_api(args)
    if args.cmd == "token":
        fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.close(fd)
        os.chmod(args.out, 0o600)
        st = os.stat(args.out)
        assert stat.S_IMODE(st.st_mode) == 0o600, "token file sem modo 0600"
        return cmd_token(args)
    if args.cmd == "api-get":
        return cmd_api_get(args)
    if args.cmd == "api-post":
        return cmd_api_post(args)
    if args.cmd == "create-service":
        return cmd_create_service(args)
    if args.cmd == "set-fqdn":
        return cmd_set_fqdn(args)
    if args.cmd == "heal-localhost":
        return cmd_heal_localhost(args)
    if args.cmd == "wait-admin":
        return cmd_wait_admin(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
