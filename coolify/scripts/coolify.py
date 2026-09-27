#!/usr/bin/env python3
"""DeskcommCRM no Coolify via SSH root + API. Stdlib only, WSL/Linux.
Segredo nunca no output: token Sanctum <id>|<token> só em arquivo 0600 e header HTTP.
Payload remoto sempre via arquivo (remote.py), nunca inline. Compose raw sempre base64.
Uso: python3 coolify.py <comando> --ssh root@IP [opções]"""
import argparse
import base64
import io
import json
import os
import re
import secrets
import shlex
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from contextlib import redirect_stdout
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remote import run_script_file, run_lines, run_stdin_file  # noqa: E402
from backup import BACKUP_DIR  # noqa: E402


def read_token(token_file):
    with open(token_file, "r", encoding="utf-8") as f:
        return f.read().strip()


def api_req(base_url, token_file, method, path, body=None):
    token = read_token(token_file)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + "/api/v1" + path, data=data, method=method)
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
    # Coolify 4.3.19: container roda como www-data sem /root/.ssh e sem bash;
    # a chave do localhost mora no banco (servers -> private_keys). Deriva a
    # publica via tinker+ssh-keygen dentro do container e testa ssh com -i.
    # Segredo nunca sai do container (arquivo 600 + shred); no output so JSON.
    script = r"""set -euo pipefail
f=/root/.ssh/authorized_keys
test -f "$f" || { echo '{"reachable":false,"reason":"no_authorized_keys"}'; exit 0; }
awk 'length{print}' "$f" > "$f.tmp" && printf '\n' >> "$f.tmp"
PUB_RAW=$(docker exec -i coolify sh -s <<'CTRLEOF1'
set -eu
KEYF=/tmp/heal_key
rm -f "$KEYF" "$KEYF.pub"
php artisan tinker --execute='$s=\App\Models\Server::where("name","localhost")->firstOrFail(); $k=\App\Models\PrivateKey::findOrFail($s->private_key_id); try{$p=\Crypt::decryptString($k->private_key);}catch(\Throwable $e){try{$p=app("encrypter")->decryptString($k->private_key);}catch(\Throwable $e2){$p=$k->private_key;}} file_put_contents("/tmp/heal_key",trim($p)."\n"); echo "";' > /dev/null 2>&1 || true
chmod 600 "$KEYF" 2>/dev/null || true
if [ -f "$KEYF" ] && ssh-keygen -y -f "$KEYF" > "$KEYF.pub" 2>/dev/null; then
echo "PUB:$(cat "$KEYF.pub")"
else
echo "PUB_FAIL"
fi
shred -u "$KEYF" 2>/dev/null || rm -f "$KEYF"
rm -f "$KEYF.pub"
CTRLEOF1
) || true
PUB=$(printf '%s\n' "$PUB_RAW" | grep '^PUB:' | head -n1 | cut -c5- || true)
if [ -z "$PUB" ]; then
echo '{"reachable":false,"reason":"pubkey_derive_failed"}'
exit 0
fi
if grep -qxF "$PUB" "$f.tmp" 2>/dev/null; then
BEFORE=true
else
printf '%s\n' "$PUB" >> "$f.tmp"
BEFORE=false
fi
cat "$f.tmp" > "$f" && chmod 600 "$f" && rm -f "$f.tmp"
HOST_RAW=$(docker exec -i coolify sh -s <<'CTRLEOF2'
set -eu
KEYF=/tmp/heal_key
rm -f "$KEYF"
php artisan tinker --execute='$s=\App\Models\Server::where("name","localhost")->firstOrFail(); $k=\App\Models\PrivateKey::findOrFail($s->private_key_id); try{$p=\Crypt::decryptString($k->private_key);}catch(\Throwable $e){try{$p=app("encrypter")->decryptString($k->private_key);}catch(\Throwable $e2){$p=$k->private_key;}} file_put_contents("/tmp/heal_key",trim($p)."\n"); echo "";' > /dev/null 2>&1 || true
chmod 600 "$KEYF" 2>/dev/null || true
H=$(ssh -i "$KEYF" -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new root@host.docker.internal hostname 2>/dev/null || true)
shred -u "$KEYF" 2>/dev/null || rm -f "$KEYF"
if [ -n "$H" ]; then
echo "HOST:$H"
else
echo "HOST_FAIL"
fi
CTRLEOF2
) || true
HOST_OUT=$(printf '%s\n' "$HOST_RAW" | grep '^HOST:' | head -n1 | cut -c6- | tr -cd 'A-Za-z0-9.-' || true)
if [ -n "$HOST_OUT" ]; then
echo "{\"reachable\":true,\"host\":\"$HOST_OUT\",\"key_present_before\":$BEFORE}"
else
echo "{\"reachable\":false,\"reason\":\"ssh_test_failed\",\"key_present_before\":$BEFORE}"
fi
"""
    r = run_script_file(a.ssh, script)
    print(r["stdout"].strip() or json.dumps(r))


def cmd_install_coolify(a):
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "curl -fsSL https://cdn.coollabs.io/coolify/install.sh -o /tmp/coolify-install.sh\n"
        "setsid bash /tmp/coolify-install.sh < /dev/null > /tmp/coolify-install.log 2>&1 &\n"
        "echo '{\"started\":true}'\n")
    if not r["ok"]:
        print(json.dumps({"installed": False, "reason": "download_ou_disparo_falhou",
                          "stderr": (r["stderr"] or "")[:200]}))
        sys.exit(1)
    last = ""
    for _ in range(a.attempts):
        h = run_lines(a.ssh, "curl -s -o /dev/null -w '%{http_code}' "
                             "http://localhost:8000/api/health || true")
        last = (h["stdout"] or "").strip()
        if last == "200":
            print(json.dumps({"installed": True}))
            return
        time.sleep(10)
    print(json.dumps({"installed": False, "reason": "timeout_health",
                      "last": last}))
    sys.exit(1)


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
        "\"UPDATE instance_settings SET is_api_enabled=true;\" </dev/null\n"
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


IMAGENS_DESKCOMM = ("deskcommcrm", "deskcomm-worker", "deskcomm-scheduler")
ENV_PRESERVADAS_PAINEL = ("SRH_TOKEN", "UPSTASH_REDIS_REST_TOKEN",
                          "RESEND_API_KEY", "RESEND_FROM_EMAIL",
                          # Segredos pos-v1.28 configuraveis pelo painel: o base.env
                          # gerado nao os carrega, e sincronizar "" apagaria o valor.
                          "TENANT_PROVISIONING_SECRET", "SMTP_PASSWORD",
                          "ARI_PASSWORD", "GOOGLE_ADS_OAUTH_CLIENT_SECRET",
                          "GOOGLE_ADS_DEVELOPER_TOKEN", "TRANSCRIPTION_API_KEY")


