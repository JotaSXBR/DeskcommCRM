# Coolify + OpenCode no Windows: armadilhas que já morderam

## PowerShell nunca carrega payload, só orquestra

Nada de `ssh <host> '...script...'` com aspas, `{{...}}`, `$()`, `\` no fim
da linha ou here-string: o PowerShell come aspas, prefixa BOM e re-encoda
acentos. Escreva o payload num arquivo com a ferramenta de edição e rode
`python3 scripts/remote.py --ssh root@<VPS_IP> --script-file x.sh`.
Só vai inline o comando de uma linha sem `"`, `$()`, `{{...}}`, `(` ou `\`.

## FQDN dirige o Traefik, env não

Num service do Coolify, a rota nasce de `service_applications.fqdn` no banco
do Coolify. Ajuste com
`python3 scripts/coolify.py set-fqdn --ssh root@<VPS_IP> --app-id <id> --fqdn https://<DOMAIN>`
(preserve `:3000` se o template declarar porta). Sintoma de FQDN errado:
tudo saudável e `503` no domínio.

## Compose cru na API precisa de base64

`POST /api/v1/services` com compose cru devolve `422 should be base64
encoded`. Use `scripts/coolify.py create-service --compose-file ...`, que
faz o base64. Nunca monte esse POST à mão.

## Nunca sobrescrever `command:` no app ou worker

O boot (bootstrap, migrate, serve) é o CMD da imagem. Override com `command:`
derruba o contêiner em crash-loop. Não declare `command:` no template.

## `heal-localhost` antes do primeiro deploy

Se o Coolify não alcança o próprio host por SSH, todo deploy falha sem erro
claro (servidor `localhost` Unreachable). Rode
`python3 scripts/coolify.py heal-localhost --ssh root@<VPS_IP>` e siga só com
`reachable:true`. É idempotente.

## `start` da API pode não materializar: re-dispare, nunca suba à mão

Se a API responde que enfileirou e os contêineres não nascem, re-dispare o
deploy pela API ou UI do Coolify. Nunca rode `docker compose up -d` no SSH:
os contêineres sobem fora da gestão e a UI mostra Exited para sempre.

## Imagem grande: sem `docker pull` em foreground

Pull de imagem grande estoura o timeout do harness e parece falha. Confira
auth e existência com `docker manifest inspect <imagem>` e deixe o Coolify
puxar no deploy assíncrono.

## `docker ps --format '{{...}}'` quebra no PowerShell via SSH

Use `python3 scripts/docker-status.py --ssh root@<VPS_IP>` (ou `--project
<uuid>` para um service). Ele devolve JSON normalizado sem quoting manual.
