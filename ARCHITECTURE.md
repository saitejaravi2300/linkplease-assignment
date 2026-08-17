# Architecture and correctness invariants

```text
PseudoGram
   |
   | POST /webhook + HMAC
   v
FastAPI
   |
   | persist event + reserve deliveries atomically
   v
SQLite (WAL)
   |                         |
   | queued deliveries       | event / delivery truth
   v                         v
Background worker        GET /stats
   |
   +--> persistent 10/60s send limiter
   |
   +--> POST /v1/dm/send
   |       |
   |       +--> 202 -> accepted -> poll GET /v1/dm/{id}
   |       +--> 500/429 -> retry
   |       +--> 400 -> failed
   |
   +--> delivered / failed terminal state
```

## Invariants

### 1. A webhook is not acknowledged before persistence

The event is inserted into SQLite inside a transaction before `/webhook` returns 200. If the transaction fails, the endpoint returns 503 so the provider can redeliver.

### 2. A user can receive a rule at most once

`deliveries` has a database-level `UNIQUE(rule_id, user_id)` constraint. The uniqueness guarantee is therefore atomic even if two webhook requests arrive at the same time.

### 3. Duplicate provider events do not re-run matching

`events.event_id` is the primary key. A repeated event ID becomes a no-op after the first durable insert.

### 4. Accepted is not delivered

A `202` response stores the provider's `dm_id` and leaves the delivery in `accepted`. Only a provider status of `delivered` increments `sent`.

### 5. Rate limiting survives restarts

Every outbound send reserves a timestamp in the same database. The worker only sends when fewer than 10 timestamps exist in the previous 60 seconds.

### 6. Retry identity is deliberate

Retries after a transport/server error reuse the same logical idempotency key. If the provider accepted the request but the client did not receive the response, the provider can return the original DM instead of creating another one. A later provider-confirmed `failed` delivery receives a fresh key for a genuinely new send attempt.
