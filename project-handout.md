# Project Handout: WhatsApp Amazon Affiliate Link Bot

This document is the full context for a client project. Read this before writing any code — it captures everything confirmed with the client so far, including how the requirements evolved during discussion.

**Source material:** the client sent two separate written spec documents (first one shorter, second one a cleaner/expanded restatement) plus a voice note and a WhatsApp screenshot showing a real sample message. The two written documents are consistent on the core logic but differ slightly in details (marketplace list, explicit throughput requirement) — these differences are called out inline below wherever relevant, rather than silently merged, so nothing gets lost.

---

## 1. One-Line Summary

A WhatsApp bot that receives a message containing an Amazon product link (plus any other content — image, caption text, etc.), finds the Amazon link inside it, swaps in the correct affiliate tracking tag **for that specific sender and that specific Amazon marketplace**, and sends the message back with only the link changed — everything else in the message passed through untouched.

---

## 2. Core Business Problem

Amazon Associates (affiliate marketers) sign up separately for each Amazon marketplace (Amazon US, UK, Canada, Germany, France, Italy, Spain, Netherlands — 8 marketplaces total). Each marketplace gives them a different **Associate Tracking ID (Associate Tag)**.

Manually remembering "which tag goes with which country" for every product link is tedious. This bot automates that: a user just forwards/sends a raw Amazon link, and the bot returns the same link with their correct tag attached — no manual work, no thinking about which country or which tag.

**Critical nuance: multi-user.** This isn't one affiliate automating their own links — it's a system serving **multiple different users**, each with their own complete set of 8 tracking IDs. Two different users sending the exact same Amazon product URL must get back two different affiliate links, because each user's tag is different.

---

## 3. Data Model

Each user has a separate tracking ID per Amazon marketplace. Think of it as a lookup table: `(user, marketplace) → tracking_id`.

Example (illustrative, not exhaustive):

| User  | US (.com)  | UK (.co.uk) | CA (.ca)   | DE (.de)   |
|-------|------------|-------------|------------|------------|
| Ali   | alius-20   | aliuk-21    | alica-20   | alide-21   |
| Ahmed | ahmedus-20 | ahmeduk-21  | ahmedca-20 | ahmedde-21 |

**Important: marketplace list is NOT a fixed set — design for it to be extensible.** The client's two spec documents listed slightly different marketplace sets (one mentioned Netherlands, the other mentioned Australia and said "and more"), which means the actual list of supported marketplaces is open-ended and may grow later. **Do not hardcode marketplaces as a fixed enum.** Instead:

- `marketplaces` table: `id`, `code` (e.g. `US`, `UK`, `AU`), `domain` (e.g. `amazon.com`, `amazon.co.uk`, `amazon.com.au`) — admin-manageable, so a new marketplace can be added without a schema change or redeploy
- `tracking_ids` table: `id`, `user_id` (FK), `marketplace_id` (FK), `tag` (string)
- `users` table: `id`, `name`, `whatsapp_number` (unique identifier for matching incoming messages), `email` (admin-editable, not otherwise used in bot logic yet)

Domain detection logic should look up the marketplace by matching the incoming URL's domain against the `marketplaces` table, not against a hardcoded if/else list — this way adding a new country is a dashboard action, not a code change.

The admin can manually edit any user's info (including email) and any of their tracking IDs at any time via the dashboard. This is standard CRUD — no special logic beyond validating and saving the edited value.

---

## 4. Runtime Flow (What Happens When a Message Arrives)

1. Bot receives an incoming WhatsApp message (webhook).
2. **Identify sender** — match the incoming WhatsApp number against the `users` table. If the number isn't recognized, decide on fallback behavior (see Open Questions).
3. **Scan the message content for an Amazon URL** — the URL can appear anywhere inside the message text/caption, mixed in with other freeform text (see Section 5 for real example).
4. **Detect the marketplace from the URL's domain** — look up the domain against the `marketplaces` table (see Section 3). Known examples so far: `amazon.com` (US), `amazon.co.uk` (UK), `amazon.ca` (CA), `amazon.de` (DE), `amazon.fr` (FR), `amazon.it` (IT), `amazon.es` (ES), `amazon.nl` (NL), `amazon.com.au` (AU) — but treat this as a starting/seed list, not the full set. The client's requirements documents have listed different, inconsistent marketplace sets across messages, so more may be added later via the admin dashboard.
5. **Look up that user's tracking ID for that specific marketplace** — this is a 2D lookup: `(sender, detected_marketplace) → tag`. E.g., a UK link from Ali pulls Ali's UK tag, not his US tag.
6. **Rewrite the URL** — attach the tag as a query parameter (`tag=<value>`). Must use a proper URL parser, NOT string concatenation, because incoming URLs may already have query params (e.g., `?th=1`), so the tag needs to be merged in correctly (`&tag=...` if params exist, `?tag=...` if not).
7. **Reconstruct and send the reply** — the original message content (image, caption text, emojis, any other text) is preserved **exactly as received**, with only the URL substring swapped out for the new tagged version.

