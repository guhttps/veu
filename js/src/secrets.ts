// Segredos: chaves de API, tokens, senhas, chaves privadas e URLs de conexão (equivalente a recognizers/secrets.py).
import { bip39, secretRules } from "./data.ts";
import type { Candidate, Recognizer } from "./entities.ts";
import { isAlpha, isLower } from "./text.ts";
import { isValidBip39 } from "./validators.ts";

export const SECRET_RECOGNIZER_LABELS = ["CHAVE_API", "TOKEN", "SENHA", "CHAVE_PRIVADA", "URL_CONEXAO", "SEGREDO"];

interface CompiledRule {
  id: string;
  label: string;
  regex: RegExp;
  score: number;
  group: number;
  filter?: string;
  trim: string;
}

let compiled: CompiledRule[] | null = null;

function rules(): CompiledRule[] {
  compiled ??= secretRules.map((rule) => ({
    id: rule.id,
    label: rule.entidade,
    regex: new RegExp(rule.padrao, "gd"),
    score: rule.pontuacao,
    group: rule.grupo ?? 0,
    filter: rule.filtro,
    trim: rule.aparar ?? "",
  }));
  return compiled;
}

const VALUE_CHARS = "[^\\s\"'`,;&<>()\\[\\]{}]";
const ASSIGNMENT = new RegExp(
  `(?<![A-Za-z0-9_.-])([A-Za-z_][A-Za-z0-9_.-]{0,60})["']?[ \\t]*(=>|:=|=|:)[ \\t]*["']?(${VALUE_CHARS}{3,500})`, "gd",
);
const PROSE_PASSWORD = new RegExp(
  `(?<![A-Za-z0-9])(?:senha|password|passwd)(?:[^\\n:=]{0,25}?)(\\s*(?::|=)\\s*|\\s+(?:é|eh|is|fica|ficou|era|para|pra|to)\\s+)["']?(${VALUE_CHARS}{3,200})`,
  "gdi",
);

// Sem separador ("Login admin, senha bGsE$34", "rede Visitantes, senha Visit@2026"): só vale com cara de senha.
const PROSE_PASSWORD_BARE = new RegExp(`(?<![A-Za-z0-9])(?:senha|password|passwd)[ \\t]+["']?(${VALUE_CHARS}{6,200})`, "gdi");
// Cabeçalho Cookie: o valor de um cookie de sessão é uma credencial ("Cookie: session_id=9f2c...; theme=dark").
const COOKIE_HEADER = /^[ \t]*(?:set-)?cookie[ \t]*:[ \t]*([^\n]+)/dgim;
const COOKIE_PAIR = /([A-Za-z0-9_.-]{1,60})=([^;\s]{8,4096})/dg;
const SESSION_COOKIE_WORDS = new Set(["session", "sessionid", "sess", "sessid", "sid", "phpsessid", "jsessionid", "auth",
  "jwt", "remember"]);

const PASSWORD_WORDS = new Set(["password", "passwd", "passphrase", "pwd", "senha", "pass", "passw"]);
const SECRET_WORDS = new Set(["secret", "token", "apikey", "credential", "credentials", "credencial", "credenciais",
  "signature", "sig", "auth"]);
