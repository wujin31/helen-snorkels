// Renders the whole page from a StatusDoc as an HTML string. Runs at build time
// (so the answer is in the first paint, JS or not) and again in the browser
// when a fresher status.json arrives. Every data string goes through esc().

import { directionDial } from "./arrows";
import { STALE_AFTER_MIN } from "./config";
import { ago, clock, compass, dayName, esc, ft, range } from "./format";
import { stamp } from "./icons";
import { tideChart } from "./tide";
import type { Factor, SpotStatus, StatusDoc } from "./types";

const CONFIDENCE_TEXT = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" };
const VIS_SCALE_FT = 40; // the visibility estimate's ceiling (config max_ft)
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

/** Indigo Ledger RangeBar: the visibility estimate as its interval, never one number. */
function visRange(spot: SpotStatus): string {
  const confidence = CONFIDENCE_TEXT[spot.confidence];
  if (!spot.vis_ft) return `<p class="il-label conf">${confidence}</p>`;
  const [lo, hi] = spot.vis_ft;
  const pct = (v: number) => `${Math.max(0, Math.min(100, (v / VIS_SCALE_FT) * 100)).toFixed(1)}%`;
  return `<div class="il-range vis">
      <div class="il-range-head"><span class="il-label">Visibility estimate</span><span class="il-range-val">${lo}–${hi} ft</span></div>
      <div class="il-range-track" role="img" aria-label="Visibility estimate: ${lo} to ${hi} ft"><span class="il-range-band" style="left:${pct(lo)};right:calc(100% - ${pct(hi)})"></span></div>
      <div class="il-range-foot"><span>0 ft</span><span class="conf">${confidence}</span><span>${VIS_SCALE_FT} ft</span></div>
    </div>`;
}

function withoutVis(reason: string): string {
  // The vis range has its own bar; don't repeat it at the start of the reason.
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
    ? `<p class="fine">Waves: ${esc(source === "mop" ? "CDIP MOP model at this spot" : source === "buoy" ? "Scripps Nearshore buoy" : "Open-Meteo offshore model")}. Visibility is an estimate from waves, pier turbidity, chlorophyll, rain and wind.</p>`
    : "";
  return `<details class="why"><summary>Why</summary>${factorList(items)}${note}</details>`;
}

/** The answer, first: verdict, where, when, and why in a line. */
function verdictBar(doc: StatusDoc, featured: SpotStatus | null, now: Date | null): string {
  const dead = doc.sources.filter((s) => !s.ok).length;
  const age = now ? `<span class="verdict-age">Updated ${esc(ago(doc.generated_at, now))}</span>` : "";
  const badge = dead
    ? ` <a class="verdict-dead" href="#foot" role="alert">${dead} source${dead > 1 ? "s" : ""} down</a>`
    : "";
  const meta = age || badge ? `<p class="verdict-meta il-label">${age}${badge}</p>` : "";
  if (!featured) {
    const verdict = doc.spots.some((s) => s.verdict === "no") ? "no" : "unknown";
    const title = verdict === "no" ? "Not today" : "Can't tell right now";
    return `
  ${heroBand(verdict, `
      <p class="verdict-stamp">${stamp(verdict === "no" ? "no" : "unknown", "stamp-lg")}</p>
      <h1 id="hero-title" class="verdict-word">${title}</h1>
      <p class="verdict-reason">${esc(doc.summary)}</p>
      ${meta}`)}`;
  }
  const when = windowText(featured);
  const reason = withoutVis(featured.reason);
  return `
  ${heroBand(featured.verdict, `
      <h1 id="hero-title">${stamp(featured.verdict, "verdict-word stamp-lg")} <span class="verdict-where">${esc(short(featured.name))}</span></h1>
      ${when ? `<p class="verdict-when">${esc(when)}</p>` : ""}
      ${reason ? `<p class="verdict-reason">${esc(reason)}</p>` : ""}
      ${meta}`)}`;
}

/**
 * Indigo Ledger Band: a full-bleed indigo block, the page's opening. The giant
 * 水 (water) is a cropped watermark and the vertical 今天 (today) a margin
 * title; both are decoration, hidden from screen readers, and off in Calm.
 */
function heroBand(verdict: string, body: string): string {
  return `
  <section class="il-band il-band-indigo il-band-has-v verdict v-${verdict}" id="verdict" aria-labelledby="hero-title">
    <span class="il-band-hanzi" lang="zh-Hant-TW" aria-hidden="true">水</span>
    <div class="il-band-inner">
      <span class="il-band-v" lang="zh-Hant-TW" aria-hidden="true">今天</span>
      <div class="il-band-body hero-body">${body}
      </div>
    </div>
  </section>`;
}

