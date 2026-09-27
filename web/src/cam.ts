// The live cam section. HDOnTap only lets its own and UCSD sites frame the
// player, so until Scripps adds this site (cam.embed_url set) it's a big
// tap-through to the live stream, drawn as a schematic, never one of our frames.

import { clock, esc } from "./format";
import type { CamInfo, CamReading } from "./types";

export type CamState = { kind: "live" } | { kind: "dark"; until: string | null };

/** Live between the light windows' start and end; otherwise dark until the next. */
export function camState(cam: CamInfo, now: Date): CamState {
  const t = now.getTime();
  for (const w of cam.light) {
    if (t < Date.parse(w.start)) return { kind: "dark", until: w.start };
    if (t < Date.parse(w.end)) return { kind: "live" };
  }
  return { kind: "dark", until: null };
}

// Pilings receding into the water, nearest first: [x, width, opacity].
const PILINGS: [number, number, number][] = [
  [34, 34, 0.9],
  [150, 20, 0.6],
  [222, 12, 0.38],
  [268, 7, 0.22],
];

/** The schematic view: water, light and pilings; faded past what the cam can see. */
function scene(live: boolean, reading: CamReading | null): string {
  const seen = reading?.pilings_visible ?? PILINGS.length;
  const pilings = PILINGS.map(([x, w, o], i) => {
    const opacity = i < seen ? o : 0.07;
    return `<rect x="${x}" y="0" width="${w}" height="180" fill="#03202c" opacity="${opacity}" />`;
  }).join("");
  const rays = live
    ? `<g fill="#ffffff" opacity="0.07"><polygon points="90,0 130,0 70,180 20,180" /><polygon points="190,0 215,0 190,180 150,180" /><polygon points="250,0 262,0 290,180 262,180" /></g>`
    : "";
  const specks = live
    ? `<g fill="#ffffff" opacity="0.35"><circle cx="112" cy="46" r="1.2" /><circle cx="200" cy="120" r="1" /><circle cx="248" cy="70" r="1.4" /><circle cx="84" cy="138" r="1" /><circle cx="300" cy="30" r="1" /></g>`
    : "";
  const top = live ? "#3a9dbd" : "#0b1d27";
  const bottom = live ? "#073549" : "#02080b";
  return `<svg class="cam-scene" viewBox="0 0 320 180" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
      <defs><linearGradient id="cam-water" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${top}" /><stop offset="1" stop-color="${bottom}" /></linearGradient></defs>
      <rect width="320" height="180" fill="url(#cam-water)" />${rays}${pilings}${specks}
    </svg>`;
}

function readingChip(reading: CamReading | null): string {
  if (!reading) return "";
  const parts = [
    reading.vis_ft ? `~${reading.vis_ft[0]}–${reading.vis_ft[1]} ft` : "",
    reading.pilings_visible != null && reading.pilings_total
      ? `${reading.pilings_visible} of ${reading.pilings_total} pilings`
      : "",
    clock(reading.time),
  ].filter(Boolean);
  return `<span class="cam-chip cam-reading">${esc(parts.join(" · "))}</span>`;
}

export function camSection(cam: CamInfo, now: Date): string {
  const state = camState(cam, now);
  const live = state.kind === "live";
  const player = live && cam.embed_url;
  const status = live
    ? `<span class="cam-chip cam-live"><span class="live-dot" aria-hidden="true"></span>Live</span>`
    : "";
  const overlay = `<div class="cam-overlay">${status}${readingChip(cam.reading)}</div>`;
  const action = live
    ? `<span class="cam-play" aria-hidden="true"><svg viewBox="0 0 24 24" width="30" height="30"><path d="M8 5.5v13l10.5-6.5z" fill="currentColor" /></svg></span><span class="cam-cta">Watch live ↗</span>`
    : `<span class="cam-cta"><strong>${state.until ? `The cam's dark until ${esc(clock(state.until))}` : "The cam's dark"}</strong><span class="cam-anyway">Open it anyway ↗</span></span>`;
  const label = `${cam.title}: watch live on HDOnTap (opens a new tab)`;
  const media = player
    ? `<div class="cam-player" data-src="${esc(cam.embed_url)}"><a class="cam-link" href="${esc(cam.watch_url)}" target="_blank" rel="noopener" aria-label="${esc(label)}">${scene(true, cam.reading)}${action}</a></div>`
    : `<a class="cam-link" href="${esc(cam.watch_url)}" target="_blank" rel="noopener" aria-label="${esc(label)}">${scene(live, cam.reading)}${action}</a>`;
  return `
  <section class="cam" id="cam" data-state="${state.kind}" data-embed="${esc(player ? cam.embed_url : "")}" aria-labelledby="cam-title">
    <div class="cam-media">${media}${overlay}</div>
    <div class="cam-foot">
      <h2 id="cam-title">${esc(cam.title)}</h2>
      <p class="cam-caption">${esc(cam.caption)}</p>
      ${player ? "" : `<p class="cam-tip">Tip: once it's playing, go full screen and tap Picture in Picture to keep the cam floating over this page.</p>`}
    </div>
  </section>`;
}
