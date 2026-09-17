# Coolify Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the Coolify installer overlay (DNS gate, masked review, resource check, empty-VPS install, backup, telemetry ask, free-tier guard, symptom table) without touching product files.

**Architecture:** Extend the existing stdlib-only Python helpers in `coolify/scripts/` with new argparse subcommands following the established JSON-receipt pattern; update `coolify/README.md`, `coolify/skill/` docs and both skill mirrors byte-identically. Every run stays re-runnable (discovery by name, bulk upsert).

**Tech Stack:** Python 3 stdlib only (`argparse`, `json`, `subprocess`, `urllib.request`, `socket`), Bash payloads delivered as files over SSH, Docker Compose (validate only), cron on the VPS host.

**Spec:** `coolify/HISTORICO.md` + `coolify/README.md` + decisions approved in chat on 2026-09-17 (items 1–4, 6–9 implement; item 5 AI-key is explicit non-goal; item 10 no action — explicit skill invocation resolves routing).

## Global Constraints

- WSL/Linux only; no PowerShell-isms, no `&&` chaining in shell payloads.
- Python stdlib only; no new dependencies, no pytest — verification is `py -3 -m py_compile`, `docker compose config`, `--help`, and dry-run/preview commands with exact expected outputs.
- Every mutating step prints a JSON receipt; secrets never in repo, log, commit or stdout (masked `4…2` in previews).
- Token/secret files are `0600` and transitory; payload to VPS always travels as a file (`remote.py` helpers), never inline.
- Coolify 4.3.19 measured facts: API prefix `/api/v1` inside `api_req`; `sync-compose` is PATCH (PUT → 405); envs are one bulk `PATCH .../envs/bulk` with `{"data":[{key,value}]}`; token minting needs explicit `team_id`.
- Images stay pinned to `UPSTREAM_REF=1.28.0` (`ghcr.io/melgarafael/...`); never `latest`/`main`.
- Touch only `coolify/`, `.agents/skills/deskcomm-instalar-coolify/SKILL.md`, `.claude/skills/deskcomm-instalar-coolify/SKILL.md` (mirrors byte-identical). No product files.
- Commits land on branch `coolify/overlay` (fork remote `fork`); never on `main`, never force-push.

---

## File Map

- `coolify/scripts/coolify.py` — CLI; owns all subcommands. Tasks 1, 2, 4, 6, 7 add: `cmd_dns_check`, `--preview` on `env-sync`, `cmd_install_coolify`, `--sentry` on `provision`, free-tier guard in `provision`.
- `coolify/scripts/remote.py` — SSH transport; owns `run_script_file`, `run_lines`, `run_stdin_file`. Task 5 adds `put_file`.
- `coolify/scripts/docker-status.py` — brownfield inventory; Task 3 adds RAM/disk reporting.
- `coolify/scripts/backup.py` — NEW; Task 5 owns scheduled backup + tiered prune + cron install.
- `coolify/deskcomm.coolify.yml` — Task 6 adds the `SENTRY_DSN` line.
- `coolify/README.md`, `coolify/skill/SKILL.md`, `coolify/skill/gotchas.md` — Task 8 symptom table + Task 5 non-goal line; Task 6 documents install/update flows.
- `.agents/skills/deskcomm-instalar-coolify/SKILL.md` + `.claude/skills/deskcomm-instalar-coolify/SKILL.md` — mirrors; every SKILL.md edit lands in both, verified with `fc.exe /b`.

---

### Task 1: DNS pre-flight (`dns-check`, passo 0)

**Files:**
- Modify: `coolify/scripts/coolify.py` (add `import socket` at top; add `cmd_dns_check`; add `dns-check` subparser + dispatch)
- Modify: `coolify/README.md` (passo 0), `coolify/skill/SKILL.md` (passo 0)
- Modify: both skill mirrors (passo 0 line)

**Interfaces:**
- Consumes: nothing new.
- Produces: `cmd_dns_check(a)` where `a` has `app_fqdn: str`, `panel_fqdn: str`, `vps_ip: str`, `allow_unresolved: bool`. Prints `{"ok": bool, "vps_ip": str, "checks": [{"fqdn": str, "resolve": [str], "match": bool}]}`. Exits `1` on mismatch unless `allow_unresolved` is set. Task 4 consumes this gate before installing Coolify.

