// Renders the whole page from a StatusDoc as an HTML string. Runs at build time
// (so the answer is in the first paint, JS or not) and again in the browser
// when a fresher status.json arrives. Every data string goes through esc().

import { directionDial } from "./arrows";
import { camSection } from "./cam";
import { STALE_AFTER_MIN } from "./config";
import { ago, clock, compass, dayName, esc, ft, range } from "./format";
import { VERDICT_WORD, verdictIcon } from "./icons";
import { tideChart } from "./tide";
import type { Factor, SpotStatus, StatusDoc } from "./types";

const CONFIDENCE_TEXT = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" };
const EFFECT_WORD = { "+": "helps", "-": "hurts", "~": "neutral" };

export function hero(doc: StatusDoc): SpotStatus | null {
  return doc.spots.find((s) => s.id === doc.best_bet) ?? doc.spots[0] ?? null;
}

function windowText(spot: SpotStatus): string {
  if (!spot.window) return "";
  const text = range(spot.window.start, spot.window.end);
  return spot.window_day === "tomorrow" ? `Tomorrow ${text}` : text;
}

function short(name: string): string {
  return name.split(" / ")[0];
}

function confidenceDots(level: SpotStatus["confidence"]): string {
  const n = { low: 1, medium: 2, high: 3 }[level];
  const dots = [1, 2, 3].map((i) => `<span class="dot${i <= n ? " on" : ""}"></span>`).join("");
  return `<span class="conf" title="${CONFIDENCE_TEXT[level]}"><span class="dots" aria-hidden="true">${dots}</span>${CONFIDENCE_TEXT[level]}</span>`;
}

function withoutVis(reason: string): string {
  // The vis range has its own chip; don't repeat it at the start of the reason.
  return reason.replace(/^~\d+–\d+ ft vis(, |$)/, "");
}

function readings(spot: SpotStatus): string {
  const c = spot.conditions;
  const swell =
    c.hs_ft == null
      ? "–"
      : `${c.hs_ft < 1 ? "<1" : ft(c.hs_ft)} ft${c.tp_s ? ` · ${Math.round(c.tp_s)} s` : ""} ${compass(c.swell_dir_deg)}`;
  const wind = c.wind_kt == null ? "–" : `${Math.round(c.wind_kt)} kt ${compass(c.wind_dir_deg)}`;
  const trend = c.tide_trend === "incoming" ? "rising" : c.tide_trend === "outgoing" ? "falling" : c.tide_trend ?? "";
  const tide = c.tide_ft == null ? "–" : `${ft(c.tide_ft)} ft ${trend}`;
  return `<dl class="readings">
      <div class="reading">${directionDial(c.swell_dir_deg, spot.shore_normal_deg, "Swell")}<dt>Swell</dt><dd>${esc(swell)}</dd></div>
      <div class="reading">${directionDial(c.wind_dir_deg, spot.shore_normal_deg, "Wind")}<dt>Wind</dt><dd>${esc(wind)}</dd></div>
      <div class="reading reading-tide"><dt>Tide now</dt><dd>${esc(tide)}</dd></div>
    </dl>`;
}

function why(spot: SpotStatus): string {
  const items = [...spot.gates.map((g) => ({ label: "No-go", effect: "-" as const, detail: g })), ...spot.factors];
  if (!items.length) return "";
  const source = spot.conditions.wave_source;
  const note = source
    ? `<p class="fine">Waves: ${esc(source === "mop" ? "CDIP MOP model at this spot" : source === "buoy" ? "Scripps Nearshore buoy" : "Open-Meteo offshore model")}. Visibility is an estimate from waves, pier turbidity and chlorophyll; there's no cam reading yet.</p>`
    : "";
  return `<details class="why"><summary>Why</summary>${factorList(items)}${note}</details>`;
}

