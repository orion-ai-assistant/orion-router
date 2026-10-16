# Native PostgreSQL Unicode paths

16 October 2026. New Windows installations support Turkish and other Unicode
code/data paths on Windows 10 1903 or newer. No system locale change, short-path
alias, drive mapping or junction is required.

`core/windows_postgres.py` is vendored from the Hub canonical shared engine.
The Hub `scripts/lifecycle/sync_router_engine.py` checks/synchronizes it and
`core/native_postgres.py`. New installations use the pinned EDB PostgreSQL
16.15-1 archive (SHA256
`25e6fcdfb8caec38691bf461125e7564508760666f7b8e5dc6a5f0818f58f81e`).
Preparation augments the existing PostgreSQL application manifests with
process-local UTF-8 in an unpublished staging directory. Vendor/derived EXE
hashes are recorded separately in `.orion-postgres-runtime.json`. Signed EXEs
are rejected by transformation; the separate signed StackBuilder installer is
excluded from the server runtime. Vendor binaries in existing installations
are never patched in place. A runtime without its ready marker is preserved
for explicit repair. Failed initdb no longer deletes/rebuilds an existing
runtime automatically.

The Unicode adapter verifies preparation evidence and critical executable
hashes. SQL input/output uses explicit UTF-8. Existing ASCII installations are
not automatically upgraded. Existing legacy Unicode runtime conversion and
full DB/runtime relocation remain separate, unimplemented lifecycle work.

This pinned HTTPS archive hash is not a verified vendor release signature.
The later signed package pipeline must sign final derived files after manifest
preparation. The local receipt does not replace signed release metadata.

Real acceptance passed in the Hub runner fixture
`.tmp/lifecycle/product-lcskvj_g`: `Türkçe İıŞşĞğ 中文/Router` executable/data root,
initial cluster creation, UTF-8 SQL roundtrip, native `pg_trgm` extension,
three concurrent starts, repeat start, owned process/TLS/UUID/API/application
schema verification, restart and controlled shutdown. The final audit found
no remaining fixture processes. Router isolated baseline: **9 passed**,
`baseline-y6xdc3eo-router`, unexpected DB/pool attempts **0/0**.

References: [Windows UTF-8 manifests](https://learn.microsoft.com/en-us/windows/apps/design/globalizing/use-utf8-code-page),
[PostgreSQL path bug](https://www.postgresql.org/message-id/16926-e4ef345545d185ab@postgresql.org).

Local commit note: the configured GPG signing process stalled and was cancelled.
This follow-up commit is unsigned; repository signing preferences were not
changed. No push was performed.
