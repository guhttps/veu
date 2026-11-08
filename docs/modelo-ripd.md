# Modelo de RIPD: uso de IA generativa externa com o Véu

Modelo de Relatório de Impacto à Proteção de Dados Pessoais (LGPD, art. 38) para o uso de assistentes de IA de terceiros (ChatGPT, Claude, Gemini, Copilot e similares) com o Véu entre os usuários e o provedor. Os trechos entre colchetes são para preencher; os demais descrevem o Véu e podem ser ajustados. **Não é parecer jurídico.** Revise com o encarregado (DPO).

## 1. Identificação

- **Controlador:** [razão social, CNPJ]
- **Encarregado:** [nome e contato]
- **Áreas envolvidas:** [atendimento, jurídico, RH, desenvolvimento...]
- **Data e versão deste relatório:** [data] / [versão]

## 2. Descrição do tratamento

- **Finalidade:** [resumir atendimentos, redigir peças, revisar código...]
- **Ferramentas de IA e provedores:** [provedor, modelo, região de processamento, contrato]
- **Como o Véu entra no fluxo:** [proxy central / extensão do navegador / biblioteca na aplicação / agentes de código]. Antes de cada envio, o Véu troca dados pessoais e segredos por marcadores (`[CPF_1]`); o provedor recebe só os marcadores. Na resposta, o Véu devolve os dados reais a quem pediu, exceto dentro de links e, para segredos, nos argumentos de ferramentas.
- **Perfil do Véu:** [pseudonimizacao / anonimizacao / judiciario / juridico / saude / financeiro / setor-publico] (veja `veu perfis`)
- **Categorias de titulares:** [clientes, pacientes, colaboradores, partes de processos...]
- **Categorias de dados:** [identificação, contato, financeiros, saúde (sensível, art. 11)...]
- **Base legal:** [art. 7º, inciso ... / art. 11, inciso ...]

## 3. Necessidade e proporcionalidade

- **Por que a IA externa é necessária:** [justificar]
- **Minimização:** o provedor recebe marcadores, não os dados. Tipos que nunca devem sair estão em `bloquear`: [listar, por exemplo CARTAO_CREDITO, CHAVE_PRIVADA]. [Se houver: textos com dados sensíveis vão para o modelo interno com `desviar_para`.]
- **Retenção:** o cofre fica na memória (ou no Redis, cifrado) e expira após [sessao_ttl] segundos sem uso. O provedor retém [conforme contrato].

## 4. Transferência internacional (art. 33)

- **Destino:** [país]
- **Mecanismo:** [cláusulas-padrão da Resolução CD/ANPD nº 19/2024 / adequação / outro]
- **Efeito do Véu:** reduz o volume e a identificabilidade do que é transferido, mas, no modo reversível, o que sai continua sendo dado pessoal pseudonimizado.

## 5. Riscos e medidas

| Risco | Probabilidade | Impacto | Medida | Risco residual |
|---|---|---|---|---|
| Dado pessoal não detectado chega ao provedor | [ ] | [ ] | Detecção por regras com dígitos verificadores e listas do IBGE; medição pública com dados de terceiros (`veu avaliar --externo todos`); [detector spaCy ligado?]; treinamento dos usuários | [ ] |
| Identificação pelo contexto (sem nome nem documento) | [ ] | [ ] | Orientação aos usuários; revisão das tarefas com dados sensíveis | [ ] |
| Injeção de prompt tenta levar dados para fora | [ ] | [ ] | A restauração não devolve dados reais em links, imagens e URLs; segredos não voltam em argumentos de ferramentas; marcadores forjados são desarmados; limite de restaurações por resposta (`max_por_resposta`) | [ ] |
| Acesso indevido ao cofre | [ ] | [ ] | Cofre na memória ou cifrado no Redis (AES-256-GCM, chave fora do Redis); sessões separadas por credencial | [ ] |
| Alteração do registro de uso | [ ] | [ ] | Auditoria encadeada com HMAC e âncoras externas (`veu auditoria ancorar`) | [ ] |
| Uso fora do proxy (sem proteção) | [ ] | [ ] | [Rede que só permite os provedores pelo gateway / extensão gerenciada com a configuração travada / `--exigir-proxy` nos agentes] | [ ] |

## 6. Registro e monitoramento

- **Registro das operações:** `veu auditoria relatorio` [periodicidade], arquivado em [local].
- **Âncoras da auditoria:** [periodicidade e onde ficam].
- **Métricas:** `/veu/metricas` no [Prometheus/Grafana], com alertas para [bloqueios, erros, restaurações acima do normal].
- **Reavaliação deste RIPD:** [periodicidade ou gatilhos: troca de provedor, de perfil, de finalidade].

## 7. Conclusão

[Parecer do encarregado: aprovado, aprovado com condições ou não aprovado, e as condições.]

Veja também: [conformidade](conformidade.md), [modelo de ameaças](modelo-de-ameacas.md), [benchmark](benchmark.md), [guia para empresas](empresas.md).
