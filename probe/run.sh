#!/usr/bin/env bash
# Can the page embed HDOnTap's player? Headers, the stream page's own embed
# code, and a real iframe load from a page pretending to be the site's origin.
# Text output only; no images are saved.
set -u
section() { printf '\n\n======== %s ========\n' "$*"; }
UA="snorkel-status (https://github.com/wujin31/helen-snorkels)"
PAGE="https://hdontap.com/stream/018408/scripps-pier-underwater-live-webcam/"
EMBED="${PAGE}embed/"

for url in "$PAGE" "$EMBED"; do
  section "Headers: $url"
  curl -sS -L -A "$UA" -o /dev/null -D - "$url" | grep -iE '^(HTTP/|location|x-frame-options|content-security-policy|content-type|cache-control)'
done

section "Embed code on the stream page"
curl -sS -L -A "$UA" "$PAGE" > /tmp/page.html
wc -c /tmp/page.html
grep -oiE '.{0,120}(embed|iframe).{0,160}' /tmp/page.html | grep -viE 'youtube|twitter|facebook' | sort -u | head -40

section "Embed page body"
curl -sS -L -A "$UA" "$EMBED" > /tmp/embed.html
wc -c /tmp/embed.html
grep -oiE '<title>.{0,120}' /tmp/embed.html
grep -oiE '.{0,80}(referrer|referer|domain|whitelist|allowed|autoplay|muted|poster|streamSrc|m3u8).{0,120}' /tmp/embed.html | sort -u | head -30

section "Iframe load from https://wujin31.github.io/helen-snorkels/"
uv run python - "$EMBED" <<'PY'
import sys, time
from playwright.sync_api import sync_playwright

embed = sys.argv[1]
host = "https://wujin31.github.io/helen-snorkels/embed-test.html"
html = f"""<!doctype html><meta name=viewport content="width=device-width">
<body style="margin:0"><iframe id=cam src="{embed}" style="width:390px;height:220px;border:0"
allow="autoplay; fullscreen; picture-in-picture" allowfullscreen></iframe></body>"""
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
    page = b.new_page(viewport={"width": 390, "height": 844}, is_mobile=True)
    msgs = []
    page.on("console", lambda m: msgs.append(f"console[{m.type}] {m.text[:200]}"))
    page.on("requestfailed", lambda r: msgs.append(f"failed {r.url[:120]} {r.failure}"))
    responses = []
    page.on("response", lambda r: responses.append((r.status, r.url[:140])) if r.request.frame != page.main_frame else None)
    page.route(host, lambda route: route.fulfill(status=200, content_type="text/html", body=html))
    page.goto(host)
    time.sleep(20)
    for f in page.frames:
        print("frame:", f.url[:160])
        if f == page.main_frame:
            continue
        try:
            info = f.evaluate("""() => {
              const v = [...document.querySelectorAll('video')].map(v => ({src: (v.currentSrc||'').slice(0,100), rs: v.readyState, paused: v.paused, w: v.videoWidth, h: v.videoHeight, autoplay: v.autoplay, muted: v.muted}));
              return {title: document.title, videos: v, text: (document.body && document.body.innerText || '').slice(0, 400), iframes: [...document.querySelectorAll('iframe')].map(i => i.src.slice(0,120))};
            }""")
            print("  ", info)
        except Exception as e:
            print("   (not inspectable)", str(e)[:200])
    print("frame responses (status, url) sample:")
    seen = set()
    for s, u in responses:
        k = u.split("?")[0]
        if k in seen:
            continue
        seen.add(k)
        print("  ", s, u)
        if len(seen) > 25:
            break
    print("\n".join(msgs[:40]))
    b.close()
PY
