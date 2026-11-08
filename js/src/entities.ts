// Tipos de dados detectados pelo Véu (os mesmos de veu/entities.py).

export const LABELS: Record<string, string> = {
  PESSOA: "Nome de pessoa",
  CPF: "CPF",
  CNPJ: "CNPJ (numérico ou alfanumérico)",
  RG: "RG",
  CNH: "CNH",
  TITULO_ELEITOR: "Título de eleitor",
  PIS: "PIS, PASEP, NIT ou NIS",
  CNS: "Cartão Nacional de Saúde (SUS)",
  PASSAPORTE: "Passaporte",
  TELEFONE: "Telefone",
  EMAIL: "E-mail",
  ENDERECO: "Endereço",
  CEP: "CEP",
  PLACA: "Placa de veículo",
  RENAVAM: "RENAVAM",
  CARTAO_CREDITO: "Cartão de crédito ou débito",
  CONTA_BANCARIA: "Agência ou conta bancária",
  CHAVE_PIX: "Chave Pix aleatória",
  DATA_NASCIMENTO: "Data de nascimento",
  IP: "Endereço IP",
  PROCESSO: "Número de processo judicial (CNJ)",
  IBAN: "IBAN (conta bancária internacional)",
  NIF_PT: "NIF ou NIPC (Portugal)",
  CC_PT: "Cartão de Cidadão (Portugal)",
  NISS_PT: "Número da Segurança Social (Portugal)",
  CUIT: "CUIT ou CUIL (Argentina)",
  DNI: "DNI (Argentina, Peru)",
  CURP: "CURP (México)",
  RFC: "RFC (México)",
  RUT: "RUT ou RUN (Chile, Uruguai)",
  CEDULA: "Cédula de identidade (Uruguai, Equador, Colômbia, Venezuela)",
  NIT: "NIT (Colômbia)",
  RUC: "RUC (Peru, Equador, Paraguai)",
  RIF: "RIF (Venezuela)",
  CHAVE_API: "Chave de API ou token de serviço (OpenAI, AWS, GitHub...)",
  TOKEN: "Token de acesso (JWT, Bearer)",
  SENHA: "Senha",
  CHAVE_PRIVADA: "Chave privada (PEM, SSH)",
  URL_CONEXAO: "URL de conexão com usuário e senha",
  SEGREDO: "Segredo em configuração (API_KEY=..., client_secret: ...)",
};

export const SECRET_LABELS: ReadonlySet<string> = new Set([
  "CHAVE_API", "TOKEN", "SENHA", "CHAVE_PRIVADA", "URL_CONEXAO", "SEGREDO",
]);

/** Trecho que um detector acha que é um dado pessoal, com uma pontuação de 0 a 1. */
export interface Candidate {
  label: string;
  start: number;
  end: number;
  score: number;
  recognizer: string;
}

/** Um dado pessoal encontrado no texto. */
export interface Entity extends Candidate {
  text: string;
}

/** Detector: qualquer objeto com nome, tipos e find(texto). */
export interface Recognizer {
  name: string;
  labels: ReadonlySet<string>;
  find(text: string): Iterable<Candidate>;
}
