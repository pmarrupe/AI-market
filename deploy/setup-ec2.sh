#!/bin/bash
set -euo pipefail

echo "═══════════════════════════════════════════════"
echo "  AI Market Command Center — EC2 Setup"
echo "═══════════════════════════════════════════════"

# Install Docker
echo "→ Installing Docker..."
sudo dnf update -y -q
sudo dnf install -y docker git
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER

# Install Docker Compose plugin
echo "→ Installing Docker Compose..."
sudo mkdir -p /usr/local/lib/docker/cli-plugins
sudo curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$(uname -m)" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
sudo chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# Clone repo
echo "→ Cloning repository..."
cd ~
if [ -d "AI-market" ]; then
  cd AI-market && git pull
else
  git clone https://github.com/pmarrupe/AI-market.git
  cd AI-market
fi

# Create .env if it doesn't exist
if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "════════════════════════════════════════════════"
  echo "  IMPORTANT: Edit .env with your API keys"
  echo "════════════════════════════════════════════════"
  echo ""
  echo "  Run: nano .env"
  echo ""
  echo "  Set at minimum:"
  echo "    LLM_ENABLED=true"
  echo "    LLM_API_KEY=sk-your-openai-key"
  echo "    CORS_ORIGINS=*"
  echo ""
  echo "  Then run: sudo docker compose up -d --build"
  echo ""
else
  echo "→ .env already exists, keeping it."
  echo "→ Building and starting..."
  sudo docker compose up -d --build
  echo ""
  echo "════════════════════════════════════════════════"
  echo "  App is starting!"
  echo "  Check status: sudo docker compose logs -f"
  echo "════════════════════════════════════════════════"
fi
