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
  `(?<![A-Za-z0-9_.-])([A-Za-z_][A-Za-z0-9_.-]{0,60})["']?[ \\t]*(=>|:=|=(?!=)|:)[ \\t]*["']?(${VALUE_CHARS}{3,500})`, "gd",
);
// Comparação não é atribuição: "if password != confirm_password:" e "password == x" ficam.
const PROSE_PASSWORD = new RegExp(
  `(?<![A-Za-z0-9])(?:senha|password|passwd)(?:[^\\n:=<>]{0,25}?)(\\s*(?::|(?<![!=<>])=(?!=))\\s*|\\s+(?:é|eh|is|fica|ficou|era|para|pra|to)\\s+)["']?(${VALUE_CHARS}{3,200})`,
  "gdi",
);

// Segredos em código que não vêm depois de "=" ou ":": argumento de função, flag de comando, tag XML, atributo
// HTML, comparação e SQL. Cada item: padrão, grupo do nome do campo (0 = sem nome), grupos do valor e como conferir.
const LITERAL = "[^\\s\"'`\\\\]{3,500}";
const ID = "[A-Za-z_][A-Za-z0-9_]{0,60}";
const ID_DOT = "[A-Za-z_][A-Za-z0-9_.]{0,60}";
const START = "(?<![A-Za-z0-9_])";
type CodeMode = "prosa" | "campo" | "estrito" | "login" | "senha" | "segredo" | "comando";
const CODE_SECRETS: [string[], RegExp, number, number[], CodeMode][] = ([
  // define('AWS_SECRET_ACCESS_KEY', '...'), putenv("API_KEY", "..."), setItem("token", "...") (só os dois argumentos)
  [["(\"", "('", "( \"", "( '"], `(?<=[A-Za-z0-9_$])\\([ \\t]*["'](${ID_DOT})["'][ \\t]*,[ \\t]*["'](${LITERAL})["'][ \\t]*\\)`, "", 1, [2], "prosa"],
  // #define API_KEY "..."
  [["#define", "# define", "#\tdefine"], `#[ \\t]*define[ \\t]+(${ID})[ \\t]+"(${LITERAL})"`, "", 1, [2], "campo"],
  // setPassword("..."), .password("..."), withApiKey("...")
  [["(\"", "('", "( \"", "( '"], `${START}(${ID})\\([ \\t]*["'](${LITERAL})["'][ \\t]*\\)`, "", 1, [2], "estrito"],
  // app.config["SECRET_KEY"] = "...", os.environ['API_KEY'] = '...'
  [["[\"", "['", "[ \"", "[ '"], `\\[[ \\t]*["'](${ID_DOT})["'][ \\t]*\\][ \\t]*=(?!=)[ \\t]*["'](${LITERAL})["']`, "", 1, [2], "campo"],
  // variable "db_password" { default = "..." } (Terraform)
  [["variable \""], `${START}variable[ \\t]+"(${ID})"[ \\t]*\\{[^{}]{0,300}?(?<![A-Za-z0-9_])default[ \\t]*=[ \\t]*"(${LITERAL})"`, "", 1, [2],
    "campo"],
  // jwt.sign(payload, "..."), jwt.encode(payload, "...", algorithm="HS256")
  [["jwt", "jsonwebtoken", "jose"], `${START}(?:jwt|jsonwebtoken|JWT|jose)\\.(?:sign|encode|decode|verify)\\([^()\\n]{1,200}?,[ \\t]*["'](${LITERAL})["']`,
    "", 0, [1], "segredo"],
  // password == "...", token !== '...', senha.equals("...")
  [["==", "!="], `${START}(${ID_DOT})[ \\t]*(?:===?|!==?)[ \\t]*["'](${LITERAL})["']`, "", 1, [2], "estrito"],
  [[".equals("], `${START}(${ID_DOT})\\.equals\\([ \\t]*"(${LITERAL})"[ \\t]*\\)`, "", 1, [2], "campo"],
  // <password>...</password> e <ns:apiKey>...</ns:apiKey>
  [["</"], `<(?:[A-Za-z_][A-Za-z0-9_.-]*:)?(${ID})(?:[ \\t][^<>\\n]{0,200})?>([^<>\\s]{3,500})</(?:[A-Za-z_][A-Za-z0-9_.-]*:)?\\1>`,
    "", 1, [2], "campo"],
  // <add key="ApiKey" value="..."/>, <input name="api_token" value="...">, <property name="password" value="..."/>
  [["value=", "value ="], `(?<![A-Za-z0-9_-])(?:name|key|id|property)[ \\t]*=[ \\t]*["']([A-Za-z_][A-Za-z0-9_.:-]{0,60})["'][^<>\\n]{0,200}?[ \\t]value[ \\t]*=[ \\t]*["']([^"'\\s<>]{3,500})["']`,
    "", 1, [2], "campo"],
  // auth=("admin", "..."), HTTPBasicAuth("u", "..."), smtp.login("u@x.com", "...") (só usuário e senha)
  [["(\"", "('", "( \"", "( '"], `${START}(${ID_DOT})[ \\t]*(?:=[ \\t]*)?\\([ \\t]*["'][^"'\\n]{1,100}["'][ \\t]*,[ \\t]*["'](${LITERAL})["'][ \\t]*\\)`,
    "", 1, [2], "login"],
  // DriverManager.getConnection(url, "user", "..."), new PDO($dsn, "root", "...")
  [["getconnection", "pdo("], `${START}(?:getConnection|PDO)\\([^,()\\n]{1,300},[ \\t]*["'][^"'\\n]*["'][ \\t]*,[ \\t]*["'](${LITERAL})["']`,
    "", 0, [1], "senha"],
  // mysqli_connect("host", "user", "..."), pymysql.connect("host", "user", "...")
  [["mysql"], `${START}(?:mysqli_connect|mysqli|mysql_connect|pymysql\\.connect|MySQLdb\\.connect)\\([ \\t]*["'][^"'\\n]*["'][ \\t]*,[ \\t]*["'][^"'\\n]*["'][ \\t]*,[ \\t]*["'](${LITERAL})["']`,
    "", 0, [1], "senha"],
  // CREATE USER x IDENTIFIED BY '...', GRANT ... TO 'u'@'h' IDENTIFIED BY '...' e WITH PASSWORD '...'
  [["identified"], `${START}(?:user|role|login|to)(?![A-Za-z0-9_])[^\\n]{0,120}?(?<![A-Za-z0-9_])identified[ \\t]+by[ \\t]+(?:password[ \\t]+)?["'](${LITERAL})["']`,
    "i", 0, [1], "senha"],
  [["password '", "password  '", "password\t'"], `${START}password[ \\t]+'(${LITERAL})'`, "i", 0, [1], "senha"],
  // curl -u admin:... e http -a admin:...
  [["curl ", "curl\t", "http ", "http\t", "https ", "https\t", "xh ", "xh\t"], `${START}(?:curl|https?|xh)[ \\t][^\\n]*?(?<![A-Za-z0-9_-])(?:-u|--user|-a|--auth)(?:[ \\t]+|=)(["']?)[^\\s:"'@/]{1,100}:(${LITERAL})\\1`,
    "", 0, [2], "comando"],
  // mysql -p... (grudado), sshpass -p ..., docker login -p ..., redis-cli -a ...
  [["mysql", "mariadb"], `${START}(?:mysql|mysqldump|mariadb|mysqladmin|mysqlimport)(?![A-Za-z0-9_])[^\\n]*?[ \\t]-p(["']?)(${LITERAL})\\1`,
    "", 0, [2], "comando"],
  [["sshpass"], `${START}sshpass[ \\t]+-p[ \\t]*(["']?)(${LITERAL})\\1`, "", 0, [2], "comando"],
  [["docker", "podman", "buildah", "skopeo", "oras ", "helm"], `${START}(?:docker|podman|buildah|skopeo|oras|helm[ \\t]+registry)[ \\t]+login(?![A-Za-z0-9_])[^\\n]*?[ \\t](?:-p|--password)(?:[ \\t]+|=)(["']?)(${LITERAL})\\1`,
    "", 0, [2], "comando"],
  [["redis-cli"], `${START}redis-cli(?![A-Za-z0-9_])[^\\n]*?[ \\t]-a[ \\t]+(["']?)(${LITERAL})\\1`, "", 0, [2], "comando"],
  [["ldap"], `${START}(?:ldapsearch|ldapmodify|ldapadd|ldapdelete|ldappasswd|ldapwhoami|ldapcompare)(?![A-Za-z0-9_])[^\\n]*?[ \\t]-w[ \\t]+(["']?)(${LITERAL})\\1`,
    "", 0, [2], "comando"],
  [["sqlcmd", "bcp"], `${START}(?:sqlcmd|bcp)(?![A-Za-z0-9_])[^\\n]*?[ \\t]-P[ \\t]*(["']?)(${LITERAL})\\1`, "", 0, [2], "comando"],
  [["mongo"], `${START}(?:mongo|mongosh|mongodump|mongorestore|mongoexport|mongoimport)(?![A-Za-z0-9_])[^\\n]*?[ \\t](?:-p|--password)(?:[ \\t]+|=)(["']?)(${LITERAL})\\1`,
    "", 0, [2], "comando"],
  [["smbclient"], `${START}smbclient(?![A-Za-z0-9_])[^\\n]*?[ \\t](?:-U|--user)(?:[ \\t]+|=)(["']?)[^\\s%"']+%(${LITERAL})\\1`, "", 0, [2],
    "comando"],
  [["xfreerdp"], `${START}xfreerdp(?![A-Za-z0-9_])[^\\n]*?[ \\t]/p:(["']?)(${LITERAL})\\1`, "", 0, [2], "comando"],
  // htpasswd -b arquivo usuario ... (a senha é o último argumento)
  [["htpasswd"], `${START}htpasswd[ \\t][^\\n]*?(?<![A-Za-z0-9_-])-[A-Za-z]*b[A-Za-z]*[ \\t][^\\n]*?[ \\t](["']?)(${LITERAL})\\1(?=[ \\t]*(?:\\r?\\n|$))`,
    "", 0, [2], "comando"],
  // echo "..." | docker login --password-stdin, echo "..." | sudo -S
  [["--password-stdin", "sudo"], `${START}(?:echo|printf)[ \\t]+(?:-[A-Za-z]+[ \\t]+)?(["']?)(${LITERAL})\\1[ \\t]*\\|[^\\n]*?(?:--password-stdin|sudo[ \\t]+-S)(?![A-Za-z0-9_-])`,
    "", 0, [2], "comando"],
  // ConvertTo-SecureString "..." -AsPlainText (PowerShell)
  [["convertto-securestring"], `(?<![A-Za-z0-9_-])ConvertTo-SecureString[ \\t]+(?:-String[ \\t]+)?(["'])(${LITERAL})\\1`, "i", 0, [2], "senha"],
] as [string[], string, string, number, number[], CodeMode][]).map(([hints, source, flags, key, values, mode]) =>
  [hints, new RegExp(source, `gd${flags}`), key, values, mode]);
