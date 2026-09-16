# Guardrails (fronteiras duras, cruzar é parar e perguntar)

- Só na VPS, domínio do painel, domínio do app e licença indicados. Nada de produção de terceiros.
- Destrutivo (`down -v`, reinstalar Coolify, wipe de volume, `rm .env`) só com OK explícito.
- Segredo nunca em repo, log, commit ou transcript. Token em arquivo 0600 e header HTTP.
- Payload remoto sempre em arquivo via `remote.py`. Nada de inline com aspas, `{{ }}`, `\`, BOM.
- Usuário cria admins no browser (Coolify + app). Agente entrega link e espera, nunca cria.
- Fale o efeito em português claro antes do "pode ir". Sem jargão interno.
