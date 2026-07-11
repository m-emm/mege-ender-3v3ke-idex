#!/bin/bash
# Write system status to web-accessible location for remote debugging

DEBUG_DIR="/var/www/html/debug"
mkdir -p "${DEBUG_DIR}"

cat > "${DEBUG_DIR}/status.txt" <<EOF
=== System Debug Info ===
Generated: $(date)

--- SSH Service Status ---
$(systemctl status ssh 2>&1 || echo "SSH service not found")

--- SSH Service Enabled? ---
$(systemctl is-enabled ssh 2>&1 || echo "Cannot check")

--- SSH Listening Ports ---
$(ss -tlnp | grep :22 || echo "No SSH listening on port 22")

--- SSH Config Check ---
$(sshd -T 2>&1 | head -20 || echo "Cannot test SSH config")

--- Journal Logs (SSH) ---
$(journalctl -u ssh --no-pager -n 50 2>&1 || echo "No SSH logs")

--- Authorized Keys ---
$(ls -la /home/*/. ssh/authorized_keys 2>&1 || echo "No authorized_keys found")

--- Network Interfaces ---
$(ip addr show 2>&1)

--- Video Devices ---
$(ls -l /dev/video* /dev/v4l/by-id/* 2>&1 || echo "No video devices found")

--- Enabled Services ---
$(systemctl list-unit-files --state=enabled | grep -E 'ssh|avahi|klipper|moonraker|nginx|vision-framebuffer|vision-capture' || echo "None found")

EOF

chmod 644 "${DEBUG_DIR}/status.txt"
echo "Debug info written to ${DEBUG_DIR}/status.txt"
