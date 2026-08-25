# Task brief: change route, DNS, or authentication

Change `[SERVICE]` exposure/authentication as one security-boundary operation.
A working URL is not proof that DNS, access control, callbacks, and NetworkPolicy
are correct.

## Required inputs

- Service ID, namespace, Service/backend, and current routes: [values]
- Desired exposure: [none/private/admin/public/exceptional host-network]
- Hostname and DNS intent: [Blocky split DNS; Cloudflare/public DNS]
- Intended clients: [LAN/WireGuard/public/mobile/webhook/API]
- Current and target auth: [native OIDC/OAuth/SAML/native/forward-auth/none]
- OIDC client type, callbacks, scopes, claims, groups, and role mapping: [details]
- Private middleware/access-proxy pattern: [identity]
- Required ingress/egress and dependencies: [ports/destinations]
- Bootstrap/first-owner and recovery-login plan: [details]
- External DNS/router/provider objects: [inventory]

## Authorization

Fill every line. Blank or ambiguous means no.

- Repository edits: [yes/no; route, Service, policy, catalog, SOPS paths]
- Create commits: [yes/no; scope]
- Push a branch: [yes/no; remote/branch]
- Open or update a pull request: [yes/no; target]
- Merge: [yes/no; exact PR and checks]
- Read-only cluster/host access: [yes/no; route/DNS/auth inspection]
- Live cluster/host mutation: [yes/no; reconcile/restart/bootstrap scope]
- Application-state mutation: [yes/no; exact role/login/bootstrap objects]
- External/provider mutation: [yes/no; exact DNS/router/OAuth objects]
- Destructive actions: [yes/no; exact record/client/credential removal]

Public exposure, provider changes, application roles, and credential rotation each
require their matching explicit authority; repository edits imply none of them.
If merge is authorized, it necessarily deploys the diff and may make declared
Cloudflare DDNS and Authentik controllers act; authorize those inevitable
effects or keep the work review-only.

## Manuals and skills

Load `home-server-safety`, `network-auth`, `service-catalog`, `secrets-sops`,
`configuration-ownership`, `application-state`, `high-risk-review`, and
`validation`; add `network-services` when changing a DNS or network-service
boundary. Route and NetworkPolicy additions, removals, and material edits all
change reviewed baseline findings, not only broadenings. Read
architecture traffic/trust boundaries, service-operations exposure and policy,
service-catalog auth profiles, configuration-ownership for UI-managed secrets,
the ingress/TLS runbook, and the service-specific auth guidance.

## Workflow

1. Trace the active workload, Service or access proxy, HTTPRoute, middleware,
   NetworkPolicy, descriptor, generated DNS/Authentik output, SOPS references, and
   external records. Record exact current exposure from each relevant client path.
2. Choose exposure before authentication. Prefer supported native OIDC/OAuth/SAML;
   use native login when appropriate. Use forward-auth only after reviewing API,
   webhook, WebSocket, callback, and official-client compatibility. Never publish
   an unauthenticated route.
3. For native OIDC, define stable slug/client ID, exact same-host HTTPS callbacks,
   minimum grants/scopes, confidential vs public/PKCE, claim reasons, provider and
   relying secret ownership, logout, role mapping, and recovery login.
4. For forward-auth, use the versioned profile that matches policy. Preserve
   `authentik-forward-single-v2` as a mandatory non-empty `allowedGroups` gate;
   do not downgrade it to v1 or add v2 semantics ad hoc to v1.
5. Keep uninitialized first-owner surfaces private and fail closed. Use a
   supported bootstrap only when it does not overwrite application state;
   otherwise withhold the public route, complete private onboarding, and add
   exposure in a second reviewed change. Identity login does not grant
   application administrator authorization.
6. Update explicit route/Service/proxy/policy manifests and the colocated
   descriptor together. Render; never hand-edit Homepage, Blocky, Cloudflare, or
   aggregate Authentik output. Removing generated DNS intent does not delete a
   provider record.
7. Start NetworkPolicy from default deny and add exact DNS, Traefik/caller,
   dependency, LAN/NFS, and public endpoint paths only. Do not trust node IPs to
   make private routes work. Keep the documented exact Pi PodCIDR exception rather
   than broadening to the cluster PodCIDR. Do not let a new public workload float
   onto the Pi without explicit proof that it cannot inherit private-route trust.
8. Run complete validation. If authorized to deploy, prove DNS from both internal
   resolvers and public authority, certificate/route conditions, endpoints,
   success and denial from each applicable client path, OIDC login/callback/logout/
   roles/mobile behavior, NetworkPolicy, and logs at the exact merged revision.

## Hard stops

Stop for public unauthenticated access, a public first-owner page, unknown native
auth capability, unreviewed forward-auth client/API breakage, wildcard or off-host
callback, node-IP/private-network trust broadening, unrestricted egress, v2 group
gate removal, a missing provider copy or unproved relying-party ownership for a
confidential client, provider mutation without authority, or inability to test
both intended success and denial paths.

## Rollback and recovery

Record prior manifests, generated output, OIDC/provider objects, encrypted Secret
references, and external DNS/router state. Preserve a recovery login. Reverting
Git does not recreate deleted provider records, reverse role changes, or un-revoke
credentials; name those coordinated reversals explicitly.

## Evidence contract

Return before/after traffic and auth flow, ownership decisions, descriptor and
generated diffs, callback/scope/group/role evidence, NetworkPolicy paths, complete
validation, exact provider/live actions, reconciled revision, and client-by-client
success/denial results without secret values.

## Acceptance criteria

- [ ] Exposure, DNS, route, backend, authentication, and policy express one
      consistent least-privilege boundary.
- [ ] Native OIDC or the documented forward-auth exception is fully justified;
      v2 group authorization is preserved where selected.
- [ ] Generated output is compiler-owned and full validation passes.
- [ ] If deployed, required clients succeed, forbidden paths fail, and exact
      callback/logout/role behavior is verified.
- [ ] External/provider and destructive work stays within explicit scope.
