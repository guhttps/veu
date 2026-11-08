# Véu e conformidade: LGPD, GDPR e normas setoriais

Para encarregados (DPOs), jurídico e segurança que avaliam o uso de IA com o Véu. **Não é parecer jurídico.** As normas foram conferidas em 07/11/2026; confira se mudaram antes de decidir.

## O que o Véu é, em termos da lei

| Modo | O que acontece | Na LGPD | No GDPR |
|---|---|---|---|
| **Marcadores reversíveis** (padrão: `[CPF_1]`) | O provedor de IA recebe marcadores; o Véu guarda os valores num cofre e devolve os dados reais na resposta | **Pseudonimização** (art. 13, § 4º): o dado continua pessoal, porque o cofre permite reverter. A restauração da resposta também é tratamento | Pseudonimização (art. 4º, item 5). Conta como medida de segurança (art. 32) e de proteção desde a concepção (art. 25) |
| **Perfil `anonimizacao`** (`[CPF]`, sem cofre) | Os valores são removidos e nada os guarda | Pode sustentar **dado anonimizado** (art. 12), desde que a pessoa não seja identificável pelo contexto com esforços razoáveis. Avalie o risco residual | Pode sair do escopo (considerando 26), com a mesma ressalva |
| **Máscara** (`***.982.247-**`) | Parte do valor fica visível | Pseudonimização, em geral: os dígitos que sobram ainda identificam | Pseudonimização |

O Véu **ajuda a cumprir** os princípios de necessidade e minimização (art. 6º, III) e o dever de segurança (art. 46). Ele **não** tira o controlador da LGPD, não substitui a base legal (arts. 7º e 11), o contrato com o provedor de IA nem a avaliação de impacto. O comando se chama `veu anonimizar` por costume, mas, com marcadores reversíveis, o resultado é pseudonimização.

## Controle a controle

| Exigência | O que o Véu oferece | O que continua com você |
|---|---|---|
| **LGPD, art. 6º, III** (necessidade) | Só marcadores saem para o provedor; `bloquear` recusa tipos que nunca devem sair | Decidir quais dados a tarefa precisa |
| **LGPD, art. 46** (segurança) | Detecção antes do envio, falha fechada, restauração que não devolve dados em links nem segredos em ferramentas, cofre cifrado no Redis ([modelo de ameaças](modelo-de-ameacas.md)) | Gestão de acessos, chaves e infraestrutura |
| **LGPD, art. 37** (registro das operações) | Auditoria encadeada, só com metadados, e `veu auditoria relatorio` (abaixo) | Manter o registro completo do tratamento |
| **LGPD, art. 38** (RIPD) | [Modelo de RIPD](modelo-ripd.md) para "uso de IA externa com o Véu" | Preencher, avaliar e aprovar |
| **LGPD, art. 33** (transferência internacional) | Reduz o volume e a identificabilidade do que vai a provedores no exterior; `desviar_para` manda textos com certos tipos a um modelo interno | O mecanismo de transferência (cláusulas-padrão da Resolução CD/ANPD nº 19/2024 ou adequação: Brasil e UE se reconheceram mutuamente em janeiro de 2026) |
| **ANPD, Nota Técnica nº 1/2026** (IA generativa) | A ANPD afirmou que a LGPD alcança prompts e saídas, não só o treinamento: é esse o tráfego que o Véu protege | — |
| **GDPR, art. 4º(5) e 32; EDPB, Guidelines 01/2025** (pseudonimização, em consulta) | Domínio de pseudonimização claro: o provedor não tem o cofre; HMAC com chave derivada no operador `hash`; segredo de 32+ caracteres obrigatório | Guardar as chaves (`VEU_SEGREDO`, `VEU_CHAVE_COFRE`) fora do alcance de quem recebe os dados |

