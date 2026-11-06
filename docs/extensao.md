# Extensão do Véu para Chrome e Edge

A extensão protege seus dados quando você usa IA pelo site, sem instalar nada além dela:

- **Ao colar:** um texto com CPF, nome, telefone, chave de API ou senha entra no campo já com os dados trocados por marcadores, como `[CPF_1]`.
- **Ao enviar:** a extensão avisa, troca os dados ou bloqueia o envio, conforme o modo.
- **Nas respostas:** os marcadores viram os dados reais de novo, só na sua tela.

Tudo roda no seu navegador. A extensão não envia nada para servidor nenhum.

Funciona em: ChatGPT, Claude, Gemini, AI Studio, NotebookLM, Copilot (inclusive o do Microsoft 365), Perplexity, DeepSeek, Mistral, Grok, Meta AI, Poe, HuggingChat, Qwen, Kimi e Maritaca. Em outros sites, use o menu do botão direito.

## Instalar

1. Baixe o `veu-extensao-<versão>.zip` da [página de releases](https://github.com/guhttps/veu/releases) e descompacte.
2. Abra `chrome://extensions` (ou `edge://extensions`) e ligue o **Modo do desenvolvedor**.
3. Clique em **Carregar sem compactação** e escolha a pasta descompactada.
4. Fixe o ícone do Véu na barra.

Na sua empresa, a TI pode instalar e configurar a extensão para todos: veja o [guia para empresas](empresas.md#extensão-gerenciada-pela-ti).

## Modos

Escolha no ícone da extensão:

| Modo | Ao colar | Ao enviar |
|---|---|---|
| **Avisar** (padrão) | Cola normalmente e mostra um aviso com o botão **Proteger** | Mostra o aviso; você decide |
| **Proteger** | Já cola com os dados trocados | Troca os dados e pede que você confira e envie de novo |
| **Bloquear** | Já cola com os dados trocados | Só envia depois que os dados forem protegidos |

Chaves privadas e outros tipos que a sua empresa bloquear nunca são enviados, em nenhum modo.

## Usar

- **Restaurar um texto copiado:** o botão "copiar" dos sites copia a versão com marcadores. Cole no campo **Restaurar um texto** do ícone do Véu e clique em **Copiar com os dados reais**. Selecionar o texto na tela e copiar com Ctrl+C já traz os dados reais.
- **Proteger num site qualquer:** selecione o texto num campo de qualquer site, clique com o botão direito e escolha **Véu: proteger o texto selecionado**.
- **Ver o que foi protegido:** o número no ícone mostra quantos dados foram protegidos na aba, e o ícone lista os tipos.

## Limites

- **Detecção:** é automática e pode deixar passar algum dado. Confira antes de enviar.
- **Arquivos anexados:** não são protegidos. Use a [página do Véu](https://guhttps.github.io/veu/) ou `veu anonimizar` antes de anexar.
- **Dados na tela:** com **Mostrar os dados reais nas respostas** ligado, os dados reais aparecem na página. Em tese, o código do site poderia lê-los na tela. Se isso for um problema, desligue a opção e use o campo **Restaurar um texto**.
- **Duração do cofre:** a correspondência entre marcadores e dados vale enquanto a aba e o navegador estiverem abertos.
