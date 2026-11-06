// Ponto de entrada do pacote para o navegador (dist/veu.global.js expõe window.veu).
export * from "./index.ts";
export { restoreObj, detectAdapter, Masker, INSTRUCTION } from "./gateway.ts";
export { createFetch } from "./integrations/fetch.ts";
