// Detectores por padrão: documentos, contatos e números (equivalente a veu/recognizers/patterns.py).
import type { Candidate, Recognizer } from "./entities.ts";
import { contextWindow, fold, wordsRegex } from "./text.ts";
import * as v from "./validators.ts";

const B = "(?<![\\p{L}\\p{N}_])";
const E = "(?![\\p{L}\\p{N}_])";

/** Pontuação conforme o valor é válido e há contexto por perto. null descarta o candidato. */
export interface Scores {
  valid: number | null;
  invalid?: number | null;
  validContext?: number | null;
  invalidContext?: number | null;
}

export function pickScore(scores: Scores, isValid: boolean, hasContext: boolean): number | null {
  const base = (isValid ? scores.valid : scores.invalid) ?? null;
  const withContext = (isValid ? scores.validContext : scores.invalidContext) ?? null;
  if (!hasContext) return base;
  if (withContext !== null) return withContext;
  return base === null ? null : Math.min(1, base + 0.15);
}

export interface PatternSpec {
  label: string;
  regex: RegExp;
  scores: Scores;
  validator?: (value: string) => boolean;
  context: RegExp | null;
  before: number;
  after: number;
  adjust?: (value: string, score: number) => number | null;
  exclude?: (value: string) => boolean;
  name?: string;
}

interface SpecOptions {
  validator?: (value: string) => boolean;
  context?: readonly string[];
  flags?: string;
  before?: number;
  after?: number;
  adjust?: (value: string, score: number) => number | null;
  exclude?: (value: string) => boolean;
  name?: string;
}

export function spec(label: string, pattern: string, scores: Scores, options: SpecOptions = {}): PatternSpec {
  return {
    label,
    regex: new RegExp(pattern, `g${options.flags ?? ""}u`),
    scores,
    validator: options.validator,
    context: wordsRegex(options.context ?? []),
    before: options.before ?? 40,
    after: options.after ?? 20,
    adjust: options.adjust,
    exclude: options.exclude,
    name: options.name,
  };
}

const S = (valid: number | null, invalid: number | null = null, validContext: number | null = null,
  invalidContext: number | null = null): Scores => ({ valid, invalid, validContext, invalidContext });

const CTX_CPF = ["cpf", "c.p.f", "cadastro de pessoa fisica", "contribuinte", "cpf/cnpj"];
const CTX_CNPJ = ["cnpj", "c.n.p.j", "cpf/cnpj", "razao social", "inscricao"];
const CTX_RG = ["rg", "r.g", "identidade", "registro geral", "carteira de identidade", "ssp", "doc. identidade", "cin"];
const CTX_CNH = ["cnh", "habilitacao", "carteira de motorista", "carteira nacional de habilitacao", "registro da cnh"];
const CTX_TITULO = ["titulo de eleitor", "titulo eleitoral", "eleitor", "inscricao eleitoral"];
const CTX_PIS = ["pis", "pasep", "pis/pasep", "nit", "nis", "pis/nit"];
const CTX_CNS = ["cns", "cartao sus", "cartao do sus", "cartao nacional de saude", "sus"];
const CTX_RENAVAM = ["renavam"];
const CTX_PASSAPORTE = ["passaporte", "passport"];
const CTX_PHONE = [
  "tel", "tel.", "telefone", "telefones", "celular", "cel", "cel.", "whatsapp", "whats", "zap", "wpp",
  "contato", "fone", "ligar", "ligue", "ramal", "numero",
];
const CTX_CEP = ["cep"];
const CTX_PLATE = ["placa", "veiculo", "carro", "moto", "caminhao", "automovel"];
const CTX_CARD = ["cartao", "credito", "debito", "visa", "mastercard", "master", "elo", "amex", "hipercard", "final"];
const CTX_PIX = ["pix", "chave pix", "chave aleatoria", "chave"];
const CTX_IP = ["ip", "endereco ip", "ipv4", "ipv6", "acesso", "login"];
const CTX_BIRTH = [
  "nascimento", "nasc", "nasc.", "nascido", "nascida", "nasceu", "data de nascimento", "dn", "d.n",
  "aniversario", "nascida em", "nascido em",
];
const CTX_ACCOUNT = ["conta", "conta corrente", "conta-corrente", "c/c", "cc", "agencia", "ag", "ag.", "poupanca", "conta poupanca"];
const CTX_PROCESS = ["processo", "autos", "proc", "proc.", "acao", "numero do processo"];
const CTX_EMAIL = ["email", "e-mail"];
const CTX_IBAN = ["iban", "swift", "bic", "transferencia internacional", "conta internacional"];

