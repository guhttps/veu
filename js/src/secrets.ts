// Segredos: chaves de API, tokens, senhas, chaves privadas e URLs de conexão (equivalente a recognizers/secrets.py).
import { secretRules } from "./data.ts";
import type { Candidate, Recognizer } from "./entities.ts";
import { isAlpha, isLower } from "./text.ts";

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
  `(?<![A-Za-z0-9])(?:senha|password|passwd)(?:[^\\n:=]{0,25}?)(\\s*(?::|=)\\s*|\\s+(?:é|eh|is)\\s+)["']?(${VALUE_CHARS}{3,200})`,
  "gdi",
);

const PASSWORD_WORDS = new Set(["password", "passwd", "passphrase", "pwd", "senha", "pass", "passw"]);
const SECRET_WORDS = new Set(["secret", "token", "apikey", "credential", "credentials", "credencial", "credenciais"]);
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
    for (const match of text.matchAll(ASSIGNMENT)) {
      const kind = keyKind(match[1]);
      if (kind === null) continue;
      const [start, end] = match.indices![3]!;
      if (text[end] === "(") continue; // password = getpass()
      const value = match[3];
      if (kind === "SENHA") {
        const prose = match[2] === ":" && keyWords(match[1]).length === 1;
        if (plausiblePassword(value, prose)) yield { label: "SENHA", start, end, score: 0.85, recognizer: this.name };
      } else if (looksRandom(value)) {
        yield { label: "SEGREDO", start, end, score: 0.85, recognizer: this.name };
      }
    }
    for (const match of text.matchAll(PROSE_PASSWORD)) {
      const [start, end] = match.indices![2]!;
      if (plausiblePassword(match[2], true)) yield { label: "SENHA", start, end, score: 0.8, recognizer: this.name };
    }
  }
}
