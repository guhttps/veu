// Validação de documentos brasileiros pelos dígitos verificadores (equivalente a veu/validators.py).
import { onlyDigits } from "./text.ts";

export const VALID_DDDS: ReadonlySet<number> = new Set([
  11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38,
  41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69,
  71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99,
]);

const CNPJ_W1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
const CNPJ_W2 = [6, ...CNPJ_W1];

function mod11(values: number[], weights: number[]): number {
  let total = 0;
  for (let i = 0; i < weights.length; i += 1) total += values[i] * weights[i];
  const rest = total % 11;
  return rest < 2 ? 0 : 11 - rest;
}

function repeated(digits: string): boolean {
  return digits.length > 0 && new Set(digits).size === 1;
}

const range = (from: number, to: number, step: number): number[] => {
  const output: number[] = [];
  for (let n = from; step > 0 ? n < to : n > to; n += step) output.push(n);
  return output;
};

/** Resto da divisão por 97 de um número em texto, sem perder precisão em números grandes. */
export function mod97(digits: string): number {
  let rest = 0;
  for (const char of digits) rest = (rest * 10 + Number(char)) % 97;
  return rest;
}

export function cpfCheckDigits(base: string): string {
  const values = [...base].map(Number);
  const first = mod11(values, range(10, 1, -1));
  const second = mod11([...values, first], range(11, 1, -1));
  return `${first}${second}`;
}

export function isValidCpf(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length !== 11 || repeated(digits)) return false;
  return cpfCheckDigits(digits.slice(0, 9)) === digits.slice(9);
}

export function normalizeCnpj(value: string): string {
  return value.replace(/[^0-9A-Za-z]/g, "").toUpperCase();
}

/** CNPJ numérico e alfanumérico: cada caractere vale o código ASCII menos 48. */
export function cnpjCheckDigits(base: string): string {
  const values = [...base.toUpperCase()].map((char) => char.charCodeAt(0) - 48);
  const first = mod11(values, CNPJ_W1);
  const second = mod11([...values, first], CNPJ_W2);
  return `${first}${second}`;
}

export function isValidCnpj(value: string): boolean {
  const cnpj = normalizeCnpj(value);
  if (cnpj.length !== 14 || !/^\d{2}$/.test(cnpj.slice(12))) return false;
  if (!/^[0-9A-Z]{12}$/.test(cnpj.slice(0, 12))) return false;
  if (/^\d+$/.test(cnpj) && repeated(cnpj)) return false;
  return cnpjCheckDigits(cnpj.slice(0, 12)) === cnpj.slice(12);
}

export function pisCheckDigit(base: string): string {
  const weights = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const rest = [...base].reduce((total, char, i) => total + Number(char) * weights[i], 0) % 11;
  const digit = 11 - rest;
  return digit >= 10 ? "0" : String(digit);
}

export function isValidPis(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length !== 11 || repeated(digits)) return false;
  return pisCheckDigit(digits.slice(0, 10)) === digits[10];
}

export function cnhCheckDigits(base: string): string {
  const values = [...base].map(Number);
  let first = values.reduce((total, value, i) => total + value * (9 - i), 0) % 11;
  let discount = 0;
  if (first >= 10) {
    first = 0;
    discount = 2;
  }
  let second = (values.reduce((total, value, i) => total + value * (i + 1), 0) % 11) - discount;
  if (second < 0) second += 11;
  if (second >= 10) second = 0;
  return `${first}${second}`;
}

export function isValidCnh(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length !== 11 || repeated(digits)) return false;
  return cnhCheckDigits(digits.slice(0, 9)) === digits.slice(9);
}

export function tituloCheckDigits(base: string): string {
  const values = [...base].map(Number);
  const uf = values[8] * 10 + values[9];
  let first = values.slice(0, 8).reduce((total, value, i) => total + value * (i + 2), 0) % 11;
  if (first === 10) first = 0;
  else if (first === 0 && (uf === 1 || uf === 2)) first = 1;
  let second = (values[8] * 7 + values[9] * 8 + first * 9) % 11;
  if (second === 10) second = 0;
  else if (second === 0 && (uf === 1 || uf === 2)) second = 1;
  return `${first}${second}`;
}

export function isValidTituloEleitor(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length !== 12 || repeated(digits)) return false;
  const uf = Number(digits.slice(8, 10));
  if (uf < 1 || uf > 28) return false;
  return tituloCheckDigits(digits.slice(0, 10)) === digits.slice(10);
}

