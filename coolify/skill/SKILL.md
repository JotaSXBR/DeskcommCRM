# deskcomm-coolify-onboarding

Conduz a instalação do DeskcommCRM (fork, sem PR) numa VPS que já tem Coolify,
do zero ao login + WhatsApp conectado. Executada do repo clonado localmente
(WSL/Linux). Sem marketplace: `git clone <fork> && cd coolify`.

## Contrato de entrada (pergunte uma coisa por vez, nunca re-pergunte o decidido)

`VPS_IP`, `COOLIFY_FQDN` completo (ex.: `panel.coolify.com.br`),
`APP_FQDN` completo, `SUPABASE_ACCESS_TOKEN` ou as 4 cópias manuais.
Chave de IA é opcional.

## Ordem (abra a reference da etapa antes de executar)

1. `docker-status.py --ssh root@IP` — inventário brownfield, reusar Coolify saudável
2. `coolify.py heal-localhost --ssh root@IP` — `reachable:true` antes de tudo
3. `wait-admin` — se já há admin, pula sozinho; senão o usuário cria no browser
4. `enable-api` + `token --out coolify.token --base-url https://<COOLIFY_FQDN>` (reusa se válido)
5. `instance-domain` — confere o FQDN do painel, nunca sobrescreve sem OK
6. `create-project` + `ensure-service` (descoberta por nome; cria só o ausente)
7. `env-sync --file base.env --app-fqdn <APP_FQDN>`
8. `set-fqdn` + `restart` (com OK explícito em produção) + `poll-tls`
9. Dono no browser do app → onboarding → QR do WhatsApp → `healthcheck.sh`

Update depois da instalação é redeploy com tags oficiais: subir `UPSTREAM_REF` no template + `sync-compose` + `env-sync` + `restart`.

Narre serviço a serviço. Prévia antes de gravar. Dono cria contas no browser.
