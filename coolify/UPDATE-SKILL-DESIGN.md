# Update pela skill Coolify, sem cron — especificação para revisão

Data: 2026-09-18. Estado: desenho aprovado por seções; especificação aguardando revisão do operador antes do writing-plans. Sem implementação, sem commit, sem acesso à VPS.

## 1. Objetivo

Dar à skill `deskcomm-instalar-coolify` uma etapa "Update" acionada pelo operador, sem cron e sem gatilho automático. O update executa o pipeline já provado na VPS (`sync-compose` + `db-apply` + `env-sync` + `restart` + `poll-tls`), com salvaguardas que hoje não existem: versão instalada lida do painel, release alvo escolhida pelo operador, arquivos da release isolados do checkout do overlay, backup obrigatório validado, prévia antes de gravar e política de falha sem restauração automática.

## 2. Escopo e não-metas

Dentro do escopo, tudo em `coolify/` + espelhos da skill (`.agents/skills/deskcomm-instalar-coolify/` e `.claude/skills/deskcomm-instalar-coolify/`, mantidos byte-idênticos):

- novos subcomandos em `coolify/scripts/coolify.py` (`version-status`, `update`);
- etapa "Update" em `coolify/skill/SKILL.md` (+ `gotchas.md`/`guardrails.md` se surgir armadilha nova);
- `coolify/README.md` e `coolify/HISTORICO.md` atualizados;
- `coolify/deskcomm.coolify.yml` com `UPSTREAM_REF` avançada quando o operador aplicar um update.

Fora do escopo (não-metas explícitas):

- nenhum arquivo do produto (`app/`, `lib/`, `workers/`, `supabase/migrations/`, `supabase/baseline.sql`, kit `hostgator-setup-kit/`); nenhum PR ao repositório oficial;
- nenhum cron, agendador ou webhook de auto-update;
- nenhuma restauração automática de banco; voltar imagens nunca é apresentada como recuperação de dados;
- WAHA (`devlikeapro/waha:latest-2026.7.2`), `srh` (digest), `redis`, rede do proxy, FQDN e segredos: intocados pelo update, exceto o necessário em `env-sync` com prévia;
- produção nunca é laboratório: a prova integrada roda em instalação de teste.

## 3. Decisões do operador (travadas no brainstorming)

1. Versão alvo: a skill identifica a versão instalada, lista releases oficiais posteriores e o operador escolhe. Nada é inventado; tag móvel (`latest`/`main`/`stable`) é recusada como alvo.
2. Janela de manutenção: update que pausa atendimento ou altera banco exige declaração de janela + backup válido + OK explícito antes de qualquer escrita.
3. Falha após alteração no banco: parar, apresentar diagnóstico e pedir autorização para cada passo de recuperação. Sem restauração automática.
4. Arquitetura: skill conduz (escolhas e aprovações) + comandos executam (verificações testáveis). Sem cron.

## 4. Arquitetura

Duas peças, ambas no overlay:

1. `coolify.py` — peça executável e testável:
   - `version-status`: lê a tag real gravada no painel (compose via `api-get`, padrão já existente em `coolify/scripts/coolify.py:585-587`) e lista releases oficiais posteriores (fonte: releases do `melgarafael/DeskcommCRM`; meio de consulta a definir no plano — GitHub API ou inspeção de tags GHCR — sem inventar endpoint aqui). Saída em JSON: instalada, disponíveis, "nada a fazer" quando iguais.
   - `update --ref 1.X.Y ...`: executa o fluxo da seção 5. `--ref` obrigatória e numerada; `--dry-run` imprime o plano sem tocar em nada.
2. Skill — peça de condução (`skill/SKILL.md` + espelho): passo 1 `version-status` e escolha do operador; passo 2 janela + backup + OK; passo 3 `update --ref`; passo 4 `poll-tls` + healthcheck + registro no `HISTORICO.md`.

## 5. Fluxo do `update --ref 1.X.Y`

Ordem executada; qualquer etapa que falhe interrompe as seguintes.

