import { existsSync, readFileSync } from "node:fs";
import { defineConfig, type Plugin } from "vite";
import { renderPage } from "./src/render";
import type { StatusDoc } from "./src/types";

// The answer is baked into index.html at build time: the page shows today's
// call on first paint, even before (or without) JavaScript.
function statusPath(): string {
  const candidates = [process.env.STATUS_JSON, "public/status.json", "fixtures/status.sample.json"];
  const found = candidates.find((p) => p && existsSync(p));
  if (!found) throw new Error("no status.json to render");
  return found;
}

function inlineStatus(): Plugin {
  return {
    name: "inline-status",
    transformIndexHtml(html) {
      const doc = JSON.parse(readFileSync(statusPath(), "utf8")) as StatusDoc;
      const json = JSON.stringify(doc).replace(/</g, "\\u003c");
      return html.replace("<!--APP-->", renderPage(doc, null)).replace("<!--STATUS-->", json);
    },
  };
}

export default defineConfig({
  base: "./",
  plugins: [inlineStatus()],
  build: { outDir: "dist", emptyOutDir: true },
});
