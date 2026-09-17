# Gotchas (armadilhas medidas)

- `docker_compose_raw` precisa ser base64, senão 422. O `create-service` já faz.
- FQDN não se move por env. Service sobe mas dá 503 = setar `service_applications.fqdn` + restart via API.
- `start` da API pode responder 200 sem materializar. Nunca subir com `docker compose up` na mão (fica Up no docker, Exited no Coolify). Re-disparar pela API.
- Instance Domain ANTES dos serviços. Restart do `coolify` no meio zera a fila de deploy.
- Service não tem fila de deploy de application. Checar por `/data/coolify/services/<uuid>/` + `docker compose ps`.
- Imagem grande: conferir com `docker manifest inspect`, deixar o Coolify puxar no deploy.
- Chave localhost grudada (authorized_keys sem newline) = todo deploy falha. `heal-localhost` sempre.
- Coolify 4.3.19: container sem `bash` e sem `/root/.ssh` (roda como www-data); a chave do localhost vem do banco via tinker (`servers` → `private_keys`), nunca de arquivo no container.
- API 4.3.19 mora em `/api/v1` (prefixo dentro do `api_req`; `--base-url` continua só o FQDN).
- `sync-compose` é `PATCH /services/{uuid}` (PUT dá 405); `env-sync` é 1 `PATCH .../envs/bulk` com `{"data":[{key,value}]}` (updateOrCreate idempotente).
- Token via API exige `team_id` (`App\Models\PersonalAccessToken` com `team_id` do time do localhost); `createToken()` puro quebra com `23502`.
- Redis é o interno (`srh`): `env-sync` deriva `UPSTASH_REDIS_REST_URL=http://srh:80` e `UPSTASH_REDIS_REST_TOKEN=<SRH_TOKEN>` quando ausentes — igual ao `install.sh` do kit. Upstash Cloud só como override manual. Nunca pedir conta externa.
- Banco novo nasce VAZIO: sem `db-apply` o worker morre em loop com "harness ausente" e o app erra tabela sumida (cache do PostgREST atrasa minutos após o DDL — erro transitório, não re-aplique por ele).
- Dono não nasce sozinho: sem `bootstrap-owner` a tela é só login, e o `/signup` precisa de e-mail de confirmação que sem SMTP não chega. O comando cria confirmado + org + admin.
- Marca dos e-mails de acesso recusada em projeto Supabase free sem SMTP próprio (400 `free_tier_sem_smtp`, medido 2026-09-16; derruba a medição do kit de 2026-08-14). URLs (Site + redirects) passam; libera a marca com plano Pro ou SMTP da Resend.
- Resend é passo opcional pré-browser (13, `env-set` + `restart`): sem ela o app funciona, só convites/LGPD não saem; a mesma chave serve de SMTP do Supabase e destrava a marca do passo 11. Nunca bloqueia a instalação.
- `docker exec -i` no meio do script engole o resto do stdin (`bash -s` morre cedo): dar a ele heredoc próprio ou `</dev/null`.
- Sem `command:` no compose dos nossos serviços. Sem `ports: 80/443`. Só `app` na rede `coolify`.