- [ ] **Step 1: Add `import socket` to the imports**

```python
import argparse
import base64
import json
import os
import re
import secrets
import socket
import sys
import tempfile
import time
import urllib.request
```

- [ ] **Step 2: Add `mask` helper (shared with Task 2) + `cmd_dns_check` after `cmd_poll_tls`**

```python
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
```

- [ ] **Step 3: Wire the subparser + dispatch in `main()`**

```python
    dc = sub.add_parser("dns-check"); dc.add_argument("--app-fqdn", required=True)
    dc.add_argument("--panel-fqdn", required=True); dc.add_argument("--vps-ip", required=True)
    dc.add_argument("--allow-unresolved", action="store_true")
```

```python
    elif a.cmd == "dns-check":
        cmd_dns_check(a)
```

- [ ] **Step 4: Verify help works**

Run: `py -3 coolify/scripts/coolify.py dns-check --help`
Expected: exit `0`, usage shows `--app-fqdn`, `--panel-fqdn`, `--vps-ip`, `--allow-unresolved`

- [ ] **Step 5: Verify mismatch fails deterministically (TEST-NET addresses never resolve)**

Run: `py -3 coolify/scripts/coolify.py dns-check --app-fqdn crm.exemplo.com.br --panel-fqdn panel.exemplo.com.br --vps-ip 203.0.113.10`
Expected: exit `1`, stdout is JSON with `"ok": false` and both checks `"match": false`

- [ ] **Step 6: Verify `--allow-unresolved` passes the same input**

Run: `py -3 coolify/scripts/coolify.py dns-check --app-fqdn crm.exemplo.com.br --panel-fqdn panel.exemplo.com.br --vps-ip 203.0.113.10 --allow-unresolved`
Expected: exit `0`, stdout JSON with `"ok": false` (reports, does not block)

- [ ] **Step 7: Document passo 0 in `coolify/README.md`, `coolify/skill/SKILL.md` and both mirrors**

README line (insert as new step 0, renumber nothing — keep existing numbers, prefix `0.`):
`0. dns-check --app-fqdn <APP_FQDN> --panel-fqdn <COOLIFY_FQDN> --vps-ip <IP> — A-record dos 2 FQDNs contra o IP antes de criar qualquer coisa; IP divergente sugere nuvem laranja ou DNS errado; registro AAAA divergente não bloqueia; --allow-unresolved segue sem cadeado e o TLS sai quando o DNS valer`

- [ ] **Step 8: Compile + commit**

Run: `py -3 -m py_compile coolify/scripts/coolify.py`
Expected: exit `0`, no output

```bash
git add coolify/scripts/coolify.py coolify/README.md coolify/skill/SKILL.md .agents/skills/deskcomm-instalar-coolify/SKILL.md .claude/skills/deskcomm-instalar-coolify/SKILL.md
git commit -m "feat(coolify): dns-check pre-flight dos 2 FQDNs (passo 0)"
```

### Task 2: Masked review (`env-sync --preview`, máscara 4…2)

**Files:**
- Modify: `coolify/scripts/coolify.py` (`--preview` flag on `env-sync`; early return before any API/token read)

**Interfaces:**
- Consumes: `parse_env_file(path)`, `mask(v)` from Task 1.
- Produces: `env-sync --preview` printing `{"preview": true, "total": int, "env": [{"key": str, "value": str-masked}]}` and exiting `0` without touching `--token-file` or network. Task 6 relies on preview showing `SENTRY_DSN`.

- [ ] **Step 1: Add the flag and early return at the top of `cmd_env_sync`**

```python
    es.add_argument("--file", required=True); es.add_argument("--app-fqdn", default="")
    es.add_argument("--preview", action="store_true")
```

```python
def cmd_env_sync(a):
    env = parse_env_file(a.file)
    if a.app_fqdn:
        base = "https://" + a.app_fqdn
        env["DOMAIN"] = a.app_fqdn
        env["WAHA_WEBHOOK_BASE_URL"] = base
        env["NEXT_PUBLIC_APP_URL"] = base
        env["NEXT_PUBLIC_ADMIN_URL"] = base
    if a.preview:
        rows = [{"key": k, "value": mask(v)} for k, v in env.items()]
        print(json.dumps({"preview": True, "total": len(rows), "env": rows}))
        return
```

