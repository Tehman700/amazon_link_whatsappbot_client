/**
 * WhatsApp linked-device adapter.
 *
 * Connects to WhatsApp as a linked device (multi-device protocol, same as
 * WhatsApp Web), listens for incoming direct messages, and bridges them to
 * the core API's POST /process-message. If the API rewrote a link, the
 * reply is sent back to the sender — re-attaching the image when the
 * original message had one. All business logic lives in the API; this
 * process is a dumb, disposable connector.
 */

import "dotenv/config";
import fs from "node:fs";
import path from "node:path";
import express from "express";
import pino from "pino";
import QRCode from "qrcode";
import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  useMultiFileAuthState,
} from "baileys";

const API_BASE = (process.env.API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
const PORT = Number(process.env.PORT ?? 4000);
const STATUS_TOKEN = process.env.STATUS_TOKEN ?? "";
const SESSION_DIR = process.env.SESSION_DIR ?? path.join(process.cwd(), "session");

const logger = pino({ level: process.env.LOG_LEVEL ?? "warn" });

let sock = null;
let latestQR = null; // raw QR string while waiting for a scan
let status = "starting"; // starting | waiting-for-scan | connected | disconnected
let connectedSince = null;
let lastError = null;

// ---------------------------------------------------------------- WhatsApp

/** Unwrap ephemeral / view-once containers down to the real message. */
function unwrap(message) {
  if (!message) return null;
  if (message.ephemeralMessage) return unwrap(message.ephemeralMessage.message);
  if (message.viewOnceMessage) return unwrap(message.viewOnceMessage.message);
  if (message.viewOnceMessageV2) return unwrap(message.viewOnceMessageV2.message);
  return message;
}

function extractText(message) {
  const m = unwrap(message);
  if (!m) return null;
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    m.documentWithCaptionMessage?.message?.documentMessage?.caption ||
    null
  );
}

async function handleMessage(msg) {
  if (!msg.message || msg.key.fromMe) return;

  const jid = msg.key.remoteJid ?? "";
  // Direct chats only — ignore groups, broadcast, status.
  if (!jid.endsWith("@s.whatsapp.net")) return;

  const sender = "+" + jid.split("@")[0];
  const text = extractText(msg.message);
  if (!text) return;

  let response;
  try {
    response = await fetch(`${API_BASE}/process-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sender, text }),
    });
  } catch (err) {
    logger.error({ err }, "core API unreachable");
    return;
  }

  if (response.status === 404) return; // unregistered sender — stay silent
  if (!response.ok) {
    logger.error({ status: response.status }, "core API error");
    return;
  }

  const result = await response.json();
  if (!result.links_replaced) return; // nothing rewritten — stay silent

  const hasImage = Boolean(unwrap(msg.message)?.imageMessage);
  if (hasImage) {
    const image = await downloadMediaMessage(msg, "buffer", {}, {
      logger,
      reuploadRequest: sock.updateMediaMessage,
    });
    await sock.sendMessage(jid, { image, caption: result.text });
  } else {
    await sock.sendMessage(jid, { text: result.text });
  }
  logger.info({ sender, links: result.links_replaced }, "replied with tagged link");
}

async function start() {
  const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);
  const { version } = await fetchLatestBaileysVersion();

  sock = makeWASocket({
    version,
    auth: state,
    logger,
    markOnlineOnConnect: false,
  });

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", ({ connection, lastDisconnect, qr }) => {
    if (qr) {
      latestQR = qr;
      status = "waiting-for-scan";
    }
    if (connection === "open") {
      latestQR = null;
      status = "connected";
      connectedSince = new Date();
      lastError = null;
      logger.warn("WhatsApp connection open");
    }
    if (connection === "close") {
      status = "disconnected";
      connectedSince = null;
      const code = lastDisconnect?.error?.output?.statusCode;
      lastError = lastDisconnect?.error?.message ?? null;
      if (code === DisconnectReason.loggedOut) {
        // Device was unlinked — wipe the session and offer a fresh QR.
        logger.warn("logged out; clearing session for re-pairing");
        fs.rmSync(SESSION_DIR, { recursive: true, force: true });
      }
      setTimeout(() => start().catch((err) => logger.error(err)), 2000);
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      await handleMessage(msg).catch((err) => logger.error({ err }, "handler failed"));
    }
  });
}

// ------------------------------------------------------------- status page

const app = express();

app.get("/health", (_req, res) => {
  res.json({ status, connected_since: connectedSince });
});

app.get("/", async (req, res) => {
  if (STATUS_TOKEN && req.query.token !== STATUS_TOKEN) {
    res.status(401).send("Unauthorized: append ?token=<STATUS_TOKEN> to the URL");
    return;
  }
  let qrImg = "";
  if (latestQR) {
    qrImg = `<img src="${await QRCode.toDataURL(latestQR, { width: 280 })}" alt="QR code">
      <p>Open WhatsApp on the phone &rarr; Linked Devices &rarr; Link a Device &rarr; scan.</p>`;
  }
  const badge =
    status === "connected"
      ? `<span class="badge ok">Connected</span>`
      : `<span class="badge">${status}</span>`;
  res.send(`<!doctype html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="10">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Amazon Bot — WhatsApp Adapter</title>
<style>
  body{font:16px/1.5 system-ui,sans-serif;background:#111;color:#eee;display:grid;place-items:center;min-height:100vh;margin:0}
  .card{background:#1c2333;border-radius:12px;padding:40px;text-align:center;max-width:420px}
  h1{font-size:20px;margin:0 0 4px}
  .muted{color:#8a93a6;font-size:14px}
  .badge{display:inline-block;border-radius:999px;padding:6px 18px;background:#39415a;margin:16px 0;font-weight:600}
  .badge.ok{background:#1d7a3c}
  img{border-radius:8px;background:#fff;padding:8px;margin-top:8px}
</style></head><body><div class="card">
  <h1>Amazon Bot — WhatsApp Adapter</h1>
  <p class="muted">Linked-device bridge to the core API</p>
  ${badge}
  ${qrImg}
  ${status === "connected" && connectedSince ? `<p class="muted">Connected since ${connectedSince.toLocaleString()}</p>` : ""}
  ${lastError ? `<p class="muted">Last error: ${lastError}</p>` : ""}
  <p class="muted">API: ${API_BASE}</p>
</div></body></html>`);
});

app.listen(PORT, () => logger.warn(`status page on :${PORT}`));

start().catch((err) => {
  logger.error(err);
  process.exit(1);
});
