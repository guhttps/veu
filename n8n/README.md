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

Os mesmos dados da [biblioteca do Véu](https://github.com/guhttps/veu#o-que-é-detectado): nomes, CPF, CNPJ, RG, CNH, telefones, e-mails, endereços, cartões, contas, chave Pix, chaves de API, senhas e documentos de Portugal e da América Latina. Nenhuma detecção automática é perfeita: veja o [benchmark](https://github.com/guhttps/veu#benchmark).

Licença MIT. Repositório: https://github.com/guhttps/veu