1. Pré-voo, só leitura: valida `--ref` numerada; descobre o serviço por nome (`DeskcommCRM`/`deskcommcrm`, como `ensure-service`); lê o compose gravado no painel via `api-get` e salva snapshot local (`compose-<ts>.b64`); compara tag instalada com `--ref` — igual significa "nada a fazer".
2. Arquivos da release isolados: obtém o `supabase/baseline.sql` e os metadados da tag `v<ref>` do repositório oficial para diretório temporário (ex.: worktree temporária ou download da release), sem trocar a branch do checkout do overlay. O template de compose permanece o do overlay, com substituição dos números. Sem os arquivos da tag → erro claro, nenhuma escrita.
3. Troca de tags: no template do overlay, altera somente o número das 3 imagens Deskcomm (`app`, `worker`, `scheduler` — hoje `deskcomm.coolify.yml:8,53,113`); WAHA e `srh` intactos. `sync-compose` via PATCH (`coolify.py:251-257`; PUT é 405 na 4.3.19).
4. Banco com critério: aplica o `baseline.sql` da release via o caminho `db-apply` existente (`coolify.py:437-485`). Não reaplicar SQL indiscriminadamente: se a release não traz mudança de schema, registrar o motivo de pular. Contagem de tabelas e harness (≥30, 4/4) são verificações mínimas, não prova suficiente — a prova é funcional (seção 7).
5. Env com preservação: antes de gravar, `env-sync --preview` (máscara `4...2`, `coolify.py:322-325`) e conferência humana. O update nunca regenera segredo que existe no painel: se `SRH_TOKEN` (ou equivalente) estiver ausente do arquivo local mas presente no painel, prevalece o valor do painel — o comportamento atual (`coolify.py:314-321`, gera quando ausente do arquivo) não pode rodar sem essa guarda, sob risco de invalidar o Redis interno. Chaves que só existem no painel (ex.: `RESEND_API_KEY` via `env-set`) nunca são apagadas, pois o bulk é upsert (`HISTORICO.md:43-44`).
6. Ativação: `restart` via API (`coolify.py:498-501`; 200 = enfileirado) → `poll-tls` até 200 com cert válido (`coolify.py:504-514`) → verificação de containers/tag e ausência de restarts anormais (padrão `docker-status.py`). Deploy sempre pela API; nunca `docker compose up` manual (gotcha vigente).
7. Pós: imprime resumo (anterior → nova, backup usado, snapshot salvo, SQL aplicado ou motivo de pulo) para registro no `HISTORICO.md`.

## 6. Falhas e recuperação

- Falha em qualquer etapa: interrompe, informa o que foi alterado, o que ficou pendente e se o atendimento segue pausado. Diagnóstico inclui os últimos erros úteis (ex.: cauda de `unexpected_errors` do `db-apply`), sem expor segredos.
- Após alteração no banco: sem restauração automática e sem propor "voltar imagens" como recuperação (baseline é aditiva; downgrade de imagem não desfaz schema — ressalva validada na exploração). A skill apresenta backup disponível + opções e aguarda autorização para cada passo.
- Queda de conexão com o agente: a próxima execução consulta o registro protegido da operação e o estado real (tag no painel, schema aplicado, backup) antes de propor retomada; nunca repete SQL às cegas.
- Dependência conhecida: o backup sob demanda remoto ainda não existe como subcomando disparável da estação (`backup.py run` roda no host; `install-cron` agenda — `backup.py:77-146`); o plano deve prever o disparo remoto pontual + validação do artefato antes do update. Bug conhecido fora do caminho crítico, registrado para não contaminar o escopo: `select_keep` casa timestamp no início do nome (`backup.py:24-31`) mas os arquivos gerados têm prefixo `db-`/`waha-` (`backup.py:92,97`), o que torna a poda inócua para esses nomes; restore documentado com `psql < db-*.sql.gz` não descomprime gzip (`README.md:39`).

## 7. Testes e prova

- Automatizados (a definir casos no plano): seleção de release; recusa de tag móvel; prévia sem escrita; bloqueio sem backup válido; preservação de segredos do painel; falha por etapa com diagnóstico; retomada sem repetir SQL; snapshot de compose salvo.
- Prova integrada em instalação de teste com dados: update aplicado, `app`/`worker`/`scheduler` na tag nova, login, onboarding e atendimento (WhatsApp) funcionais; simulação de falha confirma diagnóstico sem restauração automática.
- Critério de sucesso: versão efetivamente em execução + verificações funcionais, não apenas HTTP 200.

## 8. Riscos e pontos a fechar no plano

- Descoberta das releases oficiais (GitHub API x GHCR) e leitura do conjunto atual de envs do painel via API (endpoint a confirmar na 4.3.19) — o plano valida antes de codar.
- Formato do registro protegido da operação (local, fora do repo, sem segredos) e do snapshot de compose.
- Critério de "release sem mudança de schema" (comparar `baseline.sql` entre tags ou manifesto da release).
- Espelhos da skill byte-idênticos (gate `tests/unit/skills-embutidas.test.ts` cobre docs, não scripts — conferir por hash como no `HISTORICO.md`).
