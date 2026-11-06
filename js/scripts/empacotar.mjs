// Gera dist/veu.global.js: um arquivo só, sem dependências, para usar direto no navegador
// (<script src="veu.global.js"> expõe window.veu) e na extensão.
import { build } from "esbuild";

await build({
  entryPoints: ["src/navegador.ts"],
  bundle: true,
  format: "iife",
  globalName: "veu",
  target: ["es2022"],
  minify: true,
  legalComments: "none",
  outfile: "dist/veu.global.js",
});
console.log("dist/veu.global.js");
