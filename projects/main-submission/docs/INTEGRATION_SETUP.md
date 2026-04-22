# Integration Setup Guide

Where to get the credentials the copilot reads from `.env`.
The service can run in demo mode with minimal env, but webhook ingest requires
`COPILOT_WEBHOOK_SECRET`, and protected routes require `COPILOT_API_KEY` when set.

| Variable | What it unlocks |
|---|---|
| `COPILOT_WEBHOOK_SECRET` | Required signature verification on `/webhooks/incidents` |
| `COPILOT_API_KEY` | Protects read/admin routes via `X-API-Key` |
| `COPILOT_APPROVER_USERS` | Slack user-ID allowlist for approval/deny actions |
| `OPENROUTER_API_KEY` | AI-generated RCA narratives + recommendation bullets |
| `OPENMETADATA_BASE_URL` + `OPENMETADATA_JWT_TOKEN` | Live context resolution against your real OpenMetadata catalog |
| `SLACK_WEBHOOK_URL` | Slack delivery of the 4-block brief as a Block Kit message |
| `SLACK_SIGNING_SECRET` | Signed verification for ack/approve/deny button clicks |

---

## 1. `OPENROUTER_API_KEY`

Enables Claude-generated RCA narratives and DQ recommendations.

1. Sign up at **https://openrouter.ai**
2. **Dashboard → Keys → Create Key**
3. Copy the `sk-or-v1-...` string
4. Load $1–$5 of credit (Haiku calls are ~$0.0001 each — plenty)

Without this key the service uses deterministic template strings. The demo
works either way.

---

## 2. `OPENMETADATA_BASE_URL` + `OPENMETADATA_JWT_TOKEN`

You need a running OpenMetadata instance.

### Path A — Run OpenMetadata locally (easiest, 5 min)

```bash
mkdir ~/om-local && cd ~/om-local
curl -sL -o docker-compose.yml \
  https://github.com/open-metadata/OpenMetadata/releases/download/1.12.0-release/docker-compose.yml
docker compose up -d
# Wait ~2 min for first boot
```

- UI: **http://localhost:8585**
- Default login: `admin@open-metadata.org` / `admin`
- `OPENMETADATA_BASE_URL` = `http://localhost:8585/api`
  - From inside a Docker Compose network use: `http://host.docker.internal:8585/api`

### Path B — Collate Cloud (hosted)

- `OPENMETADATA_BASE_URL = https://<your-workspace>.getcollate.io/api`

### Getting the JWT token (both paths)