def validar_ref(ref):
    ref = (ref or "").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", ref):
        raise ValueError("ref_invalida (use X.Y.Z numerica, nunca latest/main/stable)")
    return ref


def extrair_tags_imagens(compose):
    tags = {}
    for nome in IMAGENS_DESKCOMM:
        m = re.search(r"image:\s*ghcr\.io/melgarafael/" + re.escape(nome) + r":([^\s'\"]+)",
                      compose)
        if m:
            tags[nome] = m.group(1)
    return tags


def trocar_tags_deskcomm(compose, ref):
    ref = validar_ref(ref)

    def troca(m):
        return m.group(1) + ref

    # voice-agent entra no swap mas NAO no IMAGENS_DESKCOMM: por ser perfil
    # opcional (telefonia) e o aguardar-deploy cobra todos os nomes da tupla;
    # exigi-lo ali travaria todo update de quem nao usa telefonia.
    return re.sub(r"(ghcr\.io/melgarafael/(?:deskcommcrm|deskcomm-worker|deskcomm-scheduler|deskcomm-voice-agent):)[^\s'\"]+",
                  troca, compose)


def comparar_versoes(instalada, alvo):
    atual = validar_ref(instalada)
    nova = validar_ref(alvo)
    ta = tuple(int(x) for x in atual.split("."))
    tn = tuple(int(x) for x in nova.split("."))
    if tn == ta:
        return "nada_a_fazer"
    if tn < ta:
        raise ValueError("alvo_anterior_a_instalada")
    return "update"


def mesclar_env_update(painel, arquivo):
    out = dict(arquivo)
    for k in ENV_PRESERVADAS_PAINEL:
        if painel.get(k):
            out[k] = painel[k]
    for k in ("SRH_TOKEN", "IMPERSONATE_COOKIE_SECRET"):
        if not out.get(k):
            out.pop(k, None)
    return out


def baseline_mudou(sql_novo, sql_atual):
    if sql_atual is None:
        return True
    return bytes(sql_novo) != bytes(sql_atual)


def baixar_baseline_release(ref, dir_saida):
    ref = validar_ref(ref)
    url = ("https://raw.githubusercontent.com/melgarafael/DeskcommCRM/"
           + "v" + ref + "/supabase/baseline.sql")
    req = urllib.request.Request(url, headers={"Accept": "text/plain"})
    with urllib.request.urlopen(req, timeout=120) as r:
        corpo = r.read()
    if not corpo.strip():
        raise ValueError("baseline_vazio_na_release")
    destino = os.path.join(dir_saida, "baseline-" + ref + ".sql")
    with open(destino, "wb") as f:
        f.write(corpo)
    return destino


def novo_registro_operacao(ref, dir_saida):
    return {"ref": validar_ref(ref), "dir_saida": dir_saida, "etapas": []}


def marcar_etapa(op, etapa, ok, detalhe=""):
    op["etapas"].append({"etapa": etapa, "ok": bool(ok), "detalhe": detalhe})
    return op


ORDEM_ETAPAS_UPDATE = ("snapshot", "sync-compose", "db-apply",
                       "env-sync", "restart", "aguardar-deploy", "poll-tls")


def proxima_etapa(op):
    feitas = {e["etapa"] for e in op.get("etapas", []) if e.get("ok")}
    for etapa in ORDEM_ETAPAS_UPDATE:
        if etapa not in feitas:
            return etapa
    return "concluido"


def cmd_token(a):
    if a.base_url and os.path.exists(a.out):
        s, _ = api_req(a.base_url, a.out, "GET", "/servers")
        if s == 200:
            print(json.dumps({"ok": True, "reused": True, "out": a.out}))
            return
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "docker exec -i coolify php artisan tinker --execute='"
        "$u=\\App\\Models\\User::first(); $t=$u->teams()->first(); "
        "if($t){$u->current_team_id=$t->id; $u->save();} "
        "$plain=\\Illuminate\\Support\\Str::random(40); "
        "$tok=new \\App\\Models\\PersonalAccessToken(); "
        "$tok->tokenable_type=\"App\\Models\\User\"; $tok->tokenable_id=$u->id; "
        "$tok->name=\"deskcomm-install\"; $tok->token=hash(\"sha256\",$plain); "
        "$tok->abilities=[\"*\"]; $tok->team_id=$t->id; $tok->save(); "
        "echo $tok->id.\"|\".$plain;' </dev/null\n")
    token = (r["stdout"] or "").strip().split("\n")[-1].strip()
    if "|" not in token:
        print(json.dumps({"ok": False, "reason": "token_nao_gerado"}))
        sys.exit(1)
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(token)
    os.chmod(a.out, 0o600)
    print(json.dumps({"ok": True, "out": a.out}))


PROJECT_NAME = "DeskcommCRM"
PROJECT_DESCRIPTION = ("Sistema operacional de vendas open source com agentes "
                       "de IA nativos (WhatsApp via WAHA, CRM por MCP)")


def cmd_create_project(a):
    _, items = api_list(a.base_url, a.token_file, "/projects")
    found = find_by_name(items, PROJECT_NAME)
    if found and found.get("uuid"):
        print(json.dumps({"action": "reused", "uuid": found["uuid"]}))
        return
    status, body = api_req(a.base_url, a.token_file, "POST", "/projects",
                           {"name": PROJECT_NAME,
                            "description": a.description or PROJECT_DESCRIPTION})
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
    s, b = api_req(a.base_url, a.token_file, "PATCH",
                   "/services/" + a.service_uuid,
                   {"docker_compose_raw": raw_b64})
    print(json.dumps({"status": s, "body": b[:2000]}))


def texto_imagens_painel(payload):
    try:
        bruto = payload.get("docker_compose_raw", "")
    except Exception:
        bruto = ""
    try:
        compose = base64.b64decode(bruto).decode("utf-8", "replace")
    except Exception:
        compose = ""
    if "ghcr.io/melgarafael/" in compose:
        return compose
    try:
        apps = payload.get("applications", [])
    except Exception:
        apps = []
    linhas = []
    if isinstance(apps, list):
        for app in apps:
            if isinstance(app, dict) and app.get("image"):
                linhas.append("image: " + str(app["image"]))
    return "\n".join(linhas) + ("\n" if linhas else "")


def containers_novos_ok(saida_ps, ref):
    ref = validar_ref(ref)
    vistos = set()
    for linha in (saida_ps or "").split("\n"):
        partes = linha.split("|")
        if len(partes) != 3:
            continue
        imagem = partes[1].strip()
        estado = partes[2].strip()
        for nome in IMAGENS_DESKCOMM:
            if imagem == "ghcr.io/melgarafael/" + nome + ":" + ref and estado.startswith("Up"):
                vistos.add(nome)
    return set(IMAGENS_DESKCOMM) <= vistos


