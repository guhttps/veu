// Gera dist/nodes/Veu/Veu.node.js com a biblioteca do Véu embutida (o n8n-workflow fica de fora: o n8n já tem).
import { copyFileSync, mkdirSync } from "node:fs";
import { build } from "esbuild";

await build({
  entryPoints: ["nodes/Veu/Veu.node.ts"],
  bundle: true,
  platform: "node",
  format: "cjs",
  target: ["node20"],
  external: ["n8n-workflow"],
  legalComments: "none",
  outfile: "dist/nodes/Veu/Veu.node.js",
});
mkdirSync("dist/nodes/Veu", { recursive: true });
copyFileSync("nodes/Veu/veu.svg", "dist/nodes/Veu/veu.svg");
console.log("dist/nodes/Veu/Veu.node.js");
