# Coolify nativo via OpenCode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Estender `deskcomm-instalar` com a trilha Coolify nativa executada por agente (docs + 3 scripts + template compose) e aplicar os 3 toques em `deskcomm-cliente-novo`, sem enviar nada ao upstream.

**Architecture:** Só docs e helpers novos sob `.agents/skills/deskcomm-instalar/`; nenhum compose de produção é alterado; template Coolify é arquivo novo; scripts são Python stdlib que centralizam SSH e API do Coolify para que o PowerShell nunca carregue payload.

**Tech Stack:** Markdown (skills), Python 3 stdlib (scripts), YAML (template), Vitest gates existentes.

**Spec:** `docs/superpowers/specs/2026-09-16-coolify-opencode-design.md`

## Global Constraints

- Branch `feat/coolify-opencode`; `origin` aponta só ao fork `https://github.com/JotaSXBR/DeskcommCRM`; sem remote `upstream`, sem push e sem PR a `melgarafael/DeskcommCRM`.
- Commits com identidade local `Jessé Pasqualin <jotasx@gmail.com>`; mensagens em conventional commits.
- PT-BR com acentuação correta em docs; nada de em-dash em texto de skill.
- Nenhum segredo, token ou chave em repo, log, commit ou transcript; token do Coolify vive em arquivo `0600` transitório.
- Corpo de `SKILL.md` cabe em 500 linhas; `description` de 1 a 1024 caracteres; `name` igual ao diretório.
- Todo path `references/`, `scripts/` ou `assets/` citado num `SKILL.md` precisa existir no disco.
- Após qualquer edição em `.agents/skills/`, rodar `pnpm skills:sync` e commitar as duas cópias (fonte e espelho `.claude/skills/`).
- Template Coolify: sem `caddy`, sem `ports: 80/443`, sem `network_mode: host`, sem label `traefik.enable` (TLS vem do FQDN configurado no painel).

---

## File Map

| Arquivo | Responsabilidade |
|---|---|
| `.agents/skills/deskcomm-instalar/SKILL.md` (edit) | 4ª pergunta de roteamento para a trilha Coolify |
| `.agents/skills/deskcomm-instalar/references/coolify-agente.md` (new) | Passo a passo do deploy como service Coolify nativo |
| `.agents/skills/deskcomm-instalar/references/coolify-gotchas.md` (new) | Sintoma, causa e fix de cada armadilha medida |
| `.agents/skills/deskcomm-instalar/scripts/remote.py` (new) | Dono do payload remoto via SSH |
| `.agents/skills/deskcomm-instalar/scripts/docker-status.py` (new) | `docker ps` normalizado em JSON |
| `.agents/skills/deskcomm-instalar/scripts/coolify.py` (new) | Operações da API do Coolify com token em arquivo |
| `.agents/skills/deskcomm-instalar/templates/docker-compose.coolify.yml` (new) | Compose do service, derivado do `prod` sem `caddy` |
| `.agents/skills/deskcomm-cliente-novo/SKILL.md` (edit) | 3 toques: Passo 0, Passo 4, `nunca fazer` |
| `.changes/coolify-opencode.md` (new) | Fragmento de release `capacidade_nova` |

---

### Task 1: Roteamento + os dois references da trilha Coolify

**Files:**
- Modify: `.agents/skills/deskcomm-instalar/SKILL.md`
- Create: `.agents/skills/deskcomm-instalar/references/coolify-agente.md`
- Create: `.agents/skills/deskcomm-instalar/references/coolify-gotchas.md`

**Interfaces:**
- Consumes: tabela de cenário do `SKILL.md` (linhas 31-39), `docker-compose.prod.yml`, gotchas do `fazer-ai/agents-skills`.
- Produces: âncora `references/coolify-agente.md` que a Task 3 (scripts) e a Task 4 (template) referenciam pelo nome de cada comando.

- [ ] **Step 1: RED, inserir só a citação e ver o gate acusar**

No fim da tabela de cenário do `SKILL.md`, após a linha do `É para você ou para um cliente?`, inserir esta linha:

```markdown
| **Vai instalar pelo painel Coolify, com o agente operando?** | Se sim, pare aqui e leia `references/coolify-agente.md` — o caminho abaixo (VPS crua + `install.sh` + Caddy) não vale para service gerido pelo Coolify |
```

Run: `npx vitest run tests/unit/skills-embutidas.test.ts`
Expected: FAIL com `deskcomm-instalar cita arquivo que não existe` listando `references/coolify-agente.md`. Se passar, o gate não enxergou a citação: pare e investigue o regex antes de seguir.

