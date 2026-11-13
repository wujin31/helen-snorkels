// Generates src/indigo/tokens.css from src/indigo/tokens.json (Indigo Ledger,
// copied from the design system). Re-run after replacing tokens.json:
//   node scripts/indigo-tokens.mjs
import { readFileSync, writeFileSync } from "node:fs";

const here = new URL("../src/indigo/", import.meta.url);
const t = JSON.parse(readFileSync(new URL("tokens.json", here), "utf8"));
const themes = t.color.themes.map((x) => x.id);
const [first] = themes;
const scheme = { dark: "dark", contrast: "dark", light: "light", calm: "light" };

const colorFor = (theme) =>
  t.color.tokens
    .map((tok) => {
      const v = typeof tok.value === "string" ? tok.value : tok.value[theme] ?? tok.value[first];
      return `  --${tok.name}: ${v};`;
    })
    .join("\n");

const FAMILIES = ["spacing", "radius", "shadow", "duration", "easing", "opacity", "container", "aspect"];
const others = FAMILIES.flatMap((family) => t[family]?.tokens ?? []);
// Most of these are one value; some (the v11 shadows) differ per theme.
const valueFor = (tok, theme) =>
  typeof tok.value === "object" ? tok.value[theme] ?? tok.value[first] : tok.value;
const plain = others.map((tok) => `  --${tok.name}: ${valueFor(tok, first)};`).join("\n");
const themed = (theme) =>
  others
    .filter((tok) => typeof tok.value === "object")
    .map((tok) => `  --${tok.name}: ${valueFor(tok, theme)};`)
    .join("\n");

const fonts = Object.entries(t.type.families)
  .map(([name, stack]) => `  --font-${name}: ${stack};`)
  .join("\n");

const out = `/* ${t.name}: generated from tokens.json by scripts/indigo-tokens.mjs. Don't edit by hand. */
/* ${themes.join(", ")}; "${first}" is the default, the others are set with data-theme on <html>. */
:root {
  color-scheme: ${scheme[first] ?? "dark"};
${colorFor(first)}
${fonts}
${plain}
}
${themes
  .slice(1)
  .map((id) => `:root[data-theme="${id}"] {\n  color-scheme: ${scheme[id] ?? "dark"};\n${colorFor(id)}\n${themed(id)}\n}`)
  .join("\n")}
`;
writeFileSync(new URL("tokens.css", here), out);
console.log(`wrote tokens.css: ${t.color.tokens.length} colors x ${themes.length} themes`);