// Código de verificação por SMS ou app ("seu código de verificação é 483920", "OTP: 1234").
const OTP_CODE = new RegExp(
  "(?<![A-Za-z0-9])(?:c[óo]digo\\s+(?:de\\s+)?(?:verifica[çc][ãa]o|confirma[çc][ãa]o|acesso|autentica[çc][ãa]o|login"
  + "|ativa[çc][ãa]o|valida[çc][ãa]o)|verification\\s+code|one[- ]time\\s+(?:password|code)|otp|2fa|token\\s+sms)"
  + "[^\\d\\n]{0,25}?(?<!\\d)(\\d{4,8})(?!\\d)",
  "gdi",
);
// Frase de recuperação de carteira (BIP-39): 12 a 24 palavras da lista, separadas por espaço, vírgula ou numeração.
const SEED_WORD = /[A-Za-z]+/g;
const SEED_GAP = /^[ \t\r\n,;]*(?:\d{1,2}[ \t]*[.):-]?[ \t]*)?$/;
const SEED_CONTEXT = /seed|semente|mnem[oô]nic|recupera[cç][aã]o|recovery|frase|phrase|palavras|words|carteira|wallet|backup/i;
const SEED_SIZES = [24, 21, 18, 15, 12];
let bip39Indexes: Map<string, number> | null = null;
const SECRET_PAIRS = new Set([
  "api key", "access key", "private key", "secret key", "auth key", "chave api", "signing key", "encryption key",
  "master key", "account key", "app key",
]);
const NOT_SECRET_WORDS = new Set([
  "url", "uri", "endpoint", "path", "file", "filename", "name", "type", "count", "limit", "length", "size", "ttl",
  "expires", "expiry", "expiration", "max", "min", "header", "field", "label", "prefix", "env", "var",
  "placeholder", "hint", "description", "desc", "enabled", "required", "policy", "rotation", "version", "tokens",
  "usage", "id", "ref", "arn", "mode", "format", "manager", "provider", "store", "location", "nome",
  "tipo", "arquivo", "caminho",
]);
const PLACEHOLDERS = new Set([
  "null", "none", "nil", "true", "false", "undefined", "empty", "vazio", "string", "str", "number", "int",
  "bool", "boolean", "any", "text", "texto", "required", "optional", "hidden", "secret", "password", "senha",
  "token", "redacted", "removido", "removida", "omitido", "omitida", "masked", "default",
]);
const IDENTIFIER_PARTS = /[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+/g;
const DOTTED = /^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$/;
const CONSTANT = /^[A-Z_]+$/;
const FILLER = /^[*xX.•_#-]+$/;
const RANDOM_RUN = /[A-Za-z0-9+/=_-]{8,}/g;
const PREFIX = /^(?:AKIA|ASIA|ABIA|ACCA|AIza|GOCSPX-|ya29\.|eyJ|SG\.|\$aact_|(?:[A-Za-z]{2,10}[_-]){1,2})/;

/** Prefixo que identifica o tipo da chave sem revelar o segredo ("sk-proj-", "ghp_", "AKIA"). */
export function secretPrefix(value: string): string {
  const match = PREFIX.exec(value);
  return match && match[0].length < value.length ? match[0] : "";
}

/** Palavras do nome de um campo: "DB_PASSWORD" -> [db, password]; "clientSecret" -> [client, secret]. */
export function keyWords(key: string): string[] {
  return key.split(/[_.\-\s]+/).flatMap((chunk) => chunk.match(IDENTIFIER_PARTS) ?? []).map((part) => part.toLowerCase());
}

export function keyKind(key: string): "SENHA" | "SEGREDO" | null {
  const words = keyWords(key);
  if (!words.length || words.some((word) => NOT_SECRET_WORDS.has(word))) return null;
  if (words.some((word) => PASSWORD_WORDS.has(word))) return "SENHA";
  if (words.some((word) => SECRET_WORDS.has(word))) return "SEGREDO";
  for (let i = 0; i + 1 < words.length; i += 1) if (SECRET_PAIRS.has(`${words[i]} ${words[i + 1]}`)) return "SEGREDO";
  return null;
}

export function isPlaceholder(value: string): boolean {
  const lowered = value.toLowerCase();
  return PLACEHOLDERS.has(lowered) || "$%<{[#*".includes(value[0]) || FILLER.test(value) || DOTTED.test(value)
    || CONSTANT.test(value)
    || ["your", "sua_", "seu_", "<", "example", "exemplo", "process.env", "os.environ"].some((p) => lowered.startsWith(p));
}

export function entropy(value: string): number {
  const counts = new Map<string, number>();
  for (const char of value) counts.set(char, (counts.get(char) ?? 0) + 1);
  let total = 0;
  for (const n of counts.values()) total -= (n / value.length) * Math.log2(n / value.length);
  return total;
}

/** Tem cara de chave gerada: um trecho longo misturando letras e números, ou longo e com alta entropia. */
export function looksRandom(value: string): boolean {
  if (value.length < 8 || isPlaceholder(value)) return false;
  for (const [run] of value.matchAll(RANDOM_RUN)) {
    const hasDigit = /\d/.test(run);
    const hasLetter = /[A-Za-z]/.test(run);
    if (hasDigit && hasLetter) return true;
    if (run.length >= 24 && /[A-Z]/.test(run) && /[a-z]/.test(run) && entropy(run) >= 3.5) return true;
  }
  return false;
}

/** Mistura de letras e números, ou símbolo com letras ou números: "Visit@2026" sim, "inválida" e "123456" não. */
export function looksLikePassword(value: string): boolean {
  const digit = /\p{Nd}/u.test(value);
  const alpha = /\p{L}/u.test(value);
  const symbol = /[@#$%!&*?+=_]/.test(value);
  return (digit && alpha) || (symbol && (digit || alpha));
}

export function plausiblePassword(value: string, prose: boolean): boolean {
  if (value.length < 4 || isPlaceholder(value)) return false;
  return !(prose && isAlpha(value) && (isLower(value) || isLower(value.slice(1))));
}

export class SecretRecognizer implements Recognizer {
  name = "segredos";
  labels: ReadonlySet<string> = new Set(SECRET_RECOGNIZER_LABELS);

  *find(text: string): Iterable<Candidate> {
    for (const rule of rules()) {
      for (const match of text.matchAll(rule.regex)) {
        const span = match.indices?.[rule.group];
        if (!span) continue;
        const start = span[0];
        let value = text.slice(start, span[1]);
        if (rule.trim) {
          while (value && rule.trim.includes(value[value.length - 1])) value = value.slice(0, -1);
        }
        if (!value || (rule.filter === "aleatorio" && !looksRandom(value))) continue;
        yield { label: rule.label, start, end: start + value.length, score: rule.score, recognizer: this.name };
      }
    }
    const assignment = new RegExp(ASSIGNMENT.source, ASSIGNMENT.flags); // lastIndex próprio a cada chamada
    for (let match = assignment.exec(text); match !== null; match = assignment.exec(text)) {
      // O valor pode trazer outras atribuições: em "https://site/reset?token=8f3a...", a primeira é "https:".
      assignment.lastIndex = match.indices![2]![1];
      const kind = keyKind(match[1]);
      if (kind === null) continue;
      const [start, end] = match.indices![3]!;
      if (text[end] === "(") continue; // password = getpass()
      const value = match[3];
      if (kind === "SENHA") {
        const prose = match[2] === ":" && keyWords(match[1]).length === 1;
        if (plausiblePassword(value, prose)) {
          assignment.lastIndex = end;
          yield { label: "SENHA", start, end, score: 0.85, recognizer: this.name };
        }
      } else if (looksRandom(value)) {
        assignment.lastIndex = end;
        yield { label: "SEGREDO", start, end, score: 0.85, recognizer: this.name };
      }
    }
    for (const match of text.matchAll(OTP_CODE)) {
      const [start, end] = match.indices![1]!;
      yield { label: "SENHA", start, end, score: 0.8, recognizer: this.name };
    }
    yield* this.seedPhrases(text);
    for (const match of text.matchAll(PROSE_PASSWORD)) {
      const [start, matchEnd] = match.indices![2]!;
      // O ponto que fecha a frase não faz parte da senha: "resetei a senha para Tmp#4821."
      const end = match[2].endsWith(".") && (matchEnd === text.length || /\s/.test(text[matchEnd])) ? matchEnd - 1 : matchEnd;
      if (plausiblePassword(text.slice(start, end), true)) {
        yield { label: "SENHA", start, end, score: 0.8, recognizer: this.name };
      }
    }
    for (const match of text.matchAll(PROSE_PASSWORD_BARE)) {
      const [start, matchEnd] = match.indices![1]!;
      const end = match[1].endsWith(".") && (matchEnd === text.length || /\s/.test(text[matchEnd])) ? matchEnd - 1 : matchEnd;
      const value = text.slice(start, end);
      if (plausiblePassword(value, true) && looksLikePassword(value)) {
        yield { label: "SENHA", start, end, score: 0.75, recognizer: this.name };
      }
    }
    for (const header of text.matchAll(COOKIE_HEADER)) {
      const offset = header.indices![1]![0];
      for (const pair of header[1].matchAll(COOKIE_PAIR)) {
        const [name, value] = [pair[1], pair[2]];
        const session = keyWords(name).some((word) => SESSION_COOKIE_WORDS.has(word));
        if ((keyKind(name) || session) && (looksRandom(value) || value.length >= 16)) {
          const [start, end] = pair.indices![2]!;
          yield { label: "SEGREDO", start: offset + start, end: offset + end, score: 0.85, recognizer: this.name };
        }
      }
    }
  }
  /** Sequências de palavras do BIP-39: com o checksum certo, ou 12+ palavras depois de "seed", "carteira"... */
  private *seedPhrases(text: string): Iterable<Candidate> {
    bip39Indexes ??= new Map(bip39.map((word, index) => [word, index]));
    let run: [number, number, number][] = [];
    for (const match of text.matchAll(SEED_WORD)) {
      const index = bip39Indexes.get(match[0].toLowerCase());
      const start = match.index!;
      if (index !== undefined && run.length > 0) {
        const previous = run[run.length - 1][1];
        if (start - previous > 12 || !SEED_GAP.test(text.slice(previous, start))) {
          yield* this.seedRun(text, run);
          run = [];
        }
      }
      if (index === undefined) {
        yield* this.seedRun(text, run);
        run = [];
      } else {
        run.push([start, start + match[0].length, index]);
      }
    }
    yield* this.seedRun(text, run);
  }

  private *seedRun(text: string, run: [number, number, number][]): Iterable<Candidate> {
    if (run.length < 12) return;
    for (const size of SEED_SIZES) { // a maior janela com o checksum certo
      for (let offset = 0; offset + size <= run.length; offset++) {
        const window = run.slice(offset, offset + size);
        if (isValidBip39(window.map(([, , index]) => index))) {
          yield { label: "CHAVE_PRIVADA", start: window[0][0], end: window[size - 1][1], score: 0.99, recognizer: this.name };
          return;
        }
      }
    }
    const start = run[0][0];
    if (SEED_CONTEXT.test(text.slice(Math.max(0, start - 80), start))) {
      yield { label: "CHAVE_PRIVADA", start, end: run[run.length - 1][1], score: 0.9, recognizer: this.name };
    }
  }
}
