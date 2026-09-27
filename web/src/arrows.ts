import { compass } from "./format";

/**
 * A small dial showing where swell or wind comes from, relative to the spot:
 * the sand arc is the beach (landward side), the arrow is the direction of
 * travel. Onshore means the arrow points into the sand.
 */
export function directionDial(fromDeg: number | null, shoreNormalDeg: number, label: string): string {
  const size = 44;
  const c = size / 2;
  const land = shoreNormalDeg + 180; // bearing from the spot toward land
  const arc = arcPath(c, c, 18, land - 55, land + 55);
  let arrow = "";
  if (fromDeg != null) {
    const toward = fromDeg + 180;
    const [x1, y1] = polar(c, c, 13, fromDeg);
    const [x2, y2] = polar(c, c, 13, toward);
    const [hx1, hy1] = polar(x2, y2, 6, toward + 150);
    const [hx2, hy2] = polar(x2, y2, 6, toward - 150);
    arrow =
      `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" class="dial-arrow" />` +
      `<polyline points="${hx1},${hy1} ${x2},${y2} ${hx2},${hy2}" class="dial-arrow" fill="none" />`;
  }
  const title = fromDeg == null ? `${label}: direction unknown` : `${label} from the ${compass(fromDeg)}`;
  return (
    `<svg class="dial" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img" aria-label="${title}">` +
    `<circle cx="${c}" cy="${c}" r="20" class="dial-ring" />` +
    `<path d="${arc}" class="dial-beach" />` +
    arrow +
    `</svg>`
  );
}

function polar(cx: number, cy: number, r: number, bearing: number): [number, number] {
  const rad = ((bearing - 90) * Math.PI) / 180; // bearing 0 = up (north)
  return [round(cx + r * Math.cos(rad)), round(cy + r * Math.sin(rad))];
}

function arcPath(cx: number, cy: number, r: number, from: number, to: number): string {
  const [x1, y1] = polar(cx, cy, r, from);
  const [x2, y2] = polar(cx, cy, r, to);
  return `M${x1} ${y1} A${r} ${r} 0 0 1 ${x2} ${y2}`;
}

const round = (n: number) => Math.round(n * 10) / 10;