def extrair_env_lista(itens):
    env = {}
    if isinstance(itens, list):
        for it in itens:
            if isinstance(it, dict) and it.get("key"):
                env[it["key"]] = it.get("real_value", it.get("value", "")) or ""
    return env


def diff_env(atual, desejado):
    diff = {}
    for k, v in desejado.items():
        if atual.get(k, "") != v:
            diff[k] = v
    return diff


def buscar_env_painel(base_url, token_file, service_uuid):
    s, b = api_req(base_url, token_file, "GET", "/services/" + service_uuid + "/envs")
    if s != 200:
        raise ValueError("env_painel_nao_lido status=%d" % s)
    try:
        corpo = json.loads(b)
    except Exception:
        raise ValueError("env_painel_nao_lido formato_invalido")
    itens = corpo.get("data", []) if isinstance(corpo, dict) else corpo
    if not isinstance(itens, list):
        raise ValueError("env_painel_nao_lido formato_inesperado")
    return extrair_env_lista(itens)


def resolver_env_base(a):
    if (a.file or ""):
        return parse_env_file(a.file)
    return buscar_env_painel(a.base_url, a.token_file, a.service_uuid)


def listar_releases_github(repo):
    url = "https://api.github.com/repos/" + repo + "/releases?per_page=30"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def cmd_version_status(a):
    s, b = api_req(a.base_url, a.token_file, "GET", "/services/" + a.service_uuid)
    if s != 200:
        print(json.dumps({"ok": False, "reason": "service_nao_lido", "status": s}))
        sys.exit(1)
    try:
        payload = json.loads(b)
    except Exception:
        payload = {}
    tags = extrair_tags_imagens(texto_imagens_painel(payload))
    vals = sorted({t for t in tags.values() if re.fullmatch(r"\d+\.\d+\.\d+", t)},
                  key=lambda v: tuple(int(x) for x in v.split(".")))
    instalada = vals[-1] if vals else ""
    if not instalada:
        print(json.dumps({"ok": False, "reason": "tag_instalada_nao_identificada",
                          "tags": tags}))
        sys.exit(1)
    if len(set(tags.values())) > 1:
        print(json.dumps({"ok": False, "reason": "tags_divergentes", "tags": tags}))
        sys.exit(1)
    disponiveis = []
    try:
        for rel in listar_releases_github("melgarafael/DeskcommCRM"):
            tag = (rel.get("tag_name") or "").lstrip("v")
            if re.fullmatch(r"\d+\.\d+\.\d+", tag):
                try:
                    if comparar_versoes(instalada, tag) == "update":
                        disponiveis.append(tag)
                except ValueError:
                    pass
    except Exception as e:
        print(json.dumps({"ok": False, "reason": "releases_nao_listadas",
                          "detalhe": str(e)[:200]}))
        sys.exit(1)
    disponiveis = sorted(set(disponiveis),
                         key=lambda v: tuple(int(x) for x in v.split(".")))
    print(json.dumps({"ok": True, "instalada": instalada, "tags": tags,
                      "disponiveis": disponiveis,
                      "acao": "escolha_do_operador" if disponiveis else "nada_a_fazer"}))


def cmd_instance_domain(a):
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "docker exec -i coolify-db psql -U coolify -d coolify -tAc "
        "\"SELECT fqdn FROM instance_settings LIMIT 1;\" </dev/null\n")
    print(json.dumps({"ok": r["ok"],
                      "fqdn": (r["stdout"] or "").strip()}))


def mask(v):
    s = str(v)
    return s[:4] + "..." + s[-2:] if len(s) > 8 else "..."


def cmd_dns_check(a):
    checks = []
    ok_all = True
    for fqdn in (a.app_fqdn, a.panel_fqdn):
        try:
            ips = sorted({r[4][0] for r in socket.getaddrinfo(fqdn, 443, 0, 0, 0, 0)})
        except Exception:
            ips = []
        match = a.vps_ip in ips
        checks.append({"fqdn": fqdn, "resolve": ips, "match": match})
        ok_all = ok_all and match
    print(json.dumps({"ok": ok_all, "vps_ip": a.vps_ip, "checks": checks}))
    if not ok_all and not a.allow_unresolved:
        sys.exit(1)


def parse_env_file(path):
    env = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if v.startswith("#"):
                # `.env.example` novo traz `CHAVE=   # comentario`: sem isto,
                # o texto do comentario virava valor e era sincronizado.
                v = ""
            if k:
                env[k] = v
    return env


def cmd_env_sync(a):
    env = parse_env_file(a.file) if (a.file or "") else {}
    if a.app_fqdn:
        base = "https://" + a.app_fqdn
        env["DOMAIN"] = a.app_fqdn
        env["WAHA_WEBHOOK_BASE_URL"] = base
        env["NEXT_PUBLIC_APP_URL"] = base
        env["NEXT_PUBLIC_ADMIN_URL"] = base
    try:
        painel = buscar_env_painel(a.base_url, a.token_file, a.service_uuid)
        painel_lido = True
    except ValueError:
        painel = {}
        painel_lido = False
    for k in ("SRH_TOKEN", "IMPERSONATE_COOKIE_SECRET") + ENV_PRESERVADAS_PAINEL:
        if painel.get(k):
            env[k] = painel[k]
    # Redis interno (srh) e o padrao, igual ao install.sh do kit: o token do
    # Upstash e o proprio SRH_TOKEN e a URL aponta para o conteiner srh.
    # Upstash Cloud continua possivel como override manual (valor presente vence).
    if not env.get("SRH_TOKEN"):
        env["SRH_TOKEN"] = secrets.token_hex(32)
    if not env.get("IMPERSONATE_COOKIE_SECRET"):
        env["IMPERSONATE_COOKIE_SECRET"] = secrets.token_hex(32)
    if not env.get("UPSTASH_REDIS_REST_URL"):
        env["UPSTASH_REDIS_REST_URL"] = painel.get("UPSTASH_REDIS_REST_URL", "http://srh:80")
    if not env.get("UPSTASH_REDIS_REST_TOKEN"):
        env["UPSTASH_REDIS_REST_TOKEN"] = painel.get("UPSTASH_REDIS_REST_TOKEN",
                                                     env.get("SRH_TOKEN", ""))
    diff = diff_env(painel, env) if painel_lido else dict(env)
    if a.preview:
        rows = [{"key": k, "value": mask(v)} for k, v in diff.items()]
        print(json.dumps({"preview": True, "total": len(rows), "env": rows}))
        return
    data = [{"key": k, "value": v} for k, v in diff.items()]
    if not data:
        print(json.dumps({"synced": 0, "total": 0, "acao": "sem_mudancas", "results": []}))
        return
    s, b = api_req(a.base_url, a.token_file, "PATCH",
                   "/services/" + a.service_uuid + "/envs/bulk",
                   {"data": data})
    ok = s in (200, 201)
    print(json.dumps({"synced": len(data) if ok else 0,
                      "total": len(data),
                      "painel": "lido" if painel_lido else "nao_lido_sync_total",
                      "results": [{"status": s, "action": "bulk-upsert",
                                   "ok": ok, "body": b[:200]}]}))


