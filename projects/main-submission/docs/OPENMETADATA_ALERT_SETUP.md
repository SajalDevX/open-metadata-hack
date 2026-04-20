# Pointing OpenMetadata at the Incident Copilot

This guide shows how to configure OpenMetadata so that every failed Data Quality
check fires a webhook at the copilot's `/webhooks/incidents` endpoint.

Tested against OpenMetadata 1.12.x.

---

## Prerequisites

- An OpenMetadata instance you can log into as an **Admin**.
- An **Ingestion Bot** JWT token (Settings → Bots → Ingestion Bot → Copy token).
- The copilot running and reachable from OpenMetadata (same network / Docker
  compose network / public URL). Verify with:
  ```bash
  curl http://<copilot-host>:8080/health
  ```

> **Critical:** OpenMetadata 1.12 actively **blocks** private/RFC-1918 IP ranges
> (including Docker bridge IPs like `172.17.0.x` and `127.0.0.1`). If your copilot
> is on `localhost` or a Docker network, you **must** expose it via a public URL
> (e.g. `ngrok http 8080`) before creating the OM subscription. Using a private IP
> will cause OM to reject the destination with a `400 Bad Request`.

---

## Step 1 — Decide on the integration path

| Option | When to use |
|---|---|
| **Webhook (recommended)** | OpenMetadata can reach the copilot's URL directly (public URL or same LAN). |
| **Polling** | Firewalls / NAT / private IPs block inbound traffic from OM to the copilot. Set `COPILOT_ENABLE_POLLER=true`. |

The rest of this guide covers the **webhook** path. For polling, just export
`COPILOT_ENABLE_POLLER=true`, `OPENMETADATA_BASE_URL`, `OPENMETADATA_JWT_TOKEN`
and restart the copilot — no OpenMetadata-side config needed.

---

## Step 1b — Expose the copilot on a public URL (if on localhost)

If you're running the copilot locally:

```bash
# Install ngrok once, then:
ngrok http 8080
# Copy the https://xxxx.ngrok-free.app URL — use it as <copilot-host> below
```

Verify it's reachable from outside:
```bash
curl https://xxxx.ngrok-free.app/health
# {"status":"ok", ...}
```

---

## Step 2 — Create an Alert destination in OpenMetadata

1. Go to **Settings → Notifications → Alerts** (path may vary slightly by version).
2. Click **Create** → name it `Incident Copilot`.
3. **Source / Resources:** select **`All`** (not `testCase` — OM 1.12 requires
   the resource type to be `all` for eventSubscriptions to fire reliably on DQ events).
4. **Filter:** add a condition `Test Case Status = Failed` — this avoids firing
   on every pass/resumed run.
5. **Destination type:** choose **`Webhook`** (capital W — it appears as `Webhook`
   in the OM 1.12 UI, not `Generic Webhook`).
6. **Endpoint URL:** `https://<your-ngrok-subdomain>.ngrok-free.app/webhooks/incidents`
   - For Docker compose on the same network (no NAT): `http://copilot:8080/webhooks/incidents`
   - For localhost with ngrok: use the ngrok HTTPS URL above
7. **HTTP Method:** `POST`. Content type `application/json`.
8. **Headers:** leave empty (no auth on the copilot webhook endpoint in hackathon
   mode — put the copilot behind a VPN/private network for production).
9. **Save** and click **Send Test** — you should see a new row appear at
   `http://<copilot-host>:8080/` (the dashboard).

---

## Step 3 — Verify a real failure gets routed

Trigger a test failure in your catalog (e.g. run the Profiler on a table with
a broken NULL-ratio check). Within a few seconds:

- Dashboard at `/` shows a new row with the incident ID and `approval_required`
  or `allowed` badge.
- Full brief at `/incidents/{id}/view` renders the 4-block HTML.
- JSON at `/incidents/{id}` returns the canonical payload.
- If Slack is configured, the Slack channel receives the brief.

---

## Example payload successfully ingested from OM 1.12

A real alert from OpenMetadata 1.12 looks like this at `/webhooks/incidents`:

```json
{
  "eventType": "entityCreated",
  "entityType": "testCaseResult",
  "entity": {
    "id": "8a2f3c1e-...",
    "fullyQualifiedName": "sample_data.ecommerce_db.shopify.orders",
    "testCaseResult": {
      "testCaseStatus": "Failed",
      "result": "null ratio 0.42 > threshold 0.10",
      "timestamp": 1713456789000
    }
  },
  "changeDescription": {
    "fieldsAdded": [],
    "fieldsUpdated": [
      {"name": "testCaseStatus", "oldValue": "Success", "newValue": "Failed"}
    ]
  }
}
```

The copilot's `webhook_parser.py` accepts this shape directly and also handles
`entityLink` strings like `<#E::table::sample_data.ecommerce_db.shopify.orders>`.

---

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| OM rejects destination with 400 | Private/RFC-1918 IP — use ngrok or a public URL (see Step 1b). |
| 404 from OM when sending test | Endpoint URL typo — verify with `curl /health` first. |
| Webhook arrives but `entity_fqn` is empty | OM payload shape varies by version — the parser also accepts `entityLink` like `<#E::table::svc.db.t>`. Check payload with `docker logs copilot`. |
| Policy is always `allowed` | Expected when no asset is tagged `PII.Sensitive`. To test the approval path, tag a downstream asset with that classification. |
| Dashboard empty after test fire | Check `docker logs copilot` — parser errors surface there. A known canonical envelope (`incident_id`, `entity_fqn`, `test_case_id`...) is always accepted as fallback. |
| Retries never succeed | `GET /admin/retry-queue` — `last_error` shows why Slack rejects. Verify `SLACK_WEBHOOK_URL`. |
| OM fires on create but not on test failure | Resource type set to `testCase` — change to `All` (OM 1.12 requires this). |

---

## Environment variables the copilot needs

See `.env.example` for the full list. Minimum for live OpenMetadata mode:

```bash
OPENMETADATA_BASE_URL=http://your-om-host:8585/api
OPENMETADATA_JWT_TOKEN=<ingestion-bot-token>
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...   # optional
OPENROUTER_API_KEY=sk-or-...                              # optional
```

---

## Security notes

- The webhook endpoint is unauthenticated. Put the copilot behind your private
  network, VPN, or a reverse proxy (`nginx auth_basic`, `caddy basicauth`, etc.).
- The Slack webhook URL is a secret — keep it out of logs and public repos.
- The Ingestion Bot JWT grants read access to your OM catalog — same rule.
- Container runs as the default `python` user in the `python:3.12-slim` base
  image. For production, consider building a non-root image.