Fontes: [LGPD (Planalto)](https://www.planalto.gov.br/ccivil_03/_ato2015-2018/2018/lei/l13709.htm), [Nota Técnica nº 1/2026 (IAPP)](https://iapp.org/news/a/ia-generativa-y-protecci-n-de-datos-en-brasil-posicionamiento-de-la-anpd-en-la-nota-t-cnica-n-1-2026), [adequação Brasil–UE (White & Case)](https://www.whitecase.com/insight-alert/mutual-adequacy-between-eu-and-brazil-new-era-transatlantic-data-transfers), [cláusulas-padrão (Lefosse)](https://lefosse.com/noticias/transferencia-internacional-de-dados-prazo-para-adocao-das-clausulas-padrao-da-anpd-se-encerra-em-23-de-agosto/).

## Perfis prontos por setor

```bash
veu perfis                                  # lista os perfis
veu servir --perfil judiciario              # ou VEU_PERFIL=judiciario, ou [politica] perfil = "judiciario"
```

Cada perfil só ajusta opções do Véu. Opções escritas no `veu.toml` valem mais que as do perfil.

| Perfil | Norma de referência | O que faz |
|---|---|---|
| `anonimizacao` | LGPD, art. 12 | Irreversível (`[CPF]`), sem cofre; segredos bloqueados |
| `judiciario` | CNJ, Resolução 615/2025, art. 19: dados sigilosos só vão a IA externa anonimizados ou com salvaguardas equivalentes, com registro de uso | Irreversível; segredos bloqueados. Ligue a auditoria |
| `juridico` | OAB, Recomendação 001/2024: sigilo profissional | Reversível (a peça volta com os nomes das partes); segredos bloqueados |
| `saude` | CFM, Resolução 2.454/2026: compartilhar com IA só o estritamente necessário | Reversível; segredos bloqueados; com `desviar_para`, textos com Cartão do SUS vão para o modelo interno |
| `financeiro` | Controles de terceiros e nuvem (CMN 5.274/2025); cartões fora do alcance de terceiros | Cartões, contas e IBAN removidos (irreversível); o resto, reversível; segredos bloqueados |
| `setor-publico` | Guia de IA generativa do TCU: só dados públicos em plataformas externas | Qualquer dado pessoal ou segredo faz a requisição ser recusada |

Fontes: [CNJ 615/2025 (resumo de escritório; o texto oficial estava inacessível)](https://www.barbieriadvogados.com/resolucao-cnj-615/), [CFM 2.454/2026 (Machado Meyer)](https://www.machadomeyer.com.br/pt/inteligencia-juridica/publicacoes-ij/life-sciences-e-saude/cfm-regulamenta-o-uso-de-inteligencia-artificial-na-medicina), [guia do TCU](https://portal.tcu.gov.br/publicacoes-institucionais/cartilha-manual-ou-tutorial/guia-de-uso-de-inteligencia-artificial-generativa-no-tribunal-de-contas-da-uniao-tcu), [CMN 5.274/2025 (Tenchi)](https://www.tenchisecurity.com/br/insights-news/resolucao-cmn-5-274-o-que-muda-na-gestao-de-terceiros-ate-marco-de-2026), [OAB, Recomendação 001/2024](https://www.oabsp.org.br/jornaldaadvocacia/24-11-27-1852-oab-divulga-recomendacoes-para-uso-da-inteligencia-artificial-ia-na-pratica-juridica).

Uma dúvida fica aberta no Judiciário: o art. 30 da Resolução 615 menciona pseudonimização "na origem", e o art. 19 fala em anonimização ou salvaguarda equivalente. Por isso o perfil `judiciario` usa o modo irreversível; se o seu tribunal aceitar pseudonimização com o cofre sob controle do órgão, `juridico` é a alternativa reversível.

## Registro das operações (art. 37)

O log de auditoria do proxy guarda uma linha por requisição, só com metadados: destino, tipos e quantidades de dados escondidos e restaurados, bloqueios e desvios. Nunca os valores. Dele sai o relatório:

```bash
veu auditoria relatorio auditoria.jsonl --de 2026-10-01 --ate 2026-10-31
veu auditoria relatorio auditoria.jsonl --formato json      # para planilhas e sistemas de GRC
```

O relatório confere a integridade da cadeia e mostra o período, as requisições (bloqueadas, desviadas, com erro), os destinos, as equipes e os tipos de dados, por quantidade. Para provar que linhas não foram apagadas, guarde âncoras fora do servidor (`veu auditoria ancorar`, veja o [guia para empresas](empresas.md)).

## Identificação pelo contexto

Esconder nomes e documentos não basta quando o texto diz "a gerente de 45 anos da filial de Itu, demitida em 12/03/2026". Duas ferramentas ajudam:

- **`veu risco arquivo.txt`** conta os dados diretos que sobraram e as pistas indiretas (datas, idades, cidades, cargos) e dá um nível de risco (baixo, médio ou alto). É uma heurística para orientar a revisão, não uma prova de anonimização.
- **Operador `generalizar`** (`--operador generalizar` ou `[anonimizacao] operador`): guarda só o que serve para análise e identifica menos, como o ano de nascimento, a região do CEP, o DDD e a rede do IP. O resto vira o tipo (`[PESSOA]`). Não é reversível.

## O que o Véu não garante

- **Detecção completa.** Ela é automática e pode deixar passar dados. O [benchmark](benchmark.md) mede quanto, com dados de terceiros.
- **Proteção contra identificação pelo contexto.** "O gerente da filial de Itu demitido em março" identifica alguém sem nenhum nome. Isso pesa sobretudo para o perfil `anonimizacao`.
- **Base legal, transparência e direitos dos titulares.** São obrigações do controlador, com ou sem o Véu.