---

## 5. Confirmed Message Format (Real Example)

The client shared a real screenshot of what an incoming message actually looks like. It's typically a **forwarded WhatsApp message**: an image with a freeform text caption underneath it, e.g.:

```
[Product image attached]

Usa review
Store name: YusersaEssentials
https://www.amazon.com/dp/B0GS64BBG2?th=1
```

**Key confirmed rule (explicitly stated by client, twice):**
> The bot returns ONLY the changed link. Everything else in the message — image, "Usa review", "Store name: ...", any other text — is returned exactly as received, untouched. The bot does NOT parse or extract structured fields like "product title" or "sold by" as separate data. It treats all non-URL content as opaque passthrough text.

This was a scope correction during discussion — an earlier version of the requirement implied the bot needed to fetch/extract product image, title, and seller info itself (which would have required Amazon's Product Advertising API or scraping). **That is NOT needed.** The user already includes the image and all descriptive text themselves in the message they send; the bot's only job is the link swap.

---

## 6. What This Project Explicitly Does NOT Need

- ❌ No LLM / AI model of any kind. This is 100% deterministic logic: regex for URL detection, domain string matching for marketplace detection, a database lookup, and URL query-param manipulation. No natural language understanding or ambiguity resolution is involved anywhere in this pipeline.
- ❌ No Amazon Product Advertising API (PA-API) — not fetching product data, so no need for Amazon Associate API approval.
- ❌ No scraping of Amazon product pages.
- ❌ No payment processing.
- ❌ No product search functionality — the API only rewrites an existing URL, never generates a new one from scratch.

Keep the implementation this simple. Do not over-engineer with AI/ML components — none are justified by the actual requirements.

**Performance note:** client has specified needing to support 100+ link generations per user per day. This is trivial for the described architecture (a single lookup + string operation per request) and does not require any special scaling design — a standard FastAPI + PostgreSQL setup on a small EC2 instance handles this comfortably. Worth stating explicitly back to the client that the design accommodates this, even though no extra engineering work is needed for it.

---

## 7. Recommended Architecture

**Build order — core API first, WhatsApp integration LAST.** Rationale: WhatsApp Business API setup (Meta Business verification, phone number registration) is often the slowest, least controllable part of the timeline. Building and fully testing the core transformation logic independently (via Postman/direct API calls) means development isn't blocked waiting on Meta's approval process.

**Phase 1 — Core API (standalone, no WhatsApp dependency)**
- FastAPI service, e.g. `POST /process-message`
- Input: sender identifier (phone number) + raw message text/caption (+ optionally image reference)
- Output: same content, with the Amazon link swapped for the tagged version
- Fully testable with fake/sample data — Ali, Ahmed, various marketplaces, various caption formats, URLs with and without existing query params

**Phase 2 — Admin Dashboard**
- Next.js/React CRUD interface
- Add/edit/delete users (name, WhatsApp number, email)
- Add/edit each user's 8 marketplace tracking IDs
- Simple auth (single admin, no need for complex role system in v1)
- No dependency on WhatsApp being live yet — can be built and tested in parallel with Phase 1

**Phase 3 — WhatsApp Adapter Layer (built last)**
- Thin webhook handler using WhatsApp Business Cloud API (Meta direct, or Twilio/360dialog wrapper)
- Receives WhatsApp's incoming message payload → extracts phone number + text/caption + image (if present)
- Calls the Phase 1 core API internally
- Takes the response → sends it back via WhatsApp's send-message API, reattaching the image if one was present
- Low-risk since the core logic is already tested — this layer just translates WhatsApp's payload format in and out

**Stack:**
- Backend: FastAPI
- Database: PostgreSQL
- Dashboard: Next.js / React
- Deployment: AWS EC2 + Nginx + SSL
- Messaging: WhatsApp Business Cloud API (Meta) — evaluate Twilio/360dialog as faster-to-setup alternatives if direct Meta approval is slow

---

## 8. Important Implementation Details / Edge Cases to Handle

- **URL merging must be correct**: use `urllib.parse` (or equivalent) to properly parse existing query strings and append `tag=...` — never naive string concatenation, since URLs like `?th=1` already have a `?`.
- **Shortened Amazon links** (`amzn.to/...`): these redirect to the real domain. The bot may need to resolve the redirect first to detect the true marketplace — confirm with client whether this is in scope for v1 or can be deferred.
- **Multiple Amazon links in one message**: unclear if this happens in practice — confirm with client whether to replace just the first link found, or all links present.
- **No Amazon link found in the message**: decide fallback behavior — ignore silently, or reply with an error/help message. Not yet confirmed with client.
- **Unregistered sender** (WhatsApp number not in the `users` table): decide fallback — ignore, or reply that they're not registered. Not yet confirmed with client.
- **Image handling**: the bot must be able to receive an image attachment from WhatsApp and re-send the same image in its reply, alongside the modified caption text. This is standard WhatsApp Cloud API media handling (download media by ID, re-upload/re-send).

---

## 9. Activation / Onboarding Model (Recommended, Pending Client Confirmation)

Per the original spec document, activation method was left open to the developer's recommendation. Proposed approach for v1 (simplest, lowest scope):

- **Admin manually whitelists users.** Admin adds a user's name, WhatsApp number, and tracking IDs into the dashboard.
- The bot only processes messages from WhatsApp numbers it recognizes in the `users` table.
- No self-service signup, no OTP verification flow in v1 — keeps scope tight. Can be added later as a separate phase if the client wants scale.

---

## 10. Information Still Needed From Client

- [ ] Confirmation: WhatsApp Business API access already set up, or needs to be initiated (Meta Business verification can take several days — this is the biggest external timeline risk)
- [ ] Initial list of users to onboard: names + WhatsApp numbers
- [ ] Each user's tracking ID for each of the 8 marketplaces they're active in
- [ ] Confirm the actual, final list of marketplaces needed for v1 — the client's two spec documents gave inconsistent lists (one included Netherlands, the other included Australia and said "and more"), so this needs to be nailed down explicitly rather than assumed
- [ ] Confirm "admin manually whitelists" activation approach is acceptable for v1
- [ ] Fallback behavior: what to do when no Amazon link is found in a message
- [ ] Fallback behavior: what to do with an unregistered/unknown sender
- [ ] What to do if multiple Amazon links appear in a single message
- [ ] A few more real sample forwarded messages (like the screenshot example) to test caption-format variety
- [ ] Any specific admin dashboard login/access requirements

---

## 11. Budget & Timeline (As Discussed, Not Yet Finalized With Client)

- **Estimated build time**: ~6–10 working days of focused development (~1.5–2 weeks calendar time, accounting for feedback cycles and potential WhatsApp Business API approval delays outside developer control)
- **Estimated budget**: ~110,000–140,000 PKR for MVP (core link-conversion engine + WhatsApp integration + basic admin dashboard), suggested as milestone-based payment (e.g., 30% upfront / 40% at working prototype / 30% on delivery)
- This estimate reflects the current confirmed scope (no LLM, no product data fetching, no payments) — if scope changes (e.g., self-service activation, analytics, click tracking), budget and timeline should be revisited.

---

## 12. Context for Claude Code

The developer (Tehman) has prior experience with FastAPI, PostgreSQL, React/Next.js, AWS EC2, Nginx deployment, and webhook-based automation (n8n, RetellAI/VAPI voice bots for other clients). This project is lower complexity than his past voice-AI integrations — it's essentially CRUD + webhook + string/URL manipulation, no AI components. Prioritize simplicity, correctness of the URL-merging logic, and clean separation between the core API (Phase 1) and the WhatsApp transport layer (Phase 3) so the core logic can be built and tested independently before WhatsApp API access is even ready.