function factorList(factors: Factor[]): string {
  if (!factors.length) return "";
  return `<ul class="factors">${factors
    .map(
      (f) =>
        `<li class="f f-${f.effect === "+" ? "plus" : f.effect === "-" ? "minus" : "neutral"}">` +
        `<span class="f-mark" aria-label="${EFFECT_WORD[f.effect]}" title="${EFFECT_WORD[f.effect]}">${f.effect === "-" ? "−" : f.effect}</span>` +
        `<span class="f-label">${esc(f.label)}</span> <span class="f-detail">${esc(f.detail)}</span></li>`,
    )
    .join("")}</ul>`;
}

/** The best bet's full card, right under the answer. */
function featuredCard(spot: SpotStatus): string {
  return `
  <article class="il-card il-card-paper spot featured v-${spot.verdict}" id="spot-${esc(spot.id)}">
    <header class="spot-head">
      <h2 class="il-card-title">${esc(spot.name)}</h2>
      ${stamp(spot.verdict)}
    </header>
    <p class="spot-reason">${esc(withoutVis(spot.reason) || spot.reason)}</p>
    ${visRange(spot)}
    ${readings(spot)}
    ${why(spot)}
  </article>`;
}

const AREA_ORDER = ["La Jolla", "Point Loma & Mission Bay", "North County"];

/** One spot as a one-line row that opens to its full detail. */
function spotRow(spot: SpotStatus): string {
  const when = windowText(spot);
  const go = spot.verdict === "yes" || spot.verdict === "maybe";
  const win = go && when ? `<span class="chip window">Best ${esc(when)}</span>` : "";
  const sub = go
    ? [spot.vis_ft ? `~${spot.vis_ft[0]}–${spot.vis_ft[1]} ft vis` : "", when].filter(Boolean).join(" · ")
    : withoutVis(spot.reason) || spot.reason;
  const tag = spot.difficulty === "advanced" ? ` <span class="tag">Advanced</span>` : "";
  return `
  <details class="row v-${spot.verdict}" id="spot-${esc(spot.id)}">
    <summary>
      <span class="row-main"><span class="row-name">${esc(spot.name)}${tag}</span><span class="row-sub">${esc(sub)}</span>${win}</span>
      <span class="row-verdict">${stamp(spot.verdict)}</span>
    </summary>
    <div class="row-body">
      ${go ? `<p class="spot-reason">${esc(withoutVis(spot.reason) || spot.reason)}</p>` : ""}
      ${readings(spot)}
      ${why(spot)}
    </div>
  </details>`;
}

/** Every spot but the featured one, grouped by area in a fixed order. */
function spotList(spots: SpotStatus[], featured: boolean): string {
  if (!spots.length) return "";
  const areas = [...new Set([...AREA_ORDER, ...spots.map((s) => s.area ?? "La Jolla")])];
  const groups = areas
    .map((area) => ({ area, spots: spots.filter((s) => (s.area ?? "La Jolla") === area) }))
    .filter((g) => g.spots.length);
  return `
  <section class="spot-list" aria-labelledby="spots-title">
    <h2 class="section-title" id="spots-title">${featured ? "Other spots" : "Spots"}</h2>
    ${groups
      .map((g) => `<h3 class="area">${esc(g.area)}</h3><div class="rows">${g.spots.map(spotRow).join("")}</div>`)
      .join("")}
  </section>`;
}

function waterSection(doc: StatusDoc): string {
  const d = doc.day;
  const rows: string[] = [];
  if (d.water_temp_f != null) {
    rows.push(spec("Water", `${Math.round(d.water_temp_f)}°F`, d.wetsuit ? esc(d.wetsuit) : ""));
  }
  if (d.turbidity_ntu != null) {
    rows.push(spec("Pier turbidity", `${esc(d.turbidity_ntu.toFixed(1))} NTU`));
  }
  if (d.chlorophyll_ug_l != null) {
    rows.push(spec("Chlorophyll", `${esc(d.chlorophyll_ug_l.toFixed(1))} µg/L`));
  }
  if (d.surf_forecast) {
    rows.push(spec("NWS surf", esc(d.surf_forecast)));
  }
  rows.push(spec("Daylight", esc(range(d.sunrise, d.sunset))));
  const alerts = d.alerts.length
    ? `<div class="il-notice il-notice-caution alerts" role="status"><p class="il-notice-title">NWS: ${d.alerts.map(esc).join(", ")}</p></div>`
    : "";
  return `<section class="water" aria-labelledby="water-title"><h2 id="water-title" class="section-title">Water</h2>${alerts}<dl class="il-spec facts">${rows.join("")}</dl></section>`;
}

/** One SpecList row: label, dotted leader, value, optional note. Values arrive escaped. */
function spec(label: string, value: string, note = ""): string {
  return `<div class="il-spec-row"><dt>${label}</dt><span class="il-spec-leader" aria-hidden="true"></span><dd>${value}${note ? `<span class="il-spec-note">${note}</span>` : ""}</dd></div>`;
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
  return `
  <section class="il-band il-band-tile tide-band" aria-labelledby="tide-title">
    <span class="il-band-hanzi" lang="zh-Hant-TW" aria-hidden="true">月</span>
    <div class="il-band-inner">
      <h2 id="tide-title" class="band-title">Tide · ${esc(dayName(doc.day.sunrise))} <span class="il-label">ft, MLLW</span></h2>
      <div class="tide-wrap">${tideChart(doc.day, window, now)}</div>${legend}${turns}
    </div>
  </section>`;
}