const CODE_HINTS = [...new Set(CODE_SECRETS.flatMap(([hints]) => hints))];
// Nomes de função que recebem usuário e senha: auth=(...), HTTPBasicAuth(...), smtp.login(...).
const LOGIN_WORDS = new Set(["auth", "login", "basic", "credential", "credentials", "authenticate", "signin"]);
// Funções que recebem o nome do segredo, não o valor: get_secret("API_KEY"), getenv("DB_PASSWORD").
const GETTER_WORDS = new Set(["get", "read", "load", "fetch", "lookup", "find", "has", "delete", "remove", "del", "print",
  "log", "describe", "require", "unset", "clear"]);
// Nome de variável de ambiente ("AI21_API_KEY") e nome de campo com palavra de segredo ("sentinel_password",
// "x-api-key", "workbookPasswordSet"): é nome, não valor.
const ENV_NAME = /^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$/;
const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_.-]*$/;
const COMPOUND = /[_.-]|[a-z0-9][A-Z]/;
// Palavras em minúsculas ligadas por hífen ou sublinhado ("partial-custom-token-2", "enable_oauth2_auth").
const WORDY = /^[a-z]+(?:[-_.][a-z0-9]+)+$/;
// Tag do YAML no lugar do valor ("password: !vault |", "senha: !secret wifi"): o segredo está em outro lugar.
const YAML_TAG = /^![A-Za-z_][A-Za-z0-9_]*$/;
// Comando do PowerShell no lugar do valor ("$senha = Read-Host -AsSecureString").
const CMDLET = /^(?:Get|Set|Read|New|ConvertTo|ConvertFrom|Import|Export|Invoke|Select|Join|Out|Write|Format|Find|Test|Resolve|Protect|Unprotect)-[A-Z][A-Za-z]+$/;

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
// Senha ou PIN só de números sem separador ("senha do banco 739201", "PIN do cartão 4821"). Um ano solto depois
// de "senha" ("a senha expira em 2027") fica, a não ser que a palavra seja PIN.
const NUMERIC_PIN = /(?<![A-Za-z0-9])(senha|pin|passcode)(?![A-Za-z])[^\d\n]{0,25}?(?<!\d)(\d{4,8})(?!\d|[.,/:-]\d)/dgi;
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
  "tipo", "arquivo", "caminho", "method", "methods", "algorithm", "algorithms", "alg", "scheme",
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
    || CONSTANT.test(value) || CMDLET.test(value)
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