- [ ] **Step 2: GREEN, criar `references/coolify-gotchas.md` com este conteúdo**

```markdown
# Coolify + OpenCode no Windows: armadilhas que já morderam

## PowerShell nunca carrega payload, só orquestra

Nada de `ssh <host> '...script...'` com aspas, `{{...}}`, `$()`, `\` no fim
da linha ou here-string: o PowerShell come aspas, prefixa BOM e re-encoda
acentos. Escreva o payload num arquivo com a ferramenta de edição e rode
`python3 scripts/remote.py --ssh root@<VPS_IP> --script-file x.sh`.
Só vai inline o comando de uma linha sem `"`, `$()`, `{{...}}`, `(` ou `\`.

## FQDN dirige o Traefik, env não

Num service do Coolify, a rota nasce de `service_applications.fqdn` no banco
do Coolify. Ajuste com
`python3 scripts/coolify.py set-fqdn --ssh root@<VPS_IP> --app-id <id> --fqdn https://<DOMAIN>`
(preserve `:3000` se o template declarar porta). Sintoma de FQDN errado:
tudo saudável e `503` no domínio.

## Compose cru na API precisa de base64

`POST /api/v1/services` com compose cru devolve `422 should be base64
encoded`. Use `scripts/coolify.py create-service --compose-file ...`, que
faz o base64. Nunca monte esse POST à mão.

## Nunca sobrescrever `command:` no app ou worker

O boot (bootstrap, migrate, serve) é o CMD da imagem. Override com `command:`
derruba o contêiner em crash-loop. Não declare `command:` no template.

## `heal-localhost` antes do primeiro deploy

Se o Coolify não alcança o próprio host por SSH, todo deploy falha sem erro
claro (servidor `localhost` Unreachable). Rode
`python3 scripts/coolify.py heal-localhost --ssh root@<VPS_IP>` e siga só com
`reachable:true`. É idempotente.

## `start` da API pode não materializar: re-dispare, nunca suba à mão

Se a API responde que enfileirou e os contêineres não nascem, re-dispare o
deploy pela API ou UI do Coolify. Nunca rode `docker compose up -d` no SSH:
os contêineres sobem fora da gestão e a UI mostra Exited para sempre.

## Imagem grande: sem `docker pull` em foreground

Pull de imagem grande estoura o timeout do harness e parece falha. Confira
auth e existência com `docker manifest inspect <imagem>` e deixe o Coolify
puxar no deploy assíncrono.

## `docker ps --format '{{...}}'` quebra no PowerShell via SSH

Use `python3 scripts/docker-status.py --ssh root@<VPS_IP>` (ou `--project
<uuid>` para um service). Ele devolve JSON normalizado sem quoting manual.
```

- [ ] **Step 3: GREEN, criar `references/coolify-agente.md` com este conteúdo**

```markdown
# Deploy como service Coolify nativo, operado pelo agente

Vale só quando a VPS já tem Coolify saudável e o CRM vai viver como service
gerido pelo painel. Para VPS crua, volte ao `install.sh` do `SKILL.md`.

## 0. Pré-requisitos

Acesso SSH root à VPS, painel Coolify no ar, `DOMAIN` com registro A para o
IP da VPS, token do Supabase e chaves de IA (opcionais, entram depois pela
tela em IA, Credenciais). Nenhum segredo aparece no chat ou em log.

## 1. Brownfield read-only

```bash
python3 scripts/docker-status.py --ssh root@<VPS_IP> --all
```

Nada saudável é reinstalado. Em seguida, sempre:

```bash
python3 scripts/remote.py --ssh root@<VPS_IP> --script-file scripts/healthcheck-local.sh
python3 scripts/coolify.py heal-localhost --ssh root@<VPS_IP>
```

Siga só com `reachable:true`. O arquivo `scripts/healthcheck-local.sh`
contém exatamente: `docker ps --format '{{.Names}} {{.Status}}'`.

## 2. Token da API em arquivo 0600

```bash
python3 scripts/coolify.py enable-api --ssh root@<VPS_IP>
python3 scripts/coolify.py token --ssh root@<VPS_IP> --out coolify.token
python3 scripts/coolify.py api-get --base-url http://<VPS_IP>:8000 --token-file coolify.token --path /servers
```

