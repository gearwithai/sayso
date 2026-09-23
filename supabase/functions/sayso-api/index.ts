// Sayso licensing API.
// The desktop app talks only to this function. It uses its own device tokens (not Supabase Auth),
// so the gateway's JWT check is off and every action below checks the token itself.
import { createClient } from "npm:@supabase/supabase-js@2";

const db = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!, {
  auth: { persistSession: false },
});

const TRIAL_WORDS = 2000;
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "content-type, x-sayso-token, apikey, authorization",
};

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

async function sha256(s: string) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function newToken() {
  const b = crypto.getRandomValues(new Uint8Array(32));
  return [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
}

type Device = {
  id: string; words_used: number; word_limit: number; license_id: string | null;
};

async function statusOf(d: Device) {
  if (d.license_id) {
    const { data: lic } = await db.from("licenses").select("status, expires_at, email").eq("id", d.license_id).single();
    const valid = lic && lic.status === "active" && (!lic.expires_at || new Date(lic.expires_at) > new Date());
    if (valid) {
      return { plan: "pro", allowed: true, words_used: d.words_used, word_limit: null, email: lic.email };
    }
  }
  return {
    plan: "trial",
    allowed: d.words_used < d.word_limit,
    words_used: d.words_used,
    word_limit: d.word_limit,
  };
}

async function deviceFrom(req: Request): Promise<Device | null> {
  const token = req.headers.get("x-sayso-token");
  if (!token || token.length < 32) return null;
  const { data } = await db.from("devices")
    .select("id, words_used, word_limit, license_id")
    .eq("token_hash", await sha256(token)).maybeSingle();
  return data;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);

  let body: Record<string, unknown> = {};
  try { body = await req.json(); } catch { /* empty body */ }
  const action = String(body.action ?? "");
  const version = String(body.version ?? "").slice(0, 20);

  try {
    // ---- register: first launch (or reinstall) of the app ----
    if (action === "register") {
      const machine = typeof body.machine === "string" ? body.machine.slice(0, 128) : null;
      const token = newToken();
      const token_hash = await sha256(token);
      let device: Device | null = null;
      if (machine) {
        // Same PC reinstalling keeps its trial usage and license
        const { data } = await db.from("devices").select("id, words_used, word_limit, license_id")
          .eq("machine_hash", machine).order("created_at").limit(1).maybeSingle();
        if (data) {
          await db.from("devices").update({ token_hash, app_version: version, last_seen_at: new Date().toISOString() })
            .eq("id", data.id);
          device = data;
        }
      }
      if (!device) {
        const { data, error } = await db.from("devices")
          .insert({ token_hash, machine_hash: machine, app_version: version, word_limit: TRIAL_WORDS })
          .select("id, words_used, word_limit, license_id").single();
        if (error) throw error;
        device = data;
      }
      return json({ token, ...(await statusOf(device!)) });
    }

    const device = await deviceFrom(req);
    if (!device) return json({ error: "unknown device", reregister: true }, 401);

    // ---- status: app start / every few minutes ----
    if (action === "status") {
      await db.from("devices").update({ last_seen_at: new Date().toISOString(), app_version: version || undefined })
        .eq("id", device.id);
      return json(await statusOf(device));
    }

    // ---- usage: app reports words typed (batched) ----
    if (action === "usage") {
      const words = Math.max(0, Math.min(5000, Math.floor(Number(body.words) || 0)));
      if (words) {
        const { error } = await db.rpc("sayso_add_usage", { p_device: device.id, p_words: words });
        if (error) throw error;
        device.words_used += words;
      }
      return json(await statusOf(device));
    }

    // ---- activate: user pastes a license key ----
    if (action === "activate") {
      const key = String(body.key ?? "").trim().toUpperCase();
      const { data: lic } = await db.from("licenses").select("id, status, expires_at, seats").eq("key", key).maybeSingle();
      if (!lic || lic.status !== "active" || (lic.expires_at && new Date(lic.expires_at) <= new Date())) {
        return json({ error: "That license key isn't valid or has expired." }, 400);
      }
      if (device.license_id !== lic.id) {
        const { count } = await db.from("devices").select("id", { count: "exact", head: true }).eq("license_id", lic.id);
        if ((count ?? 0) >= lic.seats) {
          return json({ error: `This key is already used on ${lic.seats} computers. Deactivate one first.` }, 400);
        }
        await db.from("devices").update({ license_id: lic.id }).eq("id", device.id);
        device.license_id = lic.id;
      }
      return json(await statusOf(device));
    }

    // ---- deactivate: free this computer's seat ----
    if (action === "deactivate") {
      await db.from("devices").update({ license_id: null }).eq("id", device.id);
      device.license_id = null;
      return json(await statusOf(device));
    }

    return json({ error: "unknown action" }, 400);
  } catch (e) {
    console.error(e);
    return json({ error: "server error" }, 500);
  }
});
