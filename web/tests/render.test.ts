import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { esc, range } from "../src/format";
import { renderPage, staleBanner } from "../src/render";
import type { StatusDoc } from "../src/types";

const sample: StatusDoc = JSON.parse(readFileSync(new URL("../fixtures/status.sample.json", import.meta.url), "utf8"));

function clone(): StatusDoc {
  return structuredClone(sample);
}

describe("renderPage", () => {
  it("leads with the best bet's verdict and window, then the details", () => {
    const html = renderPage(sample, null);
    expect(html).toContain('<span class="verdict-word">Maybe</span> <span class="verdict-where">Marine Room</span>');
    expect(html).toContain('<p class="verdict-when">7:00–8:30 am</p>');
    expect(html.indexOf('id="verdict"')).toBeLessThan(html.indexOf('id="details"'));
    expect(html).toContain("Other spots");
    expect(html).toContain('<span class="muted">· San Diego</span>');
  });

  it("asks nothing of the reader and talks only to its own data", () => {
    const html = renderPage(sample, new Date(sample.generated_at));
    expect(html).not.toContain("Log a swim");
    expect(html).not.toContain("supabase.co");
    expect(html).not.toMatch(/<(form|input|textarea|dialog)\b/);
  });

  it("links to Scripps' own cam page and embeds nothing", () => {
    const html = renderPage(sample, null);
    expect(html).toContain('href="https://coollab.ucsd.edu/pierviz/"');
    expect(html).not.toMatch(/<(iframe|video|img)\b/);
  });

  it("escapes every data string", () => {
    const doc = clone();
    doc.spots[0].reason = '<img src=x onerror="alert(1)">';
    doc.day.alerts = ["<script>bad()</script>"];
    const html = renderPage(doc, null);
    expect(html).not.toContain("<img src=x");
    expect(html).not.toContain("<script>bad");
    expect(html).toContain("&lt;script&gt;bad()&lt;/script&gt;");
  });

  it("renders every verdict with a word, not color alone", () => {
    for (const verdict of ["yes", "maybe", "no", "unknown"] as const) {
      const doc = clone();
      doc.spots[0].verdict = verdict;
      const html = renderPage(doc, null);
      expect(html).toMatch(/Yes|Maybe|No|Can't tell|Not today/);
    }
  });

  it("falls back to an overall hero when nothing is callable", () => {
    const doc = clone();
    doc.best_bet = null;
    doc.spots.forEach((s) => (s.verdict = "unknown"));
    doc.summary = "Not enough fresh data to call it right now.";
    const html = renderPage(doc, null);
    expect(html).toContain("Can't tell right now");
    expect(html).not.toContain("Other spots");
  });

  it("never calls conditions safe", () => {
    expect(renderPage(sample, new Date(sample.generated_at)).toLowerCase()).not.toMatch(/\bsafe\b/);
  });
});

describe("spot list", () => {
  function many(): StatusDoc {
    const doc = clone();
    const base = doc.spots[1];
    const extra = [
      { id: "swamis", name: "Swami's", area: "North County", verdict: "no" as const, difficulty: "moderate" },
      { id: "sea-caves", name: "La Jolla Sea Caves", area: "La Jolla", verdict: "maybe" as const, difficulty: "advanced" },
      { id: "sunset-cliffs", name: "Sunset Cliffs", area: "Point Loma & Mission Bay", verdict: "no" as const, difficulty: "advanced" },
    ];
    for (const e of extra) doc.spots.push({ ...structuredClone(base), ...e });
    return doc;
  }

  it("groups other spots by area, La Jolla first, as rows that open", () => {
    const html = renderPage(many(), null);
    const la = html.indexOf('<h3 class="area">La Jolla</h3>');
    const pl = html.indexOf('<h3 class="area">Point Loma &amp; Mission Bay</h3>');
    const nc = html.indexOf('<h3 class="area">North County</h3>');
    expect(la).toBeGreaterThan(-1);
    expect(la).toBeLessThan(pl);
    expect(pl).toBeLessThan(nc);
    expect(html).toContain('<details class="row v-no" id="spot-swamis">');
    expect(html.match(/<details class="row /g)?.length).toBe(4); // everything but the best bet
  });

  it("tags advanced spots and summarizes each row in one line", () => {
    const html = renderPage(many(), null);
    expect(html).toContain('La Jolla Sea Caves <span class="tag">Advanced</span>');
    expect(html).toMatch(/id="spot-sea-caves">[\s\S]*?<span class="row-sub">~\d+–\d+ ft vis/);
  });
});

describe("water panel", () => {
  it("shows the NWS surf forecast when there is one", () => {
    const doc = clone();
    doc.day.surf_forecast = "Surf 2–4 ft · moderate rip current risk";
    expect(renderPage(doc, null)).toContain("<dt>NWS surf</dt><dd>Surf 2–4 ft · moderate rip current risk</dd>");
    delete doc.day.surf_forecast;
    expect(renderPage(doc, null)).not.toContain("NWS surf");
  });
});

describe("staleness", () => {
  it("warns when the data is old", () => {
    const t = Date.parse(sample.generated_at);
    expect(staleBanner(sample, new Date(t + 30 * 60_000))).toBe("");
    expect(staleBanner(sample, new Date(t + 4 * 3600_000))).toContain("4 h ago");
  });
});

describe("format", () => {
  it("formats windows in Pacific time", () => {
    expect(range("2026-09-27T14:00:00Z", "2026-09-27T15:30:00Z")).toBe("7:00–8:30 am");
    expect(range("2026-09-27T18:30:00Z", "2026-09-27T20:00:00Z")).toBe("11:30 am–1:00 pm");
    expect(range("2026-12-01T15:00:00Z", "2026-12-01T16:30:00Z")).toBe("7:00–8:30 am"); // PST
  });

  it("escapes html", () => {
    expect(esc(`<a href="x">'&'</a>`)).toBe("&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;");
  });
});