export function isValidCns(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length !== 15 || !"12789".includes(digits[0])) return false;
  return [...digits].reduce((total, char, i) => total + Number(char) * (15 - i), 0) % 11 === 0;
}

export function renavamCheckDigit(base: string): string {
  const weights = [3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const total = [...base].reduce((sum, char, i) => sum + Number(char) * weights[i], 0);
  const digit = (total * 10) % 11;
  return digit === 10 ? "0" : String(digit);
}

export function isValidRenavam(value: string): boolean {
  let digits = onlyDigits(value);
  if (digits.length < 9 || digits.length > 11) return false;
  digits = digits.padStart(11, "0");
  if (repeated(digits)) return false;
  return renavamCheckDigit(digits.slice(0, 10)) === digits[10];
}

export function isValidLuhn(value: string): boolean {
  const digits = onlyDigits(value);
  if (digits.length < 13 || digits.length > 19 || repeated(digits)) return false;
  let total = 0;
  [...digits].reverse().forEach((char, position) => {
    let number = Number(char);
    if (position % 2) {
      number *= 2;
      if (number > 9) number -= 9;
    }
    total += number;
  });
  return total % 10 === 0;
}

export function isValidCard(value: string): boolean {
  const digits = onlyDigits(value);
  if (!isValidLuhn(digits) || !"23456".includes(digits[0])) return false;
  return !(digits.length === 14 && isValidCnpj(digits)) && !(digits.length === 15 && isValidCns(digits));
}

export function cnjCheckDigits(number: string, year: string, segment: string, court: string, origin: string): string {
  const rest = mod97(`${number}${year}${segment}${court}${origin}00`);
  return String(98 - rest).padStart(2, "0");
}

export function isValidProcessoCnj(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 20) return false;
  return cnjCheckDigits(d.slice(0, 7), d.slice(9, 13), d[13], d.slice(14, 16), d.slice(16)) === d.slice(7, 9);
}

export function phoneDigits(value: string): string {
  const digits = onlyDigits(value);
  return (digits.length === 12 || digits.length === 13) && digits.startsWith("55") ? digits.slice(2) : digits;
}

export function isValidPhone(value: string): boolean {
  const digits = phoneDigits(value);
  if (digits.length === 11) {
    return VALID_DDDS.has(Number(digits.slice(0, 2))) && digits[2] === "9" && !repeated(digits.slice(3));
  }
  if (digits.length === 10) {
    return VALID_DDDS.has(Number(digits.slice(0, 2))) && "2345".includes(digits[2]) && !repeated(digits.slice(2));
  }
  return false;
}

export function isValidIntlPhone(value: string): boolean {
  const digits = onlyDigits(value);
  return digits.length >= 8 && digits.length <= 15 && !repeated(digits.slice(-8));
}

export function isValidIban(value: string): boolean {
  const compact = value.replace(/[\s-]/g, "").toUpperCase();
  if (!/^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$/.test(compact)) return false;
  const rearranged = compact.slice(4) + compact.slice(0, 4);
  const number = [...rearranged].map((char) => parseInt(char, 36).toString()).join("");
  return mod97(number) === 1;
}

export function isValidIpv4(value: string): boolean {
  const parts = value.split(".");
  if (parts.length !== 4) return false;
  // Como o ipaddress do Python: sem zeros à esquerda e cada parte de 0 a 255.
  if (!parts.every((part) => /^\d{1,3}$/.test(part) && Number(part) <= 255 && !(part.length > 1 && part[0] === "0"))) {
    return false;
  }
  return !(parts[0] === "127" || value === "0.0.0.0");
}

export function isValidIpv6(value: string): boolean {
  if ((value.match(/:/g) ?? []).length < 2) return false;
  const halves = value.split("::");
  if (halves.length > 2) return false;
  const groups = (half: string) => (half === "" ? [] : half.split(":"));
  const head = groups(halves[0]);
  const tail = halves.length === 2 ? groups(halves[1]) : [];
  const all = [...head, ...tail];
  if (!all.every((group) => /^[0-9A-Fa-f]{1,4}$/.test(group))) return false;
  if (halves.length === 2 ? all.length > 7 : all.length !== 8) return false;
  const expanded = halves.length === 2
    ? [...head, ...Array(8 - all.length).fill("0"), ...tail]
    : all;
  const numbers = expanded.map((group) => parseInt(group, 16));
  const zero = numbers.every((n) => n === 0);
  const loopback = numbers.slice(0, 7).every((n) => n === 0) && numbers[7] === 1;
  return !(zero || loopback);
}

