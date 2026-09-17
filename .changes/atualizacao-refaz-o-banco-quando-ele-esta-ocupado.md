---
impacto: nada_mudou
secao: corrigido
titulo: A atualização refaz o banco quando ele está ocupado, e para de mostrar avisos falsos
---
Quem tinha materiais do acervo ligados a um agente via, a cada atualização, até três avisos de banco (`could not create unique index`), mesmo com tudo certo. Não havia dado errado: o instalador tentava recriar três regras antigas do acervo que ele mesmo apaga logo depois, e que não cabem mais no jeito atual de guardar os materiais. Essas tentativas saíram, e nenhum dado foi apagado ou alterado.

A atualização também recriava, por um momento, 21 regras de acesso antigas que ela mesma apagava em seguida, e reinstalava outras 2 numa versão mais larga que a de hoje. Isso acabou. Algumas dessas regras eram mais largas que as atuais: no meio-tempo, um usuário só de leitura conseguia alterar dados que as regras de hoje protegem — medido num Postgres de verdade, com um `viewer` que hoje não altera, não apaga e não cria um lead, e que com a regra antiga fazia as três coisas. E se a atualização falhasse justo no comando que apaga a regra antiga, ela ficava valendo até a atualização seguinte.

O ruído escondia um problema de verdade. Com o CRM atendendo, o banco às vezes recusa um comando da atualização por disputa com o próprio app (`deadlock detected`), ou a conexão cai no meio. A atualização avisava e seguia, e o que não aplicou ficava para trás: numa instalação real, o acervo dos agentes ficou sem a regra que permite lê-lo. Agora a atualização aplica o banco de novo, em até três passadas no total, e mostra na tela o que precisou refazer. Se ainda assim o banco não terminar limpo, o **fim** da saída diz isso e explica o que fazer conforme a causa: repetir a atualização quando o banco estava ocupado, ou acertar a conexão do `.env` quando faltou permissão — repetir, nesse caso, não resolveria. Na atualização pelo botão da tela esse aviso ainda não aparece: ele fica registrado em `.update.log`, na pasta do projeto no servidor.

A nova tentativa vale a partir da atualização seguinte a esta, porque quem executa uma atualização é o instalador que já está no servidor. Os avisos falsos e as regras de acesso antigas saem já nesta.