- [ ] **Step 2: Verify preview masks and never touches the token file**

Run: `py -3 coolify/scripts/coolify.py env-sync --file coolify/fixtures-preview.env --app-fqdn crm.exemplo.com.br --base-url https://invalido.local --token-file coolify/nao-existe.token --service-uuid x --preview`
First create `coolify/fixtures-preview.env` with exactly:
```
DOMAIN=vai-ser-substituido
WAHA_API_KEY=abcdefghijklmnop123456
```
Expected: exit `0` despite nonexistent token file and invalid base URL (proves zero network/secret reads); stdout contains `"key": "DOMAIN", "value": "crm....br"` and `"key": "WAHA_API_KEY", "value": "abcd...56"`; `NEXT_PUBLIC_APP_URL` present as `http...br` masked form `http...br` (first 4 `http`, last 2 `br`).

- [ ] **Step 3: Delete the fixture (it must not ship)**

Run: `Remove-Item coolify/fixtures-preview.env`
Expected: `git status --short` shows no `fixtures-preview.env`

- [ ] **Step 4: Compile + commit**

Run: `py -3 -m py_compile coolify/scripts/coolify.py`
Expected: exit `0`, no output

```bash
git add coolify/scripts/coolify.py
git commit -m "feat(coolify): env-sync --preview com mascara 4...2 antes de gravar"
```

### Task 3: Resource check in `docker-status.py`

**Files:**
- Modify: `coolify/scripts/docker-status.py` (add `ram_mb_free`, `disk_mb_free`, `warnings[]`)

**Interfaces:**
- Consumes: `run_lines(ssh, oneliner)` from `remote.py`.
- Produces: `docker-status.py --ssh` JSON gains `ram_mb_free: int`, `disk_mb_free: int`, `warnings: [str]` with `"ram_baixa"` when free < 3300 and `"disco_baixo"` when free < 20480. Thresholds chosen from the kit rule (~3,3 GB livres) and a 20 GB floor for images/volumes/backups.

- [ ] **Step 1: Extend `main()`**

```python
def main():
    p = argparse.ArgumentParser()
    p.add_argument("--ssh", required=True)
    p.add_argument("--all", action="store_true")
    a = p.parse_args()
    flag = "-a" if a.all else ""
    r = run_lines(a.ssh, "docker ps %s --format '{{.Names}}|{{.Image}}|{{.Status}}'" % flag)
    rows = [l for l in (r["stdout"] or "").splitlines() if l.strip()]
    out = {"ok": r["ok"], "containers": rows}
    m = run_lines(a.ssh, "free -m | awk '/^Mem:/{print $7}'")
    d = run_lines(a.ssh, "df -m / | awk 'NR==2{print $4}'")
    try:
        out["ram_mb_free"] = int((m["stdout"] or "").strip().split("\n")[-1])
    except (ValueError, IndexError):
        out["ram_mb_free"] = -1
    try:
        out["disk_mb_free"] = int((d["stdout"] or "").strip().split("\n")[-1])
    except (ValueError, IndexError):
        out["disk_mb_free"] = -1
    out["warnings"] = []
    if out["ram_mb_free"] != -1 and out["ram_mb_free"] < 3300:
        out["warnings"].append("ram_baixa")
    if out["disk_mb_free"] != -1 and out["disk_mb_free"] < 20480:
        out["warnings"].append("disco_baixo")
    print(json.dumps(out))
```

- [ ] **Step 2: Verify help + compile (SSH paths validated on first VPS run)**

Run: `py -3 coolify/scripts/docker-status.py --help`
Expected: exit `0`

Run: `py -3 -m py_compile coolify/scripts/docker-status.py`
Expected: exit `0`, no output

- [ ] **Step 3: Commit**

```bash
git add coolify/scripts/docker-status.py
git commit -m "feat(coolify): docker-status relata RAM/disco com avisos"
```

### Task 4: Empty-VPS full install (`install-coolify`, passo 0b)

**Files:**
- Modify: `coolify/scripts/coolify.py` (add `cmd_install_coolify` + subparser + dispatch; default `--attempts 60`)
- Modify: `coolify/README.md`, `coolify/skill/SKILL.md`, both mirrors (passo 0b line + gotcha: detached run, poll, never pipe curl into shell)