1. Log in to OpenMetadata as admin
2. Click the gear icon → **Settings**
3. Left sidebar → **Bots**
4. Click **ingestion-bot** (or create a new bot)
5. In the **JWT Token** row, pick **Unlimited** in the expiration dropdown (so
   it doesn't expire mid-demo) and click **Revoke & Generate New Token**
6. Copy the long `eyJraWQi...` string — that's your `OPENMETADATA_JWT_TOKEN`

> Why bot, not user JWT: user tokens expire in hours; bot tokens last until
> you revoke them.

### Sanity-check the values

```bash
curl -H "Authorization: Bearer $OPENMETADATA_JWT_TOKEN" \
  $OPENMETADATA_BASE_URL/v1/system/version
```
Should return a version JSON, not a 401.

---

## 3. `SLACK_WEBHOOK_URL`

Posts the 4-block brief into a Slack channel as a Block Kit message with
action buttons.

1. Go to **https://api.slack.com/apps**
2. **Create New App** → **From scratch**
   - App name: `Incident Copilot`
   - Workspace: pick yours
3. In the left sidebar, click **Incoming Webhooks**
4. Toggle **Activate Incoming Webhooks** → **On**
5. Scroll down → click **Add New Webhook to Workspace**
6. Pick the channel you want briefs posted to (e.g. `#data-incidents`)
7. Click **Allow**
8. Copy the webhook URL — looks like:
   `https://hooks.slack.com/services/T01234ABC/B98765XYZ/aBcDeFgHiJkLmN...`

### Sanity-check

```bash
curl -X POST $SLACK_WEBHOOK_URL \
  -H "Content-Type: application/json" \
  -d '{"text":"hello from copilot"}'
```

You should see `hello from copilot` in your channel.

---

## 4. `SLACK_SIGNING_SECRET`

Needed only if you want the **Acknowledge / Approve / Deny** buttons on each
Slack brief to actually do something. The copilot uses this secret to verify
that button-click requests to `/slack/actions` really come from Slack.

Same Slack app you created in step 3:

1. **https://api.slack.com/apps** → click your app
2. Left sidebar → **Basic Information**
3. Scroll to **App Credentials**
4. Find **Signing Secret** → click **Show** → copy the value

### Wire up the Request URL

For buttons to reach your copilot, Slack needs a public URL:

5. Left sidebar → **Interactivity & Shortcuts** → toggle **On**
6. **Request URL:**
   - If your copilot is already public: `https://your-public-host/slack/actions`
   - Local dev: expose port 8080 via ngrok:
     ```bash
     ngrok http 8080
     # Copy the https URL, e.g. https://a1b2c3d4.ngrok.io
     # Set Request URL to https://a1b2c3d4.ngrok.io/slack/actions
     ```
7. Click **Save Changes** in Slack

---

## Minimum-to-try matrix

You don't need all four credentials. Start with what you have:

| Have | Try this |
|---|---|
| **Nothing** | `./scripts/verify.sh` — fixture-backed demo, 30 seconds |
| **+ OpenRouter key** | Same as above, but RCA narratives come from Claude |
| **+ OpenMetadata** | Set URL + JWT, run `python3 scripts/run_server.py`, then either use poller mode (`COPILOT_ENABLE_POLLER=true`) or send signed webhook requests via a relay. See `docs/OPENMETADATA_ALERT_SETUP.md`. |
| **+ Slack webhook** | Briefs arrive in your channel as Block Kit messages. Buttons are visible but not yet clickable. |
| **+ Slack signing secret + ngrok + approver IDs** | Buttons become clickable. `approve/deny` for approval-required incidents require `COPILOT_APPROVER_USERS` (Slack user IDs). |

---

## Putting it all together in `.env`

Edit `projects/main-submission/.env` (already gitignored, safe to store secrets):

```bash
# Service
COPILOT_HOST=127.0.0.1
COPILOT_PORT=8080
COPILOT_DB_PATH=runtime/incidents.db
COPILOT_WEBHOOK_SECRET=<shared-secret>
COPILOT_API_KEY=<optional-api-key-for-read-admin-routes>
COPILOT_APPROVER_USERS=U12345,U67890

# AI
OPENROUTER_API_KEY=sk-or-v1-...

# OpenMetadata
OPENMETADATA_BASE_URL=http://localhost:8585/api
OPENMETADATA_JWT_TOKEN=eyJraWQi...

# Slack
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
SLACK_SIGNING_SECRET=abc123...
```

Then:

```bash
# Docker path
docker compose up --build

# Or direct Python path
set -a && source .env && set +a
python3 scripts/run_server.py
```

---

## Security reminders

- **Never paste live credentials in chat, commit messages, screenshots, or Slack threads.**
- If a secret leaks (even in a DM), revoke it at the source immediately.
- `.env` is gitignored globally — `git status` will not show it. Keep it that way.
- The webhook endpoint `/webhooks/incidents` requires signed requests
  (`X-Webhook-Timestamp` + `X-Webhook-Signature`) using `COPILOT_WEBHOOK_SECRET`.
- For OpenMetadata integration, use poller mode or a signing relay/proxy.
- The Slack signing-secret flow on `/slack/actions` rejects requests older than
  5 minutes (replay protection) — this is the only endpoint where Slack
  signature checking is on.
