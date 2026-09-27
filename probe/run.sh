#!/usr/bin/env bash
# Pick ~10 archived cam frames across the day and encrypt each to the
# certificate in probe/frames-cert.pem. Only ciphertext and metadata are
# committed; the key never leaves the requester. Delete this branch after.
set -u
mkdir -p probe/frames
uv run python - <<'PY'
import subprocess
from datetime import date, timedelta
from snorkel.archive import read_manifest
from snorkel.storage import storage_from_spec

storage = storage_from_spec()
records = []
for day in (date(2026, 9, 26), date(2026, 9, 27), date(2026, 9, 28)):
    records += [r for r in read_manifest(storage, day) if r.source == "cam.scripps_pier" and r.status == "ok" and r.key]
records.sort(key=lambda r: r.run_at)
print(len(records), "cam frames in the manifests")
for r in records:
    m = r.meta
    print(f"  {r.run_at:%Y-%m-%d %H:%MZ} {m.get('strategy')} bright={m.get('brightness')} sun={m.get('sun_elevation')} frozen={m.get('frozen')} {m.get('width')}x{m.get('height')}")
n = len(records)
picks = sorted({round(i * (n - 1) / 9) for i in range(10)}) if n > 10 else list(range(n))
for i in picks:
    r = records[i]
    data = storage.get(r.key)
    if not data:
        print("missing", r.key)
        continue
    name = f"probe/frames/{r.run_at:%Y%m%dT%H%MZ}.jpg.cms"
    subprocess.run(
        ["openssl", "cms", "-encrypt", "-aes256", "-binary", "-outform", "DER", "-out", name, "probe/frames-cert.pem"],
        input=data, check=True,
    )
    print("encrypted", r.key, "->", name, len(data), "bytes")
PY
