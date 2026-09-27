import { TZ } from "./config";

const clockFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: TZ,
  hour: "numeric",
  minute: "2-digit",
  hour12: true,
});
const hourFmt = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", hour12: true });
const dayFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: TZ,
  weekday: "long",
  month: "short",
  day: "numeric",
});

/** "7:00 am" */
export function clock(iso: string | Date): string {
  const parts = clockFmt.formatToParts(typeof iso === "string" ? new Date(iso) : iso);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("hour")}:${get("minute")} ${get("dayPeriod").toLowerCase()}`;
}

/** "7:00–9:30 am", or "11:30 am–1:00 pm" across noon. */
export function range(startIso: string, endIso: string): string {
  const a = clock(startIso);
  const b = clock(endIso);
  const [aTime, aPeriod] = a.split(" ");
  const [bTime, bPeriod] = b.split(" ");
  return aPeriod === bPeriod ? `${aTime}–${bTime} ${bPeriod}` : `${a}–${b}`;
}

/** "6a", "12p" for axis ticks. */
export function hourTick(d: Date): string {
  const text = hourFmt.format(d).toLowerCase().replace(" ", "");
  return text.replace("am", "a").replace("pm", "p");
}

export function dayName(iso: string | Date): string {
  return dayFmt.format(typeof iso === "string" ? new Date(iso) : iso);
}

export function ago(iso: string, now: Date): string {
  const minutes = Math.round((now.getTime() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`;
}

const COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
export function compass(deg: number | null): string {
  return deg == null ? "" : COMPASS[Math.round((((deg % 360) + 360) % 360) / 45) % 8];
}

export function ft(value: number | null, digits = 1): string {
  if (value == null) return "–";
  const text = value.toFixed(digits);
  return text.endsWith(".0") ? text.slice(0, -2) : text;
}

const ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#39;",
};

/** Escape for HTML text and attribute values. Every data string goes through this. */
export function esc(value: unknown): string {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ESCAPES[c]);
}
