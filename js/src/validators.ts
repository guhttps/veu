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
