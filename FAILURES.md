# Known limitations and failure modes

This document is intentionally honest. The assignment explicitly asks for the conditions under which the system can still lose a DM, send a duplicate, or report a wrong number.

- **Single-instance deployment assumption for the worker:** the SQLite database is shared safely between processes, but this project is designed to run one web process/worker. Running multiple independent containers with separate local disks would split the queue and rate-limit state. A production version would move the database and queue state to a shared PostgreSQL/Redis setup.

- **Hard process termination between an external send and local persistence:** the mock API supports `Idempotency-Key`, which protects the send call from a retry using the same key. If the process is killed at the exact point after the remote API accepts a request but before the local transaction records the `dm_id`, the next retry uses the same logical idempotency key, so the remote side should return the original DM. If the remote API's idempotency store itself were unavailable, reconciliation would require a provider-side lookup that this mock API does not expose by idempotency key.

- **Delivery truth is eventually consistent:** a `202 Accepted` is not counted as sent. The worker polls `/v1/dm/{dm_id}` and only increments `sent` after `delivered`. During the polling interval `/stats` intentionally reports the item as `queued`. If the process is offline for longer than the provider's retention period for DM IDs, a delivery could remain unresolved until manual intervention.

- **Local filesystem durability is not production-grade:** SQLite WAL makes the state durable on a normal persistent disk, but a deployment using ephemeral storage can lose the local queue after a restart. The Render configuration should therefore be upgraded to a persistent disk or external PostgreSQL before treating this as production infrastructure.

- **Rate-limit conservatism reduces throughput:** the sender enforces 10 requests per rolling 60 seconds locally. This prevents deliberate 429s but means a burst of 500 comments can leave many items queued for several minutes. The design chooses correctness and provider compliance over pretending the mock API can accept 500 outbound sends immediately.

- **Keyword matching is substring matching by specification:** a rule `PRICE` matches `PRICE`, `price please`, and `surprise`. If product requirements later require token/word matching, the matching rule must change and be tested explicitly.

- **A deletion received after a DM has already been delivered cannot undo the DM:** `comment.deleted` cancels queued/accepted work that has not yet reached a terminal delivered/failed state. It cannot recall a message already confirmed delivered because the mock API exposes no delete-DM operation.
