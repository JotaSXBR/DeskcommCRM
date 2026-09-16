# Gotchas (armadilhas medidas)

- `docker_compose_raw` precisa ser base64, senão 422. O `create-service` já faz.
- FQDN não se move por env. Service sobe mas dá 503 = setar `service_applications.fqdn` + restart via API.
- `start` da API pode responder 200 sem materializar. Nunca subir com `docker compose up` na mão (fica Up no docker, Exited no Coolify). Re-disparar pela API.
- Instance Domain ANTES dos serviços. Restart do `coolify` no meio zera a fila de deploy.
- Service não tem fila de deploy de application. Checar por `/data/coolify/services/<uuid>/` + `docker compose ps`.
- Imagem grande: conferir com `docker manifest inspect`, deixar o Coolify puxar no deploy.
- Chave localhost grudada (authorized_keys sem newline) = todo deploy falha. `heal-localhost` sempre.
- Sem `command:` no compose dos nossos serviços. Sem `ports: 80/443`. Só `app` na rede `coolify`.
