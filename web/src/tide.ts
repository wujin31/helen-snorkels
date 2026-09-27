import { clock, esc, ft, hourTick } from "./format";
import type { DayConditions, TimeWindow } from "./types";

export const TIDE_BOX = { w: 360, h: 150, left: 30, right: 10, top: 14, bottom: 26 };

export interface TideScale {
  x: (t: number) => number;
  y: (v: number) => number;
  t0: number;
  t1: number;
  lo: number;
  hi: number;
}

export function tideScale(day: DayConditions): TideScale | null {
  const pts = day.tide_curve;
  if (pts.length < 2) return null;
  const t0 = Date.parse(pts[0].time);
  const t1 = Date.parse(pts[pts.length - 1].time);
  const values = pts.map((p) => p.ft);
  const lo = Math.floor(Math.min(0, ...values));
  const hi = Math.ceil(Math.max(...values) + 0.5);
  const { w, h, left, right, top, bottom } = TIDE_BOX;
  return {
    t0,
    t1,
    lo,
    hi,
    x: (t) => left + ((t - t0) / (t1 - t0)) * (w - left - right),
    y: (v) => top + (1 - (v - lo) / (hi - lo)) * (h - top - bottom),
  };
}

/** Tide today: one series, best window shaded, now marked, highs/lows labeled. */
export function tideChart(day: DayConditions, window: TimeWindow | null, now: Date): string {
  const s = tideScale(day);
  if (!s) return `<p class="muted">Tide predictions unavailable.</p>`;
  const { w, h, top, bottom, left, right } = TIDE_BOX;
  const pts = day.tide_curve.map((p) => [s.x(Date.parse(p.time)), s.y(p.ft)] as const);
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join("");
  const base = s.y(s.lo);
  const area = `${line}L${pts[pts.length - 1][0].toFixed(1)} ${base}L${pts[0][0].toFixed(1)} ${base}Z`;

  const parts: string[] = [];
  // Night: before sunrise and after sunset, a quiet wash.
  const sunrise = Date.parse(day.sunrise);
  const sunset = Date.parse(day.sunset);
  if (sunrise > s.t0) {
    parts.push(`<rect class="tide-night" x="${left}" y="${top}" width="${(s.x(sunrise) - left).toFixed(1)}" height="${h - top - bottom}" />`);
  }
  if (sunset < s.t1) {
    parts.push(`<rect class="tide-night" x="${s.x(sunset).toFixed(1)}" y="${top}" width="${(w - right - s.x(sunset)).toFixed(1)}" height="${h - top - bottom}" />`);
  }
  // Gridlines at whole-foot steps (every 2 ft), labeled on the left.
  for (let v = s.lo; v <= s.hi; v += 2) {
    const y = s.y(v).toFixed(1);
    parts.push(`<line class="grid" x1="${left}" x2="${w - right}" y1="${y}" y2="${y}" />`);
    parts.push(`<text class="tick" x="${left - 6}" y="${y}" dy="0.32em" text-anchor="end">${v}</text>`);
  }
  // Best window.
  if (window) {
    const x1 = s.x(Date.parse(window.start));
    const x2 = s.x(Date.parse(window.end));
    parts.push(`<rect class="tide-window" x="${x1.toFixed(1)}" y="${top}" width="${(x2 - x1).toFixed(1)}" height="${h - top - bottom}" rx="3" />`);
  }
  parts.push(`<path class="tide-area" d="${area}" />`);
  parts.push(`<path class="tide-line" d="${line}" />`);
  // Highs and lows: the only direct labels.
  for (const turn of day.tide_turns) {
    const t = Date.parse(turn.time);
    if (t < s.t0 || t > s.t1) continue;
    const x = s.x(t);
    const y = s.y(turn.ft);
    // Highs label above the dot; lows below unless that would hit the hour ticks.
    const above = turn.kind === "high" || y + 16 > h - bottom - 2;
    parts.push(`<circle class="tide-dot" cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="4" />`);
    parts.push(
      `<text class="tide-label" x="${x.toFixed(1)}" y="${(above ? y - 9 : y + 16).toFixed(1)}" text-anchor="middle">` +
        `${turn.kind === "high" ? "High" : "Low"} ${esc(ft(turn.ft))} ft · ${esc(clock(turn.time))}</text>`,
    );
  }
  // Now.
  const n = now.getTime();
  if (n >= s.t0 && n <= s.t1) {
    const x = s.x(n).toFixed(1);
    parts.push(`<line class="tide-now" x1="${x}" x2="${x}" y1="${top}" y2="${h - bottom}" />`);
    parts.push(`<text class="tick tick-now" x="${x}" y="${top - 4}" text-anchor="middle">now</text>`);
  }
  // Hour ticks every 3 hours.
  const firstTick = new Date(s.t0);
  firstTick.setUTCMinutes(0, 0, 0);
  for (let t = firstTick.getTime(); t <= s.t1; t += 3600_000) {
    if (t < s.t0) continue;
    const hourLocal = Number(new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", hour: "numeric", hour12: false }).format(new Date(t)));
    if (hourLocal % 3 !== 0) continue;
    const x = s.x(t).toFixed(1);
    parts.push(`<text class="tick" x="${x}" y="${h - 8}" text-anchor="middle">${hourTick(new Date(t))}</text>`);
  }
  parts.push(`<line class="axis" x1="${left}" x2="${w - right}" y1="${h - bottom}" y2="${h - bottom}" />`);
  parts.push(`<g class="tide-hover" hidden><line class="tide-cross" y1="${top}" y2="${h - bottom}" /><circle class="tide-cross-dot" r="4" /></g>`);
  return (
    `<svg class="tide" viewBox="0 0 ${w} ${h}" role="img" aria-labelledby="tide-title" tabindex="0">` +
    parts.join("") +
    `</svg><div class="tide-tip" role="status" aria-live="polite" hidden></div>`
  );
}
