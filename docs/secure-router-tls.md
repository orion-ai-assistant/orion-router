# Router TLS

Router serves its secure API and dashboard on a primary HTTPS listener
on `ORION_ROUTER_TLS_HOST` (default `0.0.0.0`) and `ORION_ROUTER_TLS_PORT`
(default `9443`). All API, streaming, audio and file routes share application
state. The HTTPS server disables forwarded headers. A separate local browser
listener binds **127.0.0.1:20128** (configurable `ORION_ROUTER_LOCAL_HTTP_PORT`).
Open `http://localhost:20128/dashboard` on the Router computer. It accepts only
actual loopback peers and localhost/loopback Host authorities for its real bound
port; foreign Origin headers and DNS rebinding Hosts are rejected. Its API
keeps the existing authentication. It is never exposed/advertised to the LAN,
and Compose publishes only 9443. Hub and network clients always use pinned TLS.
The console and Settings identity card label complete, copyable addresses as
"This PC (HTTP)" and "Other devices (HTTPS)". Use the displayed HTTPS LAN URL
on another device; replacing localhost in the HTTP URL does not make it a LAN
address. Settings shows eligible LAN interfaces, not container bridge addresses.
A plain ASGI launch cannot restore public HTTP: the application rejects requests
without a TLS marker or the guarded local-listener
marker. Run `python main.py`, `cli.py prod`, or `cli.py dev`; plain
`uvicorn main:app` is unsupported and fails closed.

`persistent/tls/private-key.pem` is a persistent ECDSA P-256 private key;
`certificate.pem` is a self-signed certificate valid for approximately 50 years.
Expired certificates or certificates missing browser SAN names renew with the
same key. SAN includes localhost, 127.0.0.1, ::1, hostname and LAN addresses.
Broken keys, broken certificates,
key/certificate mismatch, or a missing key beside an existing certificate stop
startup. They are never silently replaced. Back up the persistent volume and
restrict its access to the service account; POSIX files are written with 0600.
On Windows, protect this directory with the service account's filesystem ACL.

The existing `persistent/mdns-id` UUID remains the installation identity.
The pin is lowercase hex **SHA-256 of DER SubjectPublicKeyInfo**, never the
certificate fingerprint. Certificate renewal preserves the pin.

`GET /api/v1/tls/identity` is HTTPS-only and returns
`{v:1,id,name,fp}`. `GET /dashboard/api/tls/identity` requires the existing
administrator key and returns those fields plus `port`. The local authenticated
dashboard Settings page displays the full pin for deliberate comparison in Hub.
The startup banner also prints the identity/pin. Obtain the initial pin from a
trusted local screen; discovery and remote identity responses are address hints,
not a trusted source of a replacement pin.

The TLS discovery record is `_orion-router-tls._tcp.local.` with actual bound
TLS port and TXT `id`, `name`, `v=1`, `scheme=https`, `path=/v1`, `version`.
It uses eligible LAN interfaces and reconnect/goodbye management. The legacy
`_orionrouter._tcp.local.` HTTP service is no longer published. Container discovery remains off
unless explicitly using supported host networking; Compose exposes the TLS
port and persists the identity using the existing volume.

Hub must pin the SPKI of the actual TLS connection before sending its Router
key, credentials or body. Every Router call (including health, catalogs,
worker calls, audio, file and streaming requests) uses that policy. Changes
to IP/port discovered for the same UUID never replace the pin. Key replacement
requires deliberate re-pairing; no automatic HTTP fallback is allowed.

The browser/OS may require deliberate manual trust of this local self-signed
certificate before opening `https://localhost:9443/dashboard`; Router does not
import trust automatically or disable certificate validation. Trust this
installation's certificate after local verification. Hub uses SPKI pinning and
does not depend on browser trust.
The local `http://localhost:20128/dashboard` browser entry avoids certificate
installation for PC-local administration. Do not send Hub/network traffic there.

Development uses Router TLS port 9444 (`ORION_ROUTER_TLS_DEV_PORT`) and a TLS
Next.js server on the configured UI port. Next receives the persistent key/cert
via `--experimental-https-key`/`--experimental-https-cert`; its backend proxy
starts with `NODE_EXTRA_CA_CERTS` pointing at that certificate. Local health
probes also explicitly trust only that persisted certificate. No verify=false
or accept-all callback is used. Downstream local model providers have separate
transport settings and are outside this Router listener migration.

## Same-PC installer provenance

Native installers register a local public identity locator after Python
dependencies are installed, before starting services. Windows uses
`%LOCALAPPDATA%/Orion/router-installation.json`; Linux/macOS use
`${XDG_CONFIG_HOME:-~/.config}/orion/router-installation.json`.
The file is atomically replaced (0600 on POSIX) with this schema:

```json
{"v":1,"kind":"orion-router-local-installation","root":"<absolute installation root>","certificate_path":"<root>/persistent/tls/certificate.pem","identity_path":"<root>/persistent/mdns-id","tls_port":9443}
```

It contains only public identity locations and the configured TLS port, never
private key paths or remote observations. Default native roots are
`%LOCALAPPDATA%/OrionRouter` and `~/.orion-router`; the Unix installer also
supports an explicit `ORION_INSTALL_DIR`. Registration prepares/reuses the
existing TLS identity and UUID; startup refreshes paths/port only for this
registered root or a pre-existing default native installation. Arbitrary
development checkouts never replace another installation's registration.
Docker instances do not claim native provenance. Identity paths outside the
managed root require manual Hub trust instead of automatic bootstrap.

Hub can establish first trust from installer-owned, locally owned public
certificate/UUID files, then verify the live HTTPS identity using the derived
SPKI pin. It must not accept mDNS/remote fingerprints as automatic initial
trust, replace an existing pin after a key change, or resurrect revoked trust.
Router-first and Hub-first installation order can both work because the
registration persists and startup refreshes it; Hub consumes the locator when
the Router becomes available. This does not import any OS certificate roots.

## Login Router selection

The first login dialog places a compact Router selector under the login form:
one label, a refresh icon and device short names. It refreshes on entry and every
ten seconds; the refresh icon spins for at least one second. A sole available
Router is selected on first use. Explicit selection stores only its UUID;
later refreshes preserve it. If it is missing or ambiguous, login remains
disabled until the user selects an available Router. No alternative is chosen
automatically. The selector disappears after login.
Settings retains the current Router's TLS identity card. Discovery is available
without an administrator key through `GET /dashboard/api/routers/browse`, only
over guarded local HTTP or actual HTTPS from a LAN/loopback peer. One two-second
scan is shared per process with a ten-second cache, including failed scans.
Results are unverified navigation hints, never a trust enrollment or pin update.

Panel links accept only LAN HTTPS targets or exact local HTTP port 20128;
credentials, query strings, fragments and foreign paths are rejected. UUID
conflicts block links. Opening another panel transfers no password/key/cookie.
Optional browser storage remembers only the selected UUID. It never
automatically redirects to another Router; changing the selector explicitly
opens that Router's own secure dashboard before authentication.


Windows local installation prepares only the persistent HTTPS identity with
`python -m core.tls_local`. Installation and normal startup never add certificates
to Windows trust stores or open certificate-import prompts. Native SPKI trust
remains enforced. Browser dashboards may show a self-signed certificate warning;
ignoring a warning does not authenticate the server. HTTP is not restored.

The shared DNS-SD service name remains `_orion-router-tls._tcp.local.`.
Registration uses strict=False for its length, with a real Zeroconf regression
test and live LAN UUID/HTTPS-port resolution verified.
