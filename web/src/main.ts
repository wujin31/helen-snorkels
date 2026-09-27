import "./styles.css";
import { clock, ft } from "./format";
import { renderPage } from "./render";
import { tideScale, TIDE_BOX } from "./tide";
import type { StatusDoc } from "./types";

const app = document.getElementById("app")!;
let doc: StatusDoc = JSON.parse(document.getElementById("status-data")!.textContent!);
let lastCheck = 0;

// Regions renderPage marks with ids; repainted around a playing cam player.
const REGIONS = ["top", "banner", "verdict", "details", "foot"];

function paint(next: StatusDoc): void {
  doc = next;
  const html = renderPage(doc, new Date());
  if (!repaintAroundPlayer(html)) {
    app.innerHTML = html;
    mountPlayer();
  }
  bind();
}

/** Swap everything but a playing player (moving an iframe reloads it). */
function repaintAroundPlayer(html: string): boolean {
  const current = app.querySelector<HTMLElement>("#cam");
  if (!current?.querySelector(".cam-player iframe")) return false;
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  const fresh = tpl.content.querySelector<HTMLElement>("#cam");
  if (!fresh || fresh.dataset.state !== current.dataset.state || fresh.dataset.embed !== current.dataset.embed) {
    return false;
  }
  for (const id of REGIONS) {
    const next = tpl.content.querySelector(`#${id}`);
    const old = app.querySelector(`#${id}`);
    if (!next || !old) return false;
    old.replaceWith(next);
  }
  for (const part of [".cam-overlay", ".cam-foot"]) {
    const next = fresh.querySelector(part);
    if (next) current.querySelector(part)?.replaceWith(next);
  }
  return true;
}

/** Only when the player allows this site (cam.embed_url); otherwise the link stays. */
function mountPlayer(): void {
  const slot = app.querySelector<HTMLElement>("#cam .cam-player");
  const src = slot?.dataset.src;
  if (!slot || !src || slot.querySelector("iframe")) return;
  const frame = document.createElement("iframe");
  frame.src = src;
  frame.title = "Scripps Pier underwater cam, live";
  frame.allow = "fullscreen; picture-in-picture";
  frame.allowFullscreen = true;
  frame.referrerPolicy = "strict-origin-when-cross-origin";
  slot.replaceChildren(frame);
}

function bind(): void {
  bindTide();
}

function bindTide(): void {
  const svg = app.querySelector<SVGSVGElement>("svg.tide");
  const tip = app.querySelector<HTMLDivElement>(".tide-tip");
  const scale = tideScale(doc.day);
  if (!svg || !tip || !scale) return;
  const group = svg.querySelector<SVGGElement>(".tide-hover")!;
  const line = group.querySelector("line")!;
  const dot = group.querySelector("circle")!;
  const points = doc.day.tide_curve;
  let index = -1;

  const show = (i: number) => {
    index = Math.max(0, Math.min(points.length - 1, i));
    const p = points[index];
    const x = scale.x(Date.parse(p.time));
    const y = scale.y(p.ft);
    line.setAttribute("x1", String(x));
    line.setAttribute("x2", String(x));
    dot.setAttribute("cx", String(x));
    dot.setAttribute("cy", String(y));
    group.removeAttribute("hidden");
    tip.hidden = false;
    tip.textContent = "";
    const strong = document.createElement("strong");
    strong.textContent = `${ft(p.ft)} ft`;
    tip.append(strong, ` · ${clock(p.time)}`);
    const box = svg.getBoundingClientRect();
    tip.style.left = `${Math.min(box.width - 110, Math.max(0, (x / TIDE_BOX.w) * box.width - 55))}px`;
  };
  const hide = () => {
    group.setAttribute("hidden", "");
    tip.hidden = true;
  };
  const nearest = (clientX: number) => {
    const box = svg.getBoundingClientRect();
    const x = ((clientX - box.left) / box.width) * TIDE_BOX.w;
    let best = 0;
    let bestDist = Infinity;
    points.forEach((p, i) => {
      const d = Math.abs(scale.x(Date.parse(p.time)) - x);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    return best;
  };
  svg.addEventListener("pointermove", (e) => show(nearest(e.clientX)));
  svg.addEventListener("pointerdown", (e) => show(nearest(e.clientX)));
  svg.addEventListener("pointerleave", hide);
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      show((index < 0 ? nearest(svg.getBoundingClientRect().left) : index) + (e.key === "ArrowRight" ? 1 : -1));
    } else if (e.key === "Escape") hide();
  });
}

async function refresh(): Promise<void> {
  lastCheck = Date.now();
  try {
    const res = await fetch(`status.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) return;
    const next: StatusDoc = await res.json();
    if (Date.parse(next.generated_at) > Date.parse(doc.generated_at)) {
      paint(next);
    } else {
      paint(doc); // refresh relative ages and the stale banner
    }
  } catch {
    /* offline: keep what we have; the stale banner tells the truth */
  }
}

paint(doc);
refresh();
setInterval(refresh, 10 * 60_000);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && Date.now() - lastCheck > 5 * 60_000) refresh();
});

if ("serviceWorker" in navigator && location.protocol === "https:") {
  navigator.serviceWorker.register("sw.js").catch(() => undefined);
}
