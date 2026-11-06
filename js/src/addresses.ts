// Endereços: logradouro, nome, número e complemento (equivalente a veu/recognizers/addresses.py).
import type { Candidate, Recognizer } from "./entities.ts";
import { caseless, contextWindow, wordsRegex } from "./text.ts";

const KEYWORD_ANY_CASE = caseless(
  "Rua|R\\.|Avenida|Av\\.?|Travessa|Trav\\.|Tv\\.|Alameda|Al\\.|Pra[çc]a|P[çc]a\\.|Rodovia|Rod\\.|Estrada|" +
  "Estr\\.|Viela|Beco|Ladeira|Servid[ãa]o",
);
const KEYWORD = `(?:(?:${KEYWORD_ANY_CASE})|Largo|Passagem|Vila|Via)`;
const ABBREVIATION = "(?:Dr|Dra|Prof|Profa|Gen|Cel|Mal|Pres|Eng|Sen|Dep|Gov|Cap|Ten|Sta|Sto|Pe|Frei|Dom|S)\\.";
const WORD = "[A-ZÀ-Ý][\\p{L}\\p{N}_À-ÿ'’-]*";
const NAME_PART = `(?:${ABBREVIATION}|${WORD})`;
const FIRST = `(?:(?:d[aeo]s?\\s+)?(?:\\d{1,3}\\s+(?:de\\s+)?${WORD}|${NAME_PART}))`;
const NEXT = `(?:\\s+(?:(?:d[aeo]s?|e)\\s+)?${NAME_PART})`;
const NUMBER = "(?:\\s*,\\s*|\\s+)(?:(?:n[º°o]\\.?|n\\.|número)\\s*)?(?:\\d{1,6}[A-Za-z]?|[Ss]/[Nn])(?![\\p{L}\\p{N}_/])";
const COMPLEMENT_WORDS = caseless(
  "apto?\\.?|apartamento|ap\\.|bloco|bl\\.|casa|cs\\.|sala|sl\\.|lote|lt\\.|quadra|qd\\.|" +
  "conjunto|cj\\.|andar|loja|torre|fundos|frente",
);
const COMPLEMENT = `(?:\\s*[,–-]?\\s*(?:${COMPLEMENT_WORDS})(?:\\s*[\\p{L}\\p{N}_-]{1,6})?(?![\\p{L}\\p{N}_]))`;

const CAPITALIZED = new RegExp(
  `(?<![\\p{L}\\p{N}_])${KEYWORD}\\s+${FIRST}${NEXT}{0,6}(?<number>${NUMBER})?(?:${COMPLEMENT}){0,3}`, "gu",
);
const LOWERCASE = new RegExp(
  "(?<![\\p{L}\\p{N}_])(?:rua|avenida|av\\.?|travessa|alameda|pra[çc]a|estrada)\\s+(?:[a-zà-ÿ]+\\s+){1,5}?" +
  `(?:n[º°o]\\.?\\s*)?\\d{1,6}(?![\\p{L}\\p{N}_])(?:${COMPLEMENT}){0,3}`, "gu",
);

const ADDRESS_CONTEXT = [
  "moro", "mora", "moramos", "resido", "reside", "residente", "domiciliado", "domiciliada", "endereco",
  "entrega", "entregar", "enviar para", "envio para", "localizado", "localizada", "situado", "situada",
  "sede", "fica na", "fica no", "cobranca", "imovel",
];

export class AddressRecognizer implements Recognizer {
  name = "enderecos";
  labels: ReadonlySet<string> = new Set(["ENDERECO"]);
  private context = wordsRegex(ADDRESS_CONTEXT)!;

  *find(text: string): Iterable<Candidate> {
    for (const match of text.matchAll(CAPITALIZED)) {
      const start = match.index;
      let end = start + match[0].length;
      while (end > start && (text[end - 1] === " " || text[end - 1] === ",")) end -= 1;
      let score: number;
      if (match.groups?.number) score = 0.9;
      else score = this.context.test(contextWindow(text, start, end, 40, 0)) ? 0.75 : 0.45;
      yield { label: "ENDERECO", start, end, score, recognizer: this.name };
    }
    for (const match of text.matchAll(LOWERCASE)) {
      yield { label: "ENDERECO", start: match.index, end: match.index + match[0].length, score: 0.7, recognizer: this.name };
    }
  }
}
