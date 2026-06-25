# Home Server

Docker services running on a Raspberry Pi, deployed automatically via GitHub Actions on every push to `main`.

## Architecture

All services run as Docker Compose projects connected through a shared `home-server` Docker network. [SWAG](https://docs.linuxserver.io/general/swag/) handles SSL termination and reverse proxying with Let's Encrypt certificates for `*.reza.network` subdomains. [Cloudflare DDNS](https://github.com/favonia/cloudflare-ddns) keeps DNS records pointed at the server's current IP.

```
Internet → Cloudflare DNS → Router (port forward 443) → SWAG (reverse proxy)
                                                            ↓
                                            home-server Docker network
                                                ↓         ↓        ↓
                                            Jellyfin   Radarr   ... etc
```

SWAG uses Cloudflare DNS validation for Let's Encrypt certificates, so only port 443 needs to be forwarded (port 80 is not required).

### Networking

- Services that need to be reached by SWAG join the `home-server` external network.
- Pi-hole uses `network_mode: host` (needed for DNS on port 53 and DHCP). The Raspberry Pi's IP is `192.168.1.2`.
- VPN clients use Pi-hole (`192.168.1.2`) as their DNS resolver, getting ad-blocking while connected remotely.
- qBittorrent, Radarr, Sonarr, and Prowlarr all route through Gluetun (ProtonVPN WireGuard, port forwarding enabled) via `network_mode: container:gluetun`.
- Most services are LAN/VPN-only (nginx `allow`/`deny` rules). Argilla is publicly reachable at `argilla.reza.network` for external annotators.
- Authentik provides native OIDC for services that support it. Services without native OIDC keep their own authentication and, for admin surfaces, remain LAN/VPN-only.

## Services

| Service             | Description                               | Access                                          |
| ------------------- | ----------------------------------------- | ----------------------------------------------- |
| **SWAG**            | Nginx reverse proxy + Let's Encrypt SSL   | Ports 80/443                                    |
| **Cloudflare DDNS** | Keeps DNS records updated with current IP | —                                               |
| **Authentik**       | Identity provider for native OIDC apps    | `auth.reza.network`                            |
| **Pi-hole**         | DNS-level ad blocking                     | `pihole.reza.network`                           |
| **Jellyfin**        | Media server (movies & TV)                | `jellyfin.reza.network`                         |
| **Hermes**          | AI agent (gateway + web UI)               | `hermes.reza.network`                           |
| **Radarr**          | Movie management & automation (via VPN)   | `radarr.reza.network`                           |
| **Sonarr**          | TV show management & automation (via VPN) | `sonarr.reza.network`                           |
| **Prowlarr**        | Indexer manager for Radarr/Sonarr (via VPN) | `prowlarr.reza.network`                       |
| **Jellyseerr**      | Media request management                  | `jellyseerr.reza.network`                       |
| **Downloads**       | qBittorrent + FlareSolverr (via Gluetun VPN) | `qbittorrent.reza.network`                   |
| **Actual Budget**   | Personal finance/budgeting                | `budget.reza.network`                           |
| **Heimdall**        | Dashboard/homepage                        | `homepage.reza.network`                         |
| **VPN**             | WireGuard (wg-easy)                       | `vpn.reza.network` (UI), port 1234/udp (tunnel) |
| **Samba**           | SMB file shares for media                 | Ports 139/445 (LAN-only)                        |
| **Duplicati**       | Encrypted backups of service configs      | `duplicati.reza.network`                        |
| **Glances**         | System monitoring (CPU, mem, disk, etc.)  | `glances.reza.network`                          |
| **Speedtest Tracker** | Automated internet speed monitoring     | `speedtest.reza.network`                        |
| **AnythingLLM**       | Local LLM UI & Agent interaction        | `anythingllm.reza.network`                      |
| **Argilla**           | Human review and annotation workflows   | `argilla.reza.network`                          |
| **MCPHub**            | MCP server dashboard                    | `mcphub.reza.network`                           |
| **CouchDB**           | Obsidian LiveSync server (CouchDB)      | `couchdb.reza.network`                          |

## Deployment

Pushing to `main` triggers the [deploy workflow](.github/workflows/deploy.yml):

1. **Detect changes** — uses `tj-actions/changed-files` to find which `services/` directories changed
2. **Stop deleted services** — tears down any removed service
3. **Deploy changed services** — for each changed service:
   - Runs `pre-deploy.sh` if present (also checks for `setup.sh` / `init.sh`)
   - Stops existing containers
   - Pulls latest images
   - Starts the service
4. **Health check** — verifies all services are running; attempts recovery for any that aren't

Each service runs as its own Compose project (`docker compose -p <service-name>`).

## Directory Structure

```
home-server/
├── .github/workflows/deploy.yml
├── README.md
└── services/
    ├── actual-budget/
    ├── authentik/          # Identity provider for OIDC integrations
    ├── couchdb/            # CouchDB for Obsidian LiveSync
    ├── argilla/            # Annotation and human review workflows
    ├── anythingllm/        # AnythingLLM + Postgres with PGVector
    ├── cloudflare-ddns/
    ├── downloads/          # Gluetun VPN + qBittorrent
    ├── glances/            # System monitoring
    ├── heimdall/
    ├── hermes/              # AI agent (Hermes gateway)
    ├── jellyfin/
    ├── jellyseerr/
    ├── mcphub/
    ├── pihole/
    ├── prowlarr/
    ├── radarr/
    ├── samba/
    ├── sonarr/
    ├── speedtest-tracker/   # Internet speed monitoring
    ├── swag/               # Reverse proxy + nginx configs
    │   └── config/nginx/proxy-confs/*.conf
    └── vpn/                # WireGuard (wg-easy)
```

Each service directory contains a `docker-compose.yml` and most include a `pre-deploy.sh` that creates persistent directories and sets permissions.

## Adding a New Service

1. Create `services/<name>/docker-compose.yml`:

   ```yaml
   services:
     my-service:
       image: my-image:latest
       networks:
         - home-server
       restart: unless-stopped
       security_opt:
         - no-new-privileges:true

   networks:
     home-server:
       external: true
   ```

2. If the service needs persistent storage, add a `pre-deploy.sh`:

   ```bash
   #!/bin/bash
   mkdir -p ~/persistent/my-service/config
   chmod 700 ~/persistent/my-service/config
   ```

3. To expose it via HTTPS, add a subdomain config in `services/swag/config/nginx/proxy-confs/` and add the subdomain to SWAG's `SUBDOMAINS` env var and Cloudflare DDNS's `DOMAINS` list.

4. Push to `main`.

## Required Secrets

Set these GitHub Actions secrets before deploying the relevant services:

| Secret                       | Used by                                |
| ---------------------------- | -------------------------------------- |
| `CLOUDFLARE_API_TOKEN`       | Cloudflare DDNS, SWAG (DNS validation) |
| `PROTONVPN_WIREGUARD_PRIVATE_KEY` | Downloads (Gluetun/ProtonVPN)           |
| `PIHOLE_PASSWORD`            | Pi-hole web UI                         |
| `LETSENCRYPT_EMAIL`          | SWAG (Let's Encrypt)                   |
| `AUTHENTIK_SECRET_KEY`       | Authentik application/session crypto   |
| `AUTHENTIK_POSTGRES_PASSWORD` | Authentik PostgreSQL                  |
| `AUTHENTIK_BOOTSTRAP_PASSWORD_HASH` | Initial Authentik `akadmin` password hash |
| `AUTHENTIK_BOOTSTRAP_EMAIL`  | Optional initial Authentik admin email |
| `SAMBA_PASSWORD`             | Samba file share user                  |
| `DUPLICATI_ENCRYPTION_KEY`   | Duplicati settings DB encryption       |
| `SPEEDTEST_TRACKER_APP_KEY`  | Speedtest Tracker encryption key       |
| `HERMES_WEBUI_PASSWORD`      | Hermes Web UI authentication           |
| `ACTUAL_OPENID_CLIENT_ID`    | Actual Budget Authentik OIDC client    |
| `ACTUAL_OPENID_CLIENT_SECRET` | Actual Budget Authentik OIDC secret   |
| `OPEN_WEBUI_SECRET_KEY`      | Open WebUI session/OAuth token crypto  |
| `OPEN_WEBUI_OAUTH_CLIENT_ID` | Open WebUI Authentik OIDC client       |
| `OPEN_WEBUI_OAUTH_CLIENT_SECRET` | Open WebUI Authentik OIDC secret   |
| `OPEN_WEBUI_OAUTH_ALLOWED_ROLES` | Optional Open WebUI allowed Authentik group override |
| `OPEN_WEBUI_OAUTH_ADMIN_ROLES` | Optional Open WebUI admin Authentik group override |
| `ARGILLA_PASSWORD`           | Argilla owner password                  |
| `ARGILLA_API_KEY`            | Argilla owner API key                   |
| `MCPHUB_ADMIN_PASSWORD`      | MCPHub admin password                  |
| `COUCHDB_USER`               | CouchDB admin username                 |
| `COUCHDB_PASSWORD`           | CouchDB admin password                 |

## Authentik OIDC Providers

Create OAuth2/OIDC providers in Authentik with these application slugs and redirect URIs:

| App | Authentik slug | Redirect URI |
| --- | -------------- | ------------ |
| Actual Budget | `actual-budget` | `https://budget.reza.network/openid/callback` |
| Open WebUI | `open-webui` | `https://chat.reza.network/oauth/oidc/callback` |
Open WebUI maps Authentik groups to app roles. By default, members of `open-webui-users` can log in and members of `open-webui-admins` become admins.
Open WebUI also merges OAuth logins into existing local accounts when the email address matches; only enable this with a trusted IdP such as this Authentik instance.

## Setup

1. Install Docker, Docker Compose, jq, and git on the Raspberry Pi
2. Create the shared network: `docker network create home-server`
3. Set up a [GitHub self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners)
4. Configure the required secrets in the repository settings
5. Push to `main` to deploy everything
