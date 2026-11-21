# Proposal: HA core MCP OAuth interop — issues #183050 and #192871

**Status:** PROPOSAL ONLY — for Mark's review. **No upstream PRs, issues, or comments
have been opened on `home-assistant/core`.** Any upstream interaction (including posting
verification evidence as a PR comment) requires Mark's explicit go-ahead.

| | |
|---|---|
| Author | @devbot (soft-dev), 2026-11-21 |
| Issues | [home-assistant/core#183050](https://github.com/home-assistant/core/issues/183050), [home-assistant/core#192871](https://github.com/home-assistant/core/issues/192871) |
| Source basis | `home-assistant/core` `dev` @ `c4a2c2871701` (files fetched 2026-11-21), RFC 9728 / RFC 8414 text, MCP spec 2026-07-28, live GitHub PR/issue state |
| Verification status | All "current behavior" claims below are **code-derived with file:line citations** (not executed against a live HA instance — none in this workspace). Section 6 is the executable verification runbook (MCP Inspector + curl + native-client e2e). |

---

## 1. TL;DR

| | #183050 — path-suffixed protected-resource metadata | #192871 — AS metadata missing `issuer` / relative URLs |
|---|---|---|
| Root cause (verified) | `WellKnownProtectedResourceView` only serves the origin-level document; `resource` is always the origin, never the `/api/mcp` endpoint | `WellKnownOAuthInfoView` falls back to `url_prefix = ""` whenever `get_url(hass, require_current_request=True)` raises — producing a document with **no `issuer` and relative endpoints** |
| Spec delta | RFC 9728 §3 (**MUST** serve at path-inserted URL), §3.3 (**MUST NOT use** mismatched `resource`) | RFC 8414 §2 (`issuer` **REQUIRED**), §3.3 (issuer identity); MCP SDKs reject relative endpoints at schema validation |
| Upstream state | **A fix is already open: PR [#192728](https://github.com/home-assistant/core/pull/192728) by @allenporter (the codeowner)**, opened 2026-11-14, all CI green, quality-scale review ✅, zero reviews so far | **No PR exists** (searched: no PR references #192871; no open PR touches `WellKnownOAuthInfoView`) |
| Recommended action | **Do not compete.** Verify #192728 with the runbook in §6; optionally post interop evidence on the PR *after Mark approves* | Small, self-contained PR to `homeassistant/components/auth/login_flow.py` (patch sketch in §4.3), sequenced **after** #192728 merges (same file) |

---

## 2. What the specs actually require (citations)

### RFC 9728 (OAuth 2.0 Protected Resource Metadata)

- **§3 (line 361 of rfc9728.txt):** "Protected resources supporting metadata **MUST** make a
  JSON document … available at a URL formed by inserting a well-known URI string into the
  protected resource's resource identifier between the host component and the path …".
  For resource `https://ha.example.com/api/mcp` that is
  `https://ha.example.com/.well-known/oauth-protected-resource/api/mcp`.
- **§2:** `resource` — "REQUIRED. The protected resource's resource identifier".
- **§3.3:** "The `resource` value returned **MUST be identical** to the protected resource's
  resource identifier value into which the well-known URI path suffix was inserted to create
  the URL used to retrieve the metadata. If these values are not identical, the data
  contained in the response **MUST NOT be used**." Plus the second paragraph: if the document
  was retrieved from the `WWW-Authenticate` `resource_metadata` URL, `resource` **MUST** equal
  "the URL that the client used to make the request to the resource server" (i.e. the full
  `/api/mcp` endpoint for an MCP client).
- **§5:** `WWW-Authenticate: Bearer resource_metadata="<url>"` is how a resource points
  clients at that document.

### RFC 8414 (OAuth 2.0 Authorization Server Metadata)

- **§2:** `issuer` — "REQUIRED. The authorization server's issuer identifier, which is a URL
  that uses the 'https' scheme and has no query or fragment components." Used to prevent
  mix-up attacks.
- **§3.1:** metadata location = well-known suffix inserted into the issuer identifier
  (path insertion when issuer has a path).
- **§3.3:** "The `issuer` value returned **MUST be identical** to the authorization server's
  issuer identifier value into which the well-known URI string was inserted to create the URL
  used to retrieve the metadata. If these values are not identical, the data contained in the
  response **MUST NOT be used**."
- **Precision note (important for upstream credibility):** neither RFC contains the word
  "absolute" for endpoint fields. The hard normative failures in #192871 are (a) `issuer`
  absent → §2 REQUIRED violated, and (b) with no `issuer`, §3.3 cannot be satisfied at all.
  Relative `*_endpoint` values are *practically* fatal rather than literally RFC-forbidden:
  no RFC defines a resolution base for them, the field definitions say "URL of …", and every
  MCP-ecosystem client schema enforces absolute URLs — the MCP TypeScript SDK rejects the
  document at schema validation (`invalid_format, format: 'url'`, quoted in the issue).
  The issue's claim that "RFC 8414 §3.2 requires absolute endpoints" should be reworded if
  we comment upstream: §3.2 is the response-format section; lean on §2 + §3.3 + client
  schema enforcement instead.

### MCP specification (2026-07-28, Authorization)

- "MCP servers **MUST** implement OAuth 2.0 Protected Resource Metadata (RFC9728). MCP
  clients **MUST** use OAuth 2.0 Protected Resource Metadata for authorization server
  discovery."
- "MCP authorization servers **MUST** provide at least one of … RFC8414 … / OpenID Connect
  Discovery 1.0."
- DCR is optional/deprecated; Client ID Metadata Documents are the preferred registration
  path — HA advertises `client_id_metadata_document_supported: true` and deliberately has no
  `POST /register` (stated by @allenporter in #183050).

---

## 3. Issue #183050 — path-suffixed protected-resource metadata

### 3.1 Current behavior (code walk, dev @ c4a2c2871701)

1. `homeassistant/helpers/http.py:62-80` — every unauthenticated request to a
   `requires_auth` view raises `HTTPUnauthorized` with
   `WWW-Authenticate: Bearer resource_metadata="{url_prefix}/.well-known/oauth-protected-resource"`
   — **origin-level only, no request path**. If `get_url(...)` fails, the header is omitted
   entirely ("Omit header to avoid leaking configured URLs", line 71).
2. `homeassistant/components/auth/login_flow.py:163-187` —
   `WellKnownProtectedResourceView` is registered at exactly one URL
   (`/.well-known/oauth-protected-resource`, line 168). A request to
   `/.well-known/oauth-protected-resource/api/mcp` **404s** (no route).
3. The document it does serve returns `"resource": url_prefix` — the **origin**
   (`https://ha.example.com`), never the endpoint the client actually used.
4. Consumer side: `homeassistant/components/mcp/config_flow.py:574-595` tries, in order,
   the `WWW-Authenticate` URL, the path-inserted URL, then the origin-level URL — and
   `_resource_metadata_from_response` (line 544) requires
   `data.get("resource") == mcp_server_url` (exact match). HA's own client therefore
   rejects HA's own document for `/api/mcp`: this is the "Invalid OAuth resource metadata"
   in JHopmann's log (issue comment 2026-11-08) and the sibling issue **#192740**
   (native MCP client → native MCP server on the same instance).

Both failures are exactly RFC 9728 non-conformance: §3 path-insertion **MUST** (404) and
§3.3 identity (`resource` mismatch → "MUST NOT be used").

### 3.2 Upstream state — a fix is already open (do not compete)

| PR | State | Meaning |
|---|---|---|
| [#192728](https://github.com/home-assistant/core/pull/192728) "Serve path-aware OAuth protected resource metadata per RFC 9728" | **OPEN**, author **@allenporter** (codeowner of `mcp`/`mcp_server`), opened 2026-11-14, "fixes #183050", all checks green (tests, mypy, pylint, hassfest, codecov/patch ✅), quality-scale review ✅ ("No issues found"), **0 reviews / 0 review requests** | The canonical fix. Opened by the owner, awaiting review. |
| [#188949](https://github.com/home-assistant/core/pull/188949) | CLOSED unmerged (author @cpruijsen: "The 401 header already points clients to the root metadata, so this doesn't fix the connector failure") | Earlier narrower attempt; superseded. |
| [#184691](https://github.com/home-assistant/core/pull/184691) | MERGED 2026-11-16 | HA's MCP *client* now prefers the `WWW-Authenticate` URL. |
| [#152385](https://github.com/home-assistant/core/pull/152385) | MERGED 2025-10-14 | Added the (conditional) `issuer` to AS metadata — the partial fix #192871 complains about. |

**#192728's shape** (6 files):

- `login_flow.py`: `WellKnownProtectedResourceView` gains
  `extra_urls = ["/.well-known/oauth-protected-resource/{resource_path:.+}"]`; serves
  `"resource": f"{url_prefix}{raw_suffix}"`; returns **404** when the suffix does not
  resolve to a registered `requires_auth` route (so public/unknown paths can't be
  advertised, and encoding tricks — `..`, `%2F`, double slashes — are rejected).
- `components/http/server.py`: tracks the `AbstractResource`s of auth-requiring views at
  registration time; new `async_path_requires_auth(request, raw_path)` resolves a cloned
  probe request against them.
- `helpers/http.py`: the 401 `WWW-Authenticate` now appends the request path
  (`resource_metadata="{url_prefix}/.well-known/oauth-protected-resource{resource_path}"`);
  `HomeAssistantView.register()` now returns its routes (additive API change).
- Tests: path-suffixed 200 for GET/POST/dynamic/query-ignored routes; 404 matrix for
  unregistered/public/encoded paths; CORS on the path form; WWW-Authenticate path params;
  `mcp_server` 401 advertises RFC 9728 metadata.

**Assessment: correct and minimal.** Checks made against the diff:

- `normalize_url()` (`homeassistant/util/network.py:104-112`) strips trailing slashes and
  default ports, so `f"{url_prefix}{raw_suffix}"` cannot produce `//` — no double-slash bug.
- `raw_path` excludes the query string — matches §3 (query is not part of the insertion).
- 404-for-non-protected-paths is the right call: §3.3 would reject a generic document for
  those paths anyway, and it avoids advertising metadata for routes that don't exist.
- When `mcp_server` is disabled, `/api/mcp` metadata 404s — correct (resource absent).
- RFC 9728 §3.3 paragraph 2 is satisfied only because the header now points at the
  path-suffixed URL with `resource` = full endpoint — the two changes are coupled; good.

Residual notes (candidate review comments — **only if Mark approves posting them**):

1. It does not touch AS metadata — #192871 remains (§4).
2. `async_path_requires_auth()` iterates all auth-requiring resources per metadata GET —
   fine (metadata fetches are rare), worth no change.
3. The Claude.ai connector failure in #183050 may have a second cause: some connectors
   expect DCR (`POST /register`); HA intentionally has none (CIDMD instead, per MCP spec).
   This PR fixes discovery, not DCR — set expectations accordingly.

### 3.3 Blast radius (of #192728 as written)

- `helpers/http.py` 401 header: **every** unauthenticated view (not just MCP) now advertises
  a path-suffixed `resource_metadata` URL. RFC 9728 §5-correct; HA's own client prefers it
  (merged #184691) and falls back to origin-level (its fallback list predates this). Risk:
  low, but it is the one line with fleet-wide reach.
- `components/http/server.py`: internal registration bookkeeping + `register()` return type
  — additive; affects all view registrations (CI green across the suite).
- No config-flow, storage, or API changes; `mcp_server` quality scale untouched (bot
  confirmed: only test additions in that domain).

### 3.4 Test approach for #183050

- **Already in #192728** (see above) — a competing PR would duplicate these.
- **Still missing / worth adding upstream later:** an end-to-end config-flow test of
  #192740 (HA MCP *client* → same-instance HA MCP *server* completing OAuth discovery).
  Existing tests cover each side in isolation; the reported failure is in the pair.
- **Manual/interop:** runbook §6 (MCP Inspector `--oauth-debug`, curl probes, native-client
  e2e). Evidence from that runbook is the useful thing to post on #192728 — with Mark's OK.

---

## 4. Issue #192871 — AS metadata omits `issuer` / relative URLs

### 4.1 Current behavior (code walk)

`homeassistant/components/auth/login_flow.py:118-160`, `WellKnownOAuthInfoView.get`:

```python
# Some applications require absolute urls, so we prefer using the
# current requests url if possible, with fallback to a relative url.
try:
    url_prefix = get_url(hass, require_current_request=True)
except NoURLAvailableError:
    url_prefix = ""
...
# Add issuer only when we have a valid base URL (RFC 8414 compliance)
if url_prefix:
    metadata["issuer"] = url_prefix
```

When `get_url(..., require_current_request=True)` raises, the endpoint serves relative
`/auth/authorize`-style values and **no `issuer`** — the exact document quoted in #192871.

**Why `get_url` raises even on a "correctly configured" instance** (this is the crux, and
the issue reporter can't see it from the outside):

- `get_url` (`homeassistant/helpers/network.py:113-219`) with `require_current_request=True`
  requires the configured internal/external URL to match the *request's* host **and port**
  (`_match_request_host_port`, lines 260-267).
- The request port is derived as: Host header port if present, else
  `443 if request.url.scheme == "https" else 80` (lines 253-255).
- aiohttp's `request.scheme` is `https` only when the socket itself is TLS **or** the
  forwarded middleware overrode it (aiohttp `web_request.py:390-402`).
- The override happens only if `X-Forwarded-For` is present **and** `http: use_x_forwarded_for`
  is enabled **and** the peer is a trusted proxy (`homeassistant/components/http/forwarded.py:84-115`;
  note line 84: **absent `X-Forwarded-For` skips `X-Forwarded-Proto` processing entirely**).
  Middleware order is correct (forwarded appended before request-context,
  `components/http/server.py:363-365`), so when it runs, the scheme survives.

**Failure modes that all produce the reporter's three symptoms at once** (relative AS
metadata + `/.well-known/oauth-protected-resource` 404 + 401 without `WWW-Authenticate` —
all three code paths share the same `NoURLAvailableError`):

1. TLS-terminating proxy whose forwarded headers are not processed (most common: proxy
   sends no `X-Forwarded-For`, or `use_x_forwarded_for`/`trusted_proxies` not configured).
   Connection to HA is plain HTTP → request resolves to port 80 → external
   `https://host` (443) never matches → raise. *This is the code-verified mechanism; the
   reporter states external URL is correct, which is consistent with this being the trigger,
   though their proxy config was not provided — label as inference, not fact.*
2. No configured URL at all (fresh install reached by LAN IP: the loopback fallback in
   lines 168-216 only accepts `localhost`/loopback/Supervisor hostnames).
3. Request host genuinely differs from both configured URLs.

The existing unit test **enshrines** the broken output: `tests/components/auth/test_login_flow.py:663-671`
case `no_match` expects `expected_url_prefix == ""` and no `issuer`.

HA's own MCP client tolerates this (it absolutizes relative endpoints at
`mcp/config_flow.py:105-108` and never reads `issuer`) — which is why HA-to-HA worked for
some and not others, while third-party MCP clients (TS SDK: Claude connectors, Cursor,
VS Code, MCP Inspector) reject the document at schema validation, before any authorization
request — the exact error quoted in #192871.

### 4.2 Spec delta

| Requirement | Today (fallback path) | Verdict |
|---|---|---|
| RFC 8414 §2 `issuer` REQUIRED | absent | violation |
| RFC 8414 §3.3 issuer identity | unsatisfiable (no issuer) | violation |
| Endpoint fields consumable as URLs (MCP SDK schema `format: 'url'`) | relative | rejected by clients |
| RFC 8414 §2 https scheme for issuer | n/a when no URL; request-derived fallback may be `http://` on plain-HTTP instances | known, accepted deviation for LAN-only instances (documented in patch) |

### 4.3 Minimal patch shape

**One file + tests:** `homeassistant/components/auth/login_flow.py` (`WellKnownOAuthInfoView`,
and the same helper in `WellKnownProtectedResourceView` so the proxy-scheme failure class is
fixed for both documents), plus `tests/components/auth/test_login_flow.py`.

```python
def _async_url_prefix(hass: HomeAssistant, request: web.Request) -> str:
    """Return the absolute base URL for OAuth metadata documents.

    RFC 8414 Section 2 requires an issuer; relative endpoint values have no
    defined resolution base and are rejected by MCP client schemas.
    """
    try:
        # Matches the request origin, so the issuer satisfies RFC 8414 §3.3.
        return get_url(hass, require_current_request=True)
    except NoURLAvailableError:
        pass
    try:
        # Request origin unresolved (typically a TLS-terminating proxy whose
        # forwarded headers are not processed): advertise the configured URL.
        # External first: it is the identity MCP clients reach us by.
        return get_url(hass, prefer_external=True)
    except NoURLAvailableError:
        pass
    # Nothing configured: derive a self-consistent origin from the request.
    return str(request.url.origin())
```

Then in `WellKnownOAuthInfoView.get`: `url_prefix = _async_url_prefix(hass, request)`,
**drop the `if url_prefix:` conditional — `issuer` is always emitted**, endpoints stay
`f"{url_prefix}/auth/..."` (now always absolute). In `WellKnownProtectedResourceView.get`:
replace the `except NoURLAvailableError: return 404` with the helper (document becomes
self-consistent instead of 404) — **this class's edit must be rebased on #192728**, which
rewrites the same method.

Fallback-rationalé (each step only runs when the previous one failed):

1. Request-matched URL — zero behavior change vs today whenever matching works (the
   majority of direct and properly-proxied setups), and `issuer` equals the retrieval origin
   by construction (§3.3 ✓).
2. Configured URL, external preferred — this is the **reported bug's fix**: host matches the
   request but scheme/port resolution behind the proxy fails; external URL is exactly the
   issuer the client's retrieval URL implies. (`prefer_external=True` matters: the default
   order would return the internal/LAN URL when both are set, which §3.3 would reject.)
3. Request origin — fresh installs with no configured URL get a self-consistent document
   instead of a relative one; may be `http://` on LAN-only instances (RFC 8414 prefers
   https; clients accept it; nothing better exists without a configured URL).

**Deliberately not in this patch:**

- `helpers/http.py` 401 header fallback (same `NoURLAvailableError` → header omitted).
  Not required for discovery: RFC 9728 clients construct the path-suffixed URL from the
  resource URL themselves, and origin-level works too. Also **hotspot**: #192728 rewrites
  those exact lines — sequence as a follow-up after it merges.
- `components/http/forwarded.py` (honor `X-Forwarded-Proto` even without
  `X-Forwarded-For`) — the true root cause of mode 1, but it changes scheme semantics for
  *every* request (`is_internal_request`, redirects, cookie flags). Separate PR, separate
  risk discussion; this patch makes the document correct regardless.
- Returning 404 when no URL is known (the alternative "fail loudly" design): rejected —
  HA's own MCP client falls back to guessed default paths `/authorize`, `/token` on 404
  (`mcp/config_flow.py:93-100`), which are wrong for HA; the relative document at least
  lets it proceed as today.

### 4.4 Blast radius

| Change | Reach | Risk |
|---|---|---|
| `WellKnownOAuthInfoView` fallback + always-on `issuer` | The `/.well-known/oauth-authorization-server` document — consumed by external OAuth/MCP clients (and any HA app doing OIDC-style discovery against HA) | **Zero change** when request-matching succeeds (first try wins). On the previously-broken path, output goes from schema-invalid to valid — strictly an improvement. HA's own `config_entry_oauth2_flow` does not read this document (application credentials are configured directly). |
| `WellKnownProtectedResourceView` fallback (was: 404) | `/.well-known/oauth-protected-resource` on no-URL/mismatched requests | Low; same argument. Rebase on #192728 required (hotspot: `login_flow.py`). |
| Tests | `tests/components/auth/` only | The `no_match` case expectation changes (see §4.5) — a deliberate assertion update, called out in the PR description. |

Codeowner routing note: `homeassistant/components/auth/` and `components/http/` are owned by
**@home-assistant/core** (CODEOWNERS lines 205, 866), not @allenporter — he is the
`mcp`/`mcp_server` owner (lines 1189-1192) and the de-facto driver of both issues, but review
will route to the core team.

### 4.5 Test approach for #192871

Unit tests in `tests/components/auth/test_login_flow.py` (patterns: existing
`test_well_known_auth_info` + `current_request_with_host` fixture; the fixture's mocked
request is built with an SSL context → scheme https, host `example.com` —
`packages/pytest-homeassistant/pytest_homeassistant/plugins.py:1023-1044`):

1. **Existing cases (external-match, internal-match):** unchanged expectations — proves the
   zero-regression claim for working setups.
2. **`no_match` case (line 663-671):** expectation changes from `""`/no-issuer to the
   external URL (`https://again.com`) + `issuer` present — this is the assertion update that
   encodes the fix.
3. **NEW — the reported scenario (scheme mismatch):** patch `homeassistant.helpers.http.current_request`
   with `make_mocked_request("GET", "/some/request", headers={"Host": "example.com"})`
   (**no** `sslcontext` → scheme http → port 80), configure `external_url=https://example.com`
   → `get_url(require_current_request=True)` fails (80 ≠ 443), fallback 2 must return
   `https://example.com`. This is a deterministic repro of the #192871 failure class and the
   regression test that keeps it fixed.
4. **NEW — no URL configured:** expect `issuer` and all three endpoints derived from the
   real test request origin (`http://{client.host}:{client.port}` — same technique as
   #192728's tests).
5. **Invariant across every parametrization:** `issuer` present; `yarl.URL(v).is_absolute()`
   for `authorization_endpoint`/`token_endpoint`/`revocation_endpoint`.
6. `WellKnownProtectedResourceView`: the existing `no_url` 404 test (line 766) flips to 200
   with the request-derived `resource`.

**MCP Inspector verification** — §6, expected trace in §6.2. **Native-client e2e** — §6.3.

---

## 5. Sequencing, hotspots, and what not to do

1. **No upstream writes of any kind** until Mark approves (card rule).
2. **#183050:** do not open a competing PR — #192728 exists, is codeowner-authored, and is
   green. The useful contribution is verification evidence, posted only with approval.
3. **#192871 PR** touches `login_flow.py` in the same class #192728 rewrites →
   **open it after #192728 merges** (or rebase onto it). The `helpers/http.py` header
   fallback, if ever wanted, is a third PR — same hotspot, same sequencing.
4. **hotspot: `homeassistant/components/auth/login_flow.py`** — #192728 (open) and this
   proposal both edit adjacent methods of the two well-known views; `helpers/http.py:62-80`
   is touched by #192728 and would be touched by any header fallback follow-up.
5. Quality bar: `mcp_server`/`mcp` are silver-scale with `test-coverage` as a checked rule;
   `auth`/`http` are core-team-owned with full-suite CI. Both patches are test-first and
   small; 36 PRs with "mcp" in the title have merged since 2026-06-01 (gh search,
   verified 2026-11-21 — matches the card's claim; 25 carry `integration: mcp_server`,
   24 `integration: mcp`), so a tight follow-up from outside is plausible — but for #192871
   the patch touches `auth`, which routes to the core team rather than @allenporter.

---

## 6. Verification runbook (MCP Inspector + curl + native e2e)

> Not executed in this workspace (no HA instance available here). This is the concrete
> procedure to run against a dev/prod HA with the MCP server enabled, before/after the
> patches. Inspector v2 is current (`@modelcontextprotocol/inspector`, Node ≥ 22.23.4).

### 6.1 Static probes (curl)

```bash
HA=https://ha.example.com   # or your instance

# (a) 401 challenge — expect WWW-Authenticate with path-suffixed resource_metadata
#     (post-#192728); pre-fix it is origin-level or absent
curl -si -X POST "$HA/api/mcp" \
  -H 'content-type: application/json' \
  -H 'accept: application/json, text/event-stream' \
  -H 'mcp-protocol-version: 2025-06-18' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"probe","version":"0"}}}' \
  | grep -i '^www-authenticate'

# (b) RFC 9728 §3 path-inserted document — pre-fix: 404; post-#192728: 200 with
#     resource == "$HA/api/mcp"
curl -s "$HA/.well-known/oauth-protected-resource/api/mcp" | python3 -m json.tool

# (c) RFC 8414 document — pre-fix: no issuer, relative endpoints; post-#192871: PASS
curl -s "$HA/.well-known/oauth-authorization-server" | python3 -c '
import json, sys, urllib.parse
d = json.load(sys.stdin)
assert d.get("issuer"), "missing issuer"
for k in ("authorization_endpoint", "token_endpoint", "revocation_endpoint"):
    u = urllib.parse.urlparse(d[k])
    assert u.scheme in ("http", "https") and u.netloc, f"{k} not absolute: {d[k]}"
print("PASS issuer =", d["issuer"])'
```

### 6.2 MCP Inspector (OAuth discovery trace)

```bash
npx --yes @modelcontextprotocol/inspector@2.5.0 --cli \
  --transport http --server-url "$HA/api/mcp" \
  --oauth-debug --relogin --method initialize
```

`--oauth-debug` prints one line per OAuth request/response (tokens redacted) — this is the
evidence artifact.

**Expected PRE-fix (dev @ `c4a2c2871701`) — shape of the trace** (exact ordering varies
by SDK: header URL vs. constructed path-inserted URL vs. origin fallback):

```text
[oauth] protected-resource metadata: GET https://ha.example.com/.well-known/oauth-protected-resource/api/mcp
[oauth]   -> 404 Not Found                      # §3 MUST violated (#183050)
# …and/or, via the origin-level URL from WWW-Authenticate:
[oauth]   -> 200 OK {"resource":"https://ha.example.com", …}   # ≠ request URL → §3.3 "MUST NOT be used"
[oauth] authorization-server metadata: GET https://ha.example.com/.well-known/oauth-authorization-server
[oauth]   -> 200 OK {"authorization_endpoint":"/auth/authorize", …}   # no issuer (#192871)
… SDK schema validation error: issuer expected string, received undefined …
```

**Expected POST-fix:**

```text
[oauth] protected-resource metadata: GET https://ha.example.com/.well-known/oauth-protected-resource/api/mcp
[oauth]   -> 200 OK {"resource":"https://ha.example.com/api/mcp","authorization_servers":["https://ha.example.com"]}
[oauth] authorization-server metadata: GET https://ha.example.com/.well-known/oauth-authorization-server
[oauth]   -> 200 OK {"issuer":"https://ha.example.com","authorization_endpoint":"https://ha.example.com/auth/authorize", …}
[oauth] client registration: POST https://ha.example.com/register
[oauth]   -> 404 Not Found        # EXPECTED: HA has no DCR by design; client must fall back
                                  # to Client ID Metadata Documents (HA: client_id_metadata_document_supported)
[oauth] authorization: open https://ha.example.com/auth/authorize?…&client_id=…
[oauth] token request: POST https://ha.example.com/token … -> 200 OK
```

If a client hard-fails on the 404 at `/register`, that is a **client-side** spec-compliance
bug (MCP spec: DCR optional/deprecated, CIDMD preferred) — record it, don't work around it
server-side.

Interactive equivalent: `npx @modelcontextprotocol/inspector` → Transport *Streamable HTTP*
→ server URL `$HA/api/mcp` → Connect → the OAuth view shows the same trace; complete the
PKCE round-trip in the browser; `tools/list` must return the HA tools.

### 6.3 Native HA e2e (repro of #192740 / JHopmann's log)

Settings → Devices & services → Add integration **Model Context Protocol** →
URL `$HA/api/mcp` → expect:401 → path-suffixed PRM 200 → AS metadata with `issuer` →
browser authorization → config entry created and coordinator connected. Pre-fix this fails
at "Invalid OAuth resource metadata" / "Authentication failed!".

---

## 7. Open questions for Mark

1. **#183050:** OK to post the §6.2 Inspector trace as a comment on PR #192728 (the only
   useful upstream action available there — the fix itself is already the codeowner's)?
   Otherwise we just record the runbook for later.
2. **#192871:** proceed to draft the PR against `login_flow.py` now (rebase pending
   #192728), or wait until #192728 merges to avoid double-reviewing the same file?
3. Fallback order preference: `prefer_external=True` in step 2 (recommended — matches the
   reported scenario) vs. plain `get_url(hass)` (internal first)? Reviewer may have an
   opinion; worth deciding before drafting.
4. Include the `WellKnownProtectedResourceView` fallback (same PR, rebase-dependent) or
   keep the PR to the AS-metadata view only (strictly the issue's title scope)?

---

## 8. Evidence index

**Code (dev @ `c4a2c2871701`, fetched 2026-11-21):**
`homeassistant/components/auth/login_flow.py:118-187` (both well-known views, conditional
issuer L156-158, 404 L174-177) · `homeassistant/helpers/network.py:113-219, 229-267`
(`get_url`, request port/scheme resolution) · `homeassistant/helpers/http.py:62-80`
(401 header) · `homeassistant/components/http/forwarded.py:84-115, 146-191` (XFF gate, XFP
override) · `homeassistant/components/http/server.py:363-365` (middleware order) ·
`homeassistant/components/http/request_context.py:18-25` (contextvar) ·
`homeassistant/components/mcp/config_flow.py:80-118, 532-595` (client discovery + strict
`resource` match) · `homeassistant/util/network.py:104-112` (`normalize_url`) ·
aiohttp `web_request.py:390-402, 455-460` (scheme/URL derivation) ·
`tests/components/auth/test_login_flow.py:641-770` (current expectations, incl. `no_match`).

**Specs:** RFC 9728 §§2, 3, 3.1-3.3, 5 · RFC 8414 §§2, 3, 3.1-3.3 · MCP spec 2026-07-28
Authorization (MUST RFC 9728 server-side, MUST RFC 8414/OIDC AS discovery, DCR optional).

**GitHub state (queried 2026-11-21):** issues #183050 (open,
`needs-more-information`, label `integration: mcp_server`), #192871 (open),
#192740 (open, sibling), #181505/#147059 (closed); PRs #192728 (open, allenporter, CI
green, 0 reviews), #188949 (closed unmerged), #184691 (merged 2026-11-16), #152385
(merged 2025-10-14); CODEOWNERS: `auth`/`http` → @home-assistant/core, `mcp`/`mcp_server`
→ @allenporter; merged-PR counts via `gh api search/issues` (36/25/24 since 2026-06-01).
