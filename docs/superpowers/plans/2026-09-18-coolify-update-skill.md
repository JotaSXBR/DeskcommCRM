# Update pela skill Coolify, sem cron Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar à skill `deskcomm-instalar-coolify` uma etapa "Update" acionada pelo operador, com comandos testáveis e sem cron.

**Architecture:** `coolify.py` ganha funções puras (validação, troca de tags, comparação, merge de env) cobertas por `unittest` stdlib mais dois subcomandos (`version-status`, `update`); `backup.py` ganha disparo remoto pontual; a skill documenta a condução. Nenhum toque no produto.

**Tech Stack:** Python 3 stdlib only (`argparse`, `json`, `re`, `unittest`, `urllib.request`), Coolify API `/api/v1` via SSH + token, `git show` para comparar `baseline.sql` entre tags.

**Spec:** `coolify/UPDATE-SKILL-DESIGN.md` — o plano argumenta a partir dela; executores leem os dois.

## Global Constraints

- Só `coolify/` + espelhos da skill (`.agents/skills/deskcomm-instalar-coolify/SKILL.md`, `.claude/skills/deskcomm-instalar-coolify/SKILL.md`, byte-idênticos) + este plano. Nenhum arquivo do produto.
- Nunca commitar sem pedido explícito do operador (regra global do repo; os passos abaixo terminam em verificação, não em commit).
- Segredo nunca em output, log, arquivo do repo ou transcript. Token só em arquivo `0600` e header HTTP.
- Payload remoto sempre via arquivo (`remote.py`), nunca inline. Compose raw sempre base64. `sync-compose` é PATCH (PUT dá 405 na 4.3.19).
- `--ref` sempre numerada (`X.Y.Z`); `latest`/`main`/`stable` recusadas.
- WAHA, `srh`, `redis`, rede do proxy, FQDN: intocados. Deploy sempre pela API; nunca `docker compose up` manual.
- Sem cron, sem restauração automática. Falha após alteração no banco = parar + diagnóstico + aguardar autorização.
- Comandos abaixo usam `py -3` (Windows); no WSL o equivalente é `python3`.

---

## File Structure

- `coolify/scripts/coolify.py` (modify): funções puras `validar_ref`, `extrair_tags_imagens`, `trocar_tags_deskcomm`, `comparar_versoes`, `mesclar_env_update`, `baseline_mudou`, `novo_registro_operacao`, `marcar_etapa` + subcomandos `version-status` e `update` (+ `--dry-run`, `--resume --op <arquivo>`).
- `coolify/scripts/backup.py` (modify): subcomando `backup-agora --ssh root@IP --file base.env [--waha-volume <vol>]` (disparo remoto pontual + validação do artefato).
- `coolify/tests/test_update.py` (create): suíte `unittest` stdlib das funções puras; roda com `py -3 -m unittest discover -s coolify/tests -v`, sem rede e sem SSH.
- `coolify/skill/SKILL.md` + espelho `.claude/` (modify, byte-idênticos): etapa "Update".
- `coolify/README.md`, `coolify/HISTORICO.md` (modify): documentar `version-status`/`update`/`backup-agora`.
- `coolify/deskcomm.coolify.yml` (modify apenas quando o operador aplicar um update real, nunca neste plano).

---

### Task 1: Funções puras do update + suíte unittest

**Files:**
- Modify: `coolify/scripts/coolify.py` (acrescentar após `find_by_name`, antes de `cmd_token`)
- Create: `coolify/tests/test_update.py`
- Test: `py -3 -m unittest discover -s coolify/tests -v`

