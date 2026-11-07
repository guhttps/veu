# Changelog

Todas as mudanças relevantes ficam registradas aqui.
O formato segue o [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e o projeto usa [versionamento semântico](https://semver.org/lang/pt-BR/).

## [Unreleased]

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

[Unreleased]: https://github.com/guhttps/veu/compare/v0.5.1...HEAD
[0.5.1]: https://github.com/guhttps/veu/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/guhttps/veu/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/guhttps/veu/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/guhttps/veu/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/guhttps/veu/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/guhttps/veu/releases/tag/v0.1.0
