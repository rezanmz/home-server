# Quick Setup Guide

## Prerequisites

### On your Raspberry Pi:

1. **Install Docker**:

   ```bash
   curl -fsSL https://get.docker.com -o get-docker.sh
   sudo sh get-docker.sh
   sudo usermod -aG docker $USER
   ```

2. **Install Docker Compose**:

   ```bash
   sudo apt update
   sudo apt install docker-compose-plugin
   ```

3. **Install required tools**:

   ```bash
   sudo apt install git jq
   ```

4. **Set up GitHub self-hosted runner**:
   - Go to your GitHub repository
   - Navigate to Settings → Actions → Runners
   - Click "New self-hosted runner"
   - Follow the instructions for Linux ARM64
   - Configure the runner as a service

## Repository Setup

1. **Clone this repository on your Pi**:

   ```bash
   git clone https://github.com/yourusername/home-server.git
   cd home-server
   ```

2. **Test the management script**:

   ```bash
   ./manage.sh list
   ./manage.sh validate nginx
   ```

3. **Test a service locally**:
   ```bash
   ./manage.sh start nginx
   ./manage.sh status
   ./manage.sh stop nginx
   ```

## Usage

### Adding a New Service

1. **Create service directory**:

   ```bash
   mkdir services/my-service
   cd services/my-service
   ```

2. **Create docker-compose.yml**:

   ```yaml
   version: "3.8"
   services:
     my-service:
       image: my-image:latest
       ports:
         - "8080:80"
       restart: unless-stopped
   ```

3. **Commit and push**:

   ```bash
   git add .
   git commit -m "Add my-service"
   git push
   ```

4. **The service will be automatically deployed!**

### Managing Services

```bash
# List all services
./manage.sh list

# Start a service
./manage.sh start nginx

# Stop a service
./manage.sh stop nginx

# Restart a service
./manage.sh restart nginx

# View logs
./manage.sh logs nginx

# Check status of all services
./manage.sh status

# Start all services
./manage.sh start-all

# Stop all services
./manage.sh stop-all
```

## Monitoring

- Check GitHub Actions tab for deployment status
- Use `./manage.sh status` for local service status
- Use `docker ps` to see running containers
- Use `docker compose ls` to see compose projects

## Troubleshooting

### Common Issues

1. **Permission denied for Docker**:

   ```bash
   sudo usermod -aG docker $USER
   # Then logout and login again
   ```

2. **GitHub runner not starting services**:

   - Check if the runner has Docker access
   - Verify the runner is running as the correct user

3. **Service not starting**:

   ```bash
   ./manage.sh validate servicename
   ./manage.sh logs servicename
   ```

4. **Port conflicts**:
   - Check what's using the port: `sudo netstat -tulpn | grep :8080`
   - Change the port in docker-compose.yml

### Logs

- GitHub Actions logs: Check the Actions tab in your repository
- Service logs: `./manage.sh logs servicename`
- Docker logs: `docker logs containername`

## Security Notes

- The self-hosted runner runs on your Pi with Docker access
- Keep your Pi updated with security patches
- Consider using a firewall to restrict access
- Use strong passwords for any web interfaces
- Consider setting up SSL certificates for HTTPS access

## Next Steps

1. Set up SSL certificates for nginx
2. Configure a reverse proxy for multiple services
3. Add monitoring services (Prometheus, Grafana)
4. Set up automated backups
5. Configure proper domain names and DNS
