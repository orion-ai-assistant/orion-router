# Stage 05 standalone Router package

`package.json` is the signed package identity/compatibility input: version 0.1.3,
API generation 2, Windows 10 1903+ x64 CPU host runtime. Generation 2 includes
`GET /api/v1/hubs/accounts` and `GET /api/v1/hubs/account-status`. Router has no
Hub or Flutter installation dependency.

Build tooling and hashed wheel/input locks are in the sibling Hub repository's
`scripts/release/`. `windows-packages.yml` takes an exact Router commit, builds
the static dashboard, bundles Python/PostgreSQL/FFmpeg and creates an immutable
candidate ZIP. No Node, Python SDK or Git is needed on the installed machine.
The PostgreSQL UTF-8 transform happens before final archive hashing/signing.
Supplier license documents ship with the corresponding runtime.

An out-of-band trusted bootstrap verifies TUF signatures/hashes, installs a fresh
release and records it in the existing schema-1 installation registry. Its public
package receipt pins a file inventory kept under state; this local inventory is
not itself a signature. The standalone command is `Run-Router.ps1 -Registry
<absolute-install.json>` (`-Stop` for controlled shutdown). It refuses unowned
management or a changed/unregistered package.

Code stays under `Router/releases/<package-id>`. `.pgdata-prod`, `.env`, encryption
key and TLS/UUID remain under `Router/data`; process records/Job cancellation stay
under `Router/state`. Source installations retain their old layout. Packaged
dashboard rebuild and the legacy Git/pip updater are disabled. No conversion,
automatic update or Windows Startup change is performed.

17 October 2026 source regression: 9 tests passed with DB/pool attempts 0/0.
Actual package/DB results and final artifact hashes are recorded in the sibling
Hub document `docs/orion-lifecycle-plan/05-packaging-and-release-metadata.md`.
The CI definitions have not been executed on GitHub in this local task. Production
root provisioning, clean Windows VM and rollout acceptance remain open. Stage
01/03/04 acceptance debt is unchanged; Stage 06–08 is not authorized by this work.
