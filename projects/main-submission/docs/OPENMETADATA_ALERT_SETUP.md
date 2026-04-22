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

---

## Step 1 — Decide on the integration path

| Option | When to use |
|---|---|
| **Webhook (advanced)** | You have a relay/proxy that can sign requests before forwarding to the copilot. |
| **Polling** | Firewalls / NAT block inbound traffic to the copilot. Set `COPILOT_ENABLE_POLLER=true`. |

For polling, just export `COPILOT_ENABLE_POLLER=true`, `OPENMETADATA_BASE_URL`,
`OPENMETADATA_JWT_TOKEN` and restart the copilot — no OpenMetadata-side config needed.

---

## Step 2 — Create an Alert destination in OpenMetadata

1. Go to **Settings → Notifications → Alerts** (path may vary slightly by version).
2. Click **Create** → name it `Incident Copilot`.
3. **Source:** select `Test Case` (or `Test Suite`, depending on your OM version's
   taxonomy). The trigger should be **Test Case Status Change** or equivalent.
4. **Filter:** add a condition `Test Case Status = Failed` — this avoids firing
   on every pass/resumed run.
5. **Destination:** choose **Webhook** → **Generic**.
6. **Endpoint URL:** point to your relay/proxy endpoint. The relay must forward
   to `http://<copilot-host>:8080/webhooks/incidents`.
7. **HTTP Method:** `POST`. Content type `application/json`.
8. **Headers:** your relay must add:
   - `X-Webhook-Timestamp: <unix-seconds>`
   - `X-Webhook-Signature: v1=<hex(hmac_sha256("v1:{timestamp}:{raw_body}", COPILOT_WEBHOOK_SECRET))>`
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

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| 404 from OM when sending test | Endpoint URL typo — verify with `curl /health` first. |
| Webhook arrives but `entity_fqn` is empty | OM payload shape varies by version — the parser also accepts `entityLink` like `<#E::table::svc.db.t>`. Check payload with `kubectl logs` / docker logs. |
| Policy is always `allowed` | Expected when no asset is tagged `PII.Sensitive`. To test the approval path, tag a downstream asset with that classification. |
| Dashboard empty after test fire | Check `docker logs copilot` — parser/signature errors surface there. Canonical envelopes are rejected on the public webhook route. |
| Retries never succeed | `GET /admin/retry-queue` — `last_error` shows why Slack rejects. Verify `SLACK_WEBHOOK_URL`. |

---

## Environment variables the copilot needs

See `.env.example` for the full list. Minimum for live OpenMetadata mode:

```bash
OPENMETADATA_BASE_URL=http://your-om-host:8585/api
OPENMETADATA_JWT_TOKEN=<ingestion-bot-token>
COPILOT_WEBHOOK_SECRET=<shared-secret-used-by-relay>
COPILOT_API_KEY=<optional-read-admin-api-key>
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...   # optional
OPENROUTER_API_KEY=sk-or-...                              # optional
```

---

## Security notes

- `/webhooks/incidents` requires signed requests using `COPILOT_WEBHOOK_SECRET`.
- If you set `COPILOT_API_KEY`, read/admin endpoints require `X-API-Key`.
- The Slack webhook URL is a secret — keep it out of logs and public repos.
- The Ingestion Bot JWT grants read access to your OM catalog — same rule.
- Container runs as the default `python` user in the `python:3.12-slim` base
  image. For production, consider building a non-root image.