const phoneAdjust = (value: string, score: number): number => (/[()\s.+-]/u.test(value) ? score : score - 0.3);
const isYear = (value: string): boolean => /^(?:19|20)\d{2}$/.test(value);
// Documentos já mascarados pela metade ("324.327.***-**", "***.982.247-**"): os dígitos que sobram ainda
// identificam a pessoa. Só valem com pelo menos 3 dígitos à mostra.
const M = "[\\d*xX\\u2022]";
const MB = "(?<![\\p{L}\\p{N}_*])";
const ME = "(?![\\p{L}\\p{N}_*])";
const partiallyMasked = (value: string): boolean =>
  [...value].filter((char) => /\d/.test(char)).length >= 3 && /[*xX\u2022]/.test(value);
const MONTHS = "janeiro|fevereiro|mar[cç]o|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro";

export const DEFAULT_SPECS: PatternSpec[] = [
  // CPF
  spec("CPF", `${B}\\d{3}\\.\\d{3}\\.\\d{3}-\\d{2}${E}`, S(0.95, 0.5, 1.0, 0.7), { validator: v.isValidCpf, context: CTX_CPF }),
  spec("CPF", `${B}\\d{9}-\\d{2}${E}`, S(0.9, 0.4, 1.0, 0.65), { validator: v.isValidCpf, context: CTX_CPF }),
  spec("CPF", `${B}\\d{3}\\s\\d{3}\\s\\d{3}\\s\\d{2}${E}`, S(0.85, null, 0.95, 0.6), { validator: v.isValidCpf, context: CTX_CPF }),
  spec("CPF", `${B}\\d{11}${E}`, S(0.75, null, 0.95, 0.6), { validator: v.isValidCpf, context: CTX_CPF }),
  spec("CPF", `${MB}${M}{3}\\.${M}{3}\\.${M}{3}-${M}{2}${ME}`, S(0.85, null, 0.97),
    { validator: partiallyMasked, context: CTX_CPF, name: "mascarado" }),
  // CNPJ (numérico e alfanumérico)
  spec("CNPJ", `${B}[0-9A-Z]{2}\\.[0-9A-Z]{3}\\.[0-9A-Z]{3}/[0-9A-Z]{4}-\\d{2}${E}`, S(0.95, 0.5, 1.0, 0.7),
    { validator: v.isValidCnpj, context: CTX_CNPJ }),
  spec("CNPJ", `${B}\\d{14}${E}`, S(0.75, null, 0.95, 0.6), { validator: v.isValidCnpj, context: CTX_CNPJ }),
  spec("CNPJ", `${B}\\d{2}\\s\\d{3}\\s\\d{3}\\s\\d{4}\\s\\d{2}${E}`, S(0.85, null, 0.95, 0.6),
    { validator: v.isValidCnpj, context: CTX_CNPJ }),
  spec("CNPJ", `${MB}${M}{2}\\.${M}{3}\\.${M}{3}/${M}{4}-${M}{2}${ME}`, S(0.85, null, 0.97),
    { validator: partiallyMasked, context: CTX_CNPJ, name: "mascarado" }),
  spec("CNPJ", `${B}(?=[0-9A-Z]{12}\\d{2}${E})(?=[0-9]*[A-Z])[0-9A-Z]{12}\\d{2}${E}`, S(0.6, null, 0.95, 0.55),
    { validator: v.isValidCnpj, context: CTX_CNPJ }),
  // Documentos que dependem de contexto
  spec("PIS", `${B}\\d{3}\\.\\d{5}\\.\\d{2}-\\d${E}`, S(0.85, 0.45, 1.0, 0.75), { validator: v.isValidPis, context: CTX_PIS }),
  spec("PIS", `${B}\\d{11}${E}`, S(null, null, 0.97, 0.65), { validator: v.isValidPis, context: CTX_PIS, before: 25 }),
  spec("CNH", `${B}\\d{11}${E}`, S(null, null, 0.97, 0.75), { validator: v.isValidCnh, context: CTX_CNH, before: 30 }),
  spec("CNH", `${B}\\d{10}-\\d${E}`, S(null, null, 0.97, 0.75), { validator: v.isValidCnh, context: CTX_CNH, before: 30 }),
  spec("CNH", `${MB}${M}{11}${ME}`, S(null, null, 0.9),
    { validator: partiallyMasked, context: CTX_CNH, before: 30, name: "mascarado" }),
  spec("TITULO_ELEITOR", `${B}\\d{4}\\s?\\d{4}\\s?\\d{4}${E}`, S(null, null, 0.95, 0.75),
    { validator: v.isValidTituloEleitor, context: CTX_TITULO, before: 30 }),
  spec("TITULO_ELEITOR", `${MB}${M}{4}\\s?${M}{4}\\s?${M}{4}${ME}`, S(null, null, 0.9),
    { validator: partiallyMasked, context: CTX_TITULO, before: 30, name: "mascarado" }),
  spec("RENAVAM", `${B}\\d{9,11}${E}`, S(null, null, 0.97, 0.75),
    { validator: v.isValidRenavam, context: CTX_RENAVAM, before: 25 }),
  spec("CNS", `${B}[12789]\\d{2}\\s?\\d{4}\\s?\\d{4}\\s?\\d{4}${E}`, S(0.6, null, 0.97, 0.65),
    { validator: v.isValidCns, context: CTX_CNS }),
  spec("RG", `${B}\\d{1,2}\\.\\d{3}\\.\\d{3}-[\\dXx]${E}`, S(0.6, null, 0.95), { context: CTX_RG }),
  spec("RG", `${B}\\d{7,9}-?[\\dXx]?${E}`, S(null, null, 0.85), { context: CTX_RG, before: 20 }),
  spec("RG", `${B}[A-Z]{2}-?\\d{1,2}\\.?\\d{3}\\.?\\d{3}${E}`, S(null, null, 0.85), { context: CTX_RG, before: 20 }),
  spec("RG", `${B}\\d{1,2}\\s\\d{3}\\s\\d{3}\\s[\\dXx]${E}`, S(null, null, 0.85), { context: CTX_RG, before: 20 }),
  spec("RG", `${MB}${M}{1,2}\\.?${M}{3}\\.?${M}{2,3}-?${M}${ME}`, S(null, null, 0.85),
    { validator: partiallyMasked, context: CTX_RG, before: 20, name: "mascarado" }),
  spec("PASSAPORTE", `${B}[A-Z]{2}\\d{6}${E}`, S(null, null, 0.9), { context: CTX_PASSAPORTE, before: 30 }),
  // Contatos
  spec("EMAIL", `(?<![\\p{L}\\p{N}_.+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\\.[A-Za-z0-9-]+)*\\.[A-Za-z]{2,}${E}`,
    S(0.95), { context: CTX_EMAIL }),
  spec("TELEFONE",
    `(?<![\\p{L}\\p{N}_+])(?:\\+?55[\\s.-]?)?(?:\\(\\d{2}\\)|\\d{2})[\\s.-]?(?:9[\\s.]?\\d{4}|[2-5]\\d{3})[\\s.-]?\\d{4}${E}`,
    S(0.85, null, 0.95), { validator: v.isValidPhone, context: CTX_PHONE, adjust: phoneAdjust }),
  spec("TELEFONE", `${B}9\\d{4}-\\d{4}${E}`, S(0.7, null, 0.9), { context: CTX_PHONE }),
  spec("TELEFONE",
    `(?<![\\p{L}\\p{N}_+])\\+(?!55)[1-9]\\d{0,2}(?:[\\s.-]?\\(?\\d{1,4}\\)?){1,2}(?:[\\s.-]?\\d{2,4}){2,4}${E}`,
    S(0.8, null, 0.95), { validator: v.isValidIntlPhone, context: CTX_PHONE }),
  spec("TELEFONE", `${B}[2-5]\\d{3}-\\d{4}${E}`, S(null, null, 0.8), { context: CTX_PHONE, before: 25 }),
  // Localização e veículos
  spec("CEP", `${B}\\d{5}-\\d{3}${E}`, S(0.75, null, 0.95), { context: CTX_CEP }),
  spec("CEP", `${B}\\d{2}\\.\\d{3}-\\d{3}${E}`, S(0.8, null, 0.95), { context: CTX_CEP }),
  spec("CEP", `${B}\\d{8}${E}`, S(null, null, 0.85), { context: CTX_CEP, before: 15 }),
  spec("CEP", `${B}\\d{5}\\s\\d{3}${E}`, S(null, null, 0.85), { context: CTX_CEP, before: 15 }),
  spec("PLACA", `${B}[A-Z]{3}-\\d{4}${E}`, S(0.8, null, 0.95), { context: CTX_PLATE }),
  spec("PLACA", `${B}[A-Z]{3}\\d[A-Z]\\d{2}${E}`, S(0.75, null, 0.95), { context: CTX_PLATE }),
  spec("PLACA", `${B}[A-Z]{3}\\d{4}${E}`, S(0.45, null, 0.9), { context: CTX_PLATE }),
  // Financeiro
  spec("CARTAO_CREDITO", `${B}\\d(?:[ -]?\\d){12,18}${E}`, S(0.85, null, 0.95, 0.6),
    { validator: v.isValidCard, context: CTX_CARD }),
  spec("IBAN", `${B}[A-Z]{2}\\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,4})?${E}`, S(0.95, null, 1.0),
    { validator: v.isValidIban, context: CTX_IBAN }),
  spec("CHAVE_PIX", `${B}[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}${E}`,
    S(null, null, 0.9), { context: CTX_PIX }),
  spec("CONTA_BANCARIA", `${B}\\d{1,12}(?:[.-]?\\d{1,4})?-[\\dXx]${E}`, S(null, null, 0.85),
    { context: CTX_ACCOUNT, before: 20, after: 0 }),
  spec("CONTA_BANCARIA", `${B}\\d{4,12}${E}`, S(null, null, 0.8),
    { context: CTX_ACCOUNT, before: 15, after: 0, exclude: isYear }),
  // Rede
  spec("IP", `${B}(?:\\d{1,3}\\.){3}\\d{1,3}${E}`, S(0.7, null, 0.9), { validator: v.isValidIpv4, context: CTX_IP }),
  spec("IP", `(?<![\\p{L}\\p{N}_:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\\p{L}\\p{N}_:])`, S(0.75, null, 0.9),
    { validator: v.isValidIpv6, context: CTX_IP }),
  // Datas de nascimento (só com contexto)
  spec("DATA_NASCIMENTO", `${B}(?:\\d{1,2}[/.-]\\d{1,2}[/.-](?:\\d{4}|\\d{2})|\\d{4}-\\d{2}-\\d{2})${E}`,
    S(null, null, 0.85), { validator: v.isPlausibleBirthdate, context: CTX_BIRTH, before: 35, after: 0 }),
  spec("DATA_NASCIMENTO", `${B}\\d{1,2}\\s+de\\s+(?:${MONTHS})\\s+de\\s+\\d{4}${E}`, S(null, null, 0.85),
    { validator: v.isPlausibleBirthdate, context: CTX_BIRTH, flags: "i", before: 35, after: 0 }),
  // Processos judiciais
  spec("PROCESSO", `${B}\\d{7}-\\d{2}\\.\\d{4}\\.\\d\\.\\d{2}\\.\\d{4}${E}`, S(0.9, 0.6, 1.0, 0.75),
    { validator: v.isValidProcessoCnj, context: CTX_PROCESS }),
];