O `token` nunca é impresso; `coolify.token` é transitório e nunca commitado.
Toda chamada autenticada usa `--token-file`, e JSON de POST usa `--json-file`.

## 3. Criar o service

```bash
python3 scripts/coolify.py create-service --base-url http://<VPS_IP>:8000 --token-file coolify.token --name deskcommcrm --compose-file templates/docker-compose.coolify.yml --fqdn https://<DOMAIN>
```

Sem `command:` no compose. Sem `ports: 80/443`. O TLS vem do FQDN.

## 4. Envs pelo painel ou API do service

Supabase (pooler URI, nunca Direct IPv6), `WAHA_API_KEY`,
`WAHA_HMAC_SECRET`, `INTERNAL_SECRET` e o resto do `.env.example`.
Segredo mora no env do service, em nenhum outro lugar.

## 5. Deploy e poll em background

Dispare pelo painel ou `api-post` e acompanhe serviço a serviço (app,
worker, waha, redis/srh, scheduler) com `docker-status.py --project <uuid>`.
Polls longos rodam em background; não avance sem saúde confirmada.

## 6. Pós-deploy

Abra `https://<DOMAIN>`, entre com o dono, complete o wizard, conecte o
WhatsApp pelo QR e agende `hostgator-setup-kit/backup.sh` no cron do host.
Limitação honesta: backup e update fora do painel continuam manuais até
decisão futura; o redeploy no painel não apaga a sessão se os volumes
`waha-data` e `waha-media` existirem no service.
```

- [ ] **Step 4: rodar o gate e ver passar**

Run: `npx vitest run tests/unit/skills-embutidas.test.ts tests/unit/documentacao-aponta-para-o-que-existe.test.ts`
Expected: PASS nos dois arquivos.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/deskcomm-instalar/SKILL.md .agents/skills/deskcomm-instalar/references/coolify-agente.md .agents/skills/deskcomm-instalar/references/coolify-gotchas.md
git commit -m "docs(instalar): trilha coolify nativa via agente"
```

---

### Task 2: `scripts/remote.py` e `scripts/docker-status.py`

**Files:**
- Create: `.agents/skills/deskcomm-instalar/scripts/remote.py`
- Create: `.agents/skills/deskcomm-instalar/scripts/docker-status.py`

**Interfaces:**
- Consumes: nada (stdlib + `ssh` do SO).
- Produces: CLI `remote.py --ssh --script-file [--ssh-opts] [--in-container C --exec PROG] [--capture] [--dry-run]` e `docker-status.py --ssh [--ssh-opts] [--project UUID] [--all]` que a Task 3 usa para todo acesso remoto.

- [ ] **Step 1: RED, provar que o gate acusa citação sem arquivo**

Run: `npx vitest run tests/unit/skills-embutidas.test.ts`
Expected: FAIL listando `scripts/remote.py` (citado no gotchas) como ausente. Se passar, releia o regex de citação do teste antes de seguir.

- [ ] **Step 2: criar `scripts/remote.py` com este conteúdo**