**Interfaces:**
- Consumes: nada novo (só stdlib: `re`, `json`, `os`, `time`).
- Produces: `validar_ref(ref: str) -> str`, `extrair_tags_imagens(compose: str) -> dict`, `trocar_tags_deskcomm(compose: str, ref: str) -> str`, `comparar_versoes(instalada: str, alvo: str) -> str`, `mesclar_env_update(painel: dict, arquivo: dict) -> dict`, `baseline_mudou(sql_novo: bytes, sql_atual: bytes | None) -> bool`, `novo_registro_operacao(ref: str, dir_saida: str) -> dict`, `marcar_etapa(op: dict, etapa: str, ok: bool, detalhe: str = "") -> dict`.

- [ ] **Step 1: Write the failing test**

```python
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

import coolify


class TestValidarRef(unittest.TestCase):
    def test_aceita_numerada(self):
        self.assertEqual(coolify.validar_ref("1.29.0"), "1.29.0")

    def test_recusa_moveis(self):
        for ref in ("latest", "main", "stable", "v1.29.0", "", "1.29"):
            with self.subTest(ref=ref):
                with self.assertRaises(ValueError):
                    coolify.validar_ref(ref)


class TestTagsCompose(unittest.TestCase):
    COMPOSE = (
        '    image: ghcr.io/melgarafael/deskcommcrm:1.28.0\n'
        '    image: ghcr.io/melgarafael/deskcomm-worker:1.28.0\n'
        '    image: ghcr.io/melgarafael/deskcomm-scheduler:1.28.0\n'
        '    image: devlikeapro/waha:latest-2026.7.2\n'
        '    image: hiett/serverless-redis-http@sha256:5b0b\n'
        '    image: redis:7-alpine\n'
    )

    def test_extrair_tags(self):
        tags = coolify.extrair_tags_imagens(self.COMPOSE)
        self.assertEqual(tags, {
            "deskcommcrm": "1.28.0",
            "deskcomm-worker": "1.28.0",
            "deskcomm-scheduler": "1.28.0",
        })

    def test_trocar_so_deskcomm(self):
        novo = coolify.trocar_tags_deskcomm(self.COMPOSE, "1.29.0")
        self.assertIn("ghcr.io/melgarafael/deskcommcrm:1.29.0", novo)
        self.assertIn("ghcr.io/melgarafael/deskcomm-worker:1.29.0", novo)
        self.assertIn("ghcr.io/melgarafael/deskcomm-scheduler:1.29.0", novo)
        self.assertIn("devlikeapro/waha:latest-2026.7.2", novo)
        self.assertIn("serverless-redis-http@sha256:5b0b", novo)
        self.assertIn("redis:7-alpine", novo)
        self.assertNotIn("1.28.0", novo.replace("latest-2026.7.2", ""))


class TestCompararVersoes(unittest.TestCase):
    def test_nada_a_fazer(self):
        self.assertEqual(coolify.comparar_versoes("1.28.0", "1.28.0"), "nada_a_fazer")

    def test_update(self):
        self.assertEqual(coolify.comparar_versoes("1.28.0", "1.29.0"), "update")

    def test_alvo_anterior_recusa(self):
        with self.assertRaises(ValueError):
            coolify.comparar_versoes("1.29.0", "1.28.0")


class TestMesclarEnv(unittest.TestCase):
    def test_painel_prevalece_em_preservadas(self):
        painel = {"SRH_TOKEN": "do-painel", "RESEND_API_KEY": "re_painel", "DOMAIN": "velho"}
        arquivo = {"SRH_TOKEN": "", "DOMAIN": "crm.novo.com.br"}
        out = coolify.mesclar_env_update(painel, arquivo)
        self.assertEqual(out["SRH_TOKEN"], "do-painel")
        self.assertEqual(out["RESEND_API_KEY"], "re_painel")
        self.assertEqual(out["DOMAIN"], "crm.novo.com.br")

    def test_nao_inventa_segredo(self):
        out = coolify.mesclar_env_update({}, {"DOMAIN": "x"})
        self.assertNotIn("SRH_TOKEN", out)
        self.assertNotIn("IMPERSONATE_COOKIE_SECRET", out)


class TestBaselineMudou(unittest.TestCase):
    def test_mudou(self):
        self.assertTrue(coolify.baseline_mudou(b"a", b"b"))

    def test_igual(self):
        self.assertFalse(coolify.baseline_mudou(b"a", b"a"))

    def test_sem_referencia_aplica(self):
        self.assertTrue(coolify.baseline_mudou(b"a", None))


class TestRegistroOperacao(unittest.TestCase):
    def test_marcar_etapa(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            op = coolify.novo_registro_operacao("1.29.0", d)
            self.assertEqual(op["etapas"], [])
            op2 = coolify.marcar_etapa(op, "snapshot", True, "compose-123.b64")
            self.assertEqual(op2["etapas"], [{"etapa": "snapshot", "ok": True, "detalhe": "compose-123.b64"}])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `py -3 -m unittest discover -s coolify/tests -v`
Expected: FAIL — `AttributeError` em `validar_ref` (função ainda não existe). Se o diretório `coolify/tests` não existir, criá-lo primeiro (verificação de pai antes de criar arquivo, conforme regra de shell).

- [ ] **Step 3: Write minimal implementation**

Acrescentar a `coolify/scripts/coolify.py`, após `find_by_name` (linha ~166):

```python
IMAGENS_DESKCOMM = ("deskcommcrm", "deskcomm-worker", "deskcomm-scheduler")
ENV_PRESERVADAS_PAINEL = ("SRH_TOKEN", "UPSTASH_REDIS_REST_TOKEN",
                          "RESEND_API_KEY", "RESEND_FROM_EMAIL")


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

    return re.sub(r"(ghcr\.io/melgarafael/(?:deskcommcrm|deskcomm-worker|deskcomm-scheduler):)[^\s'\"]+",
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


def novo_registro_operacao(ref, dir_saida):
    return {"ref": validar_ref(ref), "dir_saida": dir_saida, "etapas": []}


def marcar_etapa(op, etapa, ok, detalhe=""):
    op["etapas"].append({"etapa": etapa, "ok": bool(ok), "detalhe": detalhe})
    return op
```

Nota de comportamento travada pela spec: `mesclar_env_update` nunca gera segredo; a geração atual de `cmd_env_sync` (`coolify.py:314-321`) só roda no fluxo de install, nunca no update sem a guarda do painel.

- [ ] **Step 4: Run test to verify it passes**

Run: `py -3 -m unittest discover -s coolify/tests -v`
Expected: PASS em todos ( Ran 13 tests, OK ). Em seguida `py -3 -m py_compile coolify/scripts/coolify.py coolify/tests/test_update.py` sem saída (exit 0).

- [ ] **Step 5: Verificação sem commit**

Run: `git status --short`
Expected: apenas `?? coolify/tests/` e `M coolify/scripts/coolify.py`. Nada é commitado (regra global).

---

### Task 2: Subcomando `version-status`

**Files:**
- Modify: `coolify/scripts/coolify.py` (`cmd_version_status` + parser + dispatch)
- Test: `py -3 coolify/scripts/coolify.py version-status --help` (exit 0) + suíte da Task 1 verde

**Interfaces:**
- Consumes: `api_req`, `extrair_tags_imagens`, `comparar_versoes` (Task 1).
- Produces: `cmd_version_status(a)`; saída JSON `{"instalada": ..., "disponiveis": [...], "acao": "nada_a_fazer"|"escolha_do_operador"}`.

- [ ] **Step 1: Write the failing check**

Run: `py -3 coolify/scripts/coolify.py version-status --help`
Expected: FAIL com `invalid choice` (subcomando ainda não existe, exit 2).

- [ ] **Step 2: Implementar `cmd_version_status`**

```python
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
        bruto = json.loads(b).get("docker_compose_raw", "")
    except Exception:
        bruto = ""
    try:
        compose = base64.b64decode(bruto).decode("utf-8", "replace")
    except Exception:
        compose = ""
    tags = extrair_tags_imagens(compose)
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
```

Parser (junto aos demais em `main()`):

```python
vs = sub.add_parser("version-status"); vs.add_argument("--base-url", required=True)
vs.add_argument("--token-file", required=True); vs.add_argument("--service-uuid", required=True)
```

Dispatch:

```python
elif a.cmd == "version-status":
    cmd_version_status(a)
```

Decisão de formato travada: `instalada` é a maior tag numérica entre as 3 imagens; divergência entre elas aborta (`tags_divergentes`) em vez de adivinhar.

- [ ] **Step 3: Run checks**

Run: `py -3 coolify/scripts/coolify.py version-status --help`
Expected: exit 0 com uso impresso.
Run: `py -3 -m unittest discover -s coolify/tests -v`
Expected: PASS (Task 1 intacta).
Run: `py -3 -m py_compile coolify/scripts/coolify.py`
Expected: exit 0.

- [ ] **Step 4: Verificação sem commit**

Run: `git status --short`
Expected: sem arquivos novos além dos já previstos; nada commitado.

---

### Task 3: Subcomando `update` com `--dry-run` e registro de operação

**Files:**
- Modify: `coolify/scripts/coolify.py` (`cmd_update` + parser + dispatch + extração de `aplicar_schema` desde `cmd_db_apply`)
- Test: `--help` exit 0; `--dry-run` recusa `--ref` móvel sem rede; suíte verde

**Interfaces:**
- Consumes: `validar_ref`, `trocar_tags_deskcomm`, `comparar_versoes`, `mesclar_env_update`, `baseline_mudou`, `novo_registro_operacao`, `marcar_etapa` (Task 1), `api_req`, `cmd_db_apply`-equivalente interno, `parse_env_file`.
- Produces: `cmd_update(a)`; registro JSON protegido em diretório temporário do SO (`tempfile`), nunca no repo.

- [ ] **Step 1: Write the failing check**

Run: `py -3 coolify/scripts/coolify.py update --help`
Expected: FAIL com `invalid choice` (exit 2).

- [ ] **Step 2: Implementar `cmd_update` (orquestração, aborta na primeira falha)**

Parser:

```python
up = sub.add_parser("update"); up.add_argument("--base-url", required=True)
up.add_argument("--token-file", required=True); up.add_argument("--service-uuid", required=True)
up.add_argument("--ref", required=True); up.add_argument("--compose-file", required=True)
up.add_argument("--file", required=True); up.add_argument("--sql", required=True)
up.add_argument("--app-fqdn", default=""); up.add_argument("--dry-run", action="store_true")
up.add_argument("--skip-sql", action="store_true")
up.add_argument("--op", default="")
```

Comportamento (ordem da spec, seção 5):

```python
def cmd_update(a):
    ref = validar_ref(a.ref)  # recusa latest/main/stable aqui, antes de qualquer rede
    with open(a.compose_file, "r", encoding="utf-8") as f:
        template = f.read()
    if a.dry_run:
        print(json.dumps({"dry_run": True, "ref": ref,
                          "etapas": ["pre-voo", "snapshot", "sync-compose",
                                     "db-apply" if not a.skip_sql else "db-apply(pulado)",
                                     "env-sync(preview)", "restart", "poll-tls"],
                          "skip_sql": bool(a.skip_sql)}))
        return
    # --resume: implementado na Task 4; aqui só o caminho direto.
    ...
```

Caminho direto (sem `--op`), com refatoração prévia obrigatória: extrair de `cmd_db_apply` (`coolify.py:437-485`) a função `aplicar_schema(db_url: str, sql_path: str, ssh: str) -> dict` (retorna `{"ok", "fresh", "tables", "harness_missing", "unexpected_errors"}`), mantendo o comportamento fresh/update e a regex `benign` (`coolify.py:464-465`); `cmd_db_apply` passa a chamar `aplicar_schema` e imprimir. Depois: pré-voo lê o compose do painel via `api_req GET /services/<uuid>`, salva snapshot `compose-<ts>.b64` no diretório temporário e compara tags (`comparar_versoes`; igual → `{"ok": True, "acao": "nada_a_fazer"}` e encerra). Depois: `trocar_tags_deskcomm` + PATCH (mesmo corpo de `cmd_sync_compose`); `aplicar_schema` com o SQL da Task 5; `env-sync` sempre precedido de `--preview` lógico interno com a guarda `mesclar_env_update` (valores do painel lidos via `api-get` do endpoint de envs a confirmar na 4.3.19 — se o endpoint não existir, aborta com `env_painel_nao_lido` em vez de gravar); `restart` + `poll-tls` (reuso direto). Cada etapa: `marcar_etapa` no registro; falha → imprime `{"ok": False, "etapa": ..., "alterado_ate_aqui": [...], "pendente": [...], "atendimento_pausado": True}` e `sys.exit(1)`, sem tentar recuperar nada sozinho.

Critério `db-apply` pula ou aplica: a skill roda `git fetch --tags` e compara bytes do `--sql` (da release, obtido na Task 5) com `git show v<instalada>:supabase/baseline.sql`; `--skip-sql` exige motivo impresso no resumo; tag ausente ou comparação impossível → aplica por segurança com motivo `comparacao_indisponivel`.

- [ ] **Step 3: Run checks**

Run: `py -3 coolify/scripts/coolify.py update --help`
Expected: exit 0.
Run: `py -3 coolify/scripts/coolify.py update --ref stable --compose-file coolify/deskcomm.coolify.yml --file x --sql y --base-url https://x --token-file x --service-uuid u --dry-run`
Expected: exit 1 com `ref_invalida`, sem tocar em rede (validação antes de tudo).
Run: `py -3 coolify/scripts/coolify.py update --ref 1.29.0 --compose-file coolify/deskcomm.coolify.yml --file x --sql y --base-url https://x --token-file x --service-uuid u --dry-run`
Expected: exit 0 com `{"dry_run": true, ...}`.
(`--service-uuid` é obrigatório no argparse; sem ele o erro é exit 2 do argparse, não do comando.)
Run: `py -3 -m unittest discover -s coolify/tests -v` → PASS; `py_compile` → exit 0.

- [ ] **Step 4: Verificação sem commit**

`git status --short` — nada commitado.

---

### Task 4: Retomada sem repetir SQL (`--resume --op <arquivo>`)

**Files:**
- Modify: `coolify/scripts/coolify.py` (ramo `--resume` em `cmd_update`)
- Test: teste puro de retomada em `coolify/tests/test_update.py` (novo caso)

**Interfaces:**
- Consumes: registro JSON de `novo_registro_operacao`/`marcar_etapa` (Task 1) + estado real (tag no painel, harness via `to_regclass` como em `cmd_db_apply`).
- Produces: continuação a partir da primeira etapa incompleta; etapa `db-apply` concluída nunca é reaplicada — é revalidada (contagem + harness); etapa `sync-compose` concluída é reconferida pela tag no painel.

- [ ] **Step 1: Write the failing test**

```python
def test_resume_pula_db_apply_concluido(self):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        op = coolify.novo_registro_operacao("1.29.0", d)
        op = coolify.marcar_etapa(op, "snapshot", True, "compose-1.b64")
        op = coolify.marcar_etapa(op, "sync-compose", True, "200")
        op = coolify.marcar_etapa(op, "db-apply", True, "tables=109")
        self.assertEqual(coolify.proxima_etapa(op), "env-sync")
```

(Acrescentar ao `TestRegistroOperacao` da Task 1.)

Run: `py -3 -m unittest discover -s coolify/tests -v`
Expected: FAIL — `proxima_etapa` não existe.

- [ ] **Step 2: Implementar**

```python
ORDEM_ETAPAS_UPDATE = ("snapshot", "sync-compose", "db-apply",
                       "env-sync", "restart", "poll-tls")


def proxima_etapa(op):
    feitas = {e["etapa"] for e in op.get("etapas", []) if e.get("ok")}
    for etapa in ORDEM_ETAPAS_UPDATE:
        if etapa not in feitas:
            return etapa
    return "concluido"
```

No ramo `--resume`: carrega o JSON de `--op`, chama `proxima_etapa`, revalida o que está marcado como feito contra o estado real (tag no painel para `sync-compose`; harness para `db-apply`) e continua da primeira pendente. Divergência entre registro e real → aborta com `estado_divergente` e pede decisão do operador.

- [ ] **Step 3: Run**

`py -3 -m unittest discover -s coolify/tests -v` → PASS. `py_compile` → exit 0.

---

### Task 5: Arquivos da release isolados + `backup-agora` remoto

**Files:**
- Modify: `coolify/scripts/coolify.py` (obtenção do `baseline.sql` da tag para temp dir) e `coolify/scripts/backup.py` (subcomando `backup-agora`)
- Test: `py_compile` + `--help` dos dois; prova real só na VPS de teste

**Interfaces:**
- Consumes: `remote.put_file`, `remote.run_script_file` (padrão de `cmd_install_cron`, `backup.py:111-146`).
- Produces: `backup-agora --ssh root@IP --file base.env [--waha-volume <vol>]` → `{"ok": True, "db": "db-<ts>.sql.gz", "dir": "/data/coolify/backups-deskcomm/"}` após validar existência e tamanho > 0 no host.

- [ ] **Step 1: Failing checks**

Run: `py -3 coolify/scripts/backup.py backup-agora --help`
Expected: FAIL `invalid choice` (exit 2).

- [ ] **Step 2: Implementar `backup-agora`**

Segue o molde de `cmd_install_cron` (`backup.py:111-146`), mas one-shot: despacha `backup.py run` no host via SSH com env mínimo (`SUPABASE_DB_URL` lida de `--file`, nunca impressa), aguarda, lê o JSON de saída e valida o artefato (`test -s <dir>/<db>`). Sem artefato válido → `{"ok": False, "reason": "backup_nao_validado"}` e exit 1. O `update` exige esse OK antes de qualquer escrita (janela de manutenção da spec, seção 3 item 2).

Obtenção do SQL da release (em `coolify.py`): baixa `supabase/baseline.sql` da tag `v<ref>` do `melgarafael/DeskcommCRM` para `tempfile.mkdtemp(prefix="deskcomm-update-")` via `urllib` (raw.githubusercontent), recusa arquivo vazio e registra o caminho na operação. Nunca troca a branch do checkout do overlay.

- [ ] **Step 3: Run**

`py -3 coolify/scripts/backup.py backup-agora --help` → exit 0. `py_compile` nos dois scripts → exit 0. Suíte `unittest` → PASS.

---

### Task 6: Skill + docs + espelhos byte-idênticos

**Files:**
- Modify: `coolify/skill/SKILL.md`, `.agents/skills/deskcomm-instalar-coolify/SKILL.md`, `.claude/skills/deskcomm-instalar-coolify/SKILL.md` (etapa "Update" idêntica nos três), `coolify/README.md`, `coolify/HISTORICO.md`
- Test: comparação de hash dos espelhos + `git status`

- [ ] **Step 1: Escrever a etapa "Update" no `coolify/skill/SKILL.md`**

Texto condutor (4 passos): 1) `version-status` → lista → operador escolhe; 2) declara janela + `backup-agora` + OK explícito; 3) `update --ref <escolhida>` (ou `--dry-run` antes, opcional); 4) `poll-tls` + healthcheck + registro no `HISTORICO.md`. Incluir a tabela de sintomas do update: `tags_divergentes` → inspecionar compose no painel; `env_painel_nao_lido` → abortar, nunca gravar; falha pós-banco → diagnóstico + autorização, sem restore automático.

