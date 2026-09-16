# Histórico da branch `coolify/overlay` (controle de revisão)

Branch publicada em `JotaSXBR/DeskcommCRM` (`coolify/overlay`), sem PR ao oficial.
Tudo aqui é adição em `coolify/` + skill nova; nenhum arquivo do produto foi editado.

## Decisões (na ordem, todas aprovadas antes de implementar)

1. Lugar do instalador: repo novo separado → **mudou para branch `coolify/overlay` no fork**, sem PR.
2. Alvo: VPS que **já tem Coolify**; banco segue no **Supabase Cloud externo**.
3. Deploy: **compose com imagens oficiais numeradas** (`ghcr.io/melgarafael/...:1.28.0`, WAHA pinado, srh por digest), sem build na VPS.
4. Skills: **só onboarding Coolify**; sem marketplace — repo clonado local, execução dali (WSL/Linux).
5. Domínios: **2 FQDNs completos** pedidos na etapa 1 — `COOLIFY_FQDN` (ex.: `panel.coolify.com.br`, só confere se já existe) + `APP_FQDN`.
6. Token da API Coolify: **criação via SSH automática** (com seed de team); reusa `coolify.token` se válido.
7. Envs: **via API** (`PATCH .../envs`, fallback POST); `env-sync --app-fqdn` deriva `DOMAIN`, webhook, `NEXT_PUBLIC_APP_URL`/`ADMIN_URL` (ambas `https://<APP_FQDN>`).
8. Rede do proxy: default **`coolify` sobrescrevível** (`${TRAEFIK_NETWORK:-coolify}`); só o `app` encosta nela, resto isolado; projeto independente.
9. Update: **redeploy com tags oficiais** — subir `UPSTREAM_REF` + `sync-compose` + `env-sync` + `restart`.
10. Descoberta **por nome** (`DeskcommCRM`/`deskcommcrm`), sem arquivo de estado — funciona em máquina nova.
11. Skill `deskcomm-instalar-coolify` em `.agents/skills/` + espelho `.claude/skills/` (frontmatter com roteamento e cerca de escopo); scripts seguem em `coolify/`.

## Validado localmente

- `py_compile` OK nos 3 scripts; `docker compose config` OK (warnings de env vazia esperados — vêm do Coolify).
- Espelhos da skill byte-idênticos; nenhum segredo real no diff; diff só com adições.

## Pendente de prova na VPS (primeira run observa)

- Seed de team no `token` (varia por versão do Coolify).
- `GET /services` de listagem e `PUT /services/{uuid}` do `sync-compose` (fallback documentado: Edit Compose File na UI).
- Repetição de env existente e tabela `users` do `wait-admin`.
- `set-fqdn` (`service_applications.fqdn`) e `POST .../restart` na versão instalada.