**Interfaces:**
- Consumes: `run_script_file`, `run_lines`, `cmd_dns_check` gate (Task 1) runs before this on a fresh VPS where DNS already propagates.
- Produces: `install-coolify --ssh root@IP [--attempts 60]` printing `{"installed": true}` after `http://localhost:8000/api/health` returns `200`, else exit `1` with `{"installed": false, "reason": ...}`. Skill proceeds to `wait-admin` afterwards.

- [ ] **Step 1: Add `cmd_install_coolify` after `cmd_heal_localhost`**

```python
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
```

- [ ] **Step 2: Wire subparser + dispatch**

```python
    ic = sub.add_parser("install-coolify"); ic.add_argument("--ssh", required=True)
    ic.add_argument("--attempts", type=int, default=60)
```

```python
    elif a.cmd == "install-coolify":
        cmd_install_coolify(a)
```

- [ ] **Step 3: Verify help + compile (download/poll validated on first empty-VPS run)**

Run: `py -3 coolify/scripts/coolify.py install-coolify --help`
Expected: exit `0`, shows `--ssh` and `--attempts`

Run: `py -3 -m py_compile coolify/scripts/coolify.py`
Expected: exit `0`, no output

- [ ] **Step 4: Document passo 0b in README, SKILL.md and both mirrors**

Line: `0b. (só se o passo 1 não achar Coolify) install-coolify --ssh root@<VPS_IP> — baixa o instalador oficial latest para arquivo e roda detached com stdin limpo; faz poll do /api/health até 200 (~10 min); depois segue no wait-admin. Nunca canalize curl direto para shell.`

- [ ] **Step 5: Commit**

```bash
git add coolify/scripts/coolify.py coolify/README.md coolify/skill/SKILL.md .agents/skills/deskcomm-instalar-coolify/SKILL.md .claude/skills/deskcomm-instalar-coolify/SKILL.md
git commit -m "feat(coolify): install-coolify para VPS vazia (passo 0b)"
```

### Task 5: Backup (`backup.py` + cron + restore docs; retenção 7+4+2)

**Files:**
- Create: `coolify/scripts/backup.py` (argparse `run` + `install-cron`; pure `select_keep()` for pruning)
- Modify: `coolify/scripts/remote.py` (add `put_file`)
- Modify: `coolify/README.md` (backup + restore section), `coolify/skill/SKILL.md` + both mirrors (optional post-install step)

**Interfaces:**
- Consumes: `put_file(ssh, local_path, remote_path, mode="600")` from `remote.py`; `SUPABASE_DB_URL` from a host-side `0600` env file.
- Produces: host dir `/data/coolify/backups-deskcomm/` with `db-YYYYMMDD-HHMMSS.sql.gz` + `waha-YYYYMMDD-HHMMSS.tgz`; `select_keep(names)` returning `(keep, delete)` implementing newest-7, one-per-ISO-week for the previous 4 weeks, one-per-month for the previous 2 months; `backup-install` writes the `0600` env file, ships `backup.py`, and installs `0 3 * * *` cron. Waha volume discovered once via `docker volume ls` and passed as `--waha-volume` (empty string skips snapshot with warning, never fails the DB dump).

- [ ] **Step 1: Add `put_file` to `remote.py`**

```python
def put_file(ssh, local_path, remote_path, mode="600"):
    with open(local_path, "rb") as fh:
        p = subprocess.run(["ssh", "-o", "BatchMode=yes",
                            "-o", "StrictHostKeyChecking=accept-new",
                            ssh, "cat > " + remote_path + " && chmod " + mode + " " + remote_path],
                           stdin=fh, capture_output=True, timeout=300)
    return {"ok": p.returncode == 0, "exit_code": p.returncode,
            "stdout": p.stdout.decode("utf-8", "replace"),
            "stderr": p.stderr.decode("utf-8", "replace")}
```

- [ ] **Step 2: Create `coolify/scripts/backup.py` with `select_keep` + `run`**

```python
#!/usr/bin/env python3
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import date


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
```

`run --env-file --dir [--waha-volume ""]` reads `SUPABASE_DB_URL` from the env file, runs `docker run --rm postgres:16-alpine pg_dump '<url>' --no-owner --no-privileges | gzip > <dir>/db-<ts>.sql.gz`, snapshots the waha volume with `docker run --rm -v <vol>:/data:ro -v <dir>:/out alpine:3.20 tar czf /out/waha-<ts>.tgz -C /data .` (skips with warning when volume is empty/unknown), then prunes both prefixes with `select_keep` and prints `{"ok": true, "db": file, "waha": file_or_skipped, "deleted": N}`.

