# Home Server Management

This repository manages Docker services on a Raspberry Pi home server using GitHub Actions for automated deployment.

## 🏗️ Architecture

- **Services Directory**: Each service lives in its own directory under `services/`
- **Docker Compose**: Each service has its own `docker-compose.yml` file
- **Automated Deployment**: GitHub Actions detect changes and deploy services automatically
- **Self-hosted Runner**: Deployment runs directly on the Raspberry Pi

## 📁 Directory Structure

```
home-server/
├── .github/
│   └── workflows/
│       └── deploy.yml          # Main deployment workflow
├── services/
│   ├── nginx/                  # Example nginx service
│   │   ├── docker-compose.yml
│   │   ├── nginx.conf
│   │   ├── html/
│   │   └── ssl/
│   └── [other-services]/       # Add more services here
└── README.md
```

## 🚀 How It Works

### Change Detection

The workflow uses `tj-actions/changed-files` to detect which services have been modified:

1. **Changed Services**: Services with modifications are rebuilt and restarted
2. **New Services**: New services are built and started
3. **Deleted Services**: Removed services are stopped and cleaned up

### Deployment Process

1. **Detect Changes**: Identifies which services in the `services/` directory have changed
2. **Stop Deleted Services**: Stops and removes containers for deleted services
3. **Deploy Changed Services**:
   - Validates service configuration
   - Stops existing containers
   - Pulls latest images
   - Starts updated services
4. **Health Check**: Verifies deployment status

### Service Lifecycle

- **New Service**: Add directory under `services/` → Automatic deployment
- **Update Service**: Modify files → Automatic redeployment
- **Remove Service**: Delete directory → Automatic cleanup

## 📋 Adding a New Service

1. Create a new directory under `services/`:

   ```bash
   mkdir services/my-new-service
   ```

2. Add a `docker-compose.yml` file:

   ```yaml
   version: "3.8"
   services:
     my-service:
       image: my-image:latest
       ports:
         - "8080:80"
       restart: unless-stopped
   ```

3. Add any configuration files needed

4. Commit and push - the service will be deployed automatically!

## 🔧 Service Examples

### Nginx (Included)

A simple web server with:

- Custom nginx configuration
- Static HTML content
- SSL certificate support (directory prepared)

### Adding Jellyfin

```bash
mkdir services/jellyfin
```

Create `services/jellyfin/docker-compose.yml`:

```yaml
version: "3.8"
services:
  jellyfin:
    image: jellyfin/jellyfin:latest
    container_name: jellyfin
    ports:
      - "8096:8096"
    volumes:
      - ./config:/config
      - ./cache:/cache
      - /path/to/media:/media:ro
    restart: unless-stopped
    environment:
      - JELLYFIN_PublishedServerUrl=http://your-server-ip:8096
```

## ⚙️ Setup Requirements

### Self-hosted Runner Setup

1. On your Raspberry Pi, install Docker and Docker Compose
2. Set up a GitHub self-hosted runner following [GitHub's documentation](https://docs.github.com/en/actions/hosting-your-own-runners/adding-self-hosted-runners-to-a-repository)
3. Ensure the runner has Docker permissions

### Required Tools on Runner

- Docker
- Docker Compose
- jq (for JSON processing)
- git

## 🔒 Security Considerations

- Services run on self-hosted runner (your Raspberry Pi)
- Docker containers are isolated
- Consider using secrets for sensitive configuration
- Regular updates of base images recommended

## 📊 Monitoring

The workflow provides:

- Deployment status for each service
- Container health checks
- Docker system overview
- Running container list

## 🤝 Contributing

1. Add your service under `services/`
2. Test locally with `docker compose up`
3. Commit and push to trigger deployment
4. Monitor the GitHub Actions workflow

## 📝 Notes

- Each service runs with its own Docker Compose project name
- Services are isolated by default
- Modify networking in docker-compose.yml if services need to communicate
- SSL certificates should be placed in respective service directories