/** O valor é uma tag do YAML seguida do conteúdo ("!vault |", "!secret wifi"), não a senha. */
export function yamlTag(text: string, start: number, end: number): boolean {
  return YAML_TAG.test(text.slice(start, end)) && (text[end] === " " || text[end] === "\t");
}

/** SENHA, SEGREDO ou null para um valor achado em código, conforme o nome do campo e a cara do valor. */
/** O valor é um nome (de variável de ambiente ou de campo de segredo), não o segredo. */
export function namesAField(value: string): boolean {
  if (ENV_NAME.test(value)) return true;
  return IDENTIFIER.test(value) && COMPOUND.test(value) && !/\p{Nd}/u.test(value) && keyKind(value) !== null;
}

export function codeSecretKind(mode: CodeMode, key: string, value: string): "SENHA" | "SEGREDO" | null {
  if (!/[\p{L}\p{N}]/u.test(value) || namesAField(value)) return null;
  const words = keyWords(key);
  if (mode === "estrito" && words.length && GETTER_WORDS.has(words[0])) return null; // get_secret("API_KEY")
  if (mode === "login") {
    const named = keyWords(key).some((word) => LOGIN_WORDS.has(word) || PASSWORD_WORDS.has(word));
    return named && plausiblePassword(value, false) ? "SENHA" : null;
  }
  if (mode === "segredo") return plausiblePassword(value, false) ? "SEGREDO" : null;
  if (mode === "senha" || mode === "comando") {
    if (mode === "comando" && (/^[0-9]+$/.test(value) || "/~".includes(value[0]))) return null; // docker -u 1000:1000
    return plausiblePassword(value, false) ? "SENHA" : null;
  }
  const kind = keyKind(key);
  if (kind === "SENHA") {
    if (!plausiblePassword(value, mode === "prosa")) return null;
    return mode !== "estrito" || looksLikePassword(value) ? "SENHA" : null;
  }
  return kind === "SEGREDO" && looksRandom(value) && !WORDY.test(value) ? "SEGREDO" : null;
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
      const value = match[3];
      // password = getpass(), password: !vault |, password = new_password
      if (text[end] === "(" || yamlTag(text, start, end) || namesAField(value)) continue;
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
    for (const match of text.matchAll(NUMERIC_PIN)) {
      const digits = match[2];
      if (digits.length === 4 && Number(digits) >= 1950 && Number(digits) <= 2099 && match[1].toLowerCase() !== "pin") continue;
      const [start, end] = match.indices![2]!;
      yield { label: "SENHA", start, end, score: 0.75, recognizer: this.name };
    }
    yield* this.seedPhrases(text);
    for (const match of text.matchAll(PROSE_PASSWORD)) {
      const [start, matchEnd] = match.indices![2]!;
      // O ponto que fecha a frase não faz parte da senha: "resetei a senha para Tmp#4821."
      const end = match[2].endsWith(".") && (matchEnd === text.length || /\s/.test(text[matchEnd])) ? matchEnd - 1 : matchEnd;
      const value = text.slice(start, end);
      // "confirm_password:\npassword: x": o valor terminado em ":" é o rótulo da linha seguinte.
      if (plausiblePassword(value, true) && !yamlTag(text, start, end) && !value.endsWith(":") && !namesAField(value)) {
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
    // Cada regra só roda se o texto tem um trecho que ela procura (curl, define, jwt...): cada pista é
    // conferida uma vez, e o texto comum, sem nenhuma, pula todas as regras.
    const lowered = text.toLowerCase();
    const present = new Set(CODE_HINTS.filter((hint) => lowered.includes(hint)));
    for (const [hints, pattern, keyGroup, valueGroups, mode] of present.size ? CODE_SECRETS : []) {
      if (!hints.some((hint) => present.has(hint))) continue;
      for (const match of text.matchAll(pattern)) {
        const group = valueGroups.find((g) => match[g] !== undefined)!;
        const kind = codeSecretKind(mode, keyGroup ? match[keyGroup] : "", match[group]);
        if (kind !== null) {
          const [start, end] = match.indices![group]!;
          yield { label: kind, start, end, score: keyGroup ? 0.85 : 0.8, recognizer: this.name };
        }
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
