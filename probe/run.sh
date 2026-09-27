#!/usr/bin/env bash
# Round 2: HDOnTap's portal player (the one its own stream page builds from).
# Can a third-party page frame it? Text output only; no images saved.
set -u
section() { printf '\n\n======== %s ========\n' "$*"; }
UA="snorkel-status (https://github.com/wujin31/helen-snorkels)"
PAGE="https://hdontap.com/stream/018408/scripps-pier-underwater-live-webcam/"

section "Player config on the stream page"
curl -sS -L -A "$UA" "$PAGE" > /tmp/page.html
grep -oE '.{0,400}portalEmbedId.{0,900}' /tmp/page.html | head -3
grep -oiE 'portal\.hdontap\.com/s/embed[^"'"'"' ]{0,120}' /tmp/page.html | sort -u
grep -oiE 'storage\.hdontap\.com/wowza_stream_thumbnails/[^"'"'"' ]+' /tmp/page.html | sort -u

for url in \
  "https://portal.hdontap.com/s/embed/?stream=scripps_pier-underwater-HDOT" \
  "https://portal.hdontap.com/s/embed?stream=scripps_pier-underwater-HDOT" \
  "https://portal.hdontap.com/s/embed/?stream=scripps_pier-underwater-CUST"; do
  section "Headers: $url"
  curl -sS -L -A "$UA" -H "Referer: https://wujin31.github.io/helen-snorkels/" -o /tmp/p.html -D - "$url" \
    | grep -iE '^(HTTP/|location|x-frame-options|content-security-policy|content-type)'
  wc -c < /tmp/p.html
  grep -oiE '<title>.{0,100}' /tmp/p.html
done

section "Thumbnail headers"
for u in $(grep -oiE 'https://storage\.hdontap\.com/wowza_stream_thumbnails/[^"'"'"' ]+' /tmp/page.html | sort -u | head -2); do
  curl -sS -A "$UA" -o /dev/null -D - "$u" | grep -iE '^(HTTP/|content-type|content-length|last-modified|cache-control|age|expires)'
done

section "Iframe load from https://wujin31.github.io/helen-snorkels/"
uv run python - <<'PY'
import time
from playwright.sync_api import sync_playwright

host = "https://wujin31.github.io/helen-snorkels/embed-test.html"
candidates = [
    "https://portal.hdontap.com/s/embed/?stream=scripps_pier-underwater-HDOT",
    "https://portal.hdontap.com/s/embed/?stream=scripps_pier-underwater-CUST",
]
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
    for embed in candidates:
        print("\n---", embed)
        html = f"""<!doctype html><meta name=viewport content="width=device-width">
<body style="margin:0"><iframe id=cam src="{embed}" style="width:390px;height:220px;border:0"
allow="autoplay; fullscreen; picture-in-picture"></iframe></body>"""
        page = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
        msgs = []
        page.on("console", lambda m: msgs.append(f"console[{m.type}] {m.text[:220]}"))
        page.on("requestfailed", lambda r: msgs.append(f"failed {r.url[:120]} {r.failure}"))
        page.route(host, lambda route: route.fulfill(status=200, content_type="text/html", body=html))
        page.goto(host)
        time.sleep(25)
        for f in page.frames:
            print("frame:", f.url[:160])
            if f == page.main_frame:
                continue
            try:
                info = f.evaluate("""() => {
                  const v = [...document.querySelectorAll('video')].map(v => ({rs: v.readyState, paused: v.paused, w: v.videoWidth, h: v.videoHeight, t: Math.round(v.currentTime), autoplay: v.autoplay, muted: v.muted}));
                  return {title: document.title, videos: v, text: (document.body && document.body.innerText || '').replace(/\\s+/g,' ').slice(0, 300)};
                }""")
                print("  ", info)
            except Exception as e:
                print("   (not inspectable)", str(e)[:200])
        print("\n".join(m for m in msgs[:25] if "googletag" not in m))
        page.close()
    b.close()
PY
