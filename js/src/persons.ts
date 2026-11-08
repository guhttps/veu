// Nomes de pessoas por listas de nomes brasileiros e contexto (equivalente a veu/recognizers/persons.py).
import * as data from "./data.ts";
import type { Candidate, Recognizer } from "./entities.ts";
import { escapeRegex, fold, isLower, isUpper, textBefore, wordsRegex } from "./text.ts";

const WORD = /[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['’][A-Za-zÀ-ÖØ-öø-ÿ]+)*/gu;
const SPACE_GAP = /^[ \t]{1,2}$/;
export const CONNECTORS: ReadonlySet<string> = new Set([
  "da", "de", "do", "das", "dos", "e", "del", "della", "di", "du", "van", "von", "der", "d",
]);

const PERSON_CONTEXT = [
  "sr", "sr.", "sra", "sra.", "srta", "senhor", "senhora", "dona", "dom", "seu", "dr", "dr.", "dra", "dra.",
  "doutor", "doutora", "prof", "prof.", "profa", "professor", "professora", "cliente", "paciente", "aluno",
  "aluna", "nome", "nome completo", "chamo", "chama", "chamado", "chamada", "prezado", "prezada", "caro", "cara",
  "querido", "querida", "oi", "ola", "atenciosamente", "att", "cordialmente", "assinado", "assinatura",
  "titular", "responsavel", "contratante", "contratado", "contratada", "locador", "locadora", "locatario",
  "locataria", "fiador", "fiadora", "autor", "autora", "reu", "requerente", "requerido", "requerida",
  "testemunha", "advogado", "advogada", "funcionario", "funcionaria", "colaborador", "colaboradora", "colega",
  "filho", "filha", "mae", "pai", "esposa", "esposo", "marido", "irmao", "irma", "avo", "neto", "neta", "tio",
  "tia", "sobrinho", "sobrinha", "amigo", "amiga", "vizinho", "vizinha", "motorista", "entregador",
  "entregadora", "atendente", "medico", "medica", "enfermeiro", "enfermeira", "falar com", "aos cuidados de",
  "a/c", "de:", "para:", "por", "com o", "com a", "pelo", "pela", "segurado", "segurada", "beneficiario",
  "beneficiaria", "dependente", "candidato", "candidata", "inquilino", "inquilina", "proprietario",
  "proprietaria", "comprador", "compradora", "vendedor", "vendedora", "destinatario", "remetente",
];
const ORGANIZATION_WORDS: ReadonlySet<string> = new Set([
  "ltda", "ltd", "s.a", "sa", "me", "eireli", "epp", "mei", "cia", "companhia", "hospital", "clinica",
  "farmacia", "drogaria", "padaria", "mercado", "supermercado", "mercearia", "construtora", "incorporadora",
  "escola", "colegio", "faculdade", "universidade", "instituto", "fundacao", "associacao", "cooperativa",
  "sindicato", "banco", "grupo", "empresa", "industria", "industrias", "comercio", "distribuidora",
  "transportadora", "logistica", "consultoria", "tecnologia", "solucoes", "servicos", "sistemas", "restaurante",
  "lanchonete", "pizzaria", "hotel", "pousada", "academia", "loja", "lojas", "magazine", "atacadao", "posto",
  "auto", "pecas", "imobiliaria", "advocacia", "advogados", "associados", "contabilidade", "laboratorio",
  "odontologia", "studio", "estudio", "agencia", "editora", "igreja", "paroquia", "prefeitura", "secretaria",
  "ministerio", "tribunal", "assembleia", "hub", "tech", "digital", "software", "games", "foods",
]);
const STREET_BEFORE = new RegExp(
  "(?<![\\p{L}\\p{N}_])(?:rua|r\\.|av\\.?|avenida|travessa|tv\\.|alameda|al\\.|praca|pca\\.|rodovia|rod\\.|estrada|" +
  "largo|viela|beco|ladeira|vila|bairro|jardim|parque|condominio|edificio|residencial)(?:\\s+d[aeo]s?)?\\s*$", "u",
);
// Tipos de logradouro: uma sequência que começa com eles é endereço ("Avenida Paulista", "Quadra Norte").
const STREET_WORDS: ReadonlySet<string> = new Set([
  "rua", "avenida", "av", "travessa", "alameda", "praca", "rodovia", "estrada", "largo", "viela", "beco",
  "ladeira", "quadra", "conjunto", "setor", "loteamento", "condominio", "residencial", "edificio", "chacara",
  "sitio", "fazenda", "via", "vila", "jardim", "parque", "bairro",
]);
// "São Cristóvão", "Santa Maria", "Santo Antônio": lugares e santos, não pessoas.
const SAINTS: ReadonlySet<string> = new Set(["sao", "santo", "santa"]);
const GREETINGS = [
  "oi", "ola", "e ai", "eai", "fala", "bom dia", "boa tarde", "boa noite", "obrigado", "obrigada", "valeu",
  "vlw", "tchau", "beijo", "bjs", "abraco", "querido", "querida", "meu nome e", "me chamo", "sou o", "sou a",
  "aqui e o", "aqui e a", "com o", "com a",
];
const STRONG_CONTEXT = /(?:meu nome e|me chamo|nome:|nome completo:|sr\.?|sra\.?|dona|dr\.?|dra\.?)\s*$/u;

type Word = [start: number, end: number, word: string];

const casefold = (text: string): string => text.toLowerCase().replace(/ß/g, "ss");
const foldedSet = (values: readonly string[]): Set<string> => new Set(values.map(fold));

let shared: {
  firstNames: Set<string>; surnames: Set<string>; ambiguous: Set<string>; stopwords: Set<string>;
  curatedAmbiguous: Set<string>; ibgeAmbiguous: Set<string>;
  stopExact: Set<string>; places: Set<string>; organizations: Set<string>;
} | null = null;

function lists() {
  shared ??= {
    firstNames: foldedSet(data.firstNames),
    surnames: foldedSet(data.surnames),
    ambiguous: new Set([...foldedSet(data.ambiguous), ...foldedSet(data.ibgeAmbiguous)]),
    curatedAmbiguous: foldedSet(data.ambiguous),
    ibgeAmbiguous: foldedSet(data.ibgeAmbiguous),
    stopwords: foldedSet(data.stopwords),
    stopExact: new Set(data.stopwords.map(casefold)),
    places: foldedSet(data.places),
    organizations: foldedSet(data.organizations),
  };
  return shared;
}

/** Ambíguos revistos à mão ("Rosa", "Luz"): não se propagam no anonimizador. */
export function ambiguousNames(): ReadonlySet<string> {
  return lists().curatedAmbiguous;
}

/** Ambíguos que o dicionário marca como palavras ("Costa", "Nascimento"): só se propagam com inicial maiúscula. */
export function capitalizedOnlyNames(): ReadonlySet<string> {
  const { curatedAmbiguous, ibgeAmbiguous } = lists();
  return new Set([...ibgeAmbiguous].filter((word) => !curatedAmbiguous.has(word)));
}

export class PersonRecognizer implements Recognizer {
  name = "nomes";
  labels: ReadonlySet<string> = new Set(["PESSOA"]);
  private firstNames: Set<string>;
  private surnames: Set<string>;
  private ambiguous: Set<string>;
  private stopExact: Set<string>;
  private stopFolded: Set<string>;
  private places: Set<string>;
  private organizations: Set<string>;
  private context = wordsRegex(PERSON_CONTEXT)!;
  private greeting = new RegExp(`(?:^|[^\\p{L}\\p{N}_])(?:${GREETINGS.map((g) => escapeRegex(fold(g))).join("|")})[\\s,!]*$`, "u");

  constructor(extraFirstNames: Iterable<string> = [], extraSurnames: Iterable<string> = []) {
    const base = lists();
    this.firstNames = new Set([...base.firstNames, ...[...extraFirstNames].map(fold)]);
    this.surnames = new Set([...base.surnames, ...[...extraSurnames].map(fold)]);
    this.ambiguous = base.ambiguous;
    this.stopExact = base.stopExact;
    this.stopFolded = new Set([...base.stopwords].filter((w) => !this.firstNames.has(w) && !this.surnames.has(w)));
    this.places = base.places;
    this.organizations = base.organizations;
  }

  private isStop(word: string): boolean {
    return this.stopExact.has(casefold(word)) || this.stopFolded.has(fold(word));
  }

  private isCapitalized(word: string): boolean {
    if (!isUpper(word[0])) return false;
    const folded = fold(word);
    return !(isUpper(word) && word.length <= 3) || this.firstNames.has(folded) || this.surnames.has(folded);
  }

  private hasContext(text: string, start: number, before = 30): boolean {
    return this.context.test(fold(textBefore(text, start, before)));
  }

  *find(text: string): Iterable<Candidate> {
    const words: Word[] = [...text.matchAll(WORD)].map((m) => [m.index, m.index + m[0].length, m[0]]);
    let index = 0;
    while (index < words.length) {
      const word = words[index][2];
      if (!this.isCapitalized(word) || CONNECTORS.has(fold(word))) {
        index += 1;
        continue;
      }
      const sequence = [index];
      let next = index + 1;
      while (next < words.length) {
        const gap = text.slice(words[next - 1][1], words[next][0]);
        if (!SPACE_GAP.test(gap)) break;
        const candidate = words[next][2];
        if (CONNECTORS.has(fold(candidate))) {
          if (next + 1 < words.length && SPACE_GAP.test(text.slice(words[next][1], words[next + 1][0]))
            && this.isCapitalized(words[next + 1][2])) {
            sequence.push(next);
            next += 1;
            continue;
          }
          break;
        }
        if (!this.isCapitalized(candidate)) break;
        sequence.push(next);
        next += 1;
      }
      const found = this.scoreSequence(text, sequence.map((k) => words[k]));
      if (found) yield found;
      index = sequence[sequence.length - 1] + 1;
    }
    yield* this.lowercaseNames(text, words);
  }

  private scoreSequence(text: string, tokens: Word[]): Candidate | null {
    const whole = tokens.map((token) => fold(token[2])).join(" ");
    if (this.places.has(whole) || this.organizations.has(whole)) return null;
    if (tokens.some((token) => ORGANIZATION_WORDS.has(fold(token[2])))) return null;
    if (tokens.length && (STREET_WORDS.has(fold(tokens[0][2])) || SAINTS.has(fold(tokens[0][2])))) return null;
    const firstIndex = tokens.findIndex((token) => this.firstNames.has(fold(token[2])));
    if (firstIndex !== -1) {
      tokens = tokens.slice(firstIndex);
    } else {
      while (tokens.length && (this.isStop(tokens[0][2]) || CONNECTORS.has(fold(tokens[0][2])))) tokens = tokens.slice(1);
    }
    while (tokens.length && (this.isStop(tokens[tokens.length - 1][2]) || CONNECTORS.has(fold(tokens[tokens.length - 1][2])))) {
      tokens = tokens.slice(0, -1);
    }
    if (!tokens.length) return null;
    const folded = tokens.map((token) => fold(token[2]));
    const joined = folded.join(" ");
    if (this.places.has(joined) || this.organizations.has(joined)) return null;
    const start = tokens[0][0];
    const end = tokens[tokens.length - 1][1];
    if (STREET_BEFORE.test(fold(textBefore(text, start, 16)))) return null;
    const context = this.hasContext(text, start);
    const rawNameWords = tokens.map((token) => token[2]).filter((word) => !CONNECTORS.has(fold(word)));
    if (rawNameWords.length >= 2 && rawNameWords.some((word) => this.isStop(word))) return null;
    const nameWords = rawNameWords.map(fold);
    const knownFirst = this.firstNames.has(folded[0]);
    const known = nameWords.filter((word) => this.firstNames.has(word) || this.surnames.has(word)).length;
    let score: number;
    if (nameWords.length >= 2) {
      if (knownFirst && known >= 2) score = 0.9;
      else if (knownFirst) score = 0.8;
      else if (this.surnames.has(nameWords[nameWords.length - 1]) || known >= 2) score = context ? 0.7 : 0.62;
      else if (context) score = 0.65;
      else return null;
    } else {
      const word = nameWords[0];
      if (this.isStop(tokens[0][2]) || (this.places.has(word) && !this.firstNames.has(word))) return null;
      if (this.firstNames.has(word)) {
        if (this.ambiguous.has(word)) {
          if (!context) return null;
          score = 0.7;
        } else {
          score = context ? 0.8 : 0.6;
        }
      } else if (context && ((this.surnames.has(word) && !this.ambiguous.has(word)) || this.strongContext(text, start))) {
        score = 0.6;
      } else {
        return null;
      }
    }
    return { label: "PESSOA", start, end, score, recognizer: this.name };
  }

  private strongContext(text: string, start: number): boolean {
    return STRONG_CONTEXT.test(fold(textBefore(text, start, 25)));
  }

  private *lowercaseNames(text: string, words: Word[]): Iterable<Candidate> {
    let index = 0;
    while (index < words.length) {
      const [start, end, word] = words[index];
      const folded = fold(word);
      if (!isLower(word) || !this.firstNames.has(folded) || this.ambiguous.has(folded) || this.isStop(word)
        || folded.length < 3) {
        index += 1;
        continue;
      }
      let last = index;
      while (last + 1 < words.length && isLower(words[last + 1][2])
        && (this.surnames.has(fold(words[last + 1][2])) || CONNECTORS.has(fold(words[last + 1][2])))
        && SPACE_GAP.test(text.slice(words[last][1], words[last + 1][0]))) {
        last += 1;
      }
      while (last > index && CONNECTORS.has(fold(words[last][2]))) last -= 1;
      const before = fold(textBefore(text, start, 18));
      if (last > index) yield { label: "PESSOA", start, end: words[last][1], score: 0.65, recognizer: this.name };
      else if (this.greeting.test(before)) yield { label: "PESSOA", start, end, score: 0.6, recognizer: this.name };
      index = last + 1;
    }
  }
}
