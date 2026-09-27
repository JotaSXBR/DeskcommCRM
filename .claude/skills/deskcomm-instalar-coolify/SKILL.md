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
1. Inventário read-only com o `docker-status.py` (comando exato no passo 1 de `coolify/README.md`; no WSL troque `py -3` por `python3`) — reusar Coolify saudável, nunca destruir.
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

## Update (redeploy com tags oficiais, sem cron)

Sem agendador nem gatilho automático: todo update é acionado pelo operador, nesta ordem.

1. `version-status --base-url https://<COOLIFY_FQDN> --token-file coolify.token --service-uuid <uuid>` — lê a tag instalada no painel e lista as releases oficiais posteriores. O operador escolhe a alvo; `--ref` é sempre numerada (`X.Y.Z`, nunca `latest`/`main`/`stable`, senão `ref_invalida`).
2. Declare a janela de manutenção e rode `backup-agora --ssh root@<VPS_IP> [--file <env>] [--waha-volume <vol>]` — sem `--file`, passe `--base-url/--token-file/--service-uuid` e as envs vêm do painel (só em memória, sem arquivo com segredo). Só prossiga com `{"ok": true, ...}` (sem artefato válido: `backup_nao_validado`). Nada é escrito antes do OK explícito do operador.
3. `update --base-url https://<COOLIFY_FQDN> --token-file coolify.token --service-uuid <uuid> --ref <escolhida> --compose-file coolify/deskcomm.coolify.yml [--file <env>] [--sql <baseline-da-release.sql>] [--backup <artefato>] [--app-fqdn <APP_FQDN>] [--ssh root@<VPS_IP>]` — rode com `--dry-run` antes (opcional, só imprime o plano). Sem `--sql`, o `supabase/baseline.sql` da tag `v<ref>` do repositório oficial é baixado para um diretório temporário sem trocar a branch do checkout. `--file` e `--ssh` são opcionais na chamada: sem `--file`, as envs vêm do painel em tempo de execução (só em memória); sem `--ssh` o caminho direto aborta com `ssh_ausente`. `--skip-sql` só com motivo registrado no resumo.
4. O comando já termina com `restart` + `poll-tls`; confira o TLS 200, rode o `healthcheck.sh` e registre anterior → nova, backup, snapshot e motivo do SQL no `HISTORICO.md`.

Saída em JSON multi-linha: a prévia do env (`preview: true`, valores mascarados, só chaves novas/alteradas — sem mudança, nada é regravado) sai no meio e o resumo final (`ok`, `anterior`, `nova`, `backup` (<artefato>|`nao_informado`), `snapshot`, `sql`, `motivo_sql`, `registro`) na última linha — leia a última linha. Em `nada_a_fazer` (instalada igual à alvo) nada é escrito, nem snapshot. Interrupção retoma com `update ... --resume --op <registro>` sem repetir SQL concluído (etapa feita é revalidada; divergência aborta com `estado_divergente`); `--resume --op` com `--dry-run` só imprime o plano, sem revalidar o estado (benigno). Registro da operação mora em diretório temporário do SO, fora do repo, sem segredos.

| sintoma | conduta |
|---|---|
| `ref_invalida` | alvo tem que ser `X.Y.Z` numerada; tag móvel nunca entra |
| `tags_divergentes` | as 3 imagens Deskcomm discordam — inspecione o compose no painel, nunca adivinhe a instalada |
| `ssh_ausente` | informe `--ssh root@<VPS_IP>`; sem SSH o caminho direto não prossegue |
| `op_invalida` | registro de `--op` ilegível ou com `ref` diferente da pedida — confira o arquivo e a `--ref` |
| `estado_divergente` | registro diz feito mas painel/banco discordam — pare e decida com o operador, nunca force |
| `env_painel_nao_lido` | envs do painel inacessíveis — aborte, nunca grave env sem ler o painel |
| `env_arquivo_nao_lido` | o `--file` informado não foi lido — confira o caminho ou omita para ler do painel |
| `backup_nao_validado` | backup sob demanda sem artefato válido — não inicie o update |
| falha depois de alterar o banco | pare, mostre o diagnóstico (etapa, alterado até aqui, pendente) e peça autorização para cada passo de recuperação; sem restore automático, e voltar imagens não é recuperação de dados |
| `nada_a_fazer` | instalada igual à alvo — nada escrito, nada a retomar |

Detalhe de cada passo, regras e o fluxo de update (redeploy com tags oficiais): `coolify/README.md`. Guardrails e armadilhas: `coolify/skill/guardrails.md`, `coolify/skill/gotchas.md`.

## Quando der problema

| sintoma | causa mais comum | primeiro comando |
|---|---|---|
| site sem cadeado / não abre | DNS não aponta ou 80/443 fechadas | `dns-check --app-fqdn <APP> --panel-fqdn <PANEL> --vps-ip <IP>` |
| service sobe mas dá 503 | FQDN não setado no Coolify | `set-fqdn` + `restart` via API |
| UI mostra Exited com containers Up | deploy contornado por `docker compose` manual | re-disparar deploy pela API, nunca subir na mão |
| worker morre com "harness ausente" | schema não aplicado | `db-apply` antes de seguir |
| login sem usuário / signup sem e-mail | dono não criado | `bootstrap-owner` |
| e-mails de acesso em inglês / sem marca | projeto free sem SMTP | plano Pro ou Resend (passo 13) |
| tabelas somem minutos após DDL | cache do PostgREST (transitório) | esperar, não re-aplicar |

## Não-metas explícitas

- Chave de IA: o sistema pede no onboarding antes de criar o agente — fora deste skill.