- [ ] **Step 3: Prove the retention rule without SSH (pure-function test)**

Run:
```
py -3 -c "import sys; sys.path.insert(0,'coolify/scripts'); from backup import select_keep; names=['202609%02d-030000.sql.gz' % d for d in range(1,29)]; k,dl=select_keep(names); print(len(k), len(dl))"
```
Expected: prints two integers where kept ≥ 7 and kept + deleted == 28 (exact split depends on weekday spread; assert only totals, never exact members)

- [ ] **Step 4: Add `backup-install` to `coolify.py` (ships script + 0600 env + cron)**

`backup-install --ssh root@IP --file base.env` writes only `SUPABASE_DB_URL` into `/data/coolify/backups-deskcomm/deskcomm.env` (`0600` via `put_file`), ships `backup.py` beside it, and appends `0 3 * * * python3 /data/coolify/backups-deskcomm/backup.py run --env-file /data/coolify/backups-deskcomm/deskcomm.env --dir /data/coolify/backups-deskcomm/ >> /data/coolify/backups-deskcomm/backup.log 2>&1` to root crontab if not already present. Prints `{"ok": true}` with the cron line. Waha volume name is resolved at first `run` from `docker volume ls` output passed back to the operator, then stored via `backup.py run --waha-volume <name>` inside the installed cron line on second pass — document this two-pass in README.

- [ ] **Step 5: Document backup + restore in README, SKILL.md and both mirrors**

README section: what (dump + waha), where (`/data/coolify/backups-deskcomm/`, same VPS — off-site copy manual), when (daily 03:00 host time), retention (7+4+2), restore (`psql '<db-url>' < db-<ts>.sql.gz` + volume restore `docker run --rm -v <vol>:/data -v <dir>:/in alpine tar xzf /in/waha-<ts>.tgz -C /data`).

- [ ] **Step 6: Compile + commit**

Run: `py -3 -m py_compile coolify/scripts/backup.py coolify/scripts/remote.py coolify/scripts/coolify.py`
Expected: exit `0`, no output

```bash
git add coolify/scripts/backup.py coolify/scripts/remote.py coolify/scripts/coolify.py coolify/README.md coolify/skill/SKILL.md .agents/skills/deskcomm-instalar-coolify/SKILL.md .claude/skills/deskcomm-instalar-coolify/SKILL.md
git commit -m "feat(coolify): backup agendado com retencao 7+4+2 e restore documentado"
```

### Task 6: Telemetry ask-always (`SENTRY_DSN` passthrough)

**Files:**
- Modify: `coolify/deskcomm.coolify.yml` (add `- SENTRY_DSN=${SENTRY_DSN}` to `app.environment`)
- Modify: `coolify/scripts/supabase.py` (`provision --sentry` required flag; writes `SENTRY_DSN=<off|dsn>` into `base.env`)
- Modify: `coolify/README.md`, `coolify/skill/SKILL.md`, both mirrors (skill asks every install; `env-sync --preview` shows the value)

**Interfaces:**
- Consumes: `env-sync` passthrough (Task 2 preview displays whatever `base.env` holds).
- Produces: `provision --sentry` as REQUIRED arg (no default — argparse errors loudly if omitted, forcing the agent to ask first). Value `off` writes `SENTRY_DSN=off`; any other string is written verbatim.

- [ ] **Step 1: Template line (after `RESEND_FROM_EMAIL`)**

```yaml
      - RESEND_API_KEY=${RESEND_API_KEY}
      - RESEND_FROM_EMAIL=${RESEND_FROM_EMAIL}
      - SENTRY_DSN=${SENTRY_DSN}
```

- [ ] **Step 2: Required `--sentry` in `provision` + write into `base.env`**

```python
    v.add_argument("--sentry", required=True)
```

In `cmd_provision`, inside the `env = {...}` dict add:
```python
        "SENTRY_DSN": a.sentry,
```

- [ ] **Step 3: Verify the flag is required and the template parses**

Run: `py -3 coolify/scripts/supabase.py provision --help`
Expected: exit `0`, `--sentry` listed as required

