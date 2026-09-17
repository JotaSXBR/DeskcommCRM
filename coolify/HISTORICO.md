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

- `py_compile` OK nos 4 scripts; `docker compose config` OK (warnings de env vazia esperados — vêm do Coolify).
- Espelhos da skill byte-idênticos; nenhum segredo real no diff; diff só com adições.

## Primeira run na VPS (2026-09-16, Coolify 4.3.19, app `crm.fluxie.com.br`)

Continua a numeração acima; estes foram aprovados **durante** a run (cada conserto
teve OK antes de entrar), todos medidos contra a VPS real.

12. `heal-localhost` esperava `/root/.ssh/id*.pub` dentro do container → **chave do
    localhost vem do banco** (`servers` → `private_keys`, via tinker + `ssh-keygen -y`
    dentro do container, com `sh`, arquivo 600 + `shred`); segredo nunca sai do
    container nem aparece no output (só JSON).
13. `docker exec -i` no meio do script **engole o resto do stdin** (`bash -s` morre
    cedo) → heredoc próprio ou `</dev/null` em todo `docker exec -i`
    (`heal-localhost`, `token`, `enable-api`, `instance-domain`, `set-fqdn`).
14. Token: `createToken()` puro quebra (`personal_access_tokens.team_id` NOT NULL,
    `23502`) → **criação explícita via `App\Models\PersonalAccessToken` com o
    `team_id` do time do localhost**; `--execute` em aspas simples (duplas expandem
    `$var` sob `set -u`).
15. API 4.3.19 mora em **`/api/v1`** (prefixo dentro do `api_req`; `--base-url`
    continua só o FQDN); `sync-compose` é **PATCH** (PUT dá 405, provado 200);
    `env-sync` é **1 bulk** `PATCH .../envs/bulk` com `{"data":[{key,value}]}`
    (updateOrCreate idempotente) — PATCH/POST por chave não existem nessa versão.
16. Redis: **o interno (`srh`) é o padrão** — `env-sync` deriva
    `UPSTASH_REDIS_REST_URL=http://srh:80` e `UPSTASH_REDIS_REST_TOKEN=<SRH_TOKEN>`
    quando ausentes, igual ao `install.sh` do kit; Upstash Cloud só como override
    manual. Revisão de processo pedida pelo operador: nunca pedir conta externa.
17. Banco novo nasce VAZIO: **`db-apply` novo** (extensões vector/citext/pg_trgm +
    `baseline.sql` + verificação ≥30 tabelas e harness completo); fresco aplica com
    `ON_ERROR_STOP`, existente re-aplica filtrando erros benignos. Sem ele o worker
    morre em loop ("harness ausente").
18. Template: **`NODE_ENV=production` + refs de `CPF/WAHA_BYO/AI_CRED/IMPERSONATE`**
    (estavam geradas mas nunca chegavam ao `app`); `env-sync` gera `SRH_TOKEN` e
    `IMPERSONATE_COOKIE_SECRET` quando ausentes.
19. Dono: **`bootstrap-owner` novo** (Auth Admin cria confirmado + SQL cria org
    `minha-empresa`, membership admin e `platform_admins` com `mfa_required=false`,
    como o kit); sem ele a tela é só login e o `/signup` depende de e-mail.
20. Ordem da skill virou **11 passos** (`db-apply` = 7, `bootstrap-owner` = 10);
    espelhos `.agents/` + `.claude/` mantidos byte-idênticos (conferido por hash).
21. Banco antes de tudo: **`supabase.py provision` durável** (cria o projeto, **espera
    `ACTIVE_HEALTHY` até 10 min**, descobre o pooler por conexão real, configura a
    Site URL e grava `base.env`); nome duplicado na org recusa sem criar nada.
    **`db-apply` colado logo depois** — nada seguinte roda sem schema aplicado.
    Ordem virou **12 passos** (provision = 6, `db-apply` = 7).
22. E-mails de acesso: **`supabase.py marca-emails`** (subjects + modelos com a marca
    + Site URL + redirects, tudo conferido por releitura). Medido 2026-09-16: o
    Supabase passou a recusar modelo em projeto free sem SMTP próprio (400) —
    URLs passam, marca fica `free_tier_sem_smtp`; libera com plano Pro ou SMTP da
    Resend.     Ordem virou **13 passos** (`marca-emails` = 11).
