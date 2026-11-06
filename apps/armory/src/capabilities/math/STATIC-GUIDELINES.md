# Mathematics storage

This capability has no static reference data, persistent calculation history,
result cache, credentials, or capability-owned configuration. Requests and results
live in memory and anonymous subprocess pipes. Symbolic calculation caches are
cleared after each call; initialized engine code remains warm. No history is
intentionally retained and no capability-owned runtime directories are created.

At most two workers execute concurrently per server event loop. Workers are
recycled after eight calls or 30 idle seconds, and reaped on timeout, cancellation,
failure, and application lifespan shutdown. Benchmark output is printed to stdout;
it does not create persistent capability data.

The unit catalogue is Python code in `utils/units.py`, not external mutable data.
Case partitions and root certificates are generated in worker memory. Batch rows
remain in bounded application memory until returned; no record history is stored.
Progress uses one bounded in-memory queue per batch; delivery is ephemeral.
Table workflow reads existing caller-owned table registry pages without copying
the whole attachment or persisting results. Continuation receives prior result
explicitly from caller; no server-side result store exists. Metrics retain only
aggregate counters and the last 256 queue/total durations per event loop.
Native memory/CPU controls live in disposable workers, never in the server.

Worker utilities are retained across capability reloads so admission limits remain
shared with active calls. Raw JSON transport avoids retaining old wrapper result
classes. Restart Armory after changing `contract.py` or files under `utils/`:
existing workers keep their initialized solver and model definitions.