const MONTHS: Record<string, number> = {
  janeiro: 1, fevereiro: 2, marco: 3, "março": 3, abril: 4, maio: 5, junho: 6,
  julho: 7, agosto: 8, setembro: 9, outubro: 10, novembro: 11, dezembro: 12,
};

export function parseDate(value: string): Date | null {
  const text = value.trim().toLowerCase();
  let day: number;
  let month: number | undefined;
  let year: number;
  let match = /^(\d{1,2})\s+de\s+([a-zç]+)\s+de\s+(\d{4})$/.exec(text);
  if (match) {
    [day, month, year] = [Number(match[1]), MONTHS[match[2]], Number(match[3])];
  } else if ((match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(text))) {
    [year, month, day] = [Number(match[1]), Number(match[2]), Number(match[3])];
  } else if ((match = /^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})$/.exec(text))) {
    [day, month, year] = [Number(match[1]), Number(match[2]), Number(match[3])];
    if (year < 100) year += year > 30 ? 1900 : 2000;
  } else {
    return null;
  }
  if (!month || month < 1 || month > 12 || year < 1) return null;
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return date;
}

export function isPlausibleBirthdate(value: string): boolean {
  const parsed = parseDate(value);
  return parsed !== null && parsed.getUTCFullYear() >= 1900 && parsed.getUTCFullYear() <= new Date().getFullYear();
}


// Outros países (algoritmos conferidos com o python-stdnum 2.2; equivalentes a veu/validators.py).

const NIF_PT_PREFIXES = new Set(["45", "70", "71", "72", "74", "75", "77", "78", "79", "90", "91", "98", "99"]);
const sumWeights = (weights: readonly number[], digits: string): number =>
  weights.reduce((total, weight, index) => total + weight * Number(digits[index]), 0);
const mod = (value: number, base: number): number => ((value % base) + base) % base;

export function isValidNifPt(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 9 || !("12356".includes(d[0]) || NIF_PT_PREFIXES.has(d.slice(0, 2)))) return false;
  return String(mod(11 - sumWeights([9, 8, 7, 6, 5, 4, 3, 2], d), 11) % 10) === d[8];
}

const ALNUM36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ";

export function isValidCcPt(value: string): boolean {
  const compact = value.replace(/[\s-]/g, "").toUpperCase();
  if (!/^\d{9}[A-Z0-9]{2}\d$/.test(compact)) return false;
  let total = 0;
  [...compact.slice(0, -1)].reverse().forEach((char, index) => {
    let number = ALNUM36.indexOf(char);
    if (index % 2 === 0) {
      number *= 2;
      if (number > 9) number -= 9;
    }
    total += number;
  });
  return String(mod(10 - total, 10)) === compact[11];
}

export function isValidNissPt(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 11 || !"12".includes(d[0])) return false;
  return String(9 - (sumWeights([29, 23, 19, 17, 13, 11, 7, 5, 3, 2], d) % 10)) === d[10];
}

const CUIT_PREFIXES = new Set(["20", "23", "24", "27", "30", "33", "34", "50", "51", "55"]);

export function isValidCuit(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 11 || !CUIT_PREFIXES.has(d.slice(0, 2))) return false;
  return "012345678990"[11 - (sumWeights([5, 4, 3, 2, 7, 6, 5, 4, 3, 2], d) % 11)] === d[10];
}

const CURP_ALPHABET = "0123456789ABCDEFGHIJKLMN&OPQRSTUVWXYZ";
const MX_STATES = new Set([
  "AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG", "GT", "GR", "HG", "JC", "MC", "MN", "MS", "NT", "NL",
  "OC", "PL", "QT", "QR", "SP", "SL", "SR", "TC", "TS", "TL", "VZ", "YN", "ZS", "NE",
]);

function validYymmdd(text: string): boolean {
  const month = Number(text.slice(2, 4));
  const day = Number(text.slice(4, 6));
  if (month < 1 || month > 12 || day < 1) return false;
  return day <= new Date(Date.UTC(2000, month, 0)).getUTCDate(); // 2000 é bissexto: aceita 29/02
}

export function isValidCurp(value: string): boolean {
  const v = value.toUpperCase();
  if (!/^[A-Z]{4}\d{6}[HMX][A-Z]{5}[0-9A-Z]\d$/.test(v)) return false;
  if (!validYymmdd(v.slice(4, 10)) || !MX_STATES.has(v.slice(11, 13))) return false;
  const total = [...v.slice(0, 17)].reduce((sum, char, i) => sum + CURP_ALPHABET.indexOf(char) * (18 - i), 0);
  return String(mod(10 - (total % 10), 10)) === v[17];
}