```python
#!/usr/bin/env python3
"""Roda um arquivo de script no host remoto via SSH, byte a byte via stdin.

O shell local só orquestra; o payload mora no arquivo, nunca no argv.
Uso:
  python3 remote.py --ssh root@HOST --script-file x.sh
  python3 remote.py --ssh root@HOST --in-container db --exec "psql -U u -d d -v ON_ERROR_STOP=1" --script-file q.sql --capture
"""
import argparse
import shlex
import subprocess
import sys


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssh", required=True)
    ap.add_argument("--script-file", required=True)
    ap.add_argument("--ssh-opts", default="")
    ap.add_argument("--in-container", default="")
    ap.add_argument("--exec", default="bash -s")
    ap.add_argument("--capture", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(args.script_file, "rb") as f:
        payload = f.read()

    cmd = ["ssh"]
    if args.ssh_opts:
        cmd += shlex.split(args.ssh_opts)
    cmd += [args.ssh]
    if args.in_container:
        cmd += ["docker", "exec", "-i", args.in_container] + shlex.split(args.exec)
    else:
        cmd += ["bash", "-s"]

    if args.dry_run:
        print(" ".join(shlex.quote(c) for c in cmd) + " < " + args.script_file)
        return 0

    proc = subprocess.run(cmd, input=payload, capture_output=args.capture)
    if args.capture:
        sys.stdout.write(proc.stdout.decode("utf-8", "replace"))
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: criar `scripts/docker-status.py` com este conteúdo**

```python
#!/usr/bin/env python3
"""Lista contêineres do host remoto e devolve JSON normalizado.

Evita `docker ps --format '{{...}}'` montado à mão, que o PowerShell via SSH
desfigura. Uso:
  python3 docker-status.py --ssh root@HOST [--ssh-opts "-i chave"] [--project UUID] [--all]
"""
import argparse
import json
import shlex
import subprocess


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssh", required=True)
    ap.add_argument("--ssh-opts", default="")
    ap.add_argument("--project", default="")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    inner = ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"]
    if args.all:
        inner.append("--all")
    if args.project:
        inner += ["--filter", f"label=com.docker.compose.project={args.project}"]

    cmd = ["ssh"]
    if args.ssh_opts:
        cmd += shlex.split(args.ssh_opts)
    cmd += [args.ssh] + inner

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        print(json.dumps({"ok": False, "stderr": proc.stderr.decode("utf-8", "replace")}))
        return proc.returncode

    containers = []
    for line in proc.stdout.decode("utf-8", "replace").splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        containers.append({"name": parts[0], "image": parts[1], "status": parts[2]})
    print(json.dumps({"ok": True, "containers": containers}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: smoke test sem SSH (sintaxe + `--dry-run` + `--help`)**

Run: `python3 .agents/skills/deskcomm-instalar/scripts/remote.py --dry-run --ssh root@exemplo --script-file NUL 2>&1 || python3 .agents/skills/deskcomm-instalar/scripts/remote.py --help`
Expected: ajuda ou linha de comando impressa, nenhum traceback. Depois:
Run: `python3 -m py_compile .agents/skills/deskcomm-instalar/scripts/remote.py .agents/skills/deskcomm-instalar/scripts/docker-status.py && echo COMPILE-OK`
Expected: `COMPILE-OK`.

- [ ] **Step 5: gate das skills**

Run: `npx vitest run tests/unit/skills-embutidas.test.ts`
Expected: PASS (as citações `scripts/remote.py` agora existem; `scripts/coolify.py` ainda falta e o teste deve acusar só ele).

- [ ] **Step 6: Commit**

```bash
git add .agents/skills/deskcomm-instalar/scripts/remote.py .agents/skills/deskcomm-instalar/scripts/docker-status.py
git commit -m "feat(instalar): helpers remotos do caminho coolify"
```

---

### Task 3: `scripts/coolify.py` (subset Deskcomm)

**Files:**
- Create: `.agents/skills/deskcomm-instalar/scripts/coolify.py`

**Interfaces:**
- Consumes: `remote.py` (conceito: nada de segredo no argv além do header transitório em memória), token em arquivo `0600`.
- Produces: subcomandos `enable-api`, `token --out`, `api-get --path`, `api-post --path [--json-file]`, `create-service --name --compose-file [--fqdn]`, `set-fqdn --app-id --fqdn`, `heal-localhost`, `wait-admin [--attempts]`.

- [ ] **Step 1: RED, confirmar a acusação restante**

Run: `npx vitest run tests/unit/skills-embutidas.test.ts`
Expected: FAIL citando só `scripts/coolify.py`. Qualquer outro arquivo na lista indica citação com typo: corrija a citação, não o teste.

- [ ] **Step 2: criar `scripts/coolify.py` com este conteúdo**

```python
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


def ssh_run(ssh: str, remote: list[str], ssh_opts: str = "") -> subprocess.CompletedProcess:
    import shlex
    cmd = ["ssh"]
    if ssh_opts:
        cmd += shlex.split(ssh_opts)
    return subprocess.run(cmd + [ssh] + remote, capture_output=True)


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
    p = ssh_run(args.ssh, ["bash", "-s"], args.ssh_opts)
    sys.stderr.write("token deve ser gerado dentro do container coolify; saída abaixo (só metadados)\n")
    sys.stdout.write(p.stdout.decode("utf-8", "replace"))
    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode("utf-8", "replace"))
        return p.returncode
    _ = helper
    sys.stderr.write("grave o token id|segredo em " + args.out + " com modo 0600\n")
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
    p = ssh_run(args.ssh, ["bash", "-s"], args.ssh_opts)
    out = p.stdout.decode("utf-8", "replace")
    sys.stdout.write(out if out else "")
    if p.returncode != 0:
        sys.stderr.write(p.stderr.decode("utf-8", "replace"))
        return p.returncode
    if '"reachable":true' not in out:
        with open("/tmp/heal-localhost.sh", "w", encoding="utf-8", newline="\n") as f:
            f.write(script)
        sys.stderr.write("rode scripts/remote.py --script-file com o conteúdo impresso em dry-run local e re-tente\n")
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
```

Risco honesto: o shape exato de `POST /api/v1/services` varia por versão do Coolify. Mitigação embutida: UUIDs e FQDN resolvidos em runtime (sem chumbo), falha alta com a resposta do servidor impressa (sem silêncio) e fallback documentado no `coolify-agente.md` (criar o service pela UI com o mesmo template). Se o primeiro teste contra o Coolify real acusar campo ausente, ajuste só o `payload` de `cmd_create_service` nesta task, sem tocar o resto.

- [ ] **Step 3: compilar e listar subcomandos**

Run: `python3 -m py_compile .agents/skills/deskcomm-instalar/scripts/coolify.py && python3 .agents/skills/deskcomm-instalar/scripts/coolify.py --help`
Expected: lista com `enable-api`, `token`, `api-get`, `api-post`, `create-service`, `set-fqdn`, `heal-localhost`, `wait-admin`, sem traceback.

- [ ] **Step 4: gate das skills**

Run: `npx vitest run tests/unit/skills-embutidas.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/deskcomm-instalar/scripts/coolify.py
git commit -m "feat(instalar): operacoes da api do coolify"
```

---

### Task 4: `templates/docker-compose.coolify.yml`

**Files:**
- Create: `.agents/skills/deskcomm-instalar/templates/docker-compose.coolify.yml`

**Interfaces:**
- Consumes: `docker-compose.prod.yml` (serviços, healthchecks, comentários de memória), `coolify.py create-service --compose-file`.
- Produces: compose do service referenciado pelo passo 3 de `coolify-agente.md`.

Regra de derivação (sem copiar às cegas): parta do `prod` e aplique exatamente estas transformações, por âncora de conteúdo:
1. Remova o bloco inteiro do serviço `caddy:` (do cabeçalho `  caddy:` até antes de `volumes:`) e os volumes `caddy-data` e `caddy-config`.
2. Remova qualquer chave `ports:` fora do serviço `wacalls` (o template não publica TCP; o bloco UDP de `wacalls` fica, com o profile `voz`).
3. Não adicione `command:`, `network_mode:` nem labels `traefik.*` em nenhum serviço.
4. No topo, cabeçalho de 6 linhas: origem (`derivado de docker-compose.prod.yml`), o que foi removido e por quê (Caddy compete com o Traefik do Coolify nas portas 80/443), FQDN configurado no painel e volumes que precisam persistir (`waha-data`, `waha-media`).

- [ ] **Step 1: gerar o template aplicando as 4 transformações e conferir o diff**

Run: `npx vitest run tests/unit/portas-do-compose.test.ts`
Expected: PASS (o gate cobre só `prod` + `traefik`; o template novo não entra no escopo dele, mas rode para provar que nada no `prod` foi tocado).

- [ ] **Step 2: validar YAML e as invariantes do template**

Run: `node -e "const fs=require('fs');const t=fs.readFileSync('.agents/skills/deskcomm-instalar/templates/docker-compose.coolify.yml','utf8');const fails=[];if(/^\s{2}caddy:\s*$/m.test(t))fails.push('caddy presente');if(/^\s{4}ports:/m.test(t.split(/^ {2}wacalls:/m)[0]||t))fails.push('ports fora de wacalls');if(/traefik\.enable/.test(t))fails.push('label traefik');if(/network_mode:\s*host/.test(t))fails.push('host mode');if(/^\s{4}command:/m.test(t))fails.push('command override');if(!/waha-data/.test(t))fails.push('sem waha-data');if(fails.length){console.error(fails.join(', '));process.exit(1)}console.log('TEMPLATE-OK')"`
Expected: `TEMPLATE-OK`.

- [ ] **Step 3: Commit**

```bash
git add .agents/skills/deskcomm-instalar/templates/docker-compose.coolify.yml
git commit -m "feat(instalar): template compose do service coolify"
```

---

### Task 5: Toques no `cliente-novo`, fragmento de release e sincronização

**Files:**
- Modify: `.agents/skills/deskcomm-cliente-novo/SKILL.md` (3 inserções)
- Create: `.changes/coolify-opencode.md`
- Sync: `.claude/skills/` (via `pnpm skills:sync`)

**Interfaces:**
- Consumes: Passo 0, Passo 4 e `nunca fazer` atuais do `cliente-novo` (ler o arquivo na hora e ancorar no texto lido).
- Produces: skill coerente com instalação Coolify; fragmento válido em `release:conferir`.

- [ ] **Step 1: as 3 inserções (ancore no texto lido, não decore)**

1. Após a frase `Sem instalação: guia deskcomm-instalar`, acrescentar: `Instalação via Coolify entrega o mesmo contrato (app em https://<DOMAIN> com TLS, sessão do WhatsApp em volume persistente); logs e envs ficam no painel do service, e update é redeploy no painel.`
2. No checklist do Passo 4, acrescentar: `sessão WAHA sobrevive a redeploy (volume waha-data existe no service); update documentado (painel redeploy ou fluxo padrão).`
3. Em `nunca fazer`, acrescentar: `Não subir nem alterar a stack por docker compose up manual no SSH quando o service é gerido pelo Coolify (sai da gestão e a UI mostra Exited).`

- [ ] **Step 2: criar `.changes/coolify-opencode.md` com este conteúdo**

```markdown
---
impacto: capacidade_nova
secao: adicionado
titulo: Instalação pelo Coolify operada pelo agente
---
Quem instala com o painel Coolify agora tem um caminho conduzido pelo agente: a skill de instalação detecta o cenário Coolify e segue referências e scripts próprios, sem trocar o caminho padrão com Caddy. Crédito: @JotaSXBR.
```

- [ ] **Step 3: sincronizar o espelho e rodar todos os gates**

```bash
pnpm skills:sync
npx vitest run tests/unit/skills-embutidas.test.ts tests/unit/documentacao-aponta-para-o-que-existe.test.ts
pnpm release:conferir
```

Expected: exit 0 nos três. Se `skills-embutidas` acusar divergência, o sync não cobriu os arquivos novos: confira se fonte e espelho foram adicionados ao git.

- [ ] **Step 4: pré-voo e suíte cheia**

```bash
bash .agents/skills/deskcomm-contribuir/scripts/pre-voo.sh
rm -f tsconfig*.tsbuildinfo; pnpm typecheck; echo exit=$?
pnpm lint; echo exit=$?
pnpm test:unit > /tmp/vt.log 2>&1; echo exit=$?; grep -aE "Test Files|Tests " /tmp/vt.log | tail -2
pnpm test:shell; echo exit=$?
```

Expected: pré-voo sem segredo, marca ou migration sem tripla; typecheck, lint, unit e shell com `exit=0`. Não corte a saída: o rodapé do unit e os arquivos vermelhos (se houver) decidem.

- [ ] **Step 5: apontar o remote ao fork e publicar a branch**

```bash
git remote set-url origin https://github.com/JotaSXBR/DeskcommCRM
git remote -v
git add -A
git commit -m "docs(cliente-novo): contrato da instalacao coolify" --allow-empty
git push -u origin feat/coolify-opencode
```

Expected: `origin` mostra só o fork (fetch e push); nenhum remote aponta a `melgarafael/DeskcommCRM`; push completa sem `push --force`. O commit `--allow-empty` só existe se o Step 3 não deixou nada pendente; se houver resto, ele entra neste commit em vez do vazio.

---

## Self-Review

**Spec coverage:** Seção 1 coberta nas Tasks 1 a 4 (roteamento, agente, gotchas, 3 scripts, template). Seção 2 coberta na Task 5 (3 inserções literais). Seção 3 coberta na Task 5 (remotes só fork, hooks via pré-voo, gates listados, fragmento `.changes`, sem envio ao upstream em nenhum step).

**Placeholder scan:** nenhum `TBD`, `TODO`, `similar`, `apropriado` ou step sem comando e saída esperada. O único ponto de incerteza real (shape do `POST /api/v1/services` por versão do Coolify) está declarado na Task 3 com mitigação embutida (falha alta + fallback pela UI), não escondido.

**Type consistency:** nomes de comandos e flags são idênticos entre `coolify-agente.md` (Task 1), gotchas (Task 1) e implementações (Tasks 2 e 3): `remote.py --ssh/--script-file/--in-container/--exec/--capture/--dry-run`, `docker-status.py --ssh/--ssh-opts/--project/--all`, `coolify.py enable-api|token --out|api-get --path|api-post --path --json-file|create-service --name --compose-file --fqdn|set-fqdn --app-id --fqdn|heal-localhost|wait-admin --attempts`. O template referenciado é sempre `templates/docker-compose.coolify.yml`.
