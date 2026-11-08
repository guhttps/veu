# Véu para empresas

Muitas empresas não permitem instalar proxies nos computadores. O Véu não precisa disso: ele pode ficar **no servidor, no gateway que a empresa já usa ou no navegador gerenciado pela TI**. Este guia mostra os quatro caminhos, do mais central ao mais leve.

| Caminho | Protege | Instala o quê, onde | Para quem |
|---|---|---|---|
| [**Gateway central**](#gateway-central) | Aplicações internas, automações, agentes, scripts | Um serviço no Kubernetes ou no Docker | Times que chamam APIs de IA |
| [**Guardrail do LiteLLM**](#litellm) | Tudo que já passa pelo LiteLLM | Uma linha no `config.yaml` do LiteLLM | Quem já centraliza as IAs no LiteLLM |
| [**Extensão gerenciada**](#extensão-gerenciada-pela-ti) | ChatGPT, Claude, Gemini e Copilot pelo site | A extensão, instalada pela política do Chrome ou do Edge | Todos os funcionários |
| [**Agentes de código**](#agentes-de-código) | Claude Code e Cursor | Ganchos nas configurações gerenciadas | Times de desenvolvimento |

Os caminhos se combinam. Em todos, a detecção roda dentro da empresa e o cofre com os dados reais nunca vai para o provedor de IA.

## Gateway central

As aplicações trocam só a URL base (de `https://api.openai.com/v1` para `http://veu.ia.svc:8787/v1`) e mandam o token da equipe no cabeçalho `X-Veu-Token`. As chaves dos provedores ficam só no gateway (`injetar_chaves = true`).

### Kubernetes (Helm)

```bash
kubectl create namespace ia
kubectl -n ia create secret generic veu \
  --from-literal=VEU_TOKEN="$(openssl rand -hex 32)" \
  --from-literal=VEU_TOKEN_JURIDICO="$(openssl rand -hex 32)" \
  --from-literal=VEU_SEGREDO_AUDITORIA="$(openssl rand -hex 32)" \
  --from-literal=VEU_CHAVE_COFRE="$(openssl rand -hex 32)" \
  --from-literal=OPENAI_API_KEY="..." \
  --from-literal=VEU_SESSOES="rediss://:senha@redis-veu:6379/0"
helm install veu deploy/helm/veu -n ia -f meus-valores.yaml
```

O chart ([`deploy/helm/veu`](../deploy/helm/veu)) já vem com:

- **Disponibilidade:** 2 réplicas, escalonamento automático (HPA) e PodDisruptionBudget.
- **Sondas:** de vida em `/veu/saude` e de prontidão em `/veu/pronto` (inclui o Redis).
- **Contêiner fechado:** sem root, sistema de arquivos só de leitura e sem capabilities.
- **NetworkPolicy:** a saída do pod vai só para DNS, HTTPS e o Redis.
- **Métricas:** ServiceMonitor opcional para o Prometheus.

A configuração do Véu fica em `config:` no `values.yaml` (é o `veu.toml`).

### Docker Compose

Para começar num servidor só:

```bash
cd deploy
cp .env.exemplo .env       # preencha
docker compose up -d --scale veu=2
```

Esse caminho usa o [`deploy/veu-empresa.toml`](../deploy/veu-empresa.toml) e um Redis com senha.

### Equipes

Cada equipe tem o próprio token e, se quiser, a própria política:

```toml
[equipes.atendimento]
token_env = "VEU_TOKEN_ATENDIMENTO"

[equipes.juridico]
token_env = "VEU_TOKEN_JURIDICO"
bloquear = ["CARTAO_CREDITO", "CHAVE_PRIVADA"]   # recusa em vez de esconder
operador = "sintetico"                          # valores falsos realistas no lugar de [CPF_1]
```

A auditoria e as métricas (`veu_requisicoes_por_equipe_total`) mostram a equipe. Um token desconhecido recebe 401.

### Auditoria à prova de adulteração

```toml
[servidor]
log_auditoria = "-"                              # saída padrão (coletor de logs); ou um arquivo
segredo_auditoria_env = "VEU_SEGREDO_AUDITORIA"
```

Cada linha da auditoria tem só contagens (nunca os valores), o hash da linha anterior e um HMAC próprio. Quem não tem o segredo não consegue alterar ou apagar linhas sem quebrar a cadeia:

```bash
veu auditoria verificar auditoria.jsonl --segredo-env VEU_SEGREDO_AUDITORIA
# Log íntegro: 18234 registros, cadeia completa.
```

A cadeia impede alterar ou apagar linhas do meio, mas quem controla o servidor ainda poderia apagar as últimas linhas. Para detectar isso, guarde de tempos em tempos uma **âncora** fora do servidor (um bilhete, um e-mail, um armazenamento imutável):

```bash
veu auditoria ancorar auditoria.jsonl --segredo-env VEU_SEGREDO_AUDITORIA
# {"arquivo": "auditoria.jsonl", "registros": 18234, "hash": "9f2c...", "quando": "2026-11-07T21:00:00+00:00"}
veu auditoria verificar auditoria.jsonl --segredo-env VEU_SEGREDO_AUDITORIA --ancora 9f2c...
```

Se a linha da âncora sumir, a verificação falha. Cada linha também registra quantos valores reais voltaram na resposta (`restaurados`, por tipo, sem os valores), e `[restauracao] max_por_resposta` limita esse número: uma IA manipulada que tenta despejar todos os dados de uma sessão para no limite.

Com várias réplicas, cada uma escreve a própria cadeia. Guarde os logs separados por pod ou use a saída padrão, que o coletor já separa.

### Várias réplicas (Redis)

Num servidor só, `veu servir --workers 4` abre quatro processos. Como cada processo tem a sua memória, mais de um processo exige sessões no Redis, e cada um escreve a própria cadeia de auditoria (`auditoria.<pid>.jsonl`). As estatísticas e métricas também são por processo.

Com `VEU_SESSOES=rediss://...`, as conversas com `X-Veu-Sessao` funcionam em qualquer réplica: o `[CPF_1]` criado numa delas é restaurado na outra. Uma trava por sessão impede que duas réplicas deem o mesmo marcador a valores diferentes.

O cofre tem os dados reais. Por isso, no Redis ele é **cifrado** (AES-256-GCM) com a chave de `VEU_CHAVE_COFRE`, que fica fora do Redis: quem copiar o banco não lê os dados, e um cofre não pode ser trocado de sessão. Sem a chave, o Véu não inicia com sessões no Redis (num Redis isolado e descartável, `permitir_cofre_sem_cifra = true` libera). Além disso:

- use um Redis interno, com senha e TLS;
- desligue a persistência em disco (`--save ""`);
- conte com a expiração: cada sessão some após `sessao_ttl` segundos sem uso.

### Desvio para um modelo interno

Para algumas áreas, nem o dado escondido deve sair. Com o desvio, uma requisição com certos tipos de dado vai **inteira** para um modelo interno (vLLM, Ollama, TGI), e as outras seguem para o provedor externo, protegidas:

```toml
[politica]
desviar_para = "interno"
modelo_desvio = "llama3.1:70b"
desviar_tipos = ["CPF", "CNPJ", "CARTAO_CREDITO"]   # vazio = qualquer dado pessoal

[provedores.interno]
tipo = "openai"
url = "http://vllm.interno:8000/v1"
chave_env = "CHAVE_INTERNA"   # opcional
```

A chave do cliente para o provedor externo nunca é repassada ao modelo interno. As requisições desviadas aparecem em `veu_requisicoes_desviadas_total` e na auditoria (`desviado_para`).

### Links do Notion e do Google

Com `expandir_links = true`, quando alguém manda o link de uma página do Notion ou de um Google Docs, o gateway lê a página com o token da empresa (`NOTION_TOKEN`, `GOOGLE_ACCESS_TOKEN`) e entrega o conteúdo já protegido ao modelo. Só os domínios de `dominios_expandidos` são lidos.

### O que o gateway não faz

- Não autentica usuários finais: o token identifica a equipe ou a aplicação. Coloque o Véu atrás do seu gateway de API ou da sua malha de serviços se precisar de SSO.
- Não protege o que não passa por ele. Para o uso pelo site do ChatGPT, use a [extensão](#extensão-gerenciada-pela-ti).

## LiteLLM

Se a empresa já usa o [LiteLLM Proxy](https://docs.litellm.ai/), instale o Véu no mesmo ambiente (`pip install "veu[litellm]"`) e acrescente ao `config.yaml`:

```yaml
guardrails:
  - guardrail_name: veu
    litellm_params:
      guardrail: veu.integrations.litellm.VeuGuardrail
      mode: [pre_call, post_call]
      default_on: true
      veu_config: /etc/veu/veu.toml      # opcional: tipos, operadores, bloqueios
```

O guardrail protege:

- o Chat Completions (inclusive streaming e argumentos de ferramentas);
- o Responses;
- os Embeddings;
- o Completions;
- o Messages da Anthropic.

Os tipos de `bloquear` no `veu.toml` fazem o LiteLLM responder 400. O cofre fica na memória do guardrail: os metadados da requisição, que o LiteLLM pode mandar para ferramentas de observabilidade, recebem só um identificador.

## Extensão gerenciada pela TI

A [extensão](extensao.md) protege o uso pelo site (ChatGPT, Claude, Gemini, Copilot, Perplexity e outros):

- avisa quando há dados pessoais;
- protege o que é colado;
- impede o envio de segredos.

A TI instala a extensão em todos os navegadores e trava a configuração.

### 1. Instalar à força

Enquanto a extensão não está na Chrome Web Store, hospede o pacote na intranet:

1. Gere o `.crx` e o arquivo de atualização a partir do `veu-extensao-<versão>.zip` da [release](https://github.com/guhttps/veu/releases). O Chrome faz isso em `chrome://extensions` > Empacotar extensão; guarde a chave `.pem` para as próximas versões.
2. Publique o `.crx` e um `update.xml` num servidor interno.
3. Adicione à política `ExtensionInstallForcelist` a linha `<id da extensão>;https://intranet.example/veu/update.xml`.

A política pode ser aplicada pelo Google Admin, pelo Intune, por GPO ou pelo registro. No Edge, a política tem o mesmo nome.

### 2. Configurar e travar

A extensão lê a política gerenciada (`3rdparty`) com o esquema de [`extensao/politica.json`](../extensao/politica.json):

| Chave | Valores | Efeito |
|---|---|---|
| `modo` | `avisar`, `proteger`, `bloquear` | `proteger` troca os dados antes de enviar; `bloquear` só deixa enviar depois de proteger |
| `bloquearTipos` | lista, ex.: `["CHAVE_PRIVADA", "CARTAO_CREDITO"]` | Esses tipos sempre impedem o envio |
| `tipos` | lista (vazio = todos) | Tipos detectados |
| `ignorar`, `ignorarPadroes` | listas | Dados da própria empresa que podem ir para a IA |
| `restaurarRespostas` | `true` ou `false` | Mostrar os dados reais nas respostas, só na tela do usuário |
| `travarConfiguracao` | `true` | O usuário não muda nada no ícone da extensão |
| `ativo` | `true` ou `false` | Liga ou desliga |

No Windows, por exemplo (Chrome; no Edge troque `Google\Chrome` por `Microsoft\Edge`):

```text
HKLM\Software\Policies\Google\Chrome\3rdparty\extensions\<id>\policy
    modo               REG_SZ     bloquear
    travarConfiguracao REG_DWORD  1
    bloquearTipos      REG_SZ     ["CHAVE_PRIVADA","CARTAO_CREDITO","CHAVE_API"]
```

No Google Admin, envie o JSON equivalente na configuração da extensão:

```json
{ "modo": { "Value": "bloquear" }, "travarConfiguracao": { "Value": true },
  "bloquearTipos": { "Value": ["CHAVE_PRIVADA", "CARTAO_CREDITO", "CHAVE_API"] } }
```

## Agentes de código

Para Claude Code, distribua os ganchos pelas configurações gerenciadas da empresa (`managed-settings.json`), que os desenvolvedores não conseguem desligar:

```json
{
  "hooks": {
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "veu gancho prompt" }] }],
    "PreToolUse": [{ "matcher": "Read", "hooks": [{ "type": "command", "command": "veu gancho arquivo --dados-pessoais negar" }] }]
  }
}
```

Com isso:

- prompts com chaves de API, senhas ou chaves privadas não são enviados;
- o agente não lê arquivos com segredos;
- o motivo do bloqueio sugere a ferramenta MCP `ler_protegido`, que entrega o conteúdo protegido.

Veja [Claude Code e Cursor](integracoes.md#claude-code-e-cursor).

## LGPD

O Véu ajuda a aplicar a **minimização** (art. 6º, III) e as **medidas de segurança** (art. 46) quando dados pessoais seriam enviados a provedores de IA. Ele também gera evidência auditável do que foi protegido. Mesmo assim:

- **Não é uma garantia:** a detecção automática deixa passar uma fração dos dados (veja o [benchmark](../README.md#benchmark)), e marcadores reversíveis são pseudonimização, não anonimização;
- **Não substitui contratos nem análise jurídica:** os contratos com os provedores, o registro das operações e a análise de base legal continuam necessários;
- **Teste antes de confiar:** use uma amostra dos seus próprios dados e acompanhe `veu demonstrar` e `veu avaliar`.

## Lista de implantação

- [ ] Escolher os caminhos (gateway, LiteLLM, extensão, agentes)
- [ ] Gerar tokens por equipe e o segredo da auditoria; guardar num cofre de segredos
- [ ] Definir `bloquear`, `ignorar` (dados da própria empresa) e o operador
- [ ] Redis interno com TLS, se houver mais de uma réplica
- [ ] Coletar e reter a auditoria; agendar `veu auditoria verificar`
- [ ] Painel com as métricas do Prometheus (`/veu/metricas`)
- [ ] Testar com amostras reais e rodar `veu demonstrar` para o time de segurança
