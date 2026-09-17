# deskcomm-coolify-onboarding

Conduz a instalação do DeskcommCRM (fork, sem PR) numa VPS que já tem Coolify,
do zero ao login + WhatsApp conectado. Executada do repo clonado localmente
(WSL/Linux). Sem marketplace: `git clone <fork> && cd coolify`.

## Contrato de entrada (pergunte uma coisa por vez, nunca re-pergunte o decidido)

`VPS_IP`, `COOLIFY_FQDN` completo (ex.: `panel.coolify.com.br`),
`APP_FQDN` completo, `SUPABASE_ACCESS_TOKEN` ou as 4 cópias manuais.
Chave de IA é opcional.

## Ordem (abra a reference da etapa antes de executar)

0. `dns-check --app-fqdn <APP_FQDN> --panel-fqdn <COOLIFY_FQDN> --vps-ip <IP>` — DNS dos 2 FQDNs antes de tudo (`--allow-unresolved` segue sem cadeado)
1. `docker-status.py --ssh root@IP` — inventário brownfield, reusar Coolify saudável
0b. (só sem Coolify) `install-coolify --ssh root@IP` — oficial latest detached + poll health, depois wait-admin
2. `coolify.py heal-localhost --ssh root@IP` — `reachable:true` antes de tudo
3. `wait-admin` — se já há admin, pula sozinho; senão o usuário cria no browser
4. `enable-api` + `token --out coolify.token --base-url https://<COOLIFY_FQDN>` (reusa se válido)
5. `instance-domain` — confere o FQDN do painel, nunca sobrescreve sem OK
6. `supabase.py provision` (cria o projeto, aguarda ACTIVE, grava `base.env`)
7. `db-apply --file base.env --sql supabase/baseline.sql` (schema no banco, ANTES de seguir; sem ele o worker morre com "harness ausente")
8. `create-project` + `ensure-service` (descoberta por nome; cria só o ausente, projeto com descrição)
9. `env-sync --file base.env --app-fqdn <APP_FQDN>`
10. `set-fqdn` + `restart` (com OK explícito em produção) + `poll-tls`
11. `supabase.py marca-emails` (URLs dos e-mails de acesso; marca bloqueada em free sem SMTP)
12. `bootstrap-owner --file base.env --email <dono> --password <senha>` (dono confirmado + org + admin, sem e-mail)
13. (opcional) `env-set RESEND_API_KEY=<chave> RESEND_FROM_EMAIL=<remetente>` + `restart` + `poll-tls` (convites/LGPD; a chave destrava a marca do passo 11)
14. Dono no browser do app → login → onboarding → QR do WhatsApp → `healthcheck.sh`

Update depois da instalação é redeploy com tags oficiais: subir `UPSTREAM_REF` no template + `sync-compose` + `env-sync` + `restart`.

Narre serviço a serviço. Prévia antes de gravar. Dono cria contas no browser.
