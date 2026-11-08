# Metodologia do benchmark

```bash
veu avaliar --quantidade 1000           # conjuntos próprios: tabelas por tipo de dado
veu avaliar --externo todos             # conjuntos públicos de terceiros (baixados uma vez)
veu avaliar --json                      # números em JSON
veu gerar-dataset -o dados.jsonl        # exporta os textos anotados
veu avaliar --dataset dados.jsonl       # avalia um conjunto seu, no mesmo formato
```

## Conjuntos

| Conjunto | Origem | Para que serve |
|---|---|---|
| **Desenvolvimento** | 40 modelos de texto em 14 categorias, preenchidos com dados falsos (`semente=42`) | Foi usado para ajustar o detector. Mostra o teto, não a realidade. |
| **Validação** | 20 modelos escritos **depois** do ajuste e nunca usados para ajustá-lo (`semente=43`) | Mede como o detector lida com textos novos do mesmo gerador. |
| **Difíceis** | 25 casos escritos à mão em [`bench/hard.py`](../src/veu/bench/hard.py) | Gírias, maiúsculas, nomes raros, CPF com dígito errado, textos sem dados que parecem ter. |
| **Desafio** | 41 textos escritos à mão em 07/11/2026 e **congelados** ([`bench/desafio.py`](../src/veu/bench/desafio.py)) | Generalização: conversas informais, nomes de outras origens, formatos incomuns, endereços de Brasília e de conjuntos. Um teste confere o sha256: casos novos vão para um conjunto novo. |
| **BR-Agentic** | [BR-Agentic-PII-Benchmark](https://huggingface.co/datasets/guardion/BR-Agentic-PII-Benchmark) (Guardion, MIT): 41 conversas bancárias com chamadas de ferramenta | Teste externo: textos, argumentos e resultados de ferramentas escritos por outra equipe. |
| **privacy-filter-br** | Holdout v8.1 do [privacy-filter-br](https://huggingface.co/datasets/lucianfialho/privacy-filter-br-dataset) (Lucian Fialho, Apache-2.0): 17.072 documentos | Teste externo: boletos, contratos, certidões, folhas de pagamento. |

Os conjuntos externos são baixados uma vez, numa versão fixa conferida pelo sha256, para a pasta de cache do Véu. **O ajuste dos detectores nunca olha para o desafio nem para os dois conjuntos externos.** Para investigar erros, existe a parte de treino do privacy-filter-br (`--externo privacy-filter-br-treino`), que não entra nos resultados.

Todos os valores são fictícios: os conjuntos próprios usam dados gerados pelo Véu, e os externos declaram ser sintéticos.

## Métricas

- **Precisão:** das detecções, quantas eram mesmo daquele tipo. Só aparece nos conjuntos próprios: as anotações externas não cobrem tudo o que o Véu esconde (um CEP dentro do endereço, por exemplo), então a precisão por tipo não seria justa.
- **Revocação:** dos dados de um tipo, quantos foram detectados com o tipo certo (basta sobrepor o trecho).
- **Vazamento:** a fração das menções em que **algum caractere alfanumérico** ficou de fora do que foi escondido, qualquer que seja o tipo dado. Esconder "Maria" e deixar "Souza" conta como vazamento. É a métrica principal.
- **IC 95%:** intervalo de confiança do vazamento, por bootstrap sobre os textos (1.000 reamostragens, semente fixa). Com poucos textos, o intervalo fica largo: leia os dois números juntos.
- **Fora do escopo:** tipos anotados nos conjuntos externos que o Véu não esconde (valores em reais, números de pedido, datas quaisquer, URLs). Aparecem listados, mas não entram no vazamento.

## Resultados com dados de terceiros

| Conjunto | Véu | Véu + spaCy | Presidio |
|---|---:|---:|---:|
| Desafio (50 menções) | **22,0%** (10,7% a 35,4%) | 14,0% (5,3% a 25,0%) | 50,0% (34,6% a 65,3%) |
| BR-Agentic (622 menções) | **22,2%** (18,9% a 26,0%) | 16,9% (13,5% a 20,5%) | 53,1% (49,5% a 57,0%) |
| privacy-filter-br, 3.000 documentos (17.335 menções) | **0,4%** (0,3% a 0,5%) | 0,3% (0,2% a 0,4%) | 52,0% (51,4% a 52,7%) |
| privacy-filter-br, holdout inteiro (107.594 menções) | **3,3%** (3,2% a 3,5%) | — | — |
| Velocidade | ~300 mil caracteres/s | ~19 mil | 7 a 28 mil |

Vazamento (menor é melhor), com o IC 95% entre parênteses.

**Como o Presidio foi configurado.** Ele não tem uma configuração pronta para o português. Usamos a mais justa que ele oferece sem código próprio: o spaCy `pt_core_news_lg` para nomes e locais e os reconhecedores que não dependem de idioma (e-mail, telefone com a região BR, cartão, IBAN, IP, URL, data). O Presidio não traz reconhecedores de documentos brasileiros. É isso que se compara: o uso pronto de cada ferramenta. O script está em [`scripts/comparar_presidio.py`](../scripts/comparar_presidio.py), com as instruções para reproduzir.

O que os números mostram:

- **Documentos brasileiros são a maior diferença.** No privacy-filter-br, o Presidio vaza 90% dos CPFs, 99% dos CNPJs e 99% dos endereços; o Véu, menos de 1% dos CPFs e CNPJs.
- **Nomes em documentos formais eram o ponto forte do Presidio**, graças ao modelo do spaCy: 7,7% de vazamento de nomes, contra 11,9% do Véu. Com as listas do Censo 2022 e a propagação de nomes confirmados, o Véu caiu para 0,9%, sem modelo e sem perder velocidade.
- **No BR-Agentic, sobram endereços completos e contas.** As anotações contam como endereço também o bairro, a cidade e a UF ("Conjunto Exemplo, 100, Bairro, Cidade - UF"), e o Véu esconde a rua e o CEP, mas não a cidade. Contas e agências sem a palavra "conta" por perto também passam.

### O que mudou com a avaliação externa

A primeira medição no holdout do privacy-filter-br deu **20,2%** de vazamento. Investigando só na parte de treino, apareceram formatos que o Véu não reconhecia: documentos já mascarados pela metade (`324.327.***-**`, `36.496.715/****-**`, `55886******`), CNPJ, RG e CEP com espaços e CNH com hífen. Com esses formatos, o holdout caiu para **6,4%** (CPF de 24,9% para 0,5%, CNPJ de 47,0% para 0,1%, RG de 50,7% para 2,8%), sem mudar a validação própria (2,5%).

Nos nomes, a parte de treino mostrou que o Véu achava "Raul Viana", mas deixava de fora "Anthony": nomes comuns entre quem nasceu depois de 2000 não estavam nas listas. Com os 5 mil prenomes e 2 mil sobrenomes do Censo 2022 do IBGE, mais a propagação de nomes confirmados ("Rayane Souza" ... "a rayane"), o vazamento de nomes no holdout caiu de **15,4% para 1,4%**, e o geral, para **3,3%**. Para não esconder palavras comuns, os prenomes que também estão no dicionário pt_BR do LibreOffice ("Rosa", "Natal", "Glória") só contam com contexto, e municípios ("Belo Jardim") e sequências que começam com tipo de logradouro ("Avenida Paulista") ou com São, Santo e Santa deixam de ser lidos como pessoas. As detecções de nome fora das anotações na parte de treino caíram de 2.875 para 1.370 em 5.000 documentos.

## Limitações conhecidas

- **Todos os conjuntos são sintéticos.** O próprio autor do privacy-filter-br mediu que um modelo com F1 de 0,99 no sintético cai para 0,85 em 30 documentos reais. Em dados reais, espere resultados piores. Avalie com uma amostra dos seus dados (`--dataset`) antes de usar em produção.
- O desafio e a validação foram escritos pela mesma pessoa que escreveu o detector. Os conjuntos externos corrigem parte desse viés, mas não todo: contribuições de casos reais, com dados fictícios, deixam o benchmark mais confiável.
- O BR-Agentic tem só 41 conversas: os intervalos de confiança por tipo são largos.
- Os maiores vazamentos estão em nomes sem contexto ("kkkk a kamilly esqueceu"), nomes de outras origens, endereços completos (bairro e cidade) e contas bancárias sem a palavra "conta".
