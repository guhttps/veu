# Servidor de licenças do Véu Pro

Um servidor pequeno, na Cloudflare Workers (plano gratuito), que entrega e renova as chaves do Véu Pro. Ele não tem banco de dados e nunca recebe textos:

- **Depois do pagamento**, o Mercado Pago manda a pessoa para `/pronto`. O servidor confere a assinatura no Mercado Pago, assina a chave (Ed25519) e mostra a chave na tela.
- **Na renovação**, a extensão manda só a própria chave para `/renovar`. O servidor pergunta ao Mercado Pago se a assinatura continua ativa e devolve uma chave nova.
- **Na extensão**, a chave é conferida sem internet, com a chave pública que fica em `extensao/licenca.js`. Sem a chave privada, ninguém fabrica uma licença.

Arquivos:

| Arquivo | Para quê |
|---|---|
| `worker.js` | O servidor. |
| `worker.test.mjs` | Os testes, com um Mercado Pago falso: `node --test nuvem/`. |
| `gerar-chaves.mjs` | Cria o par de chaves, uma vez só. |
| `criar-planos.mjs` | Cria os planos mensal e anual no Mercado Pago. |
| `emitir-licenca.mjs` | Emite uma licença à mão (plano Empresa, cortesia, teste). |
| `wrangler.toml` | Configuração da Cloudflare (sem segredos). |

## Colocar no ar (uma vez)

Os segredos (a chave privada e o access token do Mercado Pago) vão direto do seu computador para a Cloudflare. Nunca cole nenhum deles numa conversa, num commit ou num e-mail.

1. **Conta na Cloudflare:** crie uma conta gratuita em [dash.cloudflare.com](https://dash.cloudflare.com/sign-up). Depois, num terminal na pasta do projeto:
   ```
   cd nuvem
   npx wrangler login
   ```
2. **Chaves das licenças:** na pasta do projeto, rode `node nuvem/gerar-chaves.mjs`. A chave privada fica em `C:\Users\<você>\.veu-licencas\chave-privada.txt`, e a pública entra sozinha na extensão e no `wrangler.toml`.
3. **Publicar o servidor:** dentro de `nuvem`, rode `npx wrangler deploy`. O endereço aparece no fim, algo como `https://veu-licencas.<sua-conta>.workers.dev`. Ele não é segredo.
4. **Enviar a chave privada:** dentro de `nuvem`, rode `npx wrangler secret put CHAVE_PRIVADA < "$HOME\.veu-licencas\chave-privada.txt"` (no PowerShell: `Get-Content "$HOME\.veu-licencas\chave-privada.txt" | npx wrangler secret put CHAVE_PRIVADA`).
5. **Mercado Pago:** na sua conta pessoal, abra [Suas integrações](https://www.mercadopago.com.br/developers/panel/app), crie uma aplicação ("Assinaturas") e copie o **Access Token de produção**. Envie para a Cloudflare com `npx wrangler secret put MP_TOKEN` e cole o token quando o wrangler pedir.
6. **Planos:** no PowerShell, rode `$env:MP_TOKEN = "<o mesmo access token>"; node nuvem/criar-planos.mjs https://veu-licencas.<sua-conta>.workers.dev` e depois `npx wrangler deploy` de novo. O script mostra os links de assinar.
7. **Me avise** com o endereço do servidor e os dois links de assinar (nenhum deles é segredo). Eu termino o resto (lista abaixo) e lanço a versão.

## Antes de lançar (eu faço)

- Endereço do servidor em `SERVIDOR`, no `extensao/licenca.js`.
- Botões "Assinar" na página de planos, com os links do passo 6.
- Política de privacidade: no Pro, a extensão fala com o servidor de licenças só para renovar a chave, mandando a própria chave.
- Firefox: declarar em `data_collection_permissions` o dado que vai na chave (o e-mail), e atualizar as respostas de privacidade das lojas.
- Uma assinatura de teste de ponta a ponta, cancelada em seguida.
