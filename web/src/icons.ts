import type { Verdict } from "./types";

// Verdict marks: shape carries meaning with the color, never color alone.
const PATHS: Record<Verdict, string> = {
  yes: '<path d="M7.5 12.5l3 3 6-7" />',
  maybe: '<path d="M7 13c1.5-2 3-2 5 0s3.5 2 5 0" />',
  no: '<path d="M8.5 8.5l7 7M15.5 8.5l-7 7" />',
  unknown: '<path d="M9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .8-1 1.5v.7" /><circle cx="12" cy="17" r=".6" />',
};

export function verdictIcon(verdict: Verdict, size = 28): string {
  return (
    `<svg class="vicon vicon-${verdict}" width="${size}" height="${size}" viewBox="0 0 24 24" aria-hidden="true">` +
    `<circle cx="12" cy="12" r="11" class="vicon-disc" />` +
    `<g class="vicon-mark" fill="none" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">${PATHS[verdict]}</g>` +
    `</svg>`
  );
}

export const VERDICT_WORD: Record<Verdict, string> = {
  yes: "Yes",
  maybe: "Maybe",
  no: "No",
  unknown: "Can't tell",
};
