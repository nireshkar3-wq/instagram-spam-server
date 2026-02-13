#!/bin/bash

# Setup script for Instagram Bot on Debian/Ubuntu LXC
# Run: chmod +x setup_lxc.sh && sudo ./setup_lxc.sh

echo "🚀 Starting LXC Setup for InstaBot..."

# 1. Update System
sudo apt-get update && sudo apt-get upgrade -y

# 2. Install Python and basic tools
sudo apt-get install -y python3 python3-pip python3-venv wget curl unzip fonts-liberation libappindicator3-1 libasound2 libatk-bridge2.0-0 libatk1.0-0 libc6 libcairo2 libcups2 libdbus-1-3 libexpat1 libfontconfig1 libgbm1 libgcc1 libgdk-pixbuf2.0-0 libglib2.0-0 libgtk-3-0 libnspr4 libnss3 libpango-1.0-0 libpangocairo-1.0-0 libstdc++6 libx11-6 libx11-xcb1 libxcb1 libxcomposite1 libxcursor1 libxdamage1 libxext6 libxfixes3 libxi6 libxrandr2 libxrender1 libxss1 libxtst6 xdg-utils

# 3. Install Google Chrome (Most stable for Selenium on Linux)
echo "🌐 Installing Google Chrome..."
wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
sudo dpkg -i google-chrome-stable_current_amd64.deb || sudo apt-get install -f -y
rm google-chrome-stable_current_amd64.deb

# 4. Setup Python Environment
echo "🐍 Setting up Python virtual environment..."
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 5. Create basic folders
mkdir -p Instagram_session

echo "✅ Setup complete!"
echo "To start the application, run:"
echo "source venv/bin/activate && python3 app.py"
