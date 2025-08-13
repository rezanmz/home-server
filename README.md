# Docker Services Deployment System

This repository includes a comprehensive GitHub Actions workflow and local management script for automatically deploying and managing multiple Docker services. The system is designed to handle the complete lifecycle of services including deployment, updates, and cleanup.

## 📁 Repository Structure

```
your-repo/
├── .github/
│   └── workflows/
│       └── deploy-services.yml     # Main GitHub Actions workflow
├── services/                       # Services directory
│   ├── service1/
│   │   ├── docker-compose.yml      # Service 1 configuration
│   │   ├── Dockerfile              # Optional
│   │   └── ...                     # Other service files
│   ├── service2/
│   │   ├── docker-compose.yml      # Service 2 configuration
│   │   └── ...
│   └── ...
├── manage-services.sh              # Local management script
└── README.md
```

## 🚀 Features

### GitHub Actions Workflow

- **Automatic Service Discovery**: Scans the `services/` directory for services with `docker-compose.yml` files
- **Intelligent Updates**: Only updates services that have changed
- **Service Lifecycle Management**: Handles new services, updates, and removals
- **Comprehensive Cleanup**: Removes networks and images when services are deleted
- **Health Checks**: Monitors service status after deployment
- **Error Handling**: Detailed logging and rollback capabilities
- **Resource Management**: Automatic cleanup of unused Docker resources

### Local Management Script

- **Mirror Workflow Locally**: Test deployments before pushing to production
- **Individual Service Management**: Deploy, remove, or check specific services
- **Status Monitoring**: Check the health and status of services
- **Log Viewing**: Easy access to service logs
- **Validation**: Validate Docker Compose configurations

## 📋 Prerequisites

### GitHub Actions Runner Setup

1. **Self-hosted Runner**: Must be configured on your Raspberry Pi
2. **Docker**: Docker and Docker Compose must be installed
3. **Permissions**: Runner must have access to Docker socket
4. **Storage**: Adequate disk space for images and containers

### Local Development Setup

1. **Docker**: Docker and Docker Compose installed
2. **Bash**: Bash shell (Linux/macOS/WSL)
3. **Permissions**: User must be in `docker` group

## 🔧 Setup Instructions

### 1. GitHub Repository Setup

1. **Copy the workflow file** to `.github/workflows/deploy-services.yml`
2. **Copy the management script** to the root of your repository as `manage-services.sh`
3. **Make the script executable**:
   ```bash
   chmod +x manage-services.sh
   ```

### 2. GitHub Secrets Configuration

Configure the following secrets in your GitHub repository settings:

- **Repository Secrets** (Settings → Secrets and variables → Actions):
  - Add any environment variables your services need
  - Example: `DATABASE_URL`, `API_KEY`, etc.

### 3. Self-hosted Runner Setup

Ensure your Raspberry Pi runner has proper permissions:

```bash
# Add user to docker group
sudo usermod -aG docker $USER

# Restart to apply changes
sudo systemctl restart docker

# Test Docker access
docker ps
```

### 4. Service Configuration

Each service should have its own directory under `services/` with a `docker-compose.yml` file:

```yaml
# services/myservice/docker-compose.yml
version: "3.8"

services:
  web:
    build: .
    ports:
      - "8080:80"
    environment:
      - NODE_ENV=production
    volumes:
      - /host/path:/container/path
    restart: unless-stopped

  database:
    image: postgres:13
    environment:
      - POSTGRES_DB=myapp
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
    volumes:
      - /host/data:/var/lib/postgresql/data
    restart: unless-stopped
```

## 🎯 Usage

### GitHub Actions (Automatic)

The workflow triggers automatically when:

- Code is pushed to `main`/`master` branch
- Changes are made to files in the `services/` directory
- Manual trigger via GitHub Actions UI

### Local Management

Use the management script for local testing and debugging:

```bash
# Deploy all services
./manage-services.sh deploy

# Deploy specific service
./manage-services.sh deploy myservice

# Check status of all services
./manage-services.sh status

# Check status of specific service
./manage-services.sh status myservice

# View logs
./manage-services.sh logs myservice 100

# Remove a service
./manage-services.sh remove myservice

# Validate configurations
./manage-services.sh validate

# List all services
./manage-services.sh list

# Cleanup Docker resources
./manage-services.sh cleanup

# Show help
./manage-services.sh help
```

## 📝 How It Works

### Service Discovery

1. Scans `services/` directory for subdirectories
2. Looks for `docker-compose.yml` or `docker-compose.yaml` files
3. Treats each directory as a separate service

### Deployment Process

1. **Discovery**: Find all current services
2. **Comparison**: Compare with previously deployed services
3. **Validation**: Validate all Docker Compose configurations
4. **Cleanup**: Remove services that no longer exist
5. **Deployment**: Deploy new and updated services
6. **Health Check**: Verify services are running properly
7. **State Update**: Record successfully deployed services

### Service Updates

- Services are updated using `docker-compose up -d --force-recreate`
- Only changed services are recreated
- Preserves volumes and persistent data
- Maintains zero-downtime for unchanged services

### Service Removal

When a service directory is deleted:

1. **Containers**: Stop and remove all containers
2. **Networks**: Remove service-specific networks
3. **Images**: Remove service-specific images
4. **Volumes**: Preserve mounted volumes (as requested)

## 🔍 Monitoring and Troubleshooting

### Logs

- **GitHub Actions**: Check workflow logs in Actions tab
- **Service Logs**: Use `docker-compose logs` or the management script
- **System Logs**: Check runner system logs if needed

### Common Issues

#### Permission Denied

```bash
sudo chmod 666 /var/run/docker.sock
# Or add user to docker group
sudo usermod -aG docker $USER
```

#### Service Won't Start

1. Check configuration: `./manage-services.sh validate myservice`
2. View logs: `./manage-services.sh logs myservice`
3. Check port conflicts: `docker ps`

#### Out of Disk Space

```bash
./manage-services.sh cleanup
docker system prune -af  # Aggressive cleanup
```

#### Network Conflicts

```bash
docker network ls
docker network prune
```

### Health Monitoring

- Services are checked after deployment
- Status is reported in workflow logs
- Use `docker ps` to see current container status
- Set up health checks in your `docker-compose.yml` files

## 🔒 Security Considerations

### GitHub Secrets

- Store sensitive environment variables as GitHub secrets
- Never commit secrets to the repository
- Use least privilege principle for runner permissions

### Docker Security

- Use non-root users in containers when possible
- Keep images updated and scan for vulnerabilities
- Limit resource usage in docker-compose files
- Use read-only mounts where appropriate

### Network Security

- Configure proper firewall rules
- Use internal networks for service communication
- Expose only necessary ports

## 🔄 Best Practices

### Service Configuration

- Use health checks in `docker-compose.yml`
- Set resource limits for containers
- Use restart policies (`restart: unless-stopped`)
- Store data outside containers using bind mounts

### Development Workflow

1. Test locally using `./manage-services.sh`
2. Validate configurations before committing
3. Use feature branches for major changes
4. Monitor deployment logs after pushes

### Maintenance

- Regularly run cleanup to manage disk space
- Monitor service logs for errors
- Keep Docker and Docker Compose updated
- Backup important volume data

## 📊 Example Service Structure

```yaml
# services/webapp/docker-compose.yml
version: "3.8"

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - DATABASE_URL=${DATABASE_URL}
    volumes:
      - /home/pi/app-data:/app/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    networks:
      - app-network

  redis:
    image: redis:alpine
    volumes:
      - /home/pi/redis-data:/data
    restart: unless-stopped
    networks:
      - app-network

networks:
  app-network:
    driver: bridge
```

## 🆘 Support

If you encounter issues:

1. Check the workflow logs in GitHub Actions
2. Use the local management script to debug
3. Verify Docker and Docker Compose are working
4. Check service configurations and logs
5. Ensure proper permissions and disk space

Remember to test changes locally before pushing to production!
