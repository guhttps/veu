# Publicar a extensão nas lojas

Tudo o que as lojas do Edge e do Firefox pedem, pronto para copiar. Os pacotes ficam na página de cada versão: https://github.com/guhttps/veu/releases (`veu-extensao-<versão>.zip` para o Edge e `veu-extensao-firefox-<versão>.zip` para o Firefox).

## Links

| Campo | Valor |
|---|---|
| Site | https://guhttps.github.io/veu/ |
| Política de privacidade | https://guhttps.github.io/veu/privacidade.html |
| Suporte | https://github.com/guhttps/veu/issues |
| Código-fonte | https://github.com/guhttps/veu |
| Categoria | Produtividade (Productivity) |

## Capturas de tela

`capturas/1-aviso.png`, `capturas/2-protegido.png` e `capturas/3-caixinhas.png` (1280×800). Para gerar de novo: `python scripts/empacotar_navegador.py` e `node scripts/capturas_loja.mjs`.

## Textos em português

**Nome:** Véu: proteção de dados para IA

**Resumo:** Esconde CPF, nomes, telefones, chaves de API e senhas antes de você enviar ao ChatGPT, Claude, Gemini e outras IAs.

**Descrição:**

> O Véu protege os dados pessoais e os segredos que você cola nos sites de IA. Antes de enviar, ele troca nomes, CPF, CNPJ, telefones, e-mails, cartões, chaves de API e senhas por marcadores como [PESSOA_1] e [CPF_1]. A IA trabalha normalmente com os marcadores, e você vê os dados reais de volta.
>
> Tudo roda no seu navegador: a extensão não faz conexões de rede, não coleta nada e não tem conta nem anúncios.
>
> - Três modos: avisar (mostra um aviso e você decide), proteger (troca os dados antes de enviar) e bloquear (só envia depois de proteger).
> - Você escolhe o que esconder: nomes e contatos, documentos do Brasil e de mais 21 países, dados financeiros, senhas e chaves, IPs e servidores internos, veículos.
> - Documentos conferidos pelo dígito verificador: um número qualquer não vira CPF.
> - Funciona no ChatGPT, Claude, Gemini, Copilot, Perplexity, DeepSeek, Mistral, Grok, Meta AI, Poe, Qwen, Kimi e Maritaca.
> - Empresas podem instalar e configurar pela política do navegador, com uma mensagem de orientação própria.
>
> Código aberto (MIT): https://github.com/guhttps/veu

## Textos em inglês

**Name:** Véu: data protection for AI

**Summary:** Hides names, ID numbers, phone numbers, API keys and passwords before you send text to ChatGPT, Claude, Gemini and other AIs.

**Description:**

> Véu protects the personal data and secrets you paste into AI websites. Before sending, it replaces names, ID numbers (Brazilian CPF and CNPJ, US SSN and documents from 20 other countries), phone numbers, e-mails, cards, API keys and passwords with markers such as [PESSOA_1] and [CPF_1]. The AI works normally with the markers, and you get the real data back.
>
> Everything runs in your browser: the extension makes no network connections, collects nothing, and has no account or ads.
>
> - Three modes: warn (you decide), protect (replaces the data before sending) and block (sends only after protecting).
> - You choose what to hide: names and contacts, documents, financial data, passwords and keys, IP addresses and internal servers, vehicles.
> - Documents are validated by their check digits, so a random number is not mistaken for an ID.
> - Works on ChatGPT, Claude, Gemini, Copilot, Perplexity, DeepSeek, Mistral, Grok, Meta AI, Poe, Qwen, Kimi and Maritaca.
> - Companies can deploy and configure it through browser policy, with their own guidance message.
>
> Open source (MIT): https://github.com/guhttps/veu

## Por que cada permissão (as lojas perguntam)

| Permissão | Justificativa (pode colar) |
|---|---|
| `storage` | Guarda, só no navegador, a ligação entre cada marcador e o dado real da aba (apagada ao fechar a aba) e as preferências da pessoa. |
| `contextMenus` | Itens do menu do botão direito: proteger o texto selecionado e copiar a seleção com os dados reais. |
| `activeTab` e `scripting` | Agir sobre o texto selecionado na aba atual, só quando a pessoa usa o menu do botão direito. |
| Acesso aos sites de IA | Ler o texto que a pessoa cola ou digita no campo de mensagem desses sites, para esconder os dados antes do envio. |

**Coleta de dados:** nenhuma. A extensão não transmite dados a ninguém. No Firefox, o próprio pacote declara isso (`data_collection_permissions: none`).

## Código-fonte para a Mozilla

O arquivo `veu.global.js` é gerado (a biblioteca JavaScript do Véu, empacotada com o esbuild), então a Mozilla pede o código-fonte. Envie o zip do código da mesma versão, que o GitHub gera sozinho: `https://github.com/guhttps/veu/archive/refs/tags/v<versão>.zip`. No campo de instruções, cole:

> Requirements: Node.js 22 or later and Python 3.11 or later.
>
> 1. Unzip the source and open a terminal in its folder.
> 2. `cd js && npm ci && npm run build && cd ..` (builds js/dist/veu.global.js with esbuild).
> 3. `python scripts/empacotar_navegador.py` (copies the bundle into the extension and creates dist/veu-extensao-firefox-<version>.zip).
>
> The zip in dist/ is identical to the submitted package. All other extension files (manifest.json, conteudo.js, fundo.js, popup.html, popup.js, popup.css, politica.json, icons) are the original, unprocessed sources in the extensao/ folder.