23. Resend **fora do onboarding** (decisão do operador 2026-09-16): sem ela o app
    funciona, só convites/LGPD não saem; quando vier, `env-sync` + `restart`. A mesma
    chave serve de SMTP do Supabase e destrava a marca do item 22.
24. Pedido do operador: a chave da Resend no lugar que a skill acha correto →
    **passo opcional 13** (`env-set` genérico CHAVE=valor, imprime só nomes, +
    `restart` + `poll-tls`), entre `bootstrap-owner` e o browser. Opcional de
    verdade: pular não executa nada. Ordem virou **14 passos**.
25. Pedido do operador (reinstalação com Coolify vazio): projeto criado como
    **`DeskcommCRM` + descrição** (`description` aceito e validado na 4.3.19,
    `nullable`/255); `--description` sobrescreve. Reuso por nome não regrava a
    descrição de projeto que já existe.

## Validado na VPS (primeira run, medido)

- `heal-localhost` → `{"reachable":true}` (chave já estava certa; nada mudou no host).
- `wait-admin` pula sozinho (`users=1`); `enable-api` UPDATE 1; `token` cria e **reusa**
  (`GET /api/v1/servers` 200).
- `instance-domain` confere sem sobrescrever; `create-project` 201; `ensure-service`
  201; `env-sync` bulk 201 (19→20 chaves); `set-fqdn` UPDATE 1; `restart` enfileira
  200; `poll-tls` 200.
- `db-apply` (modo update, schema já semeado pelo app): 100 tabelas, harness 4/4,
  extensões OK, zero erros inesperados.
- Pós-deploy: `worker`/`app`/`scheduler` running sem restarts, zero `boot falhou`,
  zero erros no app, `agent-engine pronto`, TLS 200.
- `bootstrap-owner`: `created` + membership `admin` + `platform_admin` verificados no banco.
- `marca-emails`: URLs OK conferidas por releitura (`site` + `redirects` gravados);
  marca recusada com `free_tier_sem_smtp` (prova da decisão 22).
- `env-set`: `--help` OK + caminho de erro `par_sem_igual` provado sem escrita; a escrita
  usa a mesma chamada bulk do `env-sync` (provada 201).
- Supabase `deskcommcrm` (sa-east-1, free) criado pela API, pooler `aws-0` provado por
  conexão real, Site URL configurada; `base.env` só em Temp `0600`, fora do repo.
- Nenhum segredo no diff, nos logs ou no transcript além do que o operador colou;
  nenhum arquivo do produto tocado (só `coolify/` + espelhos da skill).

## Pendente / dívidas (depois da primeira run)

- `db-apply` em banco VIRGEM (caminho `fresh` com `ON_ERROR_STOP`) nunca rodou — nesta
  VPS o app semeou o schema antes; a próxima instalação fresca prova.
- `supabase.py provision` completo (criação) nunca rodou na versão durável — o caminho
  foi provado pelo transitório e a trava `projeto_ja_existe` pela versão durável;
  a próxima instalação fresca prova o resto.
- Lag da cache do PostgREST após DDL (erros transitórios de "tabela sumida" por
  minutos) — documentado em `gotchas.md`, sem ação.
- Telemetria Sentry da comunidade ativa por padrão (decisão do produto; opt-out com
  `SENTRY_DSN=off`).
- Chave de IA: pós-instalação pela tela (contrato, não dívida). Resend tem passo
  próprio opcional (13); a escrita real nunca rodou — próxima instalação com chave prova.
- Gate `skills-embutidas` não rodou nesta máquina (sem `node_modules`); espelhos
  conferidos por hash manual.

## Execução autorizada (2026-09-16)

- Inventário read-only na VPS `100.109.163.58`: Coolify `4.3.19` saudável; serviços
  existentes preservados.
- `heal-localhost` executado com autorização explícita do operador; resultado:
  `reachable=true`, `key_present_before=true`.
