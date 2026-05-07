#!/bin/bash
echo "📋 Setting up LoggiFly..."

# Create persistent directory
mkdir -p ~/persistent/loggifly/config

# Create default config.yaml with Telegram settings if it doesn't exist
if [ ! -f ~/persistent/loggifly/config/config.yaml ]; then
cat << 'EOF' > ~/persistent/loggifly/config/config.yaml
# LoggiFly v2 config format
# See: https://clemcer.github.io/LoggiFly/guide/getting-started

global:
  keywords:
    - failed
    - error
    - critical

# containers:
#   rules:
#     - container_name: my-container-name
#       keywords:
#         - keyword: error
#         - regex: (username|password).*incorrect

notifications:
  apprise:
    # Telegram Apprise format: tgram://bottoken/ChatID?format=text
    # Get your bot token from @BotFather and your ChatID from @userinfobot
    url: "tgram://your_bot_token/your_chat_id?format=text"
EOF
fi

# Set proper permissions
# Using standard 1000 UID/GID for pi user
chown -R 1000 ~/persistent/loggifly/config
chmod 700 ~/persistent/loggifly/config

echo "✅ LoggiFly setup complete"
