#!/bin/bash
cd "$(dirname "$0")"

echo "Updating system packages..."
sudo apt-get update

echo "Installing required system dependencies (LibreOffice for Word to PDF, unrar for RAR to ZIP)..."
sudo apt-get install -y libreoffice unrar python3 python3-venv python3-pip

echo "Creating python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "============================"
echo "Setup complete!"
echo "Please make sure to set up your .env file with your BOT_TOKEN."
echo "You can start the bot using: ./start.sh"