/** The answer, compact, above the cam: verdict, where, when, and why in a line. */
function verdictBar(doc: StatusDoc, featured: SpotStatus | null): string {
  if (!featured) {
    const verdict = doc.spots.some((s) => s.verdict === "no") ? "no" : "unknown";
    const title = verdict === "no" ? "Not today" : "Can't tell right now";
    return `
  <section class="verdict v-${verdict}" id="verdict" aria-labelledby="hero-title">
    ${verdictIcon(verdict, 40)}
    <div class="verdict-text">
      <h1 id="hero-title" class="verdict-word">${title}</h1>
      <p class="verdict-reason">${esc(doc.summary)}</p>
    </div>
  </section>`;
  }
  const when = windowText(featured);
  const reason = withoutVis(featured.reason);
  return `
  <section class="verdict v-${featured.verdict}" id="verdict" aria-labelledby="hero-title">
    ${verdictIcon(featured.verdict, 40)}
    <div class="verdict-text">
      <h1 id="hero-title"><span class="verdict-word">${VERDICT_WORD[featured.verdict]}</span> <span class="verdict-where">${esc(short(featured.name))}</span></h1>
      ${when ? `<p class="verdict-when">${esc(when)}</p>` : ""}
      ${reason ? `<p class="verdict-reason">${esc(reason)}</p>` : ""}
    </div>
  </section>`;
}

function factorList(factors: Factor[]): string {
  if (!factors.length) return "";
  return `<ul class="factors">${factors
    .map(
      (f) =>
        `<li class="f f-${f.effect === "+" ? "plus" : f.effect === "-" ? "minus" : "neutral"}">` +
        `<span class="f-mark" aria-label="${EFFECT_WORD[f.effect]}">${f.effect === "-" ? "−" : f.effect}</span>` +
        `<span class="f-label">${esc(f.label)}</span> <span class="f-detail">${esc(f.detail)}</span></li>`,
    )
    .join("")}</ul>`;
}

function spotCard(spot: SpotStatus, featured = false): string {
  const when = windowText(spot);
  const sub = featured
    ? ""
    : [spot.vis_ft ? `~${spot.vis_ft[0]}–${spot.vis_ft[1]} ft vis` : "", when ? `best ${when}` : ""].filter(Boolean).join(" · ");
  const meta = featured
    ? `<div class="spot-meta">${spot.vis_ft ? `<span class="chip">~${spot.vis_ft[0]}–${spot.vis_ft[1]} ft vis</span>` : ""}${confidenceDots(spot.confidence)}</div>`
    : "";
  return `
  <article class="spot${featured ? " featured" : ""} v-${spot.verdict}" id="spot-${esc(spot.id)}">
    <header class="spot-head">
      <h2>${esc(spot.name)}</h2>
      <span class="verdict-chip">${verdictIcon(spot.verdict, 20)}${VERDICT_WORD[spot.verdict]}</span>
    </header>
    <p class="spot-reason">${esc(withoutVis(spot.reason) || spot.reason)}</p>
    ${sub ? `<p class="spot-sub">${esc(sub)}</p>` : ""}
    ${meta}
    ${readings(spot)}
    ${why(spot)}
  </article>`;
}

function waterSection(doc: StatusDoc): string {
  const d = doc.day;
  const rows: string[] = [];
  if (d.water_temp_f != null) {
    rows.push(`<div><dt>Water</dt><dd>${Math.round(d.water_temp_f)}°F${d.wetsuit ? ` · ${esc(d.wetsuit)}` : ""}</dd></div>`);
  }
  if (d.turbidity_ntu != null) {
    rows.push(`<div><dt>Pier turbidity</dt><dd>${esc(d.turbidity_ntu.toFixed(1))} NTU</dd></div>`);
  }
  if (d.chlorophyll_ug_l != null) {
    rows.push(`<div><dt>Chlorophyll</dt><dd>${esc(d.chlorophyll_ug_l.toFixed(1))} µg/L</dd></div>`);
  }
  rows.push(`<div><dt>Daylight</dt><dd>${esc(range(d.sunrise, d.sunset))}</dd></div>`);
  const alerts = d.alerts.length
    ? `<p class="alerts" role="note"><strong>NWS:</strong> ${d.alerts.map(esc).join(", ")}</p>`
    : "";
  return `<section class="panel" aria-labelledby="water-title"><h2 id="water-title">Water today</h2><dl class="facts">${rows.join("")}</dl>${alerts}</section>`;
}

