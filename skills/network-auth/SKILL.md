---
name: network-auth
description: Design or change home-server Services, Gateway routes, DNS, NetworkPolicies, access proxies, Authentik OIDC, or forward-auth. Use when exposure, login, callbacks, claims, or network trust changes.
---

# Change network exposure and authentication

Treat route, DNS, authentication, Service, access proxy, and NetworkPolicy as one
security boundary. A route that works is not sufficient evidence that exposure
is correct.

## Required reading

Read:

- docs/architecture.md, especially traffic flow and application boundaries;
- docs/service-operations.md sections on exposure, NetworkPolicy, route, and DNS;
- docs/service-catalog.md sections on exposure, OIDC, and forward-auth;
- docs/runbook.md ingress/TLS and the service-specific section;
- the active route, Service, middleware, proxy, policy, workload, descriptor,
  and SOPS references for the service.

Check current upstream authentication documentation when adding or revisiting an
integration. Do not assume an old native-auth exception remains necessary.

## Choose exposure first

- No route: use for internal Services and background workers.
- Private/admin: require the named LAN/WireGuard allow-list middleware and, for
  the normal pattern, a colocated access proxy. Point the Service at the proxy.
- Public: no IP allow-list; explicitly review initialization and authentication.
- Host-network UI: use only a documented protocol-specific pattern, such as
  Syncthing's loopback plus backend mTLS. Do not add a convenient route to Blocky
  or Kea management listeners.

Declare hostname, visibility, both DNS decisions, authentication, and exact
private middleware in the colocated catalog descriptor. Run the catalog render.
Do not hand-edit Homepage, Cloudflare DDNS, Blocky, or aggregate Authentik output.

Removing a generated Cloudflare hostname does not delete the provider record.
Provider and router changes require separate authorization and explicit proof.

## Trust-boundary invariants

Administrative allow-lists deliberately exclude node addresses 192.168.1.2 and
192.168.1.3. Cross-node pod-to-host-port traffic can be SNATed to a peer node;
trusting node IPs would grant unrelated pods LAN privilege. A private route
tested from a node should be denied. Test through the MetalLB VIP from an
ordinary LAN client.

WireGuard client traffic is masqueraded to the Pi PodCIDR. Only the exact
documented Pi PodCIDR exception may be used. Never broaden it to the cluster-wide
PodCIDR. Moving/replacing the Pi or changing its PodCIDR requires explicit
allow-list and high-risk-policy review.

That exception also means an Internet-facing workload scheduled on the Pi may
inherit private-route trust. Do not let a new public workload float there
without explicit placement and NetworkPolicy proof. Audiobookshelf's Beelink
pin is the safe pattern; existing floating public workloads require review and
are not automatic precedents.

For split-horizon HTTPS egress, NetworkPolicy enforcement may observe the
MetalLB VIP before DNAT or Traefik pod port 8443 after DNAT. Permit only the
documented minimum path. Namespace default-deny remains in force.

## Select authentication

For a user-facing application:

1. Prefer the application's supported native OIDC, OAuth2, or SAML integration.
2. Use native application authentication when supported SSO is absent or
   unsuitable, with the narrowest practical exposure and a documented reason.
3. Use generic forward-auth only after proving browser, API, webhook,
   WebSocket, callback, and official native-client compatibility.
4. Permit no authentication only on a private route with a specific reason.
5. Reject a public unauthenticated route.

authentik-forward-single-v1 is the standard single-app proxy profile.
authentik-forward-single-v2 adds a mandatory allowedGroups gate. Preserve v2
group authorization when modifying an existing service; it is not equivalent to
v1.

## Native OIDC gate

Declare and verify:

- stable application slug and client ID;
- exact same-host HTTPS browser, mobile, logout, and back-channel callbacks;
- authorization-code grants and minimum scopes;
- confidential versus public client;
- PKCE evidence for public clients;
- provider and relying-party secret ownership for confidential clients;
- any custom claim expression and reason;
- relying-party role mapping and first-user behavior.

Identity-provider login does not imply administrator authorization. Keep
application-side roles explicit. Prefer back-channel logout when the application
supports it.

A confidential secret used by Kubernetes belongs in SOPS on both required
sides. An application-managed relying-party secret remains in backed-up
application state and must be rotated with the provider copy as one operation.

Keep an uninitialized first-owner surface off a public route. Use a documented
fail-closed bootstrap only when the application supports one without overwriting
state. Otherwise deploy without the public route, complete separately authorized
private onboarding, verify recovery, and add exposure in a second reviewed
change. Never invent an owner marker simply to clear a 503.

## NetworkPolicy review

Start from no ingress and no egress. Add only:

- DNS to CoreDNS;
- Traefik or the exact approved caller to the published port;
- named same-namespace dependencies;
- precise LAN/NFS destinations and protocol ports;
- narrowly scoped public endpoints required by the application.

Do not copy egress: [{}], hostNetwork, a NodePort, a host port, or broad CIDR
access from another workload without a task-specific threat review. A
host-network listener's bind address may be a stronger boundary than
NetworkPolicy; verify both.

## Acceptance and authorization

Repository editing does not authorize changing router forwards, Cloudflare,
Authentik through an interactive admin UI, application roles, or live
credentials. Do not expose a new public service without explicit user scope.
Merging a descriptor can nevertheless make Flux deploy it and cause the
declared Cloudflare DDNS and Authentik blueprint controllers to act. Require
authorization for those inevitable effects before merge; manual provider
cleanup and UI work remain separate.

After merge, require:

- expected DNS answers from both Blocky resolvers and authoritative public DNS;
- valid certificate and Gateway attachment;
- HTTPRoute Accepted=True and ResolvedRefs=True;
- non-empty proxy/backend endpoints;
- correct denial and success from public, LAN, WireGuard, node-origin, and direct
  host-port paths as applicable;
- OIDC discovery, login, exact callback, logout, role mapping, recovery login,
  and official mobile-client behavior;
- NetworkPolicy proof and relevant logs.

Report which paths were not tested; do not infer access safety from a 200 response
on one path.