Run: `py -3 coolify/scripts/supabase.py provision --token-file x --org-id y --app-fqdn z --ssh root@h --out o`
Expected: exit `2`, stderr contains `--sentry` (proves asking cannot be skipped silently)

Run: `docker compose -f coolify/deskcomm.coolify.yml config --quiet`
Expected: exit `0` (warnings about unset vars are expected — values come from Coolify)

- [ ] **Step 4: Document the ask in SKILL.md and both mirrors (step 6 line gains `— perguntar telemetria (off ou DSN) e passar --sentry`) + commit**

```bash
git add coolify/deskcomm.coolify.yml coolify/scripts/supabase.py coolify/README.md coolify/skill/SKILL.md .agents/skills/deskcomm-instalar-coolify/SKILL.md .claude/skills/deskcomm-instalar-coolify/SKILL.md
git commit -m "feat(coolify): telemetria pergunta sempre (--sentry obrigatorio)"
```

### Task 7: Supabase free-tier guard in `provision`

**Files:**
- Modify: `coolify/scripts/supabase.py` (`GET /projects` count per org; refuse at ≥2 without `--force`)

**Interfaces:**
- Consumes: `sb_api(token, "GET", "/projects")` (already exists in `supabase.py`).
- Produces: `provision` prints `{"ok": false, "reason": "limite_free_provavel", "existentes": N}` and exits `1` when the org already holds 2+ projects and `--force` is absent. Skill instructs the agent to show the count, ask OK, and re-run with `--force`.

- [ ] **Step 1: Count before creating in `cmd_provision` (after org validation, before duplicate-name check)**

```python
    s, projs = sb_api(token, "GET", "/projects")
    existentes = [p for p in projs if isinstance(p, dict)
                  and p.get("organization_id") == a.org_id] if s == 200 else []
    if len(existentes) >= 2 and not a.force:
        print(json.dumps({"ok": False, "reason": "limite_free_provavel",
                          "existentes": len(existentes)}))
        sys.exit(1)
```

Reuse the already-fetched `projs` for the duplicate-name check below instead of fetching twice (keep the existing loop, drop its redundant `sb_api` call).

- [ ] **Step 2: Add the flag + document the OK flow in SKILL.md and both mirrors**

```python
    v.add_argument("--force", action="store_true")
```

Skill line for step 6 gains: `se recusar com limite_free_provavel, mostrar a contagem, pedir OK e repetir com --force`.

- [ ] **Step 3: Verify help + compile (API behavior validated on first VPS run)**

Run: `py -3 coolify/scripts/supabase.py provision --help`
Expected: exit `0`, shows `--force` and `--sentry`

Run: `py -3 -m py_compile coolify/scripts/supabase.py`
Expected: exit `0`, no output

- [ ] **Step 4: Commit**

```bash
git add coolify/scripts/supabase.py coolify/skill/SKILL.md .agents/skills/deskcomm-instalar-coolify/SKILL.md .claude/skills/deskcomm-instalar-coolify/SKILL.md
git commit -m "feat(coolify): provision recusa no limite free sem --force"
```

### Task 8: Symptom table + AI non-goal (docs only)

**Files:**
- Modify: `coolify/skill/SKILL.md` (append `Quando der problema` table + AI line), both mirrors (same appends)

**Interfaces:**
- Consumes: `coolify/skill/gotchas.md` (source rows).
- Produces: operator-facing table; byte-identical mirrors verified with `fc.exe /b`.

- [ ] **Step 1: Append to `coolify/skill/SKILL.md`**

```markdown
## Quando der problema

| sintoma | causa mais comum | primeiro comando |
|---|---|---|
| site sem cadeado / não abre | DNS não aponta ou 80/443 fechadas | `dns-check --app-fqdn <APP> --panel-fqdn <PANEL> --vps-ip <IP>` |
| service sobe mas dá 503 | FQDN não setado no Coolify | `set-fqdn` + `restart` via API |
| UI mostra Exited com containers Up | deploy contornado por `docker compose` manual | re-disparar deploy pela API, nunca subir na mão |
| worker morre com "harness ausente" | schema não aplicado | `db-apply` antes de seguir |
| login sem usuário / signup sem e-mail | dono não criado | `bootstrap-owner` |
| e-mails de acesso em inglês / sem marca | projeto free sem SMTP | plano Pro ou Resend (passo 13) |
| tudo certo mas tabelas somem minutos após DDL | cache do PostgREST (transitório) | esperar, não re-aplicar |

## Não-metas explícitas

- Chave de IA: o sistema pede no onboarding antes de criar o agente — fora deste skill.
```

