import type { Verdict } from "./types";

// Verdicts are Indigo Ledger StatusStamps: the word carries the meaning, the
// stamp's tone (go / caution / stop) backs it up. Never color alone.
export const VERDICT_WORD: Record<Verdict, string> = {
  yes: "Yes",
  maybe: "Maybe",
  no: "No",
  unknown: "Can't tell",
};

const TONE: Record<Verdict, string> = { yes: "go", maybe: "caution", no: "stop", unknown: "none" };

/** The design system's tilt: derived from the word, so the same word always sits the same way. */
export function tiltFor(word: string): number {
  let n = 0;
  for (let i = 0; i < word.length; i++) n = (n * 31 + word.charCodeAt(i)) % 997;
  return ((n % 7) - 4) * 0.6;
}

export function stamp(verdict: Verdict, extraClass = "", word = VERDICT_WORD[verdict]): string {
  const cls = `il-stamp il-stamp-${TONE[verdict]}${extraClass ? ` ${extraClass}` : ""}`;
  return `<span class="${cls}" style="--tilt:${tiltFor(word).toFixed(1)}deg">${word}</span>`;
}