- [ ] **Step 2: Espelhar byte-idêntico e conferir**

Copiar o bloco para os dois espelhos e rodar a conferência de hash (PowerShell):

```powershell
Get-FileHash .agents/skills/deskcomm-instalar-coolify/SKILL.md, .claude/skills/deskcomm-instalar-coolify/SKILL.md, coolify/skill/SKILL.md
```

Expected: os dois espelhos com hash igual entre si (o `coolify/skill/SKILL.md` é a fonte; os espelhos seguem o padrão do `HISTORICO.md:60,182` — conferir por hash manual). Se `node_modules` existir, rodar também o gate `tests/unit/skills-embutidas.test.ts`; sem ele, registrar como pendente para a máquina com deps (precedente `HISTORICO.md:118-119`).

- [ ] **Step 3: README + HISTORICO**

`README.md`: trocar a seção "Atualização" (linhas 33-35) pelo fluxo `version-status` → escolha → `backup-agora` → `update --ref` → `restart`/`poll-tls`, mantendo as regras (`UPSTREAM_REF` numerada, PATCH, fallback de colar no painel). `HISTORICO.md`: nova entrada datada com decisões e o que foi validado sem SSH.

---

### Task 7: Gate de validação local (sem SSH, sem VPS)

**Files:** nenhum (só execução). **Test:** todos os comandos abaixo com saída esperada.