- Sugestão de segurança para o agente: antes de qualquer alteração em
  `authorized_keys` do root, mostrar claramente o efeito, o escopo e solicitar
  aprovação explícita; preferir uma checagem read-only e registrar se a chave já
  estiver correta, evitando escrita desnecessária.
- Sugestão do operador: ao final da instalação, oferecer e executar uma limpeza
  explícita dos artefatos transitórios locais (`coolify.token`, `supabase.token` e
  `base.env`), sem remover código, histórico ou arquivos de configuração do
  projeto.
- Durante esta execução, `supabase.token` foi encontrado com permissão `777` e
  corrigido para `600` antes do uso. A organização Supabase foi identificada via
  API como `Fluxie Tecnologia` (`jlnicsgljkhvlhbwlayk`). O token não foi exibido.
- Para reaproveitar um projeto Supabase existente, ainda é necessário confirmar o
  `APP_FQDN`; o endpoint fornece o project ref, mas não substitui o domínio final
  usado pelo CRM.
- Projeto existente validado via API: `otrfrbjswtkhwoioleaa`, `deskcommcrm`,
  organização `jlnicsgljkhvlhbwlayk`, região `sa-east-1`, status `ACTIVE_HEALTHY`.
  Limitação encontrada: o fluxo `supabase.py provision` recusa projetos duplicados
  e gera a senha do banco apenas ao criar um projeto; a API de detalhes não expõe
  essa senha. Reuso/reset seguro precisa de senha do banco existente ou de um
  fluxo explícito para redefini-la, que ainda não está implementado neste overlay.
- No primeiro `db-apply` do projeto recriado, o caminho `fresh` falhou porque o
  script montava `psql -i`, opção inexistente. Correção mínima aplicada em
  `coolify/scripts/coolify.py`: remover `-i`; a entrada já usa `-f -` via stdin.
- O teste seguinte revelou que a URL do banco também precisava de quoting
  seguro ao compor o comando remoto; sem isso o `psql` caía no socket local.
  `coolify.py` passou a usar `shlex.quote` (stdlib) para a URL, sem imprimir
  credenciais.
- A aplicação ainda não recebia o SQL porque `docker run` não tinha `-i` no
  caminho via stdin; foi criado um comando separado `img_stdin` com `-i` antes
  da imagem, e removido o `-i` inválido do `psql` no caminho de atualização.
- Instalação concluída nesta execução: projeto Supabase recriado com ref
  `bmdlatpovndyexnzhegu`, `109` tabelas e harness `4/4`; projeto Coolify
  `mgpregpu6qvih9ofxh31chf4`; serviço `sa7onxym0op0ncaztb67uzdx`; aplicação
  `app` ID `169`, FQDN `crm.fluxie.com.br`; TLS respondeu `200` na tentativa 10.
- `env-sync` gravou `20/20` variáveis. `marca-emails` configurou Site URL e
  redirects, mas templates ficaram bloqueados por `free_tier_sem_smtp`.
- `bootstrap-owner` criou o proprietário confirmado `admin@fluxie.com.br`.
- Próximos passos humanos: login no app, onboarding, QR do WhatsApp e healthcheck.
  Resend permanece opcional; os artefatos locais secretos devem ser removidos
  explicitamente ao final (`coolify.token`, `supabase.token`, `base.env`).
- Após autorização explícita, `RESEND_API_KEY` e
  `RESEND_FROM_EMAIL=noreply@contato.fluxie.com.br` foram gravados no serviço
  Coolify (`env-set` 201); restart e TLS concluíram com `200` na tentativa 10.
  A rotina `marca-emails` continuou retornando `free_tier_sem_smtp`, indicando
  que configurar a chave no app não configura automaticamente o SMTP do projeto
  Supabase; essa etapa requer configuração própria no painel/API do Supabase.
- Correção de processo: a skill e o espelho agora exigem perguntar sobre Resend,
  explicar o impacto e confirmar remetente antes de concluir a instalação.
- Após a correção, consulta mínima confirmou conexão com o novo banco e o
  baseline aplicado: `109` tabelas públicas e harness `4/4`. Uma repetição do
  `db-apply` entrou no caminho de atualização e ficou aguardando; foi
  interrompida sem alteração adicional, pois o schema já estava validado.
