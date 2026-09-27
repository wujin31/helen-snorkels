import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { camSection, camState } from "../src/cam";
import { esc, range } from "../src/format";
import { renderPage, staleBanner } from "../src/render";
import type { StatusDoc } from "../src/types";

const sample: StatusDoc = JSON.parse(readFileSync(new URL("../fixtures/status.sample.json", import.meta.url), "utf8"));

function clone(): StatusDoc {
  return structuredClone(sample);
}

describe("renderPage", () => {
  it("leads with the best bet's verdict and window, then the cam", () => {
    const html = renderPage(sample, null);
    expect(html).toContain('<span class="verdict-word">Maybe</span> <span class="verdict-where">Marine Room</span>');
    expect(html).toContain('<p class="verdict-when">7:00–8:30 am</p>');
    expect(html.indexOf('id="verdict"')).toBeLessThan(html.indexOf('id="cam"'));
    expect(html.indexOf('id="cam"')).toBeLessThan(html.indexOf('id="details"'));
    expect(html).toContain("Other spots");
  });

  it("asks nothing of the reader and talks only to its own data", () => {
    const html = renderPage(sample, new Date(sample.generated_at));
    expect(html).not.toContain("Log a swim");
    expect(html).not.toContain("supabase.co");
    expect(html).not.toMatch(/<(form|input|textarea|dialog)\b/);
  });

  it("still renders documents from before the cam section", () => {
    const doc = clone();
    delete doc.cam;
    const html = renderPage(doc, null);
    expect(html).not.toContain('id="cam"');
    expect(html).toContain('id="verdict"');
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

describe("cam", () => {
  const cam = sample.cam!;
  const noon = new Date("2026-09-27T19:00:00Z");
  const night = new Date("2026-09-27T09:00:00Z");

  it("is live between cam light and dark outside it", () => {
    expect(camState(cam, noon)).toEqual({ kind: "live" });
    expect(camState(cam, night)).toEqual({ kind: "dark", until: cam.light[0].start });
    expect(camState(cam, new Date("2026-09-28T03:00:00Z"))).toEqual({ kind: "dark", until: cam.light[1].start });
    expect(camState(cam, new Date("2026-09-30T03:00:00Z"))).toEqual({ kind: "dark", until: null });
  });

  it("links to the live stream in a new tab, with no player it isn't allowed to frame", () => {
    const html = camSection(cam, noon);
    expect(html).toContain('data-state="live"');
    expect(html).toContain(`href="${cam.watch_url}" target="_blank" rel="noopener"`);
    expect(html).toContain("Watch live");
    expect(html).not.toContain("cam-player");
    expect(html).not.toContain("<img");
    expect(html).toContain("Picture in Picture"); // how to keep it on screen with the page
  });

  it("says when a dark cam wakes up", () => {
    const html = camSection(cam, night);
    expect(html).toContain('data-state="dark"');
    expect(html).toContain("The cam's dark until 6:52 am");
    expect(html).toContain("Open it anyway");
    expect(html).not.toContain("Watch live");
  });

  it("offers an inline player only when one is allowed, and only in daylight", () => {
    const allowed = { ...cam, embed_url: "https://portal.hdontap.com/s/embed/?stream=scripps_pier-underwater-CUST" };
    expect(camSection(allowed, noon)).toContain(`class="cam-player" data-src="${esc(allowed.embed_url)}"`);
    expect(camSection(allowed, night)).not.toContain("cam-player");
  });

  it("shows the cam model's reading when there is one", () => {
    const read = { ...cam, reading: { time: "2026-09-27T21:15:00Z", vis_ft: [11, 14] as [number, number], pilings_visible: 3, pilings_total: 4 } };
    expect(camSection(read, noon)).toContain("~11–14 ft · 3 of 4 pilings · 2:15 pm");
  });

  it("escapes cam strings", () => {
    const bad = { ...cam, caption: "<script>x()</script>", watch_url: 'https://x.test/"onmouseover="y' };
    const html = camSection(bad, noon);
    expect(html).not.toContain("<script>x");
    expect(html).not.toContain('"onmouseover="');
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