def cmd_env_set(a):
    data = []
    for item in a.set:
        if "=" not in item:
            print(json.dumps({"ok": False, "reason": "par_sem_igual",
                              "chaves": [k for k in data]}))
            sys.exit(1)
        k, v = item.split("=", 1)
        k = k.strip()
        if not k or not v.strip():
            print(json.dumps({"ok": False, "reason": "chave_ou_valor_vazio"}))
            sys.exit(1)
        data.append({"key": k, "value": v.strip()})
    if not data:
        print(json.dumps({"ok": False, "reason": "nada_a_sincronizar"}))
        sys.exit(1)
    s, b = api_req(a.base_url, a.token_file, "PATCH",
                   "/services/" + a.service_uuid + "/envs/bulk",
                   {"data": data})
    ok = s in (200, 201)
    print(json.dumps({"ok": ok, "status": s,
                      "chaves": [d["key"] for d in data] if ok else []}))
    if not ok:
        sys.exit(1)


def cmd_bootstrap_owner(a):
    env = parse_env_file(a.file)
    url = env.get("NEXT_PUBLIC_SUPABASE_URL", "").rstrip("/")
    svc = env.get("SUPABASE_SERVICE_ROLE_KEY", "")
    db_url = env.get("SUPABASE_DB_URL", "")
    email = (a.email or "").strip()
    password = a.password or ""
    if not url or not svc or not db_url or "'" in db_url:
        print(json.dumps({"ok": False, "reason": "base_env_incompleta"}))
        sys.exit(1)
    if "'" in email or "@" not in email or len(password) < 8:
        print(json.dumps({"ok": False, "reason": "email_ou_senha_invalidos"}))
        sys.exit(1)
    body = json.dumps({"email": email, "password": password,
                       "email_confirm": True,
                       "user_metadata": {"locale": "pt-BR"}}).encode("utf-8")
    req = urllib.request.Request(url + "/auth/v1/admin/users", data=body, method="POST")
    req.add_header("apikey", svc)
    req.add_header("Authorization", "Bearer " + svc)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            auth_status = "created" if r.status in (200, 201) else "http_%d" % r.status
            r.read()
    except Exception as e:
        code = getattr(getattr(e, "fp", None), "status", 0) or 0
        auth_status = "exists" if code in (400, 422) else "fail_%d" % code
        if code not in (400, 422):
            print(json.dumps({"ok": False, "reason": "auth_admin_falhou",
                              "auth": auth_status}))
            sys.exit(1)
    sql = (
        "do $$\n"
        "declare v_org uuid; v_uid uuid;\n"
        "begin\n"
        "  select id into v_uid from auth.users where email = '" + email + "';\n"
        "  if v_uid is null then\n"
        "    raise exception 'usuario nao encontrado no auth.users';\n"
        "  end if;\n"
        "  select id into v_org from public.organizations where slug='minha-empresa';\n"
        "  if v_org is null then\n"
        "    insert into public.organizations (slug, display_name, legal_name, locale, created_by)\n"
        "    values ('minha-empresa','Minha Empresa','Minha Empresa','pt-BR', v_uid)\n"
        "    returning id into v_org;\n"
        "  end if;\n"
        "  insert into public.user_organizations (user_id, organization_id, role, accepted_at)\n"
        "  values (v_uid, v_org, 'admin', now())\n"
        "  on conflict (user_id, organization_id) do update set role='admin', revoked_at=null;\n"
        "  if not exists (select 1 from public.platform_admins where user_id=v_uid and revoked_at is null) then\n"
        "    insert into public.platform_admins (user_id, granted_by, scope, mfa_required, reason)\n"
        "    values (v_uid, v_uid, 'full', false, 'Bootstrap inicial do self-host');\n"
        "  end if;\n"
        "end $$;\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False,
                                     encoding="utf-8", newline="\n") as f:
        f.write(sql)
        sql_path = f.name
    try:
        r = run_stdin_file(a.ssh, "docker run --rm -i postgres:16-alpine psql '"
                           + db_url + "' -v ON_ERROR_STOP=1 -f -", sql_path, timeout=300)
    finally:
        os.unlink(sql_path)
    if not r["ok"]:
        tail = ((r["stdout"] or "") + "\n" + (r["stderr"] or "")).strip().split("\n")[-5:]
        print(json.dumps({"ok": False, "reason": "promocao_falhou",
                          "auth": auth_status, "db": tail}))
        sys.exit(1)
    print(json.dumps({"ok": True, "auth": auth_status, "email": email}))


def aplicar_schema(db_url, sql_path, ssh):
    img = "docker run --rm postgres:16-alpine psql " + shlex.quote(db_url)
    img_stdin = "docker run --rm -i postgres:16-alpine psql " + shlex.quote(db_url)
    run_lines(ssh, img + " -v ON_ERROR_STOP=1 -c \"create extension if not exists "
              "vector with schema public; create extension if not exists citext "
              "with schema public; create extension if not exists pg_trgm "
              "with schema public;\"")
    h = run_lines(ssh, img + " -tAc \"select 1 from information_schema.tables "
                  "where table_schema='public' and table_name='organizations' limit 1\"")
    last = (h["stdout"] or "").strip().split("\n")[-1].strip() if h["ok"] else ""
    fresh = last != "1"
    unexpected = []
    applied = False
    if fresh:
        r = run_stdin_file(ssh, img_stdin + " -v ON_ERROR_STOP=1 -f -", sql_path, timeout=900)
        applied = r["ok"]
        if not applied:
            tail = ((r["stdout"] or "") + "\n" + (r["stderr"] or "")).strip().split("\n")
            unexpected = tail[-5:]
    else:
        r = run_stdin_file(ssh, img_stdin + " -q -f -", sql_path, timeout=900)
        applied = True
        benign = re.compile("already exists|multiple primary keys|multiple default "
                            "values|is already a member|already a partition")
        for line in ((r["stdout"] or "") + "\n" + (r["stderr"] or "")).split("\n"):
            if re.search("ERROR|FATAL", line, re.IGNORECASE) and not benign.search(line):
                unexpected.append(line[:200])
                if len(unexpected) >= 5:
                    break
    v = run_lines(ssh, img + " -tAc \"select count(*) from information_schema.tables "
                  "where table_schema='public'\"")
    try:
        n_tables = int((v["stdout"] or "").strip().split("\n")[-1].strip())
    except (ValueError, IndexError):
        n_tables = 0
    m = run_lines(ssh, img + " -tAc \"select coalesce(string_agg(t, ','), '') from "
                  "(values ('job_queue'),('lead_checkpoints'),('agent_inbox_items'),"
                  "('send_ledger')) as x(t) where to_regclass('public.'||t) is null\"")
    missing = (m["stdout"] or "").strip().split("\n")[-1].strip() if m["ok"] else "?"
    ok = applied and not unexpected and n_tables >= 30 and missing == ""
    return {"ok": ok, "fresh": fresh, "tables": n_tables,
            "harness_missing": missing.split(",") if missing not in ("", "?") else [],
            "unexpected_errors": unexpected}


