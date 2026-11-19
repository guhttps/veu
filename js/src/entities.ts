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
  CTPS: "Carteira de trabalho (CTPS)",
  REGISTRO_PROFISSIONAL: "Registro em conselho profissional (OAB, CRM, CRO, CREA...)",
  CADASTRO: "Número de cadastro (prontuário, matrícula, carteirinha do convênio, apólice)",
  CERTIDAO: "Matrícula de certidão de nascimento, casamento ou óbito",
  TELEFONE: "Telefone",
  EMAIL: "E-mail",
  ENDERECO: "Endereço",
  COORDENADAS: "Coordenadas de GPS",
  CEP: "CEP",
  PLACA: "Placa de veículo",
  RENAVAM: "RENAVAM",
  CARTAO_CREDITO: "Cartão de crédito ou débito",
  CONTA_BANCARIA: "Agência ou conta bancária",
  CHAVE_PIX: "Chave Pix aleatória ou Pix copia e cola",
  BOLETO: "Linha digitável ou código de barras de boleto",
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
  NUIT: "NUIT (Moçambique)",
  BI_AO: "Bilhete de Identidade (Angola)",
  BI_MZ: "Bilhete de Identidade (Moçambique)",
  SSN: "SSN ou ITIN (Estados Unidos)",
  MBI: "Medicare (Estados Unidos)",
  DNI_ES: "DNI ou NIE (Espanha)",
  CODICE_FISCALE: "Codice fiscale (Itália)",
  NIR: "Número da segurança social (França)",
  STEUER_ID: "Steuer-ID (Alemanha)",
  NINO: "National Insurance (Reino Unido)",
  NHS: "NHS (Reino Unido)",
  BSN: "BSN (Países Baixos)",
  SIN: "SIN (Canadá)",
  AADHAAR: "Aadhaar (Índia)",
  PAN: "PAN (Índia)",
  MRZ: "Zona de leitura de passaporte (MRZ)",
  VIN: "Chassi (VIN)",
  CRIPTO: "Carteira de criptomoeda (Bitcoin, Ethereum)",
  PORTA: "Porta de rede",
  SERVIDOR: "Nome de servidor interno",
  MAC: "Endereço MAC de placa de rede",
  IMEI: "IMEI de celular",
  CHAVE_API: "Chave de API ou token de serviço (OpenAI, AWS, GitHub...)",
  TOKEN: "Token de acesso (JWT, Bearer)",
  SENHA: "Senha",
  CHAVE_PRIVADA: "Chave privada (PEM, SSH) ou frase de recuperação de carteira",
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

/** Grupos de tipos para caixinhas de escolha (os mesmos do painel): cada tipo fica em exatamente um grupo. */
export { groups as GROUPS, type GroupData } from "./data.ts";
