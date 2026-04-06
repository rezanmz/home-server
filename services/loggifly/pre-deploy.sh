#!/bin/bash
echo "📋 Setting up LoggiFly..."

# Create persistent directory
mkdir -p ~/persistent/loggifly/config

# Create default config.yaml with Telegram settings if it doesn't exist
if [ ! -f ~/persistent/loggifly/config/config.yaml ]; then
cat << 'EOF' > ~/persistent/loggifly/config/config.yaml
containers:
  # Example container
  # my-container-name:
  #   keywords:
  #     - error
  #     - regex: (username|password).*incorrect 
    
global_keywords:
  keywords:
    - failed
    - error
    - critical

notifications:     
  apprise:
    # Telegram Apprise format: tgram://bottoken/ChatID
    # Get your bot token from @BotFather and your ChatID from @userinfobot
    url: "tgram://your_bot_token/your_chat_id"
EOF
fi

# Set proper permissions
# Using standard 1000 UID/GID for pi user
chown -R 1000 ~/persistent/loggifly/config
chmod 700 ~/persistent/loggifly/config

echo "✅ LoggiFly setup complete"