def cmd_db_apply(a):
    env = parse_env_file(a.file)
    db_url = env.get("SUPABASE_DB_URL", "")
    if not db_url or "'" in db_url:
        print(json.dumps({"ok": False, "reason": "db_url_ausente_ou_invalida"}))
        sys.exit(1)
    print(json.dumps(aplicar_schema(db_url, a.sql, a.ssh)))


def git_show_arquivo(revisao, caminho, partida):
    raiz = os.path.abspath(partida)
    while not os.path.isdir(os.path.join(raiz, ".git")):
        pai = os.path.dirname(raiz)
        if pai == raiz:
            raiz = os.getcwd()
            break
        raiz = pai
    try:
        p = subprocess.run(["git", "show", revisao + ":" + caminho],
                           cwd=raiz, capture_output=True, timeout=60)
    except Exception:
        return None
    if p.returncode != 0:
        return None
    return p.stdout


def cmd_update(a):
    def abortar(op, alteradas, etapa, reason, detalhe=""):
        marcar_etapa(op, etapa, False, detalhe or reason)
        resto = (list(ORDEM_ETAPAS_UPDATE[ORDEM_ETAPAS_UPDATE.index(etapa):])
                 if etapa in ORDEM_ETAPAS_UPDATE else list(ORDEM_ETAPAS_UPDATE))
        print(json.dumps({"ok": False, "etapa": etapa, "alterado_ate_aqui": list(alteradas),
                          "pendente": resto, "atendimento_pausado": True, "reason": reason}))
        sys.exit(1)

    def divergente(etapa):
        print(json.dumps({"ok": False, "reason": "estado_divergente", "etapa": etapa}))
        sys.exit(1)

    def passo_snapshot(ctx):
        op = ctx["op"]
        snap_nome = "compose-%d.b64" % int(time.time())
        snap_path = os.path.join(ctx["op_dir"], snap_nome)
        with open(snap_path, "w", encoding="utf-8") as f:
            f.write(base64.b64encode(ctx["painel_compose"].encode("utf-8")).decode("ascii"))
        marcar_etapa(op, "snapshot", True, snap_nome)
        ctx["snap_path"] = snap_path

    def passo_sync_compose(ctx):
        op = ctx["op"]
        alteradas = ctx["alteradas"]
        a = ctx["a"]
        novo_compose = trocar_tags_deskcomm(ctx["template"], ctx["ref"])
        s, b = api_req(a.base_url, a.token_file, "PATCH",
                       "/services/" + a.service_uuid,
                       {"docker_compose_raw": base64.b64encode(novo_compose.encode("utf-8")).decode("ascii")})
        if s not in (200, 201):
            abortar(op, alteradas, "sync-compose", "sync_compose_falhou", "status=%d" % s)
        alteradas.append("sync-compose")
        marcar_etapa(op, "sync-compose", True, "status=%d" % s)

    def passo_db_apply(ctx):
        op = ctx["op"]
        alteradas = ctx["alteradas"]
        a = ctx["a"]
        if a.skip_sql:
            ctx["motivo_sql"] = "skip_sql"
            marcar_etapa(op, "db-apply", True, ctx["motivo_sql"])
            return
        try:
            with open(ctx["sql_path"], "rb") as f:
                sql_novo = f.read()
        except OSError:
            abortar(op, alteradas, "db-apply", "sql_nao_lido", ctx["sql_path"])
            return
        if not sql_novo:
            abortar(op, alteradas, "db-apply", "sql_vazio", ctx["sql_path"])
        sql_atual = git_show_arquivo("v" + ctx["instalada"], "supabase/baseline.sql",
                                     os.path.dirname(os.path.abspath(a.compose_file)))
        if sql_atual is not None and not baseline_mudou(sql_novo, sql_atual):
            ctx["motivo_sql"] = "baseline_sem_mudanca"
            marcar_etapa(op, "db-apply", True, ctx["motivo_sql"])
        else:
            ctx["motivo_sql"] = "comparacao_indisponivel" if sql_atual is None else "baseline_mudou"
            env = ctx["env_base"]
            db_url = env.get("SUPABASE_DB_URL", "")
            if not db_url or "'" in db_url:
                abortar(op, alteradas, "db-apply", "db_url_ausente_ou_invalida")
            res = aplicar_schema(db_url, ctx["sql_path"], a.ssh)
            if not res["ok"]:
                abortar(op, alteradas, "db-apply", "db_apply_falhou",
                        ";".join(res["unexpected_errors"])[:500] or "gate_nao_atendido")
            ctx["sql_aplicado"] = True
            alteradas.append("db-apply")
            marcar_etapa(op, "db-apply", True, "tables=%d" % res["tables"])

    def passo_env_sync(ctx):
        op = ctx["op"]
        alteradas = ctx["alteradas"]
        a = ctx["a"]
        try:
            painel = buscar_env_painel(a.base_url, a.token_file, a.service_uuid)
        except ValueError as e:
            abortar(op, alteradas, "env-sync", "env_painel_nao_lido", str(e)[:200])
        arquivo = dict(ctx["env_base"])
        if a.app_fqdn:
            base = "https://" + a.app_fqdn
            arquivo["DOMAIN"] = a.app_fqdn
            arquivo["WAHA_WEBHOOK_BASE_URL"] = base
            arquivo["NEXT_PUBLIC_APP_URL"] = base
            arquivo["NEXT_PUBLIC_ADMIN_URL"] = base
        mesclado = mesclar_env_update(painel, arquivo)
        if not mesclado.get("UPSTASH_REDIS_REST_URL"):
            mesclado["UPSTASH_REDIS_REST_URL"] = painel.get("UPSTASH_REDIS_REST_URL",
                                                            "http://srh:80")
        if not mesclado.get("UPSTASH_REDIS_REST_TOKEN"):
            mesclado["UPSTASH_REDIS_REST_TOKEN"] = painel.get("UPSTASH_REDIS_REST_TOKEN",
                                                              mesclado.get("SRH_TOKEN", ""))
        diff = diff_env(painel, mesclado)
        if not mesclado:
            abortar(op, alteradas, "env-sync", "nada_a_sincronizar")
        print(json.dumps({"preview": True, "total": len(diff),
                          "env": [{"key": k, "value": mask(v)} for k, v in diff.items()]}))
        data = [{"key": k, "value": v} for k, v in diff.items()]
        if not data:
            marcar_etapa(op, "env-sync", True, "sem_mudancas")
            return
        s, b = api_req(a.base_url, a.token_file, "PATCH",
                       "/services/" + a.service_uuid + "/envs/bulk", {"data": data})
        if s not in (200, 201):
            abortar(op, alteradas, "env-sync", "env_sync_falhou", "status=%d" % s)
        alteradas.append("env-sync")
        marcar_etapa(op, "env-sync", True, "total=%d" % len(data))

    def passo_restart(ctx):
        op = ctx["op"]
        alteradas = ctx["alteradas"]
        a = ctx["a"]
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_restart(a)
        sys.stdout.write(buf.getvalue())
        try:
            st_restart = json.loads(buf.getvalue().strip().split("\n")[-1]).get("status", 0)
        except Exception:
            st_restart = 0
        if st_restart not in (200, 201, 202):
            abortar(op, alteradas, "restart", "restart_falhou", "status=%s" % st_restart)
        alteradas.append("restart")
        marcar_etapa(op, "restart", True, "status=%d" % st_restart)

    def passo_aguardar_deploy(ctx):
        op = ctx["op"]
        alteradas = ctx["alteradas"]
        a = ctx["a"]
        ref = ctx["ref"]
        for _ in range(60):
            r = run_lines(a.ssh, "docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}'")
            if r["ok"] and containers_novos_ok(r["stdout"] or "", ref):
                marcar_etapa(op, "aguardar-deploy", True, "tag=" + ref)
                return
            time.sleep(10)
        abortar(op, alteradas, "aguardar-deploy", "deploy_nao_estabilizou", "tag=" + ref)

    def passo_poll_tls(ctx):
        op = ctx["op"]
        alteradas = ctx["alteradas"]
        a = ctx["a"]
        if not (a.app_fqdn or ""):
            abortar(op, alteradas, "poll-tls", "poll_tls_sem_fqdn")
        ns_tls = SimpleNamespace(url="https://" + a.app_fqdn, attempts=18)
        buf = io.StringIO()
        with redirect_stdout(buf):
            cmd_poll_tls(ns_tls)
        sys.stdout.write(buf.getvalue())
        try:
            saida_tls = json.loads(buf.getvalue().strip().split("\n")[-1])
        except Exception:
            saida_tls = {}
        if not saida_tls.get("ok"):
            abortar(op, alteradas, "poll-tls", "poll_tls_falhou", str(saida_tls.get("reason", ""))[:200])
        marcar_etapa(op, "poll-tls", True, "https://" + a.app_fqdn)

    def executar_de(ctx, inicio):
        passos = {"snapshot": passo_snapshot, "sync-compose": passo_sync_compose,
                   "db-apply": passo_db_apply, "env-sync": passo_env_sync,
                   "restart": passo_restart, "aguardar-deploy": passo_aguardar_deploy,
                   "poll-tls": passo_poll_tls}
        for etapa in ORDEM_ETAPAS_UPDATE[ORDEM_ETAPAS_UPDATE.index(inicio):]:
            passos[etapa](ctx)

    def finalizar(ctx):
        print(json.dumps({"ok": True, "anterior": ctx["instalada"], "nova": ctx["ref"],
                          "backup": ctx["backup"], "snapshot": ctx["snap_path"],
                          "sql": "aplicado" if ctx["sql_aplicado"] else "pulado",
                          "motivo_sql": ctx["motivo_sql"], "registro": ctx["op_dir"]}))

    if a.resume:
        try:
            with open(a.op, "r", encoding="utf-8") as f:
                op = json.load(f)
        except Exception:
            op = None
        if not isinstance(op, dict) or not isinstance(op.get("etapas"), list):
            print(json.dumps({"ok": False, "reason": "op_invalida"}))
            sys.exit(1)
        try:
            ref = validar_ref(op.get("ref"))
            if validar_ref(a.ref) != ref:
                raise ValueError("op_invalida")
        except ValueError:
            print(json.dumps({"ok": False, "reason": "op_invalida"}))
            sys.exit(1)
        if a.dry_run:
            print(json.dumps({"dry_run": True, "ref": ref,
                              "etapas": ["pre-voo", "snapshot", "sync-compose",
                                         "db-apply" if not a.skip_sql else "db-apply(pulado)",
                                         "env-sync(preview)", "restart", "poll-tls"],
                              "skip_sql": bool(a.skip_sql)}))
            return
        proxima = proxima_etapa(op)
        if proxima == "concluido":
            print(json.dumps({"ok": True, "acao": "retomada_concluida"}))
            return
        if not (a.app_fqdn or ""):
            print(json.dumps({"ok": False, "reason": "app_fqdn_ausente"}))
            sys.exit(1)
        try:
            with open(a.compose_file, "r", encoding="utf-8") as f:
                template = f.read()
        except OSError:
            print(json.dumps({"ok": False, "reason": "compose_nao_lido"}))
            sys.exit(1)
        try:
            env_base = resolver_env_base(a)
        except OSError:
            print(json.dumps({"ok": False, "reason": "env_arquivo_nao_lido"}))
            sys.exit(1)
        except ValueError as e:
            print(json.dumps({"ok": False, "reason": "env_painel_nao_lido",
                              "detalhe": str(e)[:200]}))
            sys.exit(1)
        op_dir = op.get("dir_saida") or tempfile.mkdtemp(prefix="deskcomm-update-")
        try:
            os.makedirs(op_dir, exist_ok=True)
        except OSError:
            print(json.dumps({"ok": False, "reason": "op_invalida"}))
            sys.exit(1)
        if (a.backup or ""):
            val = run_lines(a.ssh, "test -s " + shlex.quote(BACKUP_DIR + "/" + a.backup))
            if not val.get("ok"):
                print(json.dumps({"ok": False, "reason": "backup_nao_validado"}))
                sys.exit(1)
            backup_nome = a.backup
        else:
            backup_nome = "nao_informado"
        feitas = {e["etapa"] for e in op.get("etapas", []) if e.get("ok")}
        alteradas = [e["etapa"] for e in op.get("etapas", [])
                     if e.get("ok") and e["etapa"] in ("sync-compose", "db-apply",
                                                      "env-sync", "restart")]
        s, b = api_req(a.base_url, a.token_file, "GET", "/services/" + a.service_uuid)
        if s != 200:
            if "sync-compose" in feitas:
                divergente("sync-compose")
            abortar(op, alteradas, proxima, "service_nao_lido", "status=%d" % s)
        try:
            payload = json.loads(b)
        except Exception:
            payload = {}
        tags_painel = extrair_tags_imagens(texto_imagens_painel(payload))
        painel_compose = texto_imagens_painel(payload)
        if "sync-compose" in feitas:
            if len(tags_painel) != len(IMAGENS_DESKCOMM) or set(tags_painel.values()) != {ref}:
                divergente("sync-compose")
        if "db-apply" in feitas:
            if not (a.ssh or ""):
                divergente("db-apply")
            env = env_base
            db_url = env.get("SUPABASE_DB_URL", "")
            if not db_url or "'" in db_url:
                divergente("db-apply")
            img = "docker run --rm postgres:16-alpine psql " + shlex.quote(db_url)
            v = run_lines(a.ssh, img + " -tAc \"select count(*) from information_schema.tables "
                          "where table_schema='public'\"")
            try:
                n_tabelas = int((v["stdout"] or "").strip().split("\n")[-1].strip())
            except (ValueError, IndexError):
                n_tabelas = 0
            m = run_lines(a.ssh, img + " -tAc \"select coalesce(string_agg(t, ','), '') from "
                          "(values ('job_queue'),('lead_checkpoints'),('agent_inbox_items'),"
                          "('send_ledger')) as x(t) where to_regclass('public.'||t) is null\"")
            ausentes = (m["stdout"] or "").strip().split("\n")[-1].strip() if m["ok"] else "?"
            if n_tabelas < 30 or ausentes != "":
                divergente("db-apply")
        instalada = ""
        for e in op.get("etapas", []):
            if e.get("etapa") == "pre-voo" and e.get("ok"):
                instalada = (e.get("detalhe") or "").split("->")[0].strip()
                break
        if "sync-compose" not in feitas:
            if not instalada:
                vals = sorted({t for t in tags_painel.values() if re.fullmatch(r"\d+\.\d+\.\d+", t)},
                              key=lambda v: tuple(int(x) for x in v.split(".")))
                instalada = vals[-1] if vals else ""
                if not instalada:
                    abortar(op, alteradas, proxima, "tag_instalada_nao_identificada")
                if len(set(tags_painel.values())) > 1:
                    abortar(op, alteradas, proxima, "tags_divergentes",
                            ",".join(sorted(set(tags_painel.values()))))
        elif not instalada:
            instalada = ref
        if (a.sql or ""):
            sql_path = a.sql
        elif a.skip_sql or "db-apply" in feitas:
            sql_path = ""
        else:
            try:
                sql_path = baixar_baseline_release(ref, op_dir)
            except Exception as e:
                print(json.dumps({"ok": False, "reason": "sql_download_falhou",
                                  "detalhe": str(e)[:200]}))
                sys.exit(1)
        ctx = {"a": a, "op": op, "op_dir": op_dir, "alteradas": alteradas,
               "template": template, "ref": ref, "instalada": instalada,
               "painel_compose": painel_compose, "motivo_sql": "", "sql_aplicado": False,
               "snap_path": "", "sql_path": sql_path, "backup": backup_nome,
               "env_base": env_base}
        for e in op.get("etapas", []):
            if e.get("etapa") == "snapshot" and e.get("ok") and e.get("detalhe"):
                ctx["snap_path"] = os.path.join(op_dir, e["detalhe"])
            if e.get("etapa") == "db-apply" and e.get("ok"):
                det = e.get("detalhe") or ""
                if det.startswith("tables="):
                    ctx["sql_aplicado"] = True
                    ctx["motivo_sql"] = "baseline_mudou"
                elif det:
                    ctx["motivo_sql"] = det
        executar_de(ctx, proxima)
        finalizar(ctx)
        return
    try:
        ref = validar_ref(a.ref)
    except ValueError:
        print(json.dumps({"ok": False, "reason": "ref_invalida"}))
        sys.exit(1)
    try:
        with open(a.compose_file, "r", encoding="utf-8") as f:
            template = f.read()
    except OSError:
        print(json.dumps({"ok": False, "reason": "compose_nao_lido"}))
        sys.exit(1)
    if a.dry_run:
        print(json.dumps({"dry_run": True, "ref": ref,
                          "etapas": ["pre-voo", "snapshot", "sync-compose",
                                     "db-apply" if not a.skip_sql else "db-apply(pulado)",
                                     "env-sync(preview)", "restart", "aguardar-deploy", "poll-tls"],
                          "skip_sql": bool(a.skip_sql)}))
        return
    if not (a.app_fqdn or ""):
        print(json.dumps({"ok": False, "reason": "app_fqdn_ausente"}))
        sys.exit(1)
    if not (a.ssh or ""):
        print(json.dumps({"ok": False, "reason": "ssh_ausente"}))
        sys.exit(1)
    if (a.backup or ""):
        val = run_lines(a.ssh, "test -s " + shlex.quote(BACKUP_DIR + "/" + a.backup))
        if not val.get("ok"):
            print(json.dumps({"ok": False, "reason": "backup_nao_validado"}))
            sys.exit(1)
        backup_nome = a.backup
    else:
        backup_nome = "nao_informado"
    try:
        env_base = resolver_env_base(a)
    except OSError:
        print(json.dumps({"ok": False, "reason": "env_arquivo_nao_lido"}))
        sys.exit(1)
    except ValueError as e:
        print(json.dumps({"ok": False, "reason": "env_painel_nao_lido",
                          "detalhe": str(e)[:200]}))
        sys.exit(1)
    op_dir = tempfile.mkdtemp(prefix="deskcomm-update-")
    op = novo_registro_operacao(ref, op_dir)
    alteradas = []
    if (a.sql or ""):
        sql_path = a.sql
    elif a.skip_sql:
        sql_path = ""
    else:
        try:
            sql_path = baixar_baseline_release(ref, op_dir)
        except Exception as e:
            print(json.dumps({"ok": False, "reason": "sql_download_falhou",
                              "detalhe": str(e)[:200]}))
            sys.exit(1)
    s, b = api_req(a.base_url, a.token_file, "GET", "/services/" + a.service_uuid)
    if s != 200:
        abortar(op, alteradas, "pre-voo", "service_nao_lido", "status=%d" % s)
    try:
        payload = json.loads(b)
    except Exception:
        payload = {}
    tags = extrair_tags_imagens(texto_imagens_painel(payload))
    painel_compose = texto_imagens_painel(payload)
    vals = sorted({t for t in tags.values() if re.fullmatch(r"\d+\.\d+\.\d+", t)},
                  key=lambda v: tuple(int(x) for x in v.split(".")))
    instalada = vals[-1] if vals else ""
    if not instalada:
        abortar(op, alteradas, "pre-voo", "tag_instalada_nao_identificada")
    if len(set(tags.values())) > 1:
        abortar(op, alteradas, "pre-voo", "tags_divergentes", ",".join(sorted(set(tags.values()))))
    try:
        acao = comparar_versoes(instalada, ref)
    except ValueError:
        abortar(op, alteradas, "pre-voo", "alvo_anterior_a_instalada", instalada + "->" + ref)
    if acao == "nada_a_fazer":
        marcar_etapa(op, "pre-voo", True, instalada)
        print(json.dumps({"ok": True, "acao": "nada_a_fazer", "instalada": instalada}))
        return
    marcar_etapa(op, "pre-voo", True, instalada + "->" + ref)
    ctx = {"a": a, "op": op, "op_dir": op_dir, "alteradas": alteradas,
           "template": template, "ref": ref, "instalada": instalada,
           "painel_compose": painel_compose, "motivo_sql": "", "sql_aplicado": False,
           "snap_path": "", "sql_path": sql_path, "backup": backup_nome,
           "env_base": env_base}
    executar_de(ctx, "snapshot")
    finalizar(ctx)


