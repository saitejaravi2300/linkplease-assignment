# LinkPlease Comment-to-DM Automation

A reliability-first implementation of the LinkPlease Tech Intern assignment using **FastAPI + SQLite + asyncio + httpx**.

The core design is deliberately small: persist the event before acknowledging the webhook, atomically reserve `(rule, user)` before sending, keep all outbound work in a durable database queue, enforce the provider's rolling 10/60s limit locally, and reconcile every accepted DM until it is terminal.

## What is implemented

### Part A
- `POST /rules` with the exact required request/response shape.
- Case-insensitive substring keyword matching.
- Durable event persistence and event-id deduplication.
- Atomic `(rule_id, user_id)` uniqueness so a user cannot receive the same rule twice.
- Durable outbound queue; API failures are retried.

### Part B
- HMAC-SHA256 webhook verification using the raw request body and API key.
- `GET /stats` computed from persisted delivery state.
- SQLite WAL + transactions for safe concurrent webhook ingestion.

### Part C
- Accepted DM reconciliation using `GET /v1/dm/{dm_id}`.
- Later `failed` provider deliveries are re-queued with a fresh idempotency key.
- `comment.deleted` cancels work that has not reached a terminal delivered/failed state.
- Persistent rolling-window rate limiter: never deliberately exceeds 10 outbound requests per 60 seconds.
- 500-event bursts are persisted immediately and drained safely rather than dropped.

## Important API contract

The grader-facing routes are exactly:

- `POST /webhook`
- `POST /rules`
- `GET /stats`

`POST /webhook` persists the event synchronously and does not wait for the DM to be sent. This keeps the endpoint fast while ensuring an event is not acknowledged before it is durable.

## Run locally

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
```

Put the API key from the assignment in `.env`:

```env
PSEUDOGRAM_API_KEY=your_real_key
```

Then:

```bash
uvicorn app.main:app --reload
```

Health check:

```bash
curl http://localhost:8000/health
```

Create a rule:

```bash
curl -X POST http://localhost:8000/rules ^
  -H "Content-Type: application/json" ^
  -d "{\"keyword\":\"PRICE\",\"dm_message\":\"Here's the price list\"}"
```

## Signature verification

The webhook signature is:

`sha256=<HMAC-SHA256(raw_request_body, API_KEY)>`

`REQUIRE_WEBHOOK_SIGNATURE=true` is the default. For local manual testing without a signature, set it to `false`; do not use that setting in the submitted deployment.

## Testing

```bash
pip install pytest
pytest -q
```

The tests cover matching, event redelivery, duplicate blocking, deletion cancellation, and signature verification.

## Deployment

A `render.yaml` and `Dockerfile` are included. Set `PSEUDOGRAM_API_KEY` as a secret in the deployment environment.

For a real submission, use persistent storage. The local SQLite implementation is intentionally easy to inspect, but ephemeral deployment storage can lose local state after a restart. See `FAILURES.md`.

## Test the real 500-event path

After deployment, call the mock API's simulator with your deployed webhook URL. Then compare your `/stats` with the simulator's truth endpoint. The assignment says this is the same data used by the grader, so do not skip this step.

## Suggested 3-minute Loom structure

1. 30s — show the three required endpoints and architecture.
2. 60s — explain the two correctness invariants: durable webhook ingestion and `(rule,user)` uniqueness.
3. 45s — show the queue/rate limiter/reconciliation path.
4. 30s — show the 500-event test and stats.
5. 15s — answer the tradeoff question and explain what one more week would change.

## Why these choices

- **SQLite instead of an in-memory queue:** a process restart should not erase pending work.
- **Unique database constraint instead of an application-only check:** two concurrent webhooks cannot both reserve the same `(rule,user)` pair.
- **Idempotency key per logical rule/user delivery:** a network timeout or crash around a send does not automatically create a second DM.
- **Provider status reconciliation:** `202` is treated as accepted, never as delivered.
- **Persistent rate-limit timestamps:** restarting the worker does not reset the outbound limit.

## Submission checklist

- [ ] Put the real API key in deployment secrets, not Git.
- [ ] Deploy the app and verify `/health`.
- [ ] Create at least one real rule.
- [ ] Run the provider's 500-event simulator.
- [ ] Compare `/stats` to `/v1/simulate/{run_id}/truth`.
- [ ] Inspect `FAILURES.md` and make sure you can explain every bullet.
- [ ] Record the 3-minute Loom in your own words.
- [ ] Make the GitHub repository public and keep the deployed URL alive for 7 days.
- [ ] Submit the final repository URL, working URL, Loom URL, and honest completion level to the provider's `/v1/submit` endpoint.
