// Archive gateway: lets GitHub Actions workflows in this repository read and
// write the private `archive` bucket with no stored secret.
//
// Each request carries a short-lived GitHub Actions OIDC token (audience
// "snorkel-status"). The function verifies its signature against GitHub's
// published keys, checks it was minted for this repository (by numeric id,
// which survives renames and can't be claimed by another repo), and only then
// reads or writes the bucket with the service role.
//
//   GET  /archive-gateway/health          -> {"ok": true} (no auth)
//   GET  /archive-gateway/object/<key>    -> object bytes, or 404
//   PUT  /archive-gateway/object/<key>    -> upsert object bytes
//   DELETE /archive-gateway/object/<key>  -> remove the object, or 404
//
// Deployed with verify_jwt = false because the caller's JWT is GitHub's, not
// Supabase's; the check below replaces it.

import { createRemoteJWKSet, jwtVerify } from "npm:jose@5.9.6";

const ISSUER = "https://token.actions.githubusercontent.com";
const AUDIENCE = "snorkel-status";
const REPOSITORY_ID = "1390285949"; // wujin31/helen-snorkels
const BUCKET = "archive";
const KEY_RE = /^(raw|frames|manifest|state)\/[A-Za-z0-9._\/-]+$/;
const MAX_BYTES = 25 * 1024 * 1024;

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const jwks = createRemoteJWKSet(new URL(`${ISSUER}/.well-known/jwks`));

function json(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

async function authorize(req: Request): Promise<string | null> {
  const token = (req.headers.get("authorization") ?? "").replace(/^Bearer\s+/i, "");
  if (!token) return "missing bearer token";
  try {
    const { payload } = await jwtVerify(token, jwks, { issuer: ISSUER, audience: AUDIENCE });
    if (payload.repository_id !== REPOSITORY_ID) return "token is for another repository";
    return null;
  } catch (_err) {
    return "invalid token";
  }
}

function objectUrl(key: string): string {
  const path = key.split("/").map(encodeURIComponent).join("/");
  return `${SUPABASE_URL}/storage/v1/object/${BUCKET}/${path}`;
}

const serviceHeaders = { apikey: SERVICE_KEY, authorization: `Bearer ${SERVICE_KEY}` };

async function getObject(key: string): Promise<Response> {
  const res = await fetch(objectUrl(key), { headers: serviceHeaders });
  if (res.ok) {
    return new Response(res.body, {
      headers: { "content-type": res.headers.get("content-type") ?? "application/octet-stream" },
    });
  }
  const text = await res.text();
  // Storage reports a missing object as 400 {"statusCode":"404",...} or a plain 404.
  if (res.status === 404 || /"statusCode"\s*:\s*"404"|not.?found/i.test(text)) {
    return json(404, { error: "not found", key });
  }
  return json(502, { error: `storage ${res.status}`, detail: text.slice(0, 300) });
}

async function putObject(key: string, req: Request): Promise<Response> {
  const body = new Uint8Array(await req.arrayBuffer());
  if (body.byteLength > MAX_BYTES) return json(413, { error: "too large", bytes: body.byteLength });
  const res = await fetch(objectUrl(key), {
    method: "POST",
    headers: {
      ...serviceHeaders,
      "content-type": req.headers.get("content-type") ?? "application/octet-stream",
      "x-upsert": "true",
    },
    body,
  });
  if (!res.ok) {
    return json(502, { error: `storage ${res.status}`, detail: (await res.text()).slice(0, 300) });
  }
  return json(200, { key, bytes: body.byteLength });
}

async function deleteObject(key: string): Promise<Response> {
  const res = await fetch(`${SUPABASE_URL}/storage/v1/object/${BUCKET}`, {
    method: "DELETE",
    headers: { ...serviceHeaders, "content-type": "application/json" },
    body: JSON.stringify({ prefixes: [key] }),
  });
  if (!res.ok) {
    return json(502, { error: `storage ${res.status}`, detail: (await res.text()).slice(0, 300) });
  }
  const removed = (await res.json()) as unknown[];
  return removed.length ? json(200, { key, deleted: true }) : json(404, { error: "not found", key });
}

Deno.serve(async (req: Request) => {
  const { pathname } = new URL(req.url);
  if (pathname.endsWith("/health")) return json(200, { ok: true });

  const match = pathname.match(/\/object\/(.+)$/);
  if (!match) return json(404, { error: "unknown route" });
  const key = decodeURIComponent(match[1]);
  if (!KEY_RE.test(key) || key.includes("..")) return json(400, { error: "bad key" });

  const denied = await authorize(req);
  if (denied) return json(401, { error: denied });

  if (req.method === "GET") return await getObject(key);
  if (req.method === "PUT") return await putObject(key, req);
  if (req.method === "DELETE") return await deleteObject(key);
  return json(405, { error: "method not allowed" });
});
