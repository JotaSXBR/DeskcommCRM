# Deploy como service Coolify nativo, operado pelo agente

Vale só quando a VPS já tem Coolify saudável e o CRM vai viver como service
gerido pelo painel. Para VPS crua, volte ao `install.sh` do `SKILL.md`.

## 0. Pré-requisitos

Acesso SSH root à VPS, painel Coolify no ar, `DOMAIN` com registro A para o
IP da VPS, token do Supabase e chaves de IA (opcionais, entram depois pela
tela em IA, Credenciais). Nenhum segredo aparece no chat ou em log.

## 1. Brownfield read-only

```bash
python3 scripts/docker-status.py --ssh root@<VPS_IP> --all
```

Nada saudável é reinstalado. Em seguida, sempre:

```bash
python3 scripts/remote.py --ssh root@<VPS_IP> --script-file scripts/healthcheck-local.sh
python3 scripts/coolify.py heal-localhost --ssh root@<VPS_IP>
```

Siga só com `reachable:true`. O arquivo `scripts/healthcheck-local.sh`
contém exatamente: `docker ps --format '{{.Names}} {{.Status}}'`.

## 2. Token da API em arquivo 0600

```bash
python3 scripts/coolify.py enable-api --ssh root@<VPS_IP>
python3 scripts/coolify.py token --ssh root@<VPS_IP> --out coolify.token
python3 scripts/coolify.py api-get --base-url http://<VPS_IP>:8000 --token-file coolify.token --path /servers
```

O `token` nunca é impresso; `coolify.token` é transitório e nunca commitado.
Toda chamada autenticada usa `--token-file`, e JSON de POST usa `--json-file`.

## 3. Criar o service

```bash
python3 scripts/coolify.py create-service --base-url http://<VPS_IP>:8000 --token-file coolify.token --name deskcommcrm --compose-file templates/docker-compose.coolify.yml --fqdn https://<DOMAIN>
```

Sem `command:` no compose. Sem `ports: 80/443`. O TLS vem do FQDN.

## 4. Envs pelo painel ou API do service

Supabase (pooler URI, nunca Direct IPv6), `WAHA_API_KEY`,
`WAHA_HMAC_SECRET`, `INTERNAL_SECRET` e o resto do `.env.example`.
Segredo mora no env do service, em nenhum outro lugar.

## 5. Deploy e poll em background

Dispare pelo painel ou `api-post` e acompanhe serviço a serviço (app,
worker, waha, redis/srh, scheduler) com `docker-status.py --project <uuid>`.
Polls longos rodam em background; não avance sem saúde confirmada.

## 6. Pós-deploy

Abra `https://<DOMAIN>`, entre com o dono, complete o wizard, conecte o
WhatsApp pelo QR e agende `hostgator-setup-kit/backup.sh` no cron do host.
Limitação honesta: backup e update fora do painel continuam manuais até
decisão futura; o redeploy no painel não apaga a sessão se os volumes
`waha-data` e `waha-media` existirem no service.
