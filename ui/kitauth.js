/* Kopplung und Anfrage-Unterschrift für die Handy-Oberfläche – dasselbe Verfahren wie kitctl/auth.py.
   Ohne crypto.subtle (das gibt es im Browser nur über https): SHA-256 und HMAC hier in reinem JavaScript,
   Diffie-Hellman mit BigInt. Zufall aus crypto.getRandomValues (geht auch über http). */
"use strict";
const KitAuth = (() => {
  const P = BigInt("0x" +
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DD" +
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED" +
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F" +
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B" +
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA0510" +
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF");
  const G = 2n;
  const enc = s => new TextEncoder().encode(s);
  const hex = b => Array.from(b, x => x.toString(16).padStart(2, "0")).join("");
  const unhex = h => new Uint8Array(h.match(/../g).map(x => parseInt(x, 16)));
  const cat = (...a) => { const n = a.reduce((s, x) => s + x.length, 0), o = new Uint8Array(n); let i = 0; a.forEach(x => { o.set(x, i); i += x.length; }); return o; };
  const rnd = n => { const b = new Uint8Array(n); (globalThis.crypto || require("crypto").webcrypto).getRandomValues(b); return b; };

  // ---- SHA-256 ----
  const K = new Uint32Array([
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,
    0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
    0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,
    0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,
    0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]);
  function sha256(msg) {
    const l = msg.length, nb = ((l + 9 + 63) >> 6) << 6, m = new Uint8Array(nb);
    m.set(msg); m[l] = 0x80;
    const dv = new DataView(m.buffer);
    dv.setUint32(nb - 8, Math.floor(l / 0x20000000)); dv.setUint32(nb - 4, (l << 3) >>> 0);
    const h = new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);
    const w = new Uint32Array(64);
    const rr = (x, n) => (x >>> n) | (x << (32 - n));
    for (let o = 0; o < nb; o += 64) {
      for (let i = 0; i < 16; i++) w[i] = dv.getUint32(o + 4 * i);
      for (let i = 16; i < 64; i++) {
        const s0 = rr(w[i-15], 7) ^ rr(w[i-15], 18) ^ (w[i-15] >>> 3), s1 = rr(w[i-2], 17) ^ rr(w[i-2], 19) ^ (w[i-2] >>> 10);
        w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
      }
      let [a, b, c, d, e, f, g, hh] = h;
      for (let i = 0; i < 64; i++) {
        const t1 = (hh + (rr(e, 6) ^ rr(e, 11) ^ rr(e, 25)) + ((e & f) ^ (~e & g)) + K[i] + w[i]) >>> 0;
        const t2 = ((rr(a, 2) ^ rr(a, 13) ^ rr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) >>> 0;
        hh = g; g = f; f = e; e = (d + t1) >>> 0; d = c; c = b; b = a; a = (t1 + t2) >>> 0;
      }
      h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
    }
    const out = new Uint8Array(32), od = new DataView(out.buffer);
    h.forEach((v, i) => od.setUint32(4 * i, v));
    return out;
  }
  function _hmac(k, msg) {
    const ipad = k.map(x => x ^ 0x36), opad = k.map(x => x ^ 0x5c);
    return sha256(cat(opad, sha256(cat(ipad, msg))));
  }

  // ---- Diffie-Hellman ----
  function modpow(b, e, m) { let r = 1n; b %= m; while (e > 0n) { if (e & 1n) r = r * b % m; b = b * b % m; e >>= 1n; } return r; }
  const i2b = x => unhex(x.toString(16).padStart(512, "0"));
  function keypair() { const a = BigInt("0x" + hex(rnd(32))) | (1n << 255n); return [a, modpow(G, a, P)]; }
  function derive(code, A, B, shared) { return _hmac(pad(enc(code)), cat(enc("kitpair1"), i2b(A), i2b(B), i2b(shared))); }
  function pad(key) { if (key.length > 64) key = sha256(key); const k = new Uint8Array(64); k.set(key); return k; }
  const mac = (key, label, text) => hex(_hmac(pad(key), enc(label + "|" + text)));
  const bodyHash = s => hex(sha256(enc(s || "")));
  const sign = (key, method, path, ts, nonce, bh) => hex(_hmac(pad(key), enc(method.toUpperCase() + "\n" + path + "\n" + ts + "\n" + nonce + "\n" + bh)));

  // ---- Zustand im Browser ----
  let offset = 0, device = "", cred = null;
  const store = globalThis.localStorage;
  function load(dev) { device = dev; try { cred = JSON.parse(store.getItem("kitpair:" + dev) || "null"); } catch (e) { cred = null; } return !!cred; }
  function save(c) { cred = c; try { store.setItem("kitpair:" + device, JSON.stringify(c)); } catch (e) {} }
  function forget() { cred = null; try { store.removeItem("kitpair:" + device); } catch (e) {} }
  function fields(method, path, body) {
    if (!cred) return null;
    const ts = String(Math.floor(Date.now() / 1000 + offset)), nonce = hex(rnd(12));
    return {c: cred.client_id, t: ts, n: nonce, s: sign(unhex(cred.key), method, path, ts, nonce, bodyHash(body))};
  }
  function headers(method, path, body) {
    const f = fields(method, path, body);
    return f ? {"X-Kit-Client": f.c, "X-Kit-Time": f.t, "X-Kit-Nonce": f.n, "X-Kit-Sig": f.s} : {};
  }
  function url(path) {     // für EventSource (keine eigenen Kopfzeilen möglich)
    const f = fields("GET", path, "");
    return f ? path + (path.includes("?") ? "&" : "?") + "kc=" + f.c + "&kt=" + f.t + "&kn=" + f.n + "&ks=" + f.s : path;
  }
  async function hello() {
    const t0 = Date.now() / 1000;
    const r = await fetch("/api/pair/hello", {cache: "no-store", headers: headers("GET", "/api/pair/hello", "")});
    if (r.status === 404) return null;
    const j = await r.json();
    offset = j.time - (t0 + Date.now() / 1000) / 2;
    return j;
  }
  let pending = null;
  async function start(name) {
    const [a, A] = keypair();
    const r = await fetch("/api/pair/start", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name, kind: "phone", A: A.toString(16)})});
    const j = await r.json();
    if (!j.ok) throw new Error(j.error || "Kopplung nicht möglich");
    pending = {a, A, r: j};
    if (j.device_id) device = j.device_id;
    return j;
  }
  async function confirm(code) {
    if (!pending) throw new Error("Keine Kopplung angefragt");
    const {a, A, r} = pending, B = BigInt("0x" + r.B);
    const key = derive(code, A, B, modpow(B, a, P));
    const res = await fetch("/api/pair/confirm", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({request_id: r.request_id, mac: mac(key, "client", r.request_id)})});
    const j = await res.json();
    if (!j.ok) { const e = new Error(j.error || "Kopplung fehlgeschlagen"); e.status = res.status; throw e; }
    if (mac(key, "server", j.client_id) !== j.mac) throw new Error("Der Kit hat sich nicht ausgewiesen");
    pending = null;
    save({client_id: j.client_id, key: hex(key)});
    return j;
  }
  return {sha256, hex, unhex, enc, hmac: (k, m) => _hmac(pad(k), m), modpow, keypair, derive, mac, sign, bodyHash, P, G,
          load, save, forget, headers, url, hello, start, confirm, get paired() { return !!cred; }, get device() { return device; }};
})();
if (typeof module !== "undefined") module.exports = KitAuth;
