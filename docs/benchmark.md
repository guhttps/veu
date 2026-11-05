# Metodologia do benchmark

```bash
veu avaliar --quantidade 1000           # tabelas por tipo de dado
veu avaliar --json                      # números em JSON
veu gerar-dataset -o dados.jsonl        # exporta os textos anotados
veu avaliar --dataset dados.jsonl       # avalia um conjunto seu, no mesmo formato
```

## Conjuntos

| Conjunto | Origem | Para que serve |
|---|---|---|
| **Desenvolvimento** | 40 modelos de texto em 14 categorias, preenchidos com dados falsos (`semente=42`) | Foi usado para ajustar o detector. Mostra o teto, não a realidade. |
| **Validação** | 20 modelos escritos **depois** do ajuste e nunca usados para ajustá-lo (`semente=43`) | É o número honesto: mede como o detector lida com textos novos. |
| **Difíceis** | 25 casos escritos à mão em [`bench/hard.py`](../src/veu/bench/hard.py) | Gírias, maiúsculas, nomes raros, CPF com dígito errado, textos sem dados que parecem ter. |

Os modelos misturam textos com dados pessoais e textos **sem nenhum dado** (notícias, lembretes, códigos de rastreio, versões de software), que medem os falsos positivos. Parte dos nomes usados não está nas listas do detector, para medir a detecção por contexto.

Todos os valores são gerados pelo próprio Véu (CPFs, CNPJs e cartões válidos, mas inventados; IPs nas faixas reservadas para documentação). Nenhum dado real é usado.

## Métricas

- **Precisão:** das detecções, quantas eram mesmo daquele tipo.
- **Revocação:** dos dados de um tipo, quantos foram detectados com o tipo certo (basta sobrepor o trecho).
- **Vazamento:** a fração dos dados pessoais em que **algum caractere alfanumérico** ficou de fora do que foi escondido. É mais rígido que a revocação: esconder "Maria" e deixar "Souza" conta como vazamento.

## Limitações conhecidas

- Textos sintéticos são mais regulares que textos reais. Avalie com uma amostra dos seus dados (`--dataset`) antes de usar em produção.
- O conjunto de validação foi escrito pela mesma pessoa que escreveu o detector. Contribuições de casos novos, de domínios reais e com dados fictícios, deixam o benchmark mais confiável.
- Os maiores vazamentos estão em nomes: minúsculos sem saudação ("o rayane esqueceu") e nomes raros sem sobrenome conhecido nem contexto.