const round3 = (value: number): number => Math.round(value * 1000) / 1000;

export class PatternRecognizer implements Recognizer {
  name = "padroes";
  specs: PatternSpec[];
  labels: ReadonlySet<string>;

  constructor(specs?: PatternSpec[]) {
    this.specs = specs ?? DEFAULT_SPECS;
    this.labels = new Set(this.specs.map((item) => item.label));
  }

  *find(text: string): Iterable<Candidate> {
    for (const item of this.specs) {
      for (const match of text.matchAll(item.regex)) {
        const value = match[0];
        const start = match.index;
        if (item.exclude?.(value)) continue;
        const isValid = item.validator ? item.validator(value) : true;
        let hasContext = false;
        if (item.context) {
          hasContext = item.context.test(contextWindow(text, start, start + value.length, item.before, item.after));
        }
        let score = pickScore(item.scores, isValid, hasContext);
        if (score !== null && item.adjust) score = item.adjust(value, score);
        if (score === null || score <= 0) continue;
        yield { label: item.label, start, end: start + value.length, score: round3(score), recognizer: item.name ?? this.name };
      }
    }
  }
}

/** Padrão definido pelo usuário. requiresContext: só conta com uma das palavras de contexto por perto. */
export function customPattern(label: string, pattern: string, score = 0.9, context: readonly string[] = [],
  requiresContext = false): PatternSpec {
  const scores = requiresContext ? S(null, null, score) : S(score, null, Math.min(1, score + 0.1));
  return spec(label.toUpperCase(), pattern, scores, { context: context.map(fold), name: "personalizado" });
}
