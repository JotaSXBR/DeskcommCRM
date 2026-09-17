#!/usr/bin/env python3
"""Supabase para o overlay Coolify (receita do kit, via Management API).
Cria o projeto, ESPERA ficar ACTIVE_HEALTHY, descobre o pooler por conexao
real, configura a Site URL e grava base.env. Stdlib only.
Segredo nunca no stdout: so status, nomes e contagens.
Uso: python3 supabase.py orgs --token-file supabase.token
     python3 supabase.py provision --token-file supabase.token --org-id ID
       --name deskcommcrm --region sa-east-1 --app-fqdn crm.exemplo.com.br
       --ssh root@IP --out base.env
"""
import argparse
import base64
import hashlib
import html
import json
import os
import re
import secrets
import string
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from remote import run_script_file  # noqa: E402


def read_secret(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def sb_api(token, method, path, body=None):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request("https://api.supabase.com/v1" + path,
                                 data=data, method=method)
    req.add_header("Authorization", "Bearer " + token)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except Exception as e:
        fp = getattr(e, "fp", None)
        detail = ""
        if fp is not None:
            try:
                detail = fp.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
        code = getattr(fp, "status", 0) or 0
        return code, detail


def cmd_orgs(a):
    token = read_secret(a.token_file)
    s, orgs = sb_api(token, "GET", "/organizations")
    if s != 200 or not isinstance(orgs, list):
        print(json.dumps({"ok": False, "status": s}))
        sys.exit(1)
    print(json.dumps({"ok": True, "orgs": [
        {"id": o.get("id"), "name": o.get("name")} for o in orgs]}))


def cmd_provision(a):
    token = read_secret(a.token_file)
    s, orgs = sb_api(token, "GET", "/organizations")
    names = {o.get("id"): o.get("name") for o in orgs} if s == 200 else {}
    if a.org_id not in names:
        print(json.dumps({"ok": False, "reason": "org_nao_achada"}))
        sys.exit(1)
    print("[1/6] organizacao: %s" % names[a.org_id], flush=True)
    s, projs = sb_api(token, "GET", "/projects")
    if s == 200:
        for p in projs:
            if (isinstance(p, dict) and p.get("name") == a.name
                    and p.get("organization_id") == a.org_id):
                print(json.dumps({"ok": False, "reason": "projeto_ja_existe",
                                  "ref": p.get("id")}))
                sys.exit(1)
    db_pass = "".join(secrets.choice(string.ascii_letters + string.digits)
                       for _ in range(32))
    print("[2/6] criando projeto '%s' em %s..." % (a.name, a.region), flush=True)
    s, created = sb_api(token, "POST", "/projects",
                        {"name": a.name, "organization_id": a.org_id,
                         "region": a.region, "db_pass": db_pass})
    ref = created.get("ref", "") if isinstance(created, dict) else ""
    if s not in (200, 201) or not ref:
        print(json.dumps({"ok": False, "reason": "criacao_falhou",
                          "status": s, "detail": created}))
        sys.exit(1)
    print("[3/6] aguardando o banco subir (ate 10 min)...", flush=True)
    ok = False
    for i in range(60):
        time.sleep(10)
        s, proj = sb_api(token, "GET", "/projects/" + ref)
        st = proj.get("status", "") if isinstance(proj, dict) else ""
        if st == "ACTIVE_HEALTHY":
            ok = True
            break
        if st in ("INACTIVE", "REMOVED", "RESTORE_FAILED"):
            print(json.dumps({"ok": False, "reason": "projeto_" + st.lower(),
                              "ref": ref}))
            sys.exit(1)
        if i % 6 == 0:
            print("  ...%s" % (st or ("http=%s" % s)), flush=True)
    if not ok:
        print(json.dumps({"ok": False, "reason": "timeout_active_healthy",
                          "ref": ref}))
        sys.exit(1)
    print("[4/6] buscando chaves de API...", flush=True)
    s, keys = sb_api(token, "GET", "/projects/" + ref + "/api-keys")
    by_name = {}
    if isinstance(keys, list):
        for k in keys:
            if isinstance(k, dict) and k.get("name") and k.get("api_key"):
                by_name[k["name"]] = k["api_key"]
    if "anon" not in by_name or "service_role" not in by_name:
        print(json.dumps({"ok": False, "reason": "chaves_nao_lidas", "ref": ref,
                          "achadas": sorted(by_name)}))
        sys.exit(1)
    print("[5/6] descobrindo o pooler por conexao real (via VPS)...", flush=True)
    pooler_n = None
    for n in (0, 1, 2):
        host = "aws-%d-%s.pooler.supabase.com" % (n, a.region)
        cand = ("postgresql://postgres.%s:%s@%s:5432/postgres"
                % (ref, db_pass, host))
        script = ("set -euo pipefail\n"
                  "docker run --rm postgres:16-alpine psql '"
                  + cand.replace("'", "'\"'\"'") + "' -c 'select 1' "
                  ">/dev/null 2>&1 && echo POOLER_OK || echo POOLER_FAIL\n")
        r = run_script_file(a.ssh, script)
        if "POOLER_OK" in (r["stdout"] or ""):
            pooler_n = n
            break
    if pooler_n is None:
        print(json.dumps({"ok": False, "reason": "pooler_sem_resposta",
                          "ref": ref}))
        sys.exit(1)
    app_url = "https://" + a.app_fqdn
    print("[6/6] configurando Site URL + gravando base.env...", flush=True)
    s, auth_cfg = sb_api(token, "GET", "/projects/" + ref + "/config/auth")
    site_key = None
    if isinstance(auth_cfg, dict):
        for k in auth_cfg:
            if k.lower() == "site_url":
                site_key = k
                break
    site_ok = False
    if site_key:
        s, _ = sb_api(token, "PATCH", "/projects/" + ref + "/config/auth",
                       {site_key: app_url})
        site_ok = s in (200, 201, 204)
    hx = lambda n=32: secrets.token_hex(n)  # noqa: E731
    b64 = lambda n=32: base64.b64encode(secrets.token_bytes(n)).decode()  # noqa: E731
    waha_key = hx()
    env = {
        "NEXT_PUBLIC_SUPABASE_URL": "https://%s.supabase.co" % ref,
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": by_name["anon"],
        "SUPABASE_SERVICE_ROLE_KEY": by_name["service_role"],
        "SUPABASE_DB_URL": ("postgresql://postgres.%s:%s@aws-%d-%s"
                            ".pooler.supabase.com:5432/postgres"
                            % (ref, db_pass, pooler_n, a.region)),
        "INTERNAL_SECRET": hx(),
        "INTERNAL_CRON_SECRET": hx(),
        "CPF_ENCRYPTION_KEY": hx(),
        "WAHA_BYO_ENCRYPTION_KEY": hx(),
        "AI_CRED_AES_KEY": b64(),
        "WAHA_API_KEY": waha_key,
        "WAHA_API_KEY_SHA512": hashlib.sha512(waha_key.encode()).hexdigest(),
        "WAHA_HMAC_SECRET": hx(),
        "SRH_TOKEN": hx(),
        "SENTRY_DSN": a.sentry,
    }
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for k, v in env.items():
            f.write("%s=%s\n" % (k, v))
    try:
        os.chmod(a.out, 0o600)
    except Exception:
        pass
    print(json.dumps({"ok": True, "ref": ref, "region": a.region,
                      "pooler": "aws-%d-%s" % (pooler_n, a.region),
                      "site_ok": site_ok, "chaves": len(env),
                      "out": a.out}))


def cmd_marca_emails(a):
    import time as _t
    token = read_secret(a.token_file)
    env = {}
    with open(a.file, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    m = re.match(r"https://([a-z0-9]+)\.supabase\.co",
                 env.get("NEXT_PUBLIC_SUPABASE_URL", ""))
    if not m:
        print(json.dumps({"ok": False, "reason": "url_nao_e_nuvem"}))
        sys.exit(1)
    ref = m.group(1)
    app_url = "https://" + a.app_fqdn
    accent = a.accent if re.fullmatch(r"#[0-9a-fA-F]{6}", a.accent or "") else "#506d48"
    fg = _frente_sobre(accent)
    tpl_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "supabase", "templates")
    try:
        with open(os.path.join(tpl_dir, "confirmation.html"), encoding="utf-8") as f:
            confirm = f.read()
        with open(os.path.join(tpl_dir, "recovery.html"), encoding="utf-8") as f:
            recovery = f.read()
    except OSError:
        print(json.dumps({"ok": False, "reason": "templates_nao_achados"}))
        sys.exit(1)
    marcador = "marca-emails-%d" % int(_t.time())
    marca_esc = html.escape(a.marca, quote=True)
    confirm = "<!-- %s -->\n" % marcador + _sem_nota(confirm).replace(
        "__APP_NAME__", marca_esc).replace("__ACCENT_FG__", fg).replace(
        "__ACCENT__", accent)
    recovery = "<!-- %s -->\n" % marcador + _sem_nota(recovery).replace(
        "__APP_NAME__", marca_esc).replace("__ACCENT_FG__", fg).replace(
        "__ACCENT__", accent)
    s, atual = sb_api(token, "GET", "/projects/" + ref + "/config/auth")
    if not isinstance(atual, dict) or "message" in atual:
        print(json.dumps({"ok": False, "reason": "leitura_recusada",
                          "detail": atual if isinstance(atual, str) else
                          atual.get("message", "")}))
        sys.exit(1)
    site_atual = _cfg(atual, "site_url") or ""
    allow_atual = _cfg(atual, "uri_allow_list") or ""
    if isinstance(allow_atual, list):
        allow_atual = ",".join(allow_atual)
    site_novo = site_atual
    if site_atual.rstrip("/") in ("", "http://localhost:3000"):
        site_novo = app_url
    allow_novo = allow_atual
    for entrada in (app_url.rstrip("/") + "/auth/confirm",
                    app_url.rstrip("/") + "/**"):
        if entrada not in [x.strip() for x in allow_novo.split(",") if x.strip()]:
            allow_novo = allow_novo + "," + entrada if allow_novo else entrada
    corpo_urls = {"site_url": site_novo, "uri_allow_list": allow_novo}
    s, _ = sb_api(token, "PATCH", "/projects/" + ref + "/config/auth", corpo_urls)
    urls_ok = s in (200, 201, 204)
    s, depois = sb_api(token, "GET", "/projects/" + ref + "/config/auth")
    if isinstance(depois, dict):
        urls_ok = urls_ok and (depois.get("uri_allow_list", "") == allow_novo)
    else:
        urls_ok = False
    # Modelos: o Supabase passou a recusar em projeto free sem SMTP próprio (400).
    # URLs valem mais que marca: link quebrado ninguém clica, e-mail em inglês sim.
    corpo_tpl = {"mailer_subjects_confirmation": "Confirme seu e-mail \u2014 " + a.marca,
                 "mailer_subjects_recovery": "Redefinir senha \u2014 " + a.marca,
                 "mailer_templates_confirmation_content": confirm,
                 "mailer_templates_recovery_content": recovery}
    s, resp = sb_api(token, "PATCH", "/projects/" + ref + "/config/auth", corpo_tpl)
    templates_ok, templates_motivo = False, "http_%d" % s
    if s in (200, 201, 204):
        s, depois = sb_api(token, "GET", "/projects/" + ref + "/config/auth")
        texto = json.dumps(depois) if not isinstance(depois, str) else depois
        if marcador in texto:
            templates_ok, templates_motivo = True, "conferido_por_releitura"
        else:
            templates_motivo = "releitura_nao_confere"
    elif s == 400 and "free tier" in str(resp):
        templates_motivo = "free_tier_sem_smtp"
    print(json.dumps({"ok": urls_ok, "marca": a.marca, "site": site_novo,
                      "site_aviso": site_depois_ok(site_novo, app_url, depois),
                      "redirects": allow_novo, "templates_ok": templates_ok,
                      "templates_motivo": templates_motivo}))
    if not urls_ok:
        sys.exit(1)


def site_depois_ok(site_novo, app_url, depois):
    if not isinstance(depois, dict):
        return True
    for k, v in depois.items():
        if k.lower() == "site_url":
            return str(v).rstrip("/") != app_url.rstrip("/")
    return True


def _cfg(d, nome):
    for k, v in d.items():
        if k.lower() == nome:
            return v
    return None


def _sem_nota(texto):
    if texto.lstrip().startswith("<!--"):
        fim = texto.find("-->")
        if fim != -1:
            return texto[fim + 3:].lstrip("\n")
    return texto


def _frente_sobre(accent):
    h = accent.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#171f15" if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.6 else "#ffffff"


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("orgs")
    o.add_argument("--token-file", required=True)
    v = sub.add_parser("provision")
    v.add_argument("--token-file", required=True)
    v.add_argument("--org-id", required=True)
    v.add_argument("--name", default="deskcommcrm")
    v.add_argument("--region", default="sa-east-1")
    v.add_argument("--app-fqdn", required=True)
    v.add_argument("--ssh", required=True)
    v.add_argument("--out", required=True)
    v.add_argument("--sentry", required=True)
    e = sub.add_parser("marca-emails")
    e.add_argument("--token-file", required=True)
    e.add_argument("--file", required=True)
    e.add_argument("--app-fqdn", required=True)
    e.add_argument("--marca", default="DeskcommCRM")
    e.add_argument("--accent", default="#506d48")
    a = p.parse_args()
    if a.cmd == "orgs":
        cmd_orgs(a)
    elif a.cmd == "provision":
        cmd_provision(a)
    elif a.cmd == "marca-emails":
        cmd_marca_emails(a)


if __name__ == "__main__":
    main()