- [ ] **Step 1: Compilação e ajuda**

```powershell
py -3 -m py_compile coolify/scripts/coolify.py coolify/scripts/backup.py coolify/tests/test_update.py
py -3 coolify/scripts/coolify.py version-status --help
py -3 coolify/scripts/coolify.py update --help
py -3 coolify/scripts/backup.py backup-agora --help
```

Expected: exit 0 em todos, sem saída do `py_compile`.

- [ ] **Step 2: Suíte unitária**

Run: `py -3 -m unittest discover -s coolify/tests -v`
Expected: todos PASS, zero rede, zero SSH.

- [ ] **Step 3: Sanidade do template**

Se `docker` disponível: `docker compose -f coolify/deskcomm.coolify.yml config` (warnings de env vazia são esperados — vêm do Coolify). Sem docker: registrar `compose_config_pulado_sem_docker`, sem falhar o gate.

- [ ] **Step 4: Prova integrada (VPS de teste, fora deste plano)**

Registrar como pendente explícita: update real + falha simulada numa instalação de teste com dados, antes de qualquer uso em produção (spec seção 7). Este plano não executa nada na VPS.

---

## Self-Review

**1. Spec coverage:** §1 objetivo → Tasks 2–6. §3.1 escolha do operador → Task 2. §3.2 janela+backup+OK → Tasks 5–6. §3.3 falha sem auto-restore → Tasks 3–4. §3.4 skill+comandos → Tasks 1–6. §5 fluxo (7 passos) → Tasks 2–5. §6 recuperação/retomada → Task 4. §7 testes → Tasks 1 e 7 (+ prova integrada pendente). §8 pontos abertos → fechados aqui: releases via GitHub API (Task 2), envs do painel com aborto se endpoint ausente (Task 3), critério de schema via `git show` entre tags (Task 3), registro em temp dir fora do repo (Tasks 3–4), espelhos por hash (Task 6).

**2. Placeholder scan:** sem TBD/TODO/"similar to"; cada passo traz código ou comando exato; o único comportamento condicional explícito (endpoint de envs do painel, prova integrada) tem fallback/registro definido, não promessa vaga.

**3. Type consistency:** assinaturas definidas na Task 1 (`validar_ref`, `trocar_tags_deskcomm`, `comparar_versoes`, `mesclar_env_update`, `baseline_mudou`, `novo_registro_operacao`, `marcar_etapa`, `proxima_etapa`) são as mesmas usadas nas Tasks 2–4; `ORDEM_ETAPAS_UPDATE` espelha a ordem da spec §5.