function freshness(doc: StatusDoc, now: Date | null): string {
  const stale = doc.sources.filter((s) => s.stale);
  const age = now ? ` · ${ago(doc.generated_at, now)}` : "";
  const staleList = stale.length
    ? `<ul class="stale-list">${stale.map((s) => `<li>${esc(s.label)}${s.error ? ` <span class="fine">(${esc(shortError(s.error))})</span>` : ""}</li>`).join("")}</ul>`
    : `<p class="fine">All ${doc.sources.length} sources fresh.</p>`;
  return `
  ${readingSettings()}
  <footer class="il-footer foot" id="foot">
    <div class="il-footer-text">
      <p>Updated ${esc(clock(doc.generated_at))} Pacific time${esc(age)}.</p>
      <details class="sources"><summary>${stale.length ? `${stale.length} source${stale.length > 1 ? "s" : ""} stale or down` : "Data sources"}</summary>${staleList}
        <p class="fine">NOAA CO-OPS & NWS, CDIP (Scripps), SCCOOS, Open-Meteo, County of San Diego DEHQ. Estimates, not guarantees.</p>
      </details>
      <p class="disclaimer">${esc(doc.disclaimer)}</p>
      <nav class="il-footer-links" aria-label="Footer">${doc.cam_url ? `<a href="${esc(doc.cam_url)}" rel="noopener">Scripps Pier cam</a>` : ""}<a href="#top">Back to top</a></nav>
    </div>
  </footer>`;
}

const THEMES = [["dark", "Dark"], ["light", "Light"], ["contrast", "High contrast"], ["calm", "Calm"]];
const SIZES = [["normal", "Default"], ["large", "Large"], ["larger", "Larger"]];

function dial(name: string, label: string, options: string[][]): string {
  return `<div class="il-dial"><span class="il-label">${label}</span><div class="il-dial-row" role="radiogroup" aria-label="${label}" data-setting="${name}">${options
    .map(([value, text]) => `<button type="button" role="radio" aria-checked="false" tabindex="-1" class="il-dial-opt" data-value="${value}"><span class="il-dial-tick" aria-hidden="true"></span>${text}</button>`)
    .join("")}</div></div>`;
}

/** Indigo Ledger ReadingSettings: colors, text size and motion, every option in view. main.ts wires it up. */
function readingSettings(): string {
  return `
  <section class="il-settings settings" aria-labelledby="settings-title">
    <h2 class="il-settings-title" id="settings-title">Reading settings</h2>
    <div class="il-settings-row">${dial("theme", "Colors", THEMES)}${dial("text", "Text size", SIZES)}</div>
    <button type="button" role="switch" aria-checked="false" class="il-switch" data-setting="motion"><span class="il-switch-track" aria-hidden="true"><span class="il-switch-thumb"></span></span><span class="il-switch-label">Stop all motion</span></button>
    <p class="il-settings-note">Changes apply right away and are saved in this browser. Calm uses softer colors and also stops motion.</p>
  </section>`;
}

function shortError(error: string): string {
  return error.replace(/^\w+Error: /, "").slice(0, 90);
}

export function staleBanner(doc: StatusDoc, now: Date): string {
  const minutes = (now.getTime() - Date.parse(doc.generated_at)) / 60000;
  if (minutes < STALE_AFTER_MIN) return "";
  return `<div class="il-notice il-notice-caution banner" role="alert"><p class="il-notice-title">These conditions are from ${esc(clock(doc.generated_at))} (${esc(ago(doc.generated_at, now))}).</p><div class="il-notice-body"><p>The updater may be down. Treat them as old.</p></div></div>`;
}

/** The page body. `now` is null at build time (no relative ages baked in). */
export function renderPage(doc: StatusDoc, now: Date | null): string {
  const featured = doc.spots.find((s) => s.id === doc.best_bet) ?? null;
  const others = doc.spots.filter((s) => s !== featured);
  const clockNow = now ?? new Date(doc.generated_at);
  return `
  <header class="il-header top" id="top">
    <a class="il-header-home" href="#top"><span class="il-header-name brand">Snorkel Status <span class="muted">· San Diego</span></span></a>
    <span class="updated il-label">Updated ${esc(clock(doc.generated_at))}</span>
  </header>
  <div id="banner">${now ? staleBanner(doc, now) : ""}</div>
  <main>
    ${verdictBar(doc, featured, now)}
    <div id="details">
      ${featured ? featuredCard(featured) : ""}
      ${spotList(others, featured !== null)}
      ${tideSection(doc, clockNow)}
      ${waterSection(doc)}
    </div>
  </main>
  ${freshness(doc, now)}`;
}
