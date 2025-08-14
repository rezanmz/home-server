# Jellyfin Media Server

This service provides a Jellyfin media server for streaming your media content.

## Configuration

### Environment Variables

- `TZ`: Set your timezone (e.g., `America/New_York`, `Europe/London`)
- `JELLYFIN_PublishedServerUrl`: Set to your server's external URL if needed

### Volumes

- `./config`: Jellyfin configuration data
- `./cache`: Jellyfin cache data
- `./media`: Your media files (read-only)

### Ports

- `8096`: Web interface (HTTP)
- `8920`: Web interface (HTTPS)
- `7359/udp`: Auto-discovery
- `1900/udp`: DLNA

## Setup

1. Create media directories:

   ```bash
   mkdir -p config cache media
   ```

2. Update the media volume path in `docker-compose.yml` to point to your actual media location:

   ```yaml
   - /path/to/your/media:/media:ro
   ```

3. Optionally update the timezone and published server URL

4. Start the service:

   ```bash
   ../manage.sh start jellyfin
   ```

5. Access Jellyfin at `http://your-server-ip:8096`

## First Run

1. Complete the initial setup wizard
2. Add your media libraries
3. Configure users and access permissions

## Notes

- The service will create config and cache directories automatically
- Make sure your media directory has proper read permissions
- Consider setting up hardware acceleration if your Pi supports it
