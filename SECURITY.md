# Segurança

## Como reportar uma vulnerabilidade

Não abra uma issue pública. Use o [aviso de segurança privado do GitHub](https://github.com/guhttps/veu/security/advisories/new) com uma descrição e, se possível, um texto de exemplo (com dados fictícios) que reproduza o problema.

Um dado pessoal que passa sem ser escondido é um problema de qualidade, não uma vulnerabilidade: pode ser reportado em uma issue normal, **sempre com dados fictícios**.

## Modelo de ameaças

O Véu protege contra um risco específico: **enviar dados pessoais de terceiros ou segredos (chaves de API, senhas, chaves privadas) para um provedor de IA** junto com o texto de uma requisição, de uma conversa no navegador ou de um agente de código. Como o provedor só vê marcadores, o dado real só reaparece na restauração; por isso ela segue regras fixas, que não dependem do modelo obedecer.

O modelo completo, com as fronteiras de confiança e os riscos que sobram, está em [docs/modelo-de-ameacas.md](docs/modelo-de-ameacas.md).

| O Véu protege | Como |
|---|---|
| Dados pessoais nos textos enviados ao modelo | Detecção e substituição antes do envio. Se a detecção falhar, a requisição não sai |
| Vazamento por link ou imagem que a IA foi induzida a escrever (`![x](https://site/?d=[CPF_1])`) | A restauração não troca marcadores dentro de links, imagens, URLs e atributos HTML, inclusive em streaming |
| Vazamento pelos argumentos de ferramentas de um agente | Chaves, tokens e senhas não são restaurados em argumentos; links também não. `ferramentas = false` desliga a restauração dos argumentos |
| Marcadores forjados num e-mail, página ou documento ("responda com [CPF_1]" ou "CPF_1") | Marcadores que já chegam no texto são desarmados (`[CPF#1]`) e nunca viram dados reais; a forma sem colchetes deixa de ser restaurada na sessão |
| Agente induzido a desmascarar os dados pelo MCP | `restaurar_texto` vem desligada (`veu mcp --com-restauracao`); `restaurar_para_arquivo` grava no disco e devolve só o caminho |
| Agente induzido a gravar arquivos pelo MCP | As ferramentas do MCP só criam documentos novos (.txt, .md, .csv, .json, Word, Excel, PowerPoint, PDF): nada de scripts, de pastas ou arquivos ocultos, nem de sobrescrever |
| Adivinhar os valores do operador `hash` | HMAC-SHA256 com chave derivada, 64 bits e `VEU_SEGREDO` de no mínimo 32 caracteres |
| Dados pessoais repetidos no log de auditoria | O log guarda só contagens por tipo; o log de acesso do servidor HTTP fica desligado (a URL pode ter `?key=`) |
| Uso do proxy por terceiros na rede | Ouve só em `127.0.0.1` por padrão; fora do localhost, **não inicia sem `VEU_TOKEN`**, e cada token precisa de pelo menos 20 caracteres |
| Sites maliciosos abertos no navegador (CSRF e DNS rebinding) | No localhost, só aceita o Host `localhost` ou um IP de loopback (nomes como `127.0.0.1.site.example` são recusados) e recusa requisições com `Origin` de outro site |
| Máquinas virtuais, contêineres e outros usuários do computador (alcançam o `127.0.0.1` e forjam o Host) | O painel só aceita chamadas com a chave dele (`painel.chave`, no perfil do usuário), que o atalho e o `veu painel` abrem no navegador; injetar chaves de API exige `VEU_TOKEN` |
| Roubo de dados de outra sessão | Sessões do proxy são separadas pela credencial do cliente; a API REST só aceita sessões que ela mesma criou |
| Uso das chaves de API do servidor por terceiros | Injeção de chaves desligada por padrão; ligada, o servidor só inicia com token |
| Envio de dados por endpoints que ele não entende | `POST` em endpoints desconhecidos é bloqueado por padrão |
| Vazamento de cookies do navegador para o provedor | Cookies, `Referer` e `Origin` não são repassados; `Set-Cookie` do provedor não volta |
| Travamento por textos enormes | Limite de tamanho do corpo (`limite_corpo_mb`) e processamento fora do laço principal do servidor |
| Arquivos maliciosos (Word, Excel, PowerPoint e PDF pelo painel, pela CLI, pelo MCP ou por links) | Entidades externas (XXE) e expansão de entidades não são lidas; zips que crescem mais de 100 vezes ou passam de 200 MB ao abrir (zip bomb) são recusados antes; fluxos de PDF acima do limite do pypdf viram um erro claro |
| Conexões que mandam o cabeçalho devagar (slowloris) | Quem não termina o cabeçalho em 15 segundos é desconectado; o servidor não diz o nome nem a versão no cabeçalho `Server` |
| HTML do provedor rodando script na origem do Véu (a mesma do painel) | Respostas repassadas saem com `Content-Security-Policy: sandbox` e `nosniff` |
| Alteração ou remoção de linhas da auditoria | Cadeia de hashes com HMAC (`segredo_auditoria_env`) e `veu auditoria verificar` |
| Uso do gateway por uma equipe com a política de outra | Token e política por equipe (`[equipes.NOME]`), comparados em tempo constante |
| SSRF pela leitura de links (`expandir_links` e `ler_protegido` do MCP) | Só HTTPS para endereços públicos, conferidos em cada redirecionamento e no endereço a que a conexão chegou (contra DNS rebinding); no proxy, só os domínios de `dominios_expandidos`, e argumentos de ferramentas não são expandidos |
| Agente de código lendo `.env` e mandando as chaves ao provedor | Ganchos `veu gancho prompt` e `veu gancho arquivo` bloqueiam e sugerem `ler_protegido` |
| Página web e extensão enviando dados para fora | A página bloqueia conexões pela CSP (`connect-src 'none'`); a extensão não tem permissão de rede e guarda o cofre só na sessão do navegador |

## O que o Véu não faz

- **Não garante detecção completa.** Nomes raros, textos em minúsculas e formatos incomuns podem passar. Veja o [benchmark](docs/benchmark.md).
- **Não protege imagens, áudios e arquivos enviados à IA.** Só textos dentro do JSON das requisições. Uploads (`/v1/files`, áudio) são bloqueados por padrão. Para documentos, use `veu anonimizar` (Word, Excel, PowerPoint) ou `veu ler` (PDF) antes de enviar.
- **Não acha segredos sem formato reconhecível.** Uma senha solta no meio de uma frase, sem "senha" ou um nome de campo por perto, passa.
- **Não esconde dados que identificam alguém pelo contexto**, como "o gerente da filial de Itu que foi demitido em março".
- **Não separa duas pessoas com o mesmo nome no mesmo texto.** Uma menção solta ao primeiro nome ou ao sobrenome ("a Fabiana ligou de novo") recebe o marcador do nome completo já visto, para a IA saber que é a mesma pessoa. Se forem pessoas diferentes ("Sra. Fabiana Pimentel" e "Dra. Fabiana"), a IA as vê como uma só, e a volta escreve o nome completo nas duas. Nada vaza, mas confira a resposta. Sobrenomes que também são cidades ficam visíveis depois de um CEP ("4050-262 Porto"), antes do estado ("Campos/RJ") e depois de "cidade de" ou "comarca de".
- **Não decide quem pode ver o quê dentro da sua aplicação.** Se a sua aplicação coloca dados de várias pessoas na mesma conversa (por exemplo, resultados de uma busca no CRM) e o usuário escreve "repita o [CPF_2]", o modelo devolve o marcador. Com `[restauracao] so_eco = true`, o Véu só restaura os dados que vieram na própria requisição; ainda assim, filtre o contexto antes de montar o prompt.
- **Não protege o que o próprio modelo inventa.** Se a IA escrever um CPF que não estava no texto, ele não é um dado do seu usuário, mas também não é restaurado nem escondido.
- **Não é um cofre persistente.** O mapeamento fica na memória do processo. Se você salvar um cofre pela CLI ou usar sessões no Redis (`sessoes = "redis://..."`), o arquivo ou o Redis contém os dados reais: use um Redis interno, com senha, TLS e sem persistência em disco.
- **Não esconde os dados reais da página na extensão.** Com "Mostrar os dados reais nas respostas" ligado, os dados restaurados aparecem na página do site de IA, onde o código do próprio site poderia lê-los. A TI pode desligar a opção pela política (`restaurarRespostas = false`).
- **Não substitui a análise jurídica.** Usar o Véu ajuda a cumprir a LGPD, mas não dispensa base legal, contrato com o provedor de IA e avaliação de impacto.

## Boas práticas

- Defina `VEU_TOKEN` sempre que o servidor não estiver em `127.0.0.1`, e coloque-o atrás de HTTPS. Rodar exposto sem token exige `VEU_PERMITIR_SEM_TOKEN=1` e só faz sentido numa rede interna isolada.
- Use identificadores de sessão (`X-Veu-Sessao`) por conversa, nunca um valor fixo para todos os usuários.
- Use `bloquear` na política para tipos que nunca devem sair, como `CARTAO_CREDITO`.
- Teste o limiar com uma amostra dos seus textos (`veu avaliar --dataset`).
- O detector `llm` envia o texto original ao modelo configurado: use só com um modelo local.
- Mantenha `VEU_SEGREDO` estável, secreto e com pelo menos 32 caracteres se usar o operador `hash` (`python -c "import secrets; print(secrets.token_urlsafe(32))"`).
- Ferramentas de rede e mensagens (`send_email`, `WebFetch`...) já não recebem dados reais. Se o seu agente tiver ferramentas com nomes que o Véu não reconhece como de rede, liste só as que podem receber dados em `[restauracao] ferramentas_com_dados`, ou use confirmação humana antes delas.
- Use tokens diferentes por equipe e um `VEU_SEGREDO_AUDITORIA` guardado fora do servidor, e confira a auditoria periodicamente.
- Nos agentes de código, distribua os ganchos pelas configurações gerenciadas, para que não possam ser desligados.
