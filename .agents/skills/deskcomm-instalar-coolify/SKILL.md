---
name: deskcomm-instalar-coolify
description: Instala o DeskcommCRM numa VPS que JÁ TEM Coolify (painel com domínio próprio, ex.: panel.coolify.com.br), via SSH root + API do Coolify, criando o projeto DeskcommCRM sem processo manual. Use ESTA skill — e não a deskcomm-instalar — sempre que a VPS de destino já roda Coolify, ou quando pedirem instalação via Coolify, redeploy ou update das imagens oficiais. Ela ignora as demais skills e a doutrina de contribuição do repo.
metadata:
  publico: operador da própria VPS com Coolify
  fonte-de-verdade: coolify/README.md
---

# Instalar via Coolify (escopo fechado)

Siga SOMENTE este guia. Não aplique outras skills nem a doutrina de contribuição do repositório (sem PR, sem tripla de migration, sem packaging do kit original, sem editar nada fora de `coolify/` e dos arquivos novos desta skill). O produto mora no upstream; aqui só se opera a instalação na VPS indicada.

## Contrato de entrada (uma coisa por vez, nunca re-pergunte o decidido)

`VPS_IP` (SSH root com chave), `COOLIFY_FQDN` completo (ex.: `panel.coolify.com.br`), `APP_FQDN` completo, `SUPABASE_ACCESS_TOKEN` (ou as 4 cópias manuais). Chave de IA é opcional e entra depois pela tela.

## Ordem (comandos a partir da raiz do repo)

0. `dns-check --app-fqdn <APP_FQDN> --panel-fqdn <COOLIFY_FQDN> --vps-ip <IP>` — A-record dos 2 FQDNs antes de criar qualquer coisa (`--allow-unresolved` segue sem cadeado)
1. `py -3 coolify/scripts/docker-status.py --ssh root@<VPS_IP>` (no WSL: `python3`) — inventário read-only, reusar Coolify saudável, nunca destruir.
0b. (só se o passo 1 não achar Coolify) `install-coolify --ssh root@<VPS_IP>` — instalador oficial latest em arquivo + run detached + poll do /api/health até 200; depois segue no wait-admin. Nunca canalize curl direto para shell.
2. `coolify.py heal-localhost --ssh root@<VPS_IP>` — exige `reachable:true` antes de tudo.
3. `coolify.py wait-admin --ssh root@<VPS_IP>` — se já há admin, pula sozinho; senão o usuário cria no browser do painel.
4. `coolify.py enable-api --ssh root@<VPS_IP>` + `coolify.py token --ssh root@<VPS_IP> --out coolify.token --base-url https://<COOLIFY_FQDN>` — reusa o token se válido; arquivo `0600` transitório, nunca no log.
5. `coolify.py instance-domain --ssh root@<VPS_IP>` — confere o FQDN do painel, nunca sobrescreve sem OK explícito.
6. `supabase.py provision --token-file supabase.token --org-id <org> --app-fqdn <APP_FQDN> --ssh root@<VPS_IP> --out base.env` — antes, perguntar se envia relatórios de erro (off ou DSN) e passar `--sentry`; cria o projeto, aguarda ACTIVE, grava `base.env` (nome duplicado recusa sem criar; `limite_free_provavel` mostra a contagem — pedir OK e repetir com `--force`).
7. `coolify.py db-apply --file base.env --sql supabase/baseline.sql --ssh root@<VPS_IP>` — extensões + schema no banco, ANTES de seguir (sem este passo o worker morre com "harness ausente").
8. `coolify.py create-project` + `coolify.py ensure-service --project-uuid <uuid> --compose-file coolify/deskcomm.coolify.yml` — descoberta por nome (`DeskcommCRM`/`deskcommcrm`), cria só o ausente (projeto com descrição).
9. `coolify.py env-sync --file base.env --app-fqdn <APP_FQDN> --base-url https://<COOLIFY_FQDN> --token-file coolify.token --service-uuid <uuid>` — deriva `DOMAIN`, webhook, `NEXT_PUBLIC_APP_URL` e `NEXT_PUBLIC_ADMIN_URL`.
10. `coolify.py set-fqdn --ssh root@<VPS_IP> --app-id <id> --fqdn <APP_FQDN>` + `restart` (com OK explícito em produção) + `poll-tls https://<APP_FQDN>`.
11. `supabase.py marca-emails --token-file supabase.token --file base.env --app-fqdn <APP_FQDN>` — URLs dos e-mails de acesso (marca recusada em free sem SMTP: `free_tier_sem_smtp`).
12. `coolify.py bootstrap-owner --file base.env --email <dono> --password <senha> --ssh root@<VPS_IP>` — dono confirmado + org + admin, sem depender de e-mail.
13. **Pergunte obrigatoriamente** se o operador quer configurar o Resend; explique que sem ele o app funciona, mas convites e e-mails de LGPD não saem. Se fornecer a chave, confirme o remetente/domínio e só então execute `coolify.py env-set RESEND_API_KEY=<chave> RESEND_FROM_EMAIL=<remetente> --service-uuid <uuid> --base-url https://<COOLIFY_FQDN> --token-file coolify.token` + `restart` + `poll-tls` — a chave também destrava a marca do passo 11. Se recusar, registre que foi pulado.
14. Dono no browser do app → login → onboarding → QR do WhatsApp → `healthcheck.sh` do kit original.
15. (opcional, recomendado) `backup.py install-cron --ssh root@<VPS_IP> --file base.env` — dump diário + waha, retenção 7+4+2 em `/data/coolify/backups-deskcomm/` (descubra o volume e repita com `--waha-volume`).

Detalhe de cada passo, regras e o fluxo de update (redeploy com tags oficiais): `coolify/README.md`. Guardrails e armadilhas: `coolify/skill/guardrails.md`, `coolify/skill/gotchas.md`.