const RFC_GENERIC = new Set(["XAXX010101000", "XEXX010101000"]);

export function isValidRfc(value: string): boolean {
  const v = value.toUpperCase();
  if (RFC_GENERIC.has(v) || !/^[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}$/u.test(v)) return false;
  return validYymmdd(v.slice(-9, -3));
}

export function isValidRutCl(value: string): boolean {
  const compact = value.replace(/[.\s-]/g, "").toUpperCase();
  if (!/^\d{6,8}[0-9K]$/.test(compact)) return false;
  const body = compact.slice(0, -1);
  const total = [...body].reverse().reduce((sum, n, i) => sum + Number(n) * (2 + (i % 6)), 0);
  const rest = 11 - (total % 11);
  return (rest === 11 ? "0" : rest === 10 ? "K" : String(rest)) === compact.slice(-1);
}

export function isValidCiUy(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 8) return false;
  return String(mod(10 - (sumWeights([2, 9, 8, 7, 6, 3, 4], d) % 10), 10)) === d[7];
}

export function isValidRutUy(value: string): boolean {
  const d = onlyDigits(value);
  const register = Number(d.slice(0, 2));
  if (d.length !== 12 || register < 1 || register > 22 || d.slice(2, 8) === "000000" || d.slice(8, 11) !== "001") return false;
  const check = mod(-sumWeights([4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2], d), 11);
  return check !== 10 && String(check) === d[11];
}

const NIT_WEIGHTS = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71];

export function isValidNitCo(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length < 8 || d.length > 16) return false;
  const body = [...d.slice(0, -1)].reverse();
  const total = body.reduce((sum, n, i) => sum + (i < NIT_WEIGHTS.length ? NIT_WEIGHTS[i] * Number(n) : 0), 0);
  return "01987654321"[total % 11] === d.slice(-1);
}

export function isValidRucPe(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 11 || !["10", "15", "17", "20"].includes(d.slice(0, 2))) return false;
  return String((11 - (sumWeights([5, 4, 3, 2, 7, 6, 5, 4, 3, 2], d) % 11)) % 10) === d[10];
}

const ecProvince = (d: string): boolean => {
  const province = Number(d.slice(0, 2));
  return (province >= 1 && province <= 24) || d.slice(0, 2) === "30" || d.slice(0, 2) === "50";
};

export function isValidCiEc(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 10 || !ecProvince(d) || Number(d[2]) >= 6) return false;
  let total = 0;
  for (let i = 0; i < 9; i += 1) {
    const product = Number(d[i]) * (i % 2 === 0 ? 2 : 1);
    total += product > 9 ? product - 9 : product;
  }
  return String(mod(10 - (total % 10), 10)) === d[9];
}

export function isValidRucEc(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length !== 13 || !ecProvince(d)) return false;
  if (Number(d[2]) < 6) return isValidCiEc(d.slice(0, 10)) && d.slice(10) !== "000";
  if (d[2] === "6") return sumWeights([3, 2, 7, 6, 5, 4, 3, 2, 1], d) % 11 === 0 && d.slice(9) !== "0000";
  if (d[2] === "9") return sumWeights([4, 3, 2, 7, 6, 5, 4, 3, 2, 1], d) % 11 === 0 && d.slice(10) !== "000";
  return false;
}

export function isValidRucPy(value: string): boolean {
  const d = onlyDigits(value);
  if (d.length < 6 || d.length > 9) return false;
  const total = [...d.slice(0, -1)].reverse().reduce((sum, n, i) => sum + Number(n) * (2 + i), 0);
  return String(mod(-total, 11) % 10) === d.slice(-1);
}

export const isValidRuc = (value: string): boolean => isValidRucPe(value) || isValidRucEc(value) || isValidRucPy(value);
export const isValidCedula = (value: string): boolean => isValidCiUy(value) || isValidCiEc(value);

const RIF_LETTERS: Record<string, number> = { V: 4, E: 8, J: 12, P: 16, G: 20 };

export function isValidRif(value: string): boolean {
  const compact = value.replace(/[\s-]/g, "").toUpperCase();
  if (!/^[VEJPG]\d{9}$/.test(compact)) return false;
  const total = RIF_LETTERS[compact[0]] + sumWeights([3, 2, 7, 6, 5, 4, 3, 2], compact.slice(1));
  return "00987654321"[total % 11] === compact[9];
}
