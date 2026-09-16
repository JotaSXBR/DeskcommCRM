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

1. `py -3 coolify/scripts/docker-status.py --ssh root@<VPS_IP>` (no WSL: `python3`) — inventário read-only, reusar Coolify saudável, nunca destruir.
2. `coolify.py heal-localhost --ssh root@<VPS_IP>` — exige `reachable:true` antes de tudo.
3. `coolify.py wait-admin --ssh root@<VPS_IP>` — se já há admin, pula sozinho; senão o usuário cria no browser do painel.
4. `coolify.py enable-api --ssh root@<VPS_IP>` + `coolify.py token --ssh root@<VPS_IP> --out coolify.token --base-url https://<COOLIFY_FQDN>` — reusa o token se válido; arquivo `0600` transitório, nunca no log.
5. `coolify.py instance-domain --ssh root@<VPS_IP>` — confere o FQDN do painel, nunca sobrescreve sem OK explícito.
6. `coolify.py create-project` + `coolify.py ensure-service --project-uuid <uuid> --compose-file coolify/deskcomm.coolify.yml` — descoberta por nome (`DeskcommCRM`/`deskcommcrm`), cria só o ausente.
7. `coolify.py env-sync --file base.env --app-fqdn <APP_FQDN> --base-url https://<COOLIFY_FQDN> --token-file coolify.token --service-uuid <uuid>` — deriva `DOMAIN`, webhook, `NEXT_PUBLIC_APP_URL` e `NEXT_PUBLIC_ADMIN_URL`.
8. `coolify.py set-fqdn --ssh root@<VPS_IP> --app-id <id> --fqdn <APP_FQDN>` + `restart` (com OK explícito em produção) + `poll-tls https://<APP_FQDN>`.
9. Dono no browser do app → onboarding → QR do WhatsApp → `healthcheck.sh` do kit original.

Detalhe de cada passo, regras e o fluxo de update (redeploy com tags oficiais): `coolify/README.md`. Guardrails e armadilhas: `coolify/skill/guardrails.md`, `coolify/skill/gotchas.md`.
