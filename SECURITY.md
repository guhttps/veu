# Segurança

## Como reportar uma vulnerabilidade

Não abra uma issue pública. Use o [aviso de segurança privado do GitHub](https://github.com/guhttps/veu/security/advisories/new) com uma descrição e, se possível, um texto de exemplo (com dados fictícios) que reproduza o problema.

Um dado pessoal que passa sem ser escondido é um problema de qualidade, não uma vulnerabilidade: pode ser reportado em uma issue normal, **sempre com dados fictícios**.

## Modelo de ameaças

O Véu protege contra um risco específico: **enviar dados pessoais de terceiros para um provedor de IA** junto com o texto de uma requisição.

| O Véu protege | Como |
|---|---|
| Dados pessoais nos textos enviados ao modelo | Detecção e substituição antes do envio |
| Dados pessoais repetidos no log de auditoria | O log guarda só contagens por tipo |
| Uso do proxy por terceiros na rede | Ouve só em `127.0.0.1` por padrão; `VEU_TOKEN` para expor |
| Uso das chaves de API do servidor por terceiros | Injeção de chaves desligada por padrão |
| Envio de dados por endpoints que ele não entende | `POST` em endpoints desconhecidos é bloqueado por padrão |

## O que o Véu não faz

- **Não garante detecção completa.** Nomes raros, textos em minúsculas e formatos incomuns podem passar. Veja o [benchmark](docs/benchmark.md).
- **Não protege imagens, áudios, PDFs e arquivos.** Só textos dentro do JSON das requisições. Uploads (`/v1/files`, áudio) são bloqueados por padrão.
- **Não esconde dados que identificam alguém pelo contexto**, como "o gerente da filial de Itu que foi demitido em março".
- **Não protege o que o próprio modelo inventa.** Se a IA escrever um CPF que não estava no texto, ele não é um dado do seu usuário, mas também não é restaurado nem escondido.
- **Não é um cofre persistente.** O mapeamento fica na memória do processo. Se você salvar um cofre pela CLI, o arquivo contém os dados reais.
- **Não substitui a análise jurídica.** Usar o Véu ajuda a cumprir a LGPD, mas não dispensa base legal, contrato com o provedor de IA e avaliação de impacto.

## Boas práticas

- Defina `VEU_TOKEN` sempre que o servidor não estiver em `127.0.0.1`, e coloque-o atrás de HTTPS.
- Use `bloquear` na política para tipos que nunca devem sair, como `CARTAO_CREDITO`.
- Teste o limiar com uma amostra dos seus textos (`veu avaliar --dataset`).
- O detector `llm` envia o texto original ao modelo configurado: use só com um modelo local.
- Mantenha `VEU_SEGREDO` estável e secreto se usar o operador `hash`.
