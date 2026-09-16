# DeskcommCRM no Coolify (overlay do fork, sem PR)

Instalação automática na sua VPS com Coolify via SSH root + API do Coolify.
Clonado local e executado daqui. Sem marketplace, sem build na VPS, sem tocar no produto.

## Contrato de entrada (etapa 1, tudo completo)

- `VPS_IP` — IP da VPS (SSH root com chave)
- `COOLIFY_FQDN` — endereço completo do painel, ex.: `panel.coolify.com.br` (se já existe e saudável, só reaproveita)
- `APP_FQDN` — endereço completo do app, ex.: `crm.empresa.com.br`
- `SUPABASE_ACCESS_TOKEN` (`sbp_...`) — cria o projeto sozinho e configura Site URL; sem ele, as 4 cópias manuais + `marca-emails.sh` depois
- Chave de IA opcional (cadastra depois em IA › Credenciais)

## Instalação (primeira vez)

1. `scripts/docker-status.py` — inventário brownfield read-only, nunca destrói
2. `scripts/coolify.py heal-localhost` — normaliza `authorized_keys`, confirma container→host
3. `wait-admin` — se já há admin, pula sozinho; senão, único manual no browser do painel
4. `enable-api` + `token --out coolify.token --base-url https://<COOLIFY_FQDN>` via SSH (reusa o token se válido; semeia o team antes de gerar; arquivo `0600` transitório, nunca no log)
5. `instance-domain` — lê e mostra o FQDN do painel; se ausente, setar ANTES dos serviços + `docker restart coolify` (com OK explícito; no seu caso já existe, só confere)
6. `create-project` — reusa `DeskcommCRM` se existir; `ensure-service --project-uuid <uuid> --compose-file deskcomm.coolify.yml` — reusa `deskcommcrm` se existir (descoberta por nome, funciona em máquina nova sem estado)
7. `env-sync --file base.env --app-fqdn <APP_FQDN>` — PATCH por chave (cria a ausente), deriva `DOMAIN`, `WAHA_WEBHOOK_BASE_URL`, `NEXT_PUBLIC_APP_URL` e `NEXT_PUBLIC_ADMIN_URL` (ambas `https://<APP_FQDN>`)
8. `set-fqdn --app-id <id> --fqdn <APP_FQDN>` + `restart` via API (com OK explícito em produção) + `poll-tls https://<APP_FQDN>` até 200 com cert válido
9. Dono no browser → onboarding → WhatsApp QR (app do celular em Aparelhos conectados) → `healthcheck.sh`

## Atualização (update = redeploy com tags oficiais)

As imagens vêm do repositório oficial (`ghcr.io/melgarafael/...`), nunca do fork. Atualizar é subir os números de `UPSTREAM_REF` no `deskcomm.coolify.yml` e rodar: `sync-compose --service-uuid <uuid> --compose-file deskcomm.coolify.yml` + `env-sync` + `restart` (com OK explícito). Sem build, sem clone do produto. Se o `sync-compose` responder 404/405 nessa versão do Coolify, o fallback é colar o template em Configuration › Edit Compose File › Save › Deploy.

## Regras

- `UPSTREAM_REF=1.28.0` numerada, nunca `latest`/`main`. Update = trocar a ref e regenerar.
- Imagens publicadas, `pull_policy: always` (digest imutável usa `missing`). Nenhum `build:`-only.
- Sem `ports: 80/443`. Só `app` na rede do proxy (`${TRAEFIK_NETWORK:-coolify}`, projeto independente); `waha/redis/srh` só na `internal`. Sem serviço `caddy`.
- Segredo nunca em repo/log/commit. Token Sanctum `<id>|<token>` só em arquivo `0600` e header HTTP.
- Payload remoto sempre em arquivo via `remote.py --script-file`, nunca inline.
