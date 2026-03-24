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
- Pi-hole uses `network_mode: host` (needed for DNS on port 53 and DHCP). The Raspberry Pi's IP is `192.168.2.2`.
- VPN clients use Pi-hole (`192.168.2.2`) as their DNS resolver, getting ad-blocking while connected remotely.
- qBittorrent, Radarr, Sonarr, and Prowlarr all route through Gluetun (NordVPN WireGuard) via `network_mode: container:gluetun`.
- All services are LAN/VPN-only (nginx `allow`/`deny` rules).

## Services

| Service             | Description                               | Access                                          |
| ------------------- | ----------------------------------------- | ----------------------------------------------- |
| **SWAG**            | Nginx reverse proxy + Let's Encrypt SSL   | Ports 80/443                                    |
| **Cloudflare DDNS** | Keeps DNS records updated with current IP | —                                               |
| **Pi-hole**         | DNS-level ad blocking                     | `pihole.reza.network`                           |
| **Jellyfin**        | Media server (movies & TV)                | `jellyfin.reza.network`                         |
| **Radarr**          | Movie management & automation (via VPN)   | `radarr.reza.network`                           |
| **Sonarr**          | TV show management & automation (via VPN) | `sonarr.reza.network`                           |
| **Prowlarr**        | Indexer manager for Radarr/Sonarr (via VPN) | `prowlarr.reza.network`                       |
| **Jellyseerr**      | Media request management (via VPN)        | `jellyseerr.reza.network`                       |
| **Downloads**       | qBittorrent + FlareSolverr (via Gluetun VPN) | `qbittorrent.reza.network`                   |
| **Actual Budget**   | Personal finance/budgeting                | `budget.reza.network`                           |
| **Heimdall**        | Dashboard/homepage                        | `homepage.reza.network`                         |
| **VPN**             | WireGuard (wg-easy)                       | `vpn.reza.network` (UI), port 1234/udp (tunnel) |
| **Samba**           | SMB file shares for media                 | Ports 139/445 (LAN-only)                        |
| **Duplicati**       | Encrypted backups of service configs      | `duplicati.reza.network`                        |

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
    ├── cloudflare-ddns/
    ├── downloads/          # Gluetun VPN + qBittorrent
    ├── heimdall/
    ├── jellyfin/
    ├── jellyseerr/
    ├── pihole/
    ├── prowlarr/
    ├── radarr/
    ├── samba/
    ├── sonarr/
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

These must be set as GitHub Actions secrets:

| Secret                       | Used by                                |
| ---------------------------- | -------------------------------------- |
| `CLOUDFLARE_API_TOKEN`       | Cloudflare DDNS, SWAG (DNS validation) |
| `NORD_WIREGUARD_PRIVATE_KEY` | Downloads (Gluetun/NordVPN)            |
| `PIHOLE_PASSWORD`            | Pi-hole web UI                         |
| `LETSENCRYPT_EMAIL`          | SWAG (Let's Encrypt)                   |
| `SAMBA_PASSWORD`             | Samba file share user                  |
| `DUPLICATI_ENCRYPTION_KEY`   | Duplicati settings DB encryption       |

## Setup

1. Install Docker, Docker Compose, jq, and git on the Raspberry Pi
2. Create the shared network: `docker network create home-server`
3. Set up a [GitHub self-hosted runner](https://docs.github.com/en/actions/hosting-your-own-runners)
4. Configure the required secrets in the repository settings
5. Push to `main` to deploy everything
