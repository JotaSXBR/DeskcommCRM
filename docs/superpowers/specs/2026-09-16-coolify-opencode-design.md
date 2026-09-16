# Design: Coolify nativo via OpenCode (fork-local)

Data: 2026-09-16
Status: aprovado pelo usuário (3 seções)
Branch: `feat/coolify-opencode` (local, sem push ao upstream)
Escopo: fork `https://github.com/JotaSXBR/DeskcommCRM` + local apenas. Nada é enviado a `melgarafael/DeskcommCRM`.

## Contexto e decisão

VPS existe, Coolify já instalado. OpenCode roda no Windows local via SSH.
Deploy como service Coolify nativo. Referência: `fazer-ai/agents-skills`
(`agents-onboarding`, Tier A Coolify), adaptada ao Deskcomm, não copiada.

Decisão aprovada: A revisada. Estender `deskcomm-instalar` com trilha
Coolify executada por agente, mais toque mínimo em `deskcomm-cliente-novo`.
Sem skill nova, sem mudança de schema, sem envio ao upstream.

## Seção 1: `deskcomm-instalar` + trilha Coolify (aprovada)

Roteamento: 1 edição no topo do `SKILL.md`, após descobrir o cenário.
Se Coolify nativo via agente, ler `references/coolify-agente.md`.
Caminho default (VPS crua + `install.sh` + Caddy) intocado.
Fonte da verdade continua `install.sh`; o novo doc declara divergências.

Novo `references/coolify-agente.md`, nesta ordem:
0. pré-reqs (SSH root, painel no ar, `DOMAIN`, token Supabase, chaves IA opcionais).
1. brownfield read-only (`docker ps`, saúde do Coolify, `heal-localhost` antes de deployar).
2. token API Coolify em arquivo `0600`, nunca em chat, log ou repo.
3. criar service com compose adaptado: derivado do `prod`, sem `caddy`,
   sem `ports: 80/443`, app na 3000 com FQDN `https://<DOMAIN>`,
   volumes `waha-data` e `waha-media` persistentes.
4. envs pela UI ou API do service (pooler Supabase URI, `WAHA_API_KEY`,
   `WAHA_HMAC_SECRET`, `INTERNAL_SECRET`, resto do `.env.example`).
5. deploy assíncrono narrado serviço a serviço
   (app, worker, waha, redis/srh, scheduler), poll em background,
   sem `docker pull` em foreground.
6. pós-deploy: abrir `https://<DOMAIN>`, login do dono, wizard,
   QR do WhatsApp, backup. Limitação documentada: `backup.sh` ainda
   exige cron no host, não é reinventado aqui.

Novo `references/coolify-gotchas.md`, só o que morde:
FQDN dirige o Traefik (env não), `docker_compose_raw` em base64,
nunca `command:` no app ou worker, `heal-localhost`,
fila de service não é fila de application,
`start` que não materializa exige re-disparo pela API ou UI,
nunca `docker compose up` manual no SSH,
PowerShell só orquestra (payload em arquivo, nunca inline,
sem here-string, sem `\` de continuação, sem `{{}}` cru),
`docker ps --format` manual quebra via SSH.

Scripts vendorados em `.agents/skills/deskcomm-instalar/scripts/`
(Python stdlib, crédito MIT a `fazer-ai/agents-skills`):
`remote.py` (dono do payload remoto, `--script-file`,
`--in-container` + `--exec`), `coolify.py` subset Deskcomm
(`heal-localhost`, `enable-api`, `token --out 0600`,
`api-get`/`api-post --token-file --json-file`,
`create-service --compose-file`, `set-fqdn`, `wait-admin`),
`docker-status.py` (ps normalizado em JSON).
Fora: Harbor, Chatwoot, Langfuse, hub, `bunx`. Nada disso existe aqui.
Template `templates/docker-compose.coolify.yml` derivado do `prod`.

## Seção 2: `deskcomm-cliente-novo` (aprovada, 3 toques)

1. Passo 0: instalação via Coolify entrega o mesmo contrato
   (TLS, WhatsApp persiste em volume). Diferenças: logs e envs no
   painel do service, update por redeploy. Resto inalterado.
2. Passo 4: checklist ganha 2 linhas. Sessão WAHA sobrevive a
   redeploy (volume existe) e update documentado (painel vs tela).
3. `nunca fazer`: 1 linha. Nada de `docker compose up` manual no SSH
   em service gerido pelo Coolify. Config de agente continua só pela
   tela (motor lê versão publicada, SQL não muda nada).

Triagem, pacote do nicho, anatomia do prompt, ordem pela tela
e publicar como ato humano não mudam.

## Seção 3: fluxo fork-local e testes (aprovada, corrigida)

Remotes: `origin` aponta ao fork. Sem remote `upstream`, sem fetch,
sem push e sem PR a `melgarafael/DeskcommCRM`. Passo futuro explícito,
não executado. Branch de trabalho nasce do `main` local.
`armar-hooks.sh` uma vez por clone. Pré-voo local antes de qualquer push
ao fork. Sem `APP_IMAGE=latest`, sem marca no código, sem segredo no diff.

Gates: `skills:sync` mais `skills-embutidas.test.ts` e
`documentacao-aponta-para-o-que-existe.test.ts` verdes,
`typecheck`, `lint`, `test:unit` com rodapé completo,
`test:shell` por tocar kit ou compose.
Pressão RED para GREEN em 3 cenários: payload inline no PowerShell,
token em argv ou log, e compose manual fora da gestão.
Com a skill, os três usam `remote.py`, `--token-file` e API ou UI.
Fragmento `.changes/<kebab>.md` com `capacidade_nova` e
`pnpm release:conferir`. Sem seção à mão no `CHANGELOG`.

## Fora de escopo

Skill nova, Tier Portainer ou compose genérico, migração de Chatwoot
antigo, caminho manual sem IA, `coolify.py` completo do fazer-ai,
cron de backup dentro do Coolify, mudança de schema ou RLS.

## Riscos

Redeploy sem volume apaga sessão do WhatsApp. FQDN errado dá 503 com
tudo saudável. Token em log vaza no transcript. Compose manual sai da
gestão do Coolify. Cada um tem sintoma e fix no gotchas.

## Próximo passo

`writing-plans` para o plano de implementação. Nenhum código alterado
neste doc.