function tideSection(doc: StatusDoc, now: Date): string {
  const best = hero(doc);
  const window = best && best.window_day !== "tomorrow" ? best.window : null;
  const turns = doc.day.tide_turns.length
    ? `<details class="table-view"><summary>Tide table</summary><table><tbody>${doc.day.tide_turns
        .map((t) => `<tr><th scope="row">${t.kind === "high" ? "High" : "Low"}</th><td>${esc(clock(t.time))}</td><td>${esc(ft(t.ft))} ft</td></tr>`)
        .join("")}</tbody></table></details>`
    : "";
  const legend = window
    ? `<p class="fine"><span class="key-window" aria-hidden="true"></span>Best window at ${esc(short(best!.name))}</p>`
    : "";
  return `<section class="panel" aria-labelledby="tide-title"><h2 id="tide-title">Tide · ${esc(dayName(doc.day.sunrise))} (ft, MLLW)</h2>${tideChart(doc.day, window, now)}${legend}${turns}</section>`;
}

function freshness(doc: StatusDoc, now: Date | null): string {
  const stale = doc.sources.filter((s) => s.stale);
  const age = now ? ` · ${ago(doc.generated_at, now)}` : "";
  const staleList = stale.length
    ? `<ul class="stale-list">${stale.map((s) => `<li>${esc(s.label)}${s.error ? ` <span class="fine">(${esc(shortError(s.error))})</span>` : ""}</li>`).join("")}</ul>`
    : `<p class="fine">All ${doc.sources.length} sources fresh.</p>`;
  return `
  <footer class="foot" id="foot">
    <p>Updated ${esc(clock(doc.generated_at))}${esc(age)}.${doc.cam?.info_url ? ` <a href="${esc(doc.cam.info_url)}" rel="noopener">Scripps PierViz ↗</a>` : ""}</p>
    <details class="sources"><summary>${stale.length ? `${stale.length} source${stale.length > 1 ? "s" : ""} stale or down` : "Data sources"}</summary>${staleList}
      <p class="fine">NOAA CO-OPS & NWS, CDIP (Scripps), SCCOOS, Open-Meteo, County of San Diego DEHQ. Estimates, not guarantees.</p>
    </details>
    <p class="disclaimer">${esc(doc.disclaimer)}</p>
  </footer>`;
}

function shortError(error: string): string {
  return error.replace(/^\w+Error: /, "").slice(0, 90);
}

export function staleBanner(doc: StatusDoc, now: Date): string {
  const minutes = (now.getTime() - Date.parse(doc.generated_at)) / 60000;
  if (minutes < STALE_AFTER_MIN) return "";
  return `<p class="banner" role="alert">These conditions are from ${esc(clock(doc.generated_at))} (${esc(ago(doc.generated_at, now))}). The updater may be down; treat them as old.</p>`;
}

/**
 * The page body. `now` is null at build time (no relative ages baked in).
 * Top-level regions carry ids so the browser can repaint around a playing
 * cam player without reloading it (main.ts).
 */
export function renderPage(doc: StatusDoc, now: Date | null): string {
  const featured = doc.spots.find((s) => s.id === doc.best_bet) ?? null;
  const others = doc.spots.filter((s) => s !== featured);
  const clockNow = now ?? new Date(doc.generated_at);
  return `
  <header class="top" id="top">
    <span class="brand">Snorkel Status <span class="muted">· La Jolla</span></span>
    <span class="updated">Updated ${esc(clock(doc.generated_at))}</span>
  </header>
  <div id="banner">${now ? staleBanner(doc, now) : ""}</div>
  <main>
    ${verdictBar(doc, featured)}
    ${doc.cam ? camSection(doc.cam, clockNow) : ""}
    <div id="details">
      ${featured ? spotCard(featured, true) : ""}
      ${others.length ? `<h2 class="section-title">${featured ? "Other spots" : "Spots"}</h2><div class="spots">${others.map((s) => spotCard(s)).join("")}</div>` : ""}
      ${tideSection(doc, clockNow)}
      ${waterSection(doc)}
    </div>
  </main>
  ${freshness(doc, now)}`;
}