def cmd_set_fqdn(a):
    fqdn = a.fqdn.replace("'", "''")
    r = run_script_file(a.ssh, "set -euo pipefail\n"
        "docker exec -i coolify-db psql -U coolify -d coolify -v ON_ERROR_STOP=1 -c "
        "\"UPDATE service_applications SET fqdn='https://" + fqdn + "' "
        "WHERE id=" + str(a.app_id) + ";\" </dev/null\n"
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
    ic = sub.add_parser("install-coolify"); ic.add_argument("--ssh", required=True)
    ic.add_argument("--attempts", type=int, default=60)
    w = sub.add_parser("wait-admin"); w.add_argument("--ssh", required=True)
    w.add_argument("--attempts", type=int, default=120)
    e = sub.add_parser("enable-api"); e.add_argument("--ssh", required=True)
    t = sub.add_parser("token"); t.add_argument("--ssh", required=True)
    t.add_argument("--out", required=True); t.add_argument("--base-url", default="")
    cp = sub.add_parser("create-project"); cp.add_argument("--base-url", required=True)
    cp.add_argument("--token-file", required=True)
    cp.add_argument("--description", default="")
    cs = sub.add_parser("ensure-service"); cs.add_argument("--base-url", required=True)
    cs.add_argument("--token-file", required=True); cs.add_argument("--project-uuid", required=True)
    cs.add_argument("--name", default="deskcommcrm"); cs.add_argument("--server-uuid", default="")
    cs.add_argument("--compose-file", required=True)
    cs.add_argument("--environment", default="production")
    sc = sub.add_parser("sync-compose"); sc.add_argument("--base-url", required=True)
    sc.add_argument("--token-file", required=True); sc.add_argument("--service-uuid", required=True)
    sc.add_argument("--compose-file", required=True)
    idd = sub.add_parser("instance-domain"); idd.add_argument("--ssh", required=True)
    dc = sub.add_parser("dns-check"); dc.add_argument("--app-fqdn", required=True)
    dc.add_argument("--panel-fqdn", required=True); dc.add_argument("--vps-ip", required=True)
    dc.add_argument("--allow-unresolved", action="store_true")
    g = sub.add_parser("api-get"); g.add_argument("--base-url", required=True)
    g.add_argument("--token-file", required=True); g.add_argument("--path", required=True)
    es = sub.add_parser("env-sync"); es.add_argument("--base-url", required=True)
    es.add_argument("--token-file", required=True); es.add_argument("--service-uuid", required=True)
    es.add_argument("--file", default=""); es.add_argument("--app-fqdn", default="")
    es.add_argument("--preview", action="store_true")
    en = sub.add_parser("env-set"); en.add_argument("--base-url", required=True)
    en.add_argument("--token-file", required=True); en.add_argument("--service-uuid", required=True)
    en.add_argument("--set", nargs="+", required=True,
                    help="pares CHAVE=valor (ex.: RESEND_API_KEY=re_...); imprime so os nomes")
    sf = sub.add_parser("set-fqdn"); sf.add_argument("--ssh", required=True)
    sf.add_argument("--app-id", required=True); sf.add_argument("--fqdn", required=True)
    da = sub.add_parser("db-apply"); da.add_argument("--ssh", required=True)
    da.add_argument("--file", required=True); da.add_argument("--sql", required=True)
    bo = sub.add_parser("bootstrap-owner"); bo.add_argument("--ssh", required=True)
    bo.add_argument("--file", required=True); bo.add_argument("--email", required=True)
    bo.add_argument("--password", required=True)
    rs = sub.add_parser("restart"); rs.add_argument("--base-url", required=True)
    rs.add_argument("--token-file", required=True); rs.add_argument("--service-uuid", required=True)
    pt = sub.add_parser("poll-tls"); pt.add_argument("--url", required=True)
    pt.add_argument("--attempts", type=int, default=18)
    vs = sub.add_parser("version-status"); vs.add_argument("--base-url", required=True)
    vs.add_argument("--token-file", required=True); vs.add_argument("--service-uuid", required=True)
    up = sub.add_parser("update"); up.add_argument("--base-url", required=True)
    up.add_argument("--token-file", required=True); up.add_argument("--service-uuid", required=True)
    up.add_argument("--ref", required=True); up.add_argument("--compose-file", required=True)
    up.add_argument("--file", default=""); up.add_argument("--sql", default="")
    up.add_argument("--backup", default="")
    up.add_argument("--app-fqdn", default=""); up.add_argument("--dry-run", action="store_true")
    up.add_argument("--skip-sql", action="store_true")
    up.add_argument("--op", default="")
    up.add_argument("--resume", action="store_true")
    up.add_argument("--ssh", default="")
    a = p.parse_args()
    if a.cmd == "heal-localhost":
        cmd_heal_localhost(a)
    elif a.cmd == "install-coolify":
        cmd_install_coolify(a)
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
    elif a.cmd == "dns-check":
        cmd_dns_check(a)
    elif a.cmd == "api-get":
        s, b = api_req(a.base_url, a.token_file, "GET", a.path)
        print(json.dumps({"status": s, "body": b[:2000]}))
    elif a.cmd == "env-sync":
        cmd_env_sync(a)
    elif a.cmd == "env-set":
        cmd_env_set(a)
    elif a.cmd == "set-fqdn":
        cmd_set_fqdn(a)
    elif a.cmd == "db-apply":
        cmd_db_apply(a)
    elif a.cmd == "bootstrap-owner":
        cmd_bootstrap_owner(a)
    elif a.cmd == "restart":
        cmd_restart(a)
    elif a.cmd == "poll-tls":
        cmd_poll_tls(a)
    elif a.cmd == "version-status":
        cmd_version_status(a)
    elif a.cmd == "update":
        cmd_update(a)


if __name__ == "__main__":
    main()
