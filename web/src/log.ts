// Two-tap post-swim log. A private link (…/#key=…) stores her log key on the
// phone once; the key-checked Supabase functions do the rest. No accounts.

import { SUPABASE_PUBLISHABLE_KEY, SUPABASE_URL } from "./config";
import { clock } from "./format";
import type { StatusDoc } from "./types";

const KEY_STORE = "snorkel-log-key";

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Take a key from the URL hash (once), remember it, and clean the URL. */
export function logKey(): string | null {
  const match = /(?:^|[#&])key=([A-Za-z0-9_-]{20,})/.exec(window.location.hash);
  if (match) {
    try {
      storage()?.setItem(KEY_STORE, match[1]);
    } catch {
      /* private mode: key lives for this visit only */
    }
    history.replaceState(null, "", window.location.pathname + window.location.search);
    return match[1];
  }
  try {
    return storage()?.getItem(KEY_STORE) ?? null;
  } catch {
    return null;
  }
}

async function rpc<T>(fn: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${SUPABASE_URL}/rest/v1/rpc/${fn}`, {
    method: "POST",
    headers: { apikey: SUPABASE_PUBLISHABLE_KEY, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(res.status === 400 && detail.includes("invalid log key") ? "This phone's log link isn't valid any more." : `Couldn't save (${res.status}).`);
  }
  return res.json() as Promise<T>;
}

interface RecentSwim {
  spot_id: string;
  swam_at: string;
  vis_ft: number | null;
  rating: number | null;
}

function el<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, string> = {}, text?: string) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text != null) node.textContent = text;
  return node;
}

function localInputValue(d: Date): string {
  const offset = d.getTimezoneOffset() * 60000;
  return new Date(d.getTime() - offset).toISOString().slice(0, 16);
}

export function openLogSheet(doc: StatusDoc, key: string): void {
  document.querySelector("dialog.log")?.remove();
  const dialog = el("dialog", { class: "log", "aria-labelledby": "log-title" });
  const form = el("form", { method: "dialog" });
  form.append(el("h2", { id: "log-title" }, "How was it?"));

  const best = doc.spots.find((s) => s.id === doc.best_bet) ?? doc.spots[0];
  const spots = el("fieldset", { class: "seg" });
  spots.append(el("legend", {}, "Where"));
  for (const spot of doc.spots) {
    const id = `log-spot-${spot.id}`;
    const input = el("input", { type: "radio", name: "spot", value: spot.id, id });
    if (spot.id === best?.id) input.setAttribute("checked", "");
    spots.append(input, el("label", { for: id }, spot.name.split(" / ")[0]));
  }

  const visGuess = best?.vis_ft ? Math.round((best.vis_ft[0] + best.vis_ft[1]) / 2) : 10;
  const visWrap = el("div", { class: "field" });
  const visOut = el("output", { for: "log-vis", class: "vis-out" }, `${visGuess} ft`);
  const vis = el("input", { type: "range", id: "log-vis", name: "vis", min: "0", max: "40", step: "1", value: String(visGuess) });
  vis.addEventListener("input", () => (visOut.textContent = `${vis.value} ft${vis.value === "40" ? "+" : ""}`));
  const visLabel = el("label", { for: "log-vis" }, "Visibility ");
  visLabel.append(visOut);
  visWrap.append(visLabel, vis);

  const rating = el("fieldset", { class: "seg rating" });
  rating.append(el("legend", {}, "Rating"));
  for (let i = 1; i <= 5; i++) {
    const id = `log-r${i}`;
    const input = el("input", { type: "radio", name: "rating", value: String(i), id });
    if (i === 3) input.setAttribute("checked", "");
    rating.append(input, el("label", { for: id, "aria-label": `${i} of 5` }, String(i)));
  }

  const when = el("div", { class: "field" });
  const whenInput = el("input", { type: "datetime-local", id: "log-when", name: "when", value: localInputValue(new Date()) });
  when.append(el("label", { for: "log-when" }, "When"), whenInput);

  const note = el("div", { class: "field" });
  const noteInput = el("textarea", { id: "log-note", name: "note", rows: "2", maxlength: "500", placeholder: "Leopard sharks, surge, murky at the reef…" });
  note.append(el("label", { for: "log-note" }, "Note (optional)"), noteInput);

  const status = el("p", { class: "log-status", role: "status" });
  const actions = el("div", { class: "actions" });
  const cancel = el("button", { type: "button", class: "ghost" }, "Cancel");
  const save = el("button", { type: "submit", class: "primary" }, "Save");
  cancel.addEventListener("click", () => dialog.close());
  actions.append(cancel, save);

  const recent = el("ul", { class: "recent" });
  form.append(spots, visWrap, rating, when, note, status, actions, recent);
  dialog.append(form);
  document.body.append(dialog);
  dialog.addEventListener("close", () => dialog.remove());

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = new FormData(form);
    save.disabled = true;
    status.textContent = "Saving…";
    try {
      await rpc("log_swim", {
        p_key: key,
        p_spot_id: String(data.get("spot")),
        p_vis_ft: Number(data.get("vis")),
        p_rating: Number(data.get("rating")),
        p_note: String(data.get("note") ?? ""),
        p_swam_at: new Date(String(data.get("when"))).toISOString(),
      });
      status.textContent = "Saved. Thank you, that's what makes the forecast better.";
      setTimeout(() => dialog.close(), 1200);
    } catch (err) {
      status.textContent = err instanceof Error ? err.message : "Couldn't save.";
      save.disabled = false;
    }
  });

  dialog.showModal();
  rpc<RecentSwim[]>("recent_swims", { p_key: key, p_limit: 3 })
    .then((rows) => {
      if (!rows.length) return;
      recent.append(el("li", { class: "fine" }, "Recent"));
      for (const r of rows) {
        const name = doc.spots.find((s) => s.id === r.spot_id)?.name.split(" / ")[0] ?? r.spot_id;
        const day = new Date(r.swam_at).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "America/Los_Angeles" });
        recent.append(el("li", {}, `${day} ${clock(r.swam_at)} · ${name} · ${r.vis_ft ?? "–"} ft · ${r.rating ?? "–"}/5`));
      }
    })
    .catch(() => {
      /* recent list is a nicety */
    });
}
