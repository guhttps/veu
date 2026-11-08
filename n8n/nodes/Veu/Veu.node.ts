// Nó do Véu para o n8n: "Esconder dados" antes da IA e "Restaurar dados" na resposta.
// A biblioteca do Véu vai embutida no pacote (sem dependências em tempo de execução, como o n8n pede).
import type { IDataObject, IExecuteFunctions, INodeExecutionData, INodeType, INodeTypeDescription } from "n8n-workflow";
import { NodeOperationError } from "n8n-workflow";
import { Veu, Vault } from "../../../js/src/index.ts";
import type { VaultData } from "../../../js/src/index.ts";

const OPERADORES = [
  { name: "Marcadores, como [CPF_1] (dá para restaurar)", value: "token" },
  { name: "Máscara, como ***.982.247-** (não volta)", value: "mascara" },
  { name: "Remover, como [CPF] (não volta)", value: "remover" },
];

export class Veu_ implements INodeType {
  description: INodeTypeDescription = {
    displayName: "Véu",
    name: "veu",
    icon: "file:veu.svg",
    group: ["transform"],
    version: 1,
    subtitle: '={{$parameter["operation"] === "restaurar" ? "Restaurar dados" : "Esconder dados"}}',
    description: "Esconde CPF, nomes, telefones, e-mails e chaves de API antes da IA e devolve os dados reais depois",
    defaults: { name: "Véu" },
    inputs: ["main"],
    outputs: ["main"],
    properties: [
      {
        displayName: "Operação",
        name: "operation",
        type: "options",
        noDataExpression: true,
        default: "esconder",
        options: [
          { name: "Esconder Dados", value: "esconder", action: "Esconder dados antes da IA",
            description: "Troca dados pessoais e segredos por marcadores, como [CPF_1]" },
          { name: "Restaurar Dados", value: "restaurar", action: "Restaurar dados na resposta da IA",
            description: "Troca os marcadores da resposta pelos dados reais" },
        ],
      },
      {
        displayName: "Texto",
        name: "texto",
        type: "string",
        typeOptions: { rows: 4 },
        default: "",
        required: true,
        description: "O texto a proteger ou a resposta da IA a restaurar. Use uma expressão, como {{ $json.mensagem }}.",
      },
      {
        displayName: "Cofre",
        name: "cofre",
        type: "json",
        default: "",
        required: true,
        displayOptions: { show: { operation: ["restaurar"] } },
        description: 'O cofre que o nó "Esconder dados" devolveu, por exemplo {{ $("Véu").item.json.cofre }}',
      },
      {
        displayName: "Como Esconder",
        name: "operador",
        type: "options",
        default: "token",
        displayOptions: { show: { operation: ["esconder"] } },
        options: OPERADORES,
      },
      {
        displayName: "Opções",
        name: "opcoes",
        type: "collection",
        placeholder: "Adicionar opção",
        default: {},
        displayOptions: { show: { operation: ["esconder"] } },
        options: [
          {
            displayName: "Recusar Se Tiver",
            name: "bloquear",
            type: "string",
            default: "CHAVE_PRIVADA",
            description: "Tipos que fazem o item dar erro em vez de seguir, separados por vírgula (por exemplo CARTAO_CREDITO)",
          },
          {
            displayName: "Nunca Esconder",
            name: "ignorar",
            type: "string",
            default: "",
            description: "Valores da sua empresa que nunca são escondidos, separados por vírgula",
          },
          {
            displayName: "Campo De Saída",
            name: "campo",
            type: "string",
            default: "textoProtegido",
            description: "Nome do campo com o texto protegido",
          },
        ],
      },
    ],
  };

  async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    const items = this.getInputData();
    const saida: INodeExecutionData[] = [];
    const instancias = new Map<string, Veu>();
    for (let indice = 0; indice < items.length; indice += 1) {
      try {
        const operacao = this.getNodeParameter("operation", indice) as string;
        const texto = String(this.getNodeParameter("texto", indice) ?? "");
        if (operacao === "restaurar") {
          const bruto = this.getNodeParameter("cofre", indice);
          const dados = (typeof bruto === "string" ? JSON.parse(bruto || "{}") : bruto) as VaultData;
          const cofre = Vault.fromJSON(dados);
          saida.push({ json: { ...items[indice].json, textoRestaurado: cofre.restore(texto) }, pairedItem: { item: indice } });
          continue;
        }
        const operador = this.getNodeParameter("operador", indice) as string;
        const opcoes = this.getNodeParameter("opcoes", indice, {}) as IDataObject;
        const ignorar = String(opcoes.ignorar ?? "").split(",").map((valor) => valor.trim()).filter(Boolean);
        const chave = JSON.stringify([operador, ignorar]);
        if (!instancias.has(chave)) instancias.set(chave, new Veu({ operator: operador, allowlist: ignorar }));
        const resultado = instancias.get(chave)!.anonymize(texto);
        const contagem = resultado.counts();
        const bloquear = String(opcoes.bloquear ?? "CHAVE_PRIVADA").split(",").map((tipo) => tipo.trim().toUpperCase()).filter(Boolean);
        const recusados = bloquear.filter((tipo) => contagem[tipo]);
        if (recusados.length) {
          throw new NodeOperationError(this.getNode(), `O Véu recusou o texto: ele contém ${recusados.join(", ")}.`, { itemIndex: indice });
        }
        saida.push({
          json: {
            ...items[indice].json,
            [String(opcoes.campo || "textoProtegido")]: resultado.text,
            encontrados: contagem,
            // O cofre tem os dados reais: passe-o só para o nó "Restaurar dados", nunca para a IA.
            cofre: resultado.vault.toJSON() as unknown as IDataObject,
          },
          pairedItem: { item: indice },
        });
      } catch (erro) {
        if (this.continueOnFail()) {
          saida.push({ json: { erro: (erro as Error).message }, pairedItem: { item: indice } });
          continue;
        }
        throw erro instanceof NodeOperationError ? erro : new NodeOperationError(this.getNode(), erro as Error, { itemIndex: indice });
      }
    }
    return [saida];
  }
}

// O n8n procura a classe pelo nome do arquivo (Veu.node.js -> Veu).
export { Veu_ as Veu };