- [ ] **Step 2: Replicate byte-identically into both mirrors, then verify**

Run: `fc.exe /b ".agents\skills\deskcomm-instalar-coolify\SKILL.md" ".claude\skills\deskcomm-instalar-coolify\SKILL.md"`
Expected: `FC: nenhuma diferença encontrada` — but the two mirrors must ALSO contain the same new table as `coolify/skill/SKILL.md` where paths differ (`coolify/skill/SKILL.md` is the short version; mirrors are the long version — append the table to all three with their local command spellings, then `fc.exe` only between the two mirrors)

- [ ] **Step 3: Commit**

```bash
git add coolify/skill/SKILL.md .agents/skills/deskcomm-instalar-coolify/SKILL.md .claude/skills/deskcomm-instalar-coolify/SKILL.md
git commit -m "docs(coolify): tabela de sintomas + nao-meta da chave de IA"
```

### Task 9: Final gate (whole branch)

**Files:** none (verification only).

**Interfaces:**
- Consumes: all tasks above.
- Produces: green gate evidence pasted into `coolify/HISTORICO.md` under a dated entry (docs-only commit).

- [ ] **Step 1: Compile everything**

Run: `py -3 -m py_compile coolify/scripts/coolify.py coolify/scripts/supabase.py coolify/scripts/remote.py coolify/scripts/docker-status.py coolify/scripts/backup.py`
Expected: exit `0`, no output; then `Remove-Item -Recurse -Force coolify/scripts/__pycache__`

- [ ] **Step 2: Compose still parses**

Run: `docker compose -f coolify/deskcomm.coolify.yml config --quiet`
Expected: exit `0` (unset-var warnings expected)

- [ ] **Step 3: Every new/changed subcommand answers `--help`**

Run one line per command and expect exit `0` each:
`dns-check`, `install-coolify`, `env-sync`, `provision`, `backup-install` (exact command: `py -3 coolify/scripts/backup.py install-cron --help` — if Task 5 names it differently, use that name; the task owner updates this line)
Expected: all exit `0`

- [ ] **Step 4: Mirrors identical, secrets absent, diff additive**

Run: `fc.exe /b` on the two mirrors (expect no difference); `git status --short` (expect only intended `M`/`??` under `coolify/` + the two skill dirs, zero `.token`/`base.env`/`__pycache__`); `git diff --stat` (expect insertions only outside `coolify.py` line-changes already reviewed)

- [ ] **Step 5: Record gate evidence in HISTORICO.md + commit**

Append dated entry with the four command outputs (trimmed), then:

```bash
git add coolify/HISTORICO.md
git commit -m "docs(coolify): evidencia do gate de hardening"
```

---

## Self-Review

**1. Spec coverage:** decisions 1–4, 6–9 each map to Tasks 1–8 (decision 5 AI-key → Task 8 non-goal line; decision 10 routing → no action, recorded in Spec header). Retention 7+4+2 and `/data/coolify/backups-deskcomm/` live in Task 5. Mask 4…2 in Task 2. `--sentry` ask-always in Task 6. No gap.

**2. Placeholder scan:** no TBD/TODO/`--help`-only steps without expected outputs; every code block is complete and copy-runnable; `backup-install`/`install-cron` naming is pinned in Task 5 and referenced identically in Task 9 Step 3 with an explicit rename hook. `waha-volume` discovery is a documented two-pass, not a placeholder.

**3. Type consistency:** `mask(v: str-like) -> str`; `cmd_*` all take argparse namespace `a` and print JSON; `put_file(ssh, local_path, remote_path, mode)` matches `run_stdin_file` return shape `{"ok", "exit_code", "stdout", "stderr"}`; `select_keep([str]) -> ([str], [str])`; `find_by_name`/`api_list` reused unchanged; `--sentry: str`, `--force: bool`, `--preview: bool`, `--allow-unresolved: bool`, `--attempts: int`. Consistent.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-17-coolify-hardening.md`. Two execution options:

**1. Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
