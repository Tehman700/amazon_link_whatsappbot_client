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

// IDs of messages this adapter sent — used to stop the bot's own replies in
// the self-chat from being processed again (infinite loop guard).
const sentIds = new Set();

// Rolling log of recent message decisions, shown on the status page so the
// bot can be debugged from a browser without SSH.
const events = [];
function logEvent(jid, outcome) {
  events.unshift({ time: new Date(), jid, outcome });
  if (events.length > 20) events.pop();
  logger.warn({ jid, outcome }, "message event");
}

/** True when the chat is the account's own "Message Yourself" chat.
 *  Handles both classic phone JIDs and WhatsApp's newer LID addressing. */
function isSelfChat(jid) {
  const me = sock?.user;
  if (!me) return false;
  const pn = (me.id ?? "").split(":")[0];
  const lid = (me.lid ?? "").split(":")[0];
  return jid === `${pn}@s.whatsapp.net` || (Boolean(lid) && jid === `${lid}@lid`);
}

/** Resolve the sender's phone number (+E164) from a message.
 *  Handles classic phone JIDs and LID (privacy-addressed) chats via every
 *  known fallback: key alt fields (6.7.x: senderPn/participantPn, v7:
 *  remoteJidAlt/participantAlt) and the lid-mapping store when available. */
function resolveSender(jid, msg) {
  const pnFrom = (value) =>
    value && String(value).includes("@s.whatsapp.net")
      ? "+" + String(value).split("@")[0].split(":")[0]
      : null;

  if (jid.endsWith("@s.whatsapp.net")) return "+" + jid.split("@")[0];
  if (jid.endsWith("@lid")) {
    const key = msg.key ?? {};
    const direct =
      pnFrom(key.senderPn) ||
      pnFrom(key.participantPn) ||
      pnFrom(key.remoteJidAlt) ||
      pnFrom(key.participantAlt) ||
      pnFrom(key.participant);
    if (direct) return direct;
    try {
      const mapped = sock?.signalRepository?.lidMapping?.getPNForLID?.(jid);
      const viaStore = pnFrom(mapped);
      if (viaStore) return viaStore;
    } catch {
      /* mapping store not available in this Baileys version */
    }
    if (key.fromMe) return "+" + (sock?.user?.id ?? "").split(":")[0];
  }
  return null;
}

async function handleMessage(msg, upsertType) {
  const jid = msg.key?.remoteJid ?? "";
  // Direct chats only — ignore groups, broadcast, status.
  if (jid.endsWith("@g.us") || jid === "status@broadcast" || jid.endsWith("@newsletter"))
    return;

  // Undecryptable / stub messages have no content — log instead of silence,
  // repeated occurrences point at a broken session (fix: unlink + re-pair).
  if (!msg.message) {
    logEvent(jid, `skipped: no content (stub=${msg.messageStubType ?? "?"} type=${upsertType})`);
    return;
  }

  const selfChat = isSelfChat(jid);

  // Outgoing messages are ignored, EXCEPT in the account's "Message
  // Yourself" chat, where they enable solo testing by the bot's owner.
  if (msg.key.fromMe) {
    if (!selfChat) return;
    if (sentIds.has(msg.key.id)) return; // our own reply — don't loop
  }

  // Own-device messages can arrive as 'append' instead of 'notify'. Accept
  // append only in the self-chat and only if fresh, so pairing history sync
  // never triggers a flood of replies.
  if (upsertType !== "notify") {
    const ts = Number(msg.messageTimestamp ?? 0) * 1000;
    if (!selfChat || !ts || Date.now() - ts > 120_000) {
      logEvent(jid, `skipped: non-notify upsert (type=${upsertType}, selfChat=${selfChat})`);
      return;
    }
  }

  const sender = resolveSender(jid, msg);
  if (!sender) {
    logEvent(
      jid,
      `skipped: cannot resolve sender number (key=${JSON.stringify(msg.key)})`,
    );
    return;
  }
  const text = extractText(msg.message);
  if (!text) {
    logEvent(jid, `skipped: no text/caption (from ${sender})`);
    return;
  }

  let response;
  try {
    response = await fetch(`${API_BASE}/process-message`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sender, text }),
    });
  } catch (err) {
    logEvent(jid, `error: core API unreachable (${err.message})`);
    return;
  }

  if (response.status === 404) {
    logEvent(jid, `skipped: ${sender} is not a registered user`);
    return;
  }
  if (!response.ok) {
    logEvent(jid, `error: core API returned ${response.status}`);
    return;
  }

  const result = await response.json();
  if (!result.links_replaced) {
    logEvent(jid, "skipped: no Amazon link found/rewritten");
    return;
  }

  // Never reply to a @lid address — Baileys 6.x accepts such sends but they
  // are frequently not delivered. We know the sender's real number, so reply
  // to the classic phone-number jid instead (WhatsApp shows both in one chat).
  const replyJid = jid.endsWith("@lid")
    ? sender.slice(1) + "@s.whatsapp.net"
    : jid;

  const hasImage = Boolean(unwrap(msg.message)?.imageMessage);
  let sent;
  if (hasImage) {
    const image = await downloadMediaMessage(msg, "buffer", {}, {
      logger,
      reuploadRequest: sock.updateMediaMessage,
    });
    sent = await sock.sendMessage(replyJid, { image, caption: result.text });
  } else {
    sent = await sock.sendMessage(replyJid, { text: result.text });
  }
  if (sent?.key?.id) {
    sentIds.add(sent.key.id);
    if (sentIds.size > 500) sentIds.delete(sentIds.values().next().value);
  }
  logEvent(
    jid,
    `replied: ${result.links_replaced} link(s) tagged for ${sender} (to ${replyJid})`,
  );
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
    for (const msg of messages) {
      await handleMessage(msg, type).catch((err) =>
        logEvent(msg.key?.remoteJid ?? "?", `error: handler failed (${err.message})`),
      );
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
  // Refresh fast only while pairing (QR codes rotate); slow when settled.
  const refreshSeconds = status === "waiting-for-scan" ? 10 : 120;
  res.send(`<!doctype html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="${refreshSeconds}">
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
  .events{text-align:left;margin-top:24px;border-top:1px solid #39415a;padding-top:12px}
  .events h2{font-size:14px;color:#8a93a6;margin:0 0 8px}
  .event{font-size:13px;padding:6px 0;border-bottom:1px solid #262d40;word-break:break-all}
</style></head><body><div class="card">
  <h1>Amazon Bot — WhatsApp Adapter</h1>
  <p class="muted">Linked-device bridge to the core API</p>
  ${badge}
  ${qrImg}
  ${status === "connected" && connectedSince ? `<p class="muted">Connected since ${connectedSince.toLocaleString()}</p>` : ""}
  ${lastError ? `<p class="muted">Last error: ${lastError}</p>` : ""}
  ${
    // Hidden debug view — append &events=1 to the URL to see message decisions.
    req.query.events === "1" && events.length
      ? `<div class="events"><h2>Recent messages</h2>${events
          .map(
            (e) =>
              `<div class="event"><span class="muted">${e.time.toLocaleTimeString()}</span> ${e.jid}<br>${e.outcome}</div>`,
          )
          .join("")}</div>`
      : ""
  }
</div></body></html>`);
});

app.listen(PORT, () => logger.warn(`status page on :${PORT}`));

start().catch((err) => {
  logger.error(err);
  process.exit(1);
});
