# home-server

Dockerized services for my Raspberry Pi, deployed via a self-hosted GitHub Actions runner.

## Layout

```
services/
  cloudflare-ddns/
    compose.yaml
  nginx/
    compose.yaml
    nginx.conf
    html/
      index.html
.github/workflows/deploy.yml
```

## Services

- **cloudflare-ddns**: Updates DNS for `reza.network` using Cloudflare's API. Image: `favonia/cloudflare-ddns:1.15.1` ([repo](https://github.com/favonia/cloudflare-ddns)).
- **nginx**: Serves a simple static site on `reza.network`.
  - HTTPS via Let's Encrypt using Cloudflare DNS-01 (no port 80 dependency). Exposes ports 80 and 443. Auto-renew with `certbot` sidecar.
  - Requires repo secrets: `LETSENCRYPT_EMAIL`, `CLOUDFLARE_API_TOKEN` (token needs Zone DNS Edit on `reza.network`).

## CI/CD

- Pushes to `main` automatically deploy only the services that changed.
- Runner: `runs-on: self-hosted` (Raspberry Pi).
- Secret required: `CLOUDFLARE_API_TOKEN` (repository secret).

## Local usage (optional)

From each service directory:

```bash
# cloudflare-ddns
cd services/cloudflare-ddns
export CLOUDFLARE_API_TOKEN=...  # if running locally
docker compose -f compose.yaml up -d --pull always

# nginx
cd ../nginx
docker compose -f compose.yaml up -d --pull always
```

## Notes

- cloudflare-ddns defaults are used; it updates `A` and `AAAA` records unless providers are disabled. See the upstream README for options and security notes: [favonia/cloudflare-ddns](https://github.com/favonia/cloudflare-ddns).
