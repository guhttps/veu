# @guhttps/n8n-nodes-veu

**Véu para o n8n.** Esconde dados pessoais e segredos (CPF, nomes, telefones, e-mails, cartões, chaves de API) antes de o texto ir para a IA e devolve os dados reais na resposta. Ideal para atendimento por WhatsApp com IA sem expor os dados do cliente.

```
Cliente escreve:   "Oi, sou a Maria Souza, CPF 529.982.247-25, quero a segunda via"
A IA recebe:       "Oi, sou a [PESSOA_1], CPF [CPF_1], quero a segunda via"
A IA responde:     "Olá [PESSOA_1], a segunda via do CPF [CPF_1] foi enviada"
O cliente recebe:  "Olá Maria Souza, a segunda via do CPF 529.982.247-25 foi enviada"
```

## Instalar

No n8n, abra **Configurações > Nós da comunidade > Instalar** e digite `@guhttps/n8n-nodes-veu`. O nó não tem dependências: a detecção roda dentro do próprio n8n, sem chamar nenhum serviço.

## Usar

O nó **Véu** tem duas operações:

- **Esconder dados:** recebe um texto e devolve `textoProtegido` (com marcadores, como `[CPF_1]`), `encontrados` (quantos dados de cada tipo) e `cofre`. Mande para a IA só o `textoProtegido`.
- **Restaurar dados:** recebe a resposta da IA e o `cofre` do passo anterior (por exemplo, `{{ $('Véu: esconder').item.json.cofre }}`) e devolve `textoRestaurado`.

Opções de "Esconder dados":

| Opção | Efeito |
|---|---|
| Como esconder | Marcadores (`[CPF_1]`, dá para restaurar), máscara (`***.982.247-**`) ou remover (`[CPF]`) |
| Recusar se tiver | Tipos que fazem o item dar erro em vez de seguir (padrão: `CHAVE_PRIVADA`) |
| Nunca esconder | Valores da sua empresa que nunca são escondidos (e-mail de contato, CNPJ) |
| Campo de saída | Nome do campo com o texto protegido (padrão: `textoProtegido`) |

O **cofre tem os dados reais**: passe-o só para o nó "Restaurar dados", nunca para a IA. Ele fica nos dados da execução do n8n, como o texto original já ficaria.

## Modelo: WhatsApp com IA (Evolution API)

Importe [`modelos/whatsapp-evolution.json`](modelos/whatsapp-evolution.json) em **Fluxos > Importar do arquivo**. Ele recebe a mensagem pelo webhook da Evolution API, esconde os dados, pergunta à OpenAI, restaura a resposta e responde no WhatsApp. Configure a credencial da OpenAI e as variáveis `EVOLUTION_URL`, `EVOLUTION_INSTANCIA` e `EVOLUTION_APIKEY`.

## O que é detectado

Os mesmos dados da [biblioteca do Véu](https://github.com/guhttps/veu#o-que-é-detectado): nomes, CPF, CNPJ, RG, CNH, telefones, e-mails, endereços, cartões, contas, chave Pix, chaves de API, senhas e documentos de mais 21 países. Nenhuma detecção automática é perfeita: veja o [benchmark](https://github.com/guhttps/veu#benchmark).

## In English

**Véu for n8n** hides personal data and secrets (names, ID numbers, phone numbers, e-mails, cards, API keys) before text goes to an AI model, and puts the real data back in the answer. It is built for AI customer support over WhatsApp without exposing customer data. The node has no runtime dependencies: detection runs inside n8n and calls no external service.

**Install:** in n8n, open **Settings > Community nodes > Install** and enter `@guhttps/n8n-nodes-veu`.

**Operations** (the node's interface is in Portuguese):

- **Esconder dados** (hide data): takes a text and returns `textoProtegido` (with markers such as `[CPF_1]`), `encontrados` (counts per type) and `cofre` (the vault). Send only `textoProtegido` to the AI.
- **Restaurar dados** (restore data): takes the AI's answer and the `cofre` from the previous step (for example `{{ $('Véu: esconder').item.json.cofre }}`) and returns `textoRestaurado`.

Options of "Esconder dados": *Como esconder* (reversible markers, a mask such as `***.982.247-**`, or removal), *Recusar se tiver* (types that make the item fail instead of continuing; default `CHAVE_PRIVADA`), *Nunca esconder* (your company's own values that are never hidden) and *Campo de saída* (the output field name).

**The vault holds the real data:** pass it only to "Restaurar dados", never to the AI. It stays in n8n's execution data, as the original text would.

**Template:** import [`modelos/whatsapp-evolution.json`](modelos/whatsapp-evolution.json) (WhatsApp through the Evolution API, with OpenAI). Set the OpenAI credential and the `EVOLUTION_URL`, `EVOLUTION_INSTANCIA` and `EVOLUTION_APIKEY` variables.

**Detection:** the same as the [Véu library](https://github.com/guhttps/veu/blob/main/README.en.md): names, Brazilian documents validated by check digits, phones, e-mails, addresses, cards, bank accounts, API keys, passwords and documents from 21 other countries. No automatic detection is perfect.

MIT license. Repositório / repository: https://github.com/guhttps/veu
