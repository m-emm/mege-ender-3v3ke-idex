#!/bin/bash
# Install Klipper configuration from git repository to printer_data directory

set -e

REPO_DIR="$HOME/mege-ender-3v3ke-idex"
CONFIG_SOURCE="${REPO_DIR}/klipper_setup/klipper_config/printer.cfg"
CONFIG_DEST="$HOME/printer_data/config/printer.cfg"
BACKUP_DIR="$HOME/printer_data/config/backups"

echo "=== Klipper Config Installer ==="

# Check if repo exists
if [ ! -d "$REPO_DIR" ]; then
    echo "Error: Repository not found at $REPO_DIR"
    echo "Please clone the repository first:"
    echo "  cd ~ && git clone https://github.com/YOUR_USERNAME/mege-ender-3v3ke-idex.git"
    exit 1
fi

# Pull latest changes
echo "Pulling latest changes from git..."
cd "$REPO_DIR"
git pull

# Check if source config exists
if [ ! -f "$CONFIG_SOURCE" ]; then
    echo "Error: Source config not found at $CONFIG_SOURCE"
    exit 1
fi

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Backup existing config if it exists
if [ -f "$CONFIG_DEST" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="${BACKUP_DIR}/printer.cfg.${TIMESTAMP}"
    echo "Backing up existing config to $BACKUP_FILE"
    cp "$CONFIG_DEST" "$BACKUP_FILE"
fi

# Copy new config
echo "Installing new config..."
cp "$CONFIG_SOURCE" "$CONFIG_DEST"

echo "Config installed successfully!"
echo ""
echo "Next steps:"
echo "1. Review the config: nano $CONFIG_DEST"
echo "2. Verify MCU serial IDs match: ls -l /dev/serial/by-id/"
echo "3. Restart Klipper: sudo systemctl restart klipper"
echo "4. Check for errors: tail -f ~/printer_data/logs/klippy.log"
echo ""
echo "To restore a backup:"
echo "  cp $BACKUP_DIR/printer.cfg.TIMESTAMP $CONFIG_DEST"
echo "  sudo systemctl restart klipper"
