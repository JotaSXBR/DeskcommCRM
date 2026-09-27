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
6. `supabase.py provision` (cria o projeto, aguarda ACTIVE, grava `base.env`) — perguntar telemetria antes (off ou DSN) e passar `--sentry`; se recusar com `limite_free_provavel`, mostrar a contagem, pedir OK e repetir com `--force`
7. `db-apply --file base.env --sql supabase/baseline.sql` (schema no banco, ANTES de seguir; sem ele o worker morre com "harness ausente")
8. `create-project` + `ensure-service` (descoberta por nome; cria só o ausente, projeto com descrição)
9. `env-sync --file base.env --app-fqdn <APP_FQDN>`
10. `set-fqdn` + `restart` (com OK explícito em produção) + `poll-tls`
11. `supabase.py marca-emails` (URLs dos e-mails de acesso; marca bloqueada em free sem SMTP)
12. `bootstrap-owner --file base.env --email <dono> --password <senha>` (dono confirmado + org + admin, sem e-mail)
13. (opcional) `env-set RESEND_API_KEY=<chave> RESEND_FROM_EMAIL=<remetente>` + `restart` + `poll-tls` (convites/LGPD; a chave destrava a marca do passo 11)
14. Dono no browser do app → login → onboarding → QR do WhatsApp → `healthcheck.sh`
15. (opcional, recomendado) `backup.py install-cron --ssh root@IP --file base.env` — dump diário + waha, retenção 7+4+2 em `/data/coolify/backups-deskcomm/`

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

Narre serviço a serviço. Prévia antes de gravar. Dono cria contas no browser.

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
