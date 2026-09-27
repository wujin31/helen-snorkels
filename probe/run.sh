#!/usr/bin/env bash
# Round 3: what happens when a phone opens HDOnTap's player-only page directly
# (top-level, not framed)? Text only: player attributes, PiP, inline play.
set -u
section() { printf '\n\n======== %s ========\n' "$*"; }
uv run python - <<'PY'
import time
from playwright.sync_api import sync_playwright

IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1")
pages = {
    "player-only": "https://hdontap.com/stream/018408/scripps-pier-underwater-live-webcam/embed/",
    "stream page": "https://hdontap.com/stream/018408/scripps-pier-underwater-live-webcam/",
    "pierviz": "https://coollab.ucsd.edu/pierviz/",
}
with sync_playwright() as p:
    b = p.chromium.launch(args=["--autoplay-policy=user-gesture-required"])
    for name, url in pages.items():
        print(f"\n======== {name}: {url}")
        ctx = b.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True, user_agent=IPHONE_UA)
        page = ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
        except Exception as e:
            print("load failed:", str(e)[:200]); ctx.close(); continue
        time.sleep(12)
        for f in page.frames:
            try:
                info = f.evaluate("""() => {
                  const vids = [...document.querySelectorAll('video')].map(v => {
                    const r = v.getBoundingClientRect();
                    return {box: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
                      playsinline: v.playsInline || v.hasAttribute('webkit-playsinline'), controls: v.controls,
                      autoplay: v.autoplay, muted: v.muted, paused: v.paused, readyState: v.readyState,
                      noPiP: v.disablePictureInPicture || v.hasAttribute('disablepictureinpicture'),
                      noRemote: v.disableRemotePlayback, cls: (v.className||'').slice(0,60)};
                  });
                  const libs = ['videojs','Hls','jwplayer','flowplayer','Clappr','shaka'].filter(k => k in window);
                  const text = (document.body && document.body.innerText || '').replace(/\\s+/g,' ');
                  return {title: document.title, docHeight: document.documentElement.scrollHeight, videos: vids, libs,
                          ads: /advert|sponsor|preroll|ad will|skip ad/i.test(text), text: text.slice(0, 240)};
                }""")
                print(f" frame {f.url[:90]}\n   {info}")
            except Exception as e:
                print(f" frame {f.url[:90]} (not inspectable) {str(e)[:120]}")
        # Try a user tap on the first visible video/play control.
        try:
            target = page.locator("video, .vjs-big-play-button, [aria-label*=Play i], button[title*=Play i]").first
            target.tap(timeout=5000)
            time.sleep(6)
            state = page.evaluate("() => [...document.querySelectorAll('video')].map(v => ({paused: v.paused, t: Math.round(v.currentTime), rs: v.readyState}))")
            print("  after tap:", state)
        except Exception as e:
            print("  tap:", str(e)[:160])
        ctx.close()
    b.close()
PY
