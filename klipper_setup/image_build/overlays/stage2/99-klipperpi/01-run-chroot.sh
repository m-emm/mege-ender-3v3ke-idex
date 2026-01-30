#!/bin/bash
# Runs inside the target rootfs during pi-gen build.

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

FILES_DIR="/opt/klipperpi-files"
BUILD_ENV="${FILES_DIR}/build.env"

die() {
  echo "ERROR: $*" >&2
  exit 1
}

log() {
  echo
  echo "==> $*"
}

require_file() {
  local f="$1"
  [ -f "$f" ] || die "Missing required file: $f"
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"
}

# --- Load build env ----------------------------------------------------------

require_file "${BUILD_ENV}"

set -a
# shellcheck disable=SC1090
source "${BUILD_ENV}"
set +a

: "${USERNAME:?USERNAME is required in build.env}"
: "${HOSTNAME:?HOSTNAME is required in build.env}"
: "${MAINSAIL_VERSION:?MAINSAIL_VERSION is required in build.env}"

if ! id "${USERNAME}" >/dev/null 2>&1; then
  die "User ${USERNAME} not found; ensure FIRST_USER_NAME matches USERNAME."
fi

USER_HOME="/home/${USERNAME}"
PRINTER_DATA="${USER_HOME}/printer_data"
CONFIG_DIR="${PRINTER_DATA}/config"
LOG_DIR="${PRINTER_DATA}/logs"
COMMS_DIR="${PRINTER_DATA}/comms"

BOOT_CONFIG="/boot/firmware/config.txt"
if [ ! -f "${BOOT_CONFIG}" ]; then
  BOOT_CONFIG="/boot/config.txt"
fi

# --- Sanity prerequisites ----------------------------------------------------

require_cmd apt-get
require_cmd install
require_cmd sed
require_cmd git
require_cmd python3
require_cmd systemctl

# --- Helpers ----------------------------------------------------------------

clone_repo() {
  local url="$1"
  local dir="$2"
  local ref="${3:-}"

  if [ ! -d "${dir}/.git" ]; then
    log "Cloning ${url} -> ${dir}"
    git clone "${url}" "${dir}"
  fi

  log "Updating ${dir}"
  git -C "${dir}" fetch --tags origin

  if [ -n "${ref}" ]; then
    log "Checking out ${dir} @ ${ref}"
    git -C "${dir}" checkout -f "${ref}"
  else
    # fall back to main/master if no ref pinned
    git -C "${dir}" checkout -f origin/main 2>/dev/null || \
    git -C "${dir}" checkout -f origin/master 2>/dev/null || true
  fi
}

systemctl_enable_safe() {
  local unit="$1"
  # "enable" should work even if systemd isn't running; it creates symlinks.
  systemctl enable "${unit}" >/dev/null 2>&1 || die "Failed to enable ${unit}"
}

# --- Base package install ----------------------------------------------------

log "APT: update + baseline packages"
apt-get update

# Install everything we need in one go (less chance of missing apt indices later)
apt-get install -y --no-install-recommends \
  ca-certificates \
  curl \
  wget \
  unzip \
  git \
  openssh-server \
  avahi-daemon \
  nginx \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  build-essential \
  libsodium23

# You install these later; keeping them separate is fine, but installing here makes it deterministic.
# If you want to keep image smaller, move dev packages into a conditional section.
# (KlipperScreen needs them if you're building python wheels.)
apt-get install -y --no-install-recommends \
  libcairo2-dev \
  libgirepository1.0-dev \
  libglib2.0-dev \
  libgtk-3-dev \
  gobject-introspection \
  pkg-config \
  ninja-build

# Install X and lightdm for KlipperScreen
apt-get install -y --no-install-recommends \
  lightdm \
  xserver-xorg \
  xinit

# --- Hostname / hosts --------------------------------------------------------

log "Setting hostname to ${HOSTNAME}"
echo "${HOSTNAME}" > /etc/hostname

# Ensure /etc/hosts has a 127.0.1.1 line for hostname
if grep -qE '^127\.0\.1\.1\s' /etc/hosts; then
  sed -i "s/^127\.0\.1\.1\s.*/127.0.1.1\t${HOSTNAME}/" /etc/hosts
else
  echo -e "127.0.1.1\t${HOSTNAME}" >> /etc/hosts
fi

# --- Timezone / locale -------------------------------------------------------

if [ -n "${TIMEZONE:-}" ]; then
  log "Configuring timezone: ${TIMEZONE}"
  ln -sf "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime
  dpkg-reconfigure -f noninteractive tzdata
fi

if [ -n "${LOCALE:-}" ]; then
  log "Configuring locale: ${LOCALE}"
  # Avoid repeated entries if script is re-run during development
  if ! grep -q "^${LOCALE} UTF-8$" /etc/locale.gen; then
    echo "${LOCALE} UTF-8" >> /etc/locale.gen
  fi
  locale-gen "${LOCALE}"
  update-locale LANG="${LOCALE}"
fi

# --- SSH: keys + hardening + host keys --------------------------------------

log "Configuring SSH (hardening + authorized_keys + host keys)"

require_file "${FILES_DIR}/sshd_hardening.conf"
require_file "${FILES_DIR}/authorized_keys"

install -d -m 0755 /etc/ssh/sshd_config.d
install -m 0644 "${FILES_DIR}/sshd_hardening.conf" /etc/ssh/sshd_config.d/99-klipper-hardening.conf

# If a "sshswitch" service exists on the base image, ensure it cannot interfere
systemctl disable sshswitch.service >/dev/null 2>&1 || true
systemctl mask sshswitch.service >/dev/null 2>&1 || true

# Ensure host keys exist in the final image
rm -f /etc/ssh/ssh_host_* || true
ssh-keygen -A

# Ensure user keys exist with correct permissions
install -d -m 0700 "${USER_HOME}/.ssh"
install -m 0600 "${FILES_DIR}/authorized_keys" "${USER_HOME}/.ssh/authorized_keys"
chown -R "${USERNAME}:${USERNAME}" "${USER_HOME}/.ssh"

# Make sure ssh service is enabled (service name is "ssh" on Debian/RPi OS)
systemctl unmask ssh >/dev/null 2>&1 || true
systemctl_enable_safe ssh

# Optional: ensure sshd listens on all interfaces (only if your hardening config changes it)
# You can keep this commented unless you suspect ListenAddress issues.
# sed -i 's/^\s*#\?\s*ListenAddress.*/ListenAddress 0.0.0.0/' /etc/ssh/sshd_config || true

# --- Avahi (Bonjour/zeroconf) ------------------------------------------------

log "Configuring Avahi"
require_file "${FILES_DIR}/avahi-daemon.conf"
install -m 0644 "${FILES_DIR}/avahi-daemon.conf" /etc/avahi/avahi-daemon.conf
systemctl_enable_safe avahi-daemon

# --- printer_data layout -----------------------------------------------------

log "Creating printer_data layout under ${PRINTER_DATA}"

require_file "${FILES_DIR}/printer.cfg"
require_file "${FILES_DIR}/moonraker.conf"

install -d -m 0755 -o "${USERNAME}" -g "${USERNAME}" \
  "${CONFIG_DIR}" "${LOG_DIR}" "${COMMS_DIR}"

install -m 0644 "${FILES_DIR}/printer.cfg" "${CONFIG_DIR}/printer.cfg"
install -m 0644 "${FILES_DIR}/moonraker.conf" "${CONFIG_DIR}/moonraker.conf"
chown -R "${USERNAME}:${USERNAME}" "${PRINTER_DATA}"

# --- X wrapper (KlipperScreen) ----------------------------------------------

log "Configuring X wrapper for KlipperScreen"
require_file "${FILES_DIR}/Xwrapper.config"
install -d -m 0755 /etc/X11
install -m 0644 "${FILES_DIR}/Xwrapper.config" /etc/X11/Xwrapper.config

# Configure X to use DPI-1 output correctly
log "Configuring X for DPI display"
install -d -m 0755 /etc/X11/xorg.conf.d
cat >/etc/X11/xorg.conf.d/99-dpi-display.conf <<'EOF'
Section "Monitor"
    Identifier "DPI-1"
    Option "Primary" "true"
EndSection

Section "Screen"
    Identifier "Default Screen"
    Monitor "DPI-1"
    DefaultDepth 24
    SubSection "Display"
        Depth 24
        Modes "800x480"
    EndSubSection
EndSection
EOF

# --- LightDM auto-login ------------------------------------------------------

log "Configuring LightDM auto-login for ${USERNAME}"
install -d -m 0755 /etc/lightdm/lightdm.conf.d
cat >/etc/lightdm/lightdm.conf.d/50-klipperpi.conf <<EOF
[Seat:*]
autologin-user=${USERNAME}
autologin-user-timeout=0
user-session=klipper
EOF

# --- Klipper X session desktop entry -----------------------------------------

log "Installing Klipper xsession desktop entry"
install -d -m 0755 /usr/share/xsessions
cat >/usr/share/xsessions/klipper.desktop <<'EOF'
[Desktop Entry]
Name=Klipper
Comment=Start KlipperScreen
Exec=/usr/local/bin/klipperscreen-xsession
Type=Application
EOF

# --- LightDM enablement and graphical target ---------------------------------

log "Setting default display manager and graphical target"
echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager
systemctl_enable_safe lightdm

# Deterministic graphical target (works reliably in chroot)
ln -sf /lib/systemd/system/graphical.target /etc/systemd/system/default.target

# --- Nginx for Mainsail ------------------------------------------------------

log "Configuring nginx for Mainsail"
require_file "${FILES_DIR}/nginx-mainsail.conf"

install -m 0644 "${FILES_DIR}/nginx-mainsail.conf" /etc/nginx/sites-available/mainsail
ln -sf /etc/nginx/sites-available/mainsail /etc/nginx/sites-enabled/mainsail
rm -f /etc/nginx/sites-enabled/default
systemctl_enable_safe nginx

# --- Systemd units -----------------------------------------------------------

log "Installing systemd units"

require_file "${FILES_DIR}/klipper.service"
require_file "${FILES_DIR}/moonraker.service"
# Note: klipperscreen.service not needed - LightDM handles KlipperScreen

install -m 0644 "${FILES_DIR}/klipper.service" /etc/systemd/system/klipper.service
install -m 0644 "${FILES_DIR}/moonraker.service" /etc/systemd/system/moonraker.service

# Replace __USER__ placeholder
sed -i "s/__USER__/${USERNAME}/g" \
  /etc/systemd/system/klipper.service \
  /etc/systemd/system/moonraker.service

systemctl daemon-reload

# Enable units (after they exist)
systemctl_enable_safe klipper
systemctl_enable_safe moonraker
# Note: klipperscreen runs via LightDM, not as a systemd service

# --- Display overlay (optional) ---------------------------------------------

log "Applying PiTFT43 display overlay"
if [ -f "${BOOT_CONFIG}" ]; then
  require_file "${FILES_DIR}/pitft43.conf"
  if ! grep -q "gt911_btt_tft43_dip" "${BOOT_CONFIG}"; then
    cat "${FILES_DIR}/pitft43.conf" >> "${BOOT_CONFIG}"
  fi
  
  # Disable DSI display auto-detection to prevent dual-screen setup
  # (DPI display is configured manually in pitft43.conf)
  if grep -q "^display_auto_detect=1" "${BOOT_CONFIG}"; then
    sed -i 's/^display_auto_detect=1/display_auto_detect=0/' "${BOOT_CONFIG}"
    log "Disabled display_auto_detect to prevent dual-screen configuration"
  fi
  
  # Disable vc4-kms-v3d and replace with vc4-fkms-v3d for DPI compatibility
  if grep -q "^dtoverlay=vc4-kms-v3d" "${BOOT_CONFIG}"; then
    sed -i 's/^dtoverlay=vc4-kms-v3d/dtoverlay=vc4-fkms-v3d/' "${BOOT_CONFIG}"
    log "Switched to vc4-fkms-v3d overlay for DPI display compatibility"
  fi
  
  # Enable disable_fw_kms_setup if not already set
  if ! grep -q "^disable_fw_kms_setup=1" "${BOOT_CONFIG}"; then
    sed -i '/dtoverlay=vc4-kms-v3d/a disable_fw_kms_setup=1' "${BOOT_CONFIG}"
    log "Enabled disable_fw_kms_setup for DPI display"
  fi

  mkdir -p /boot/firmware/overlays /boot/overlays
  if [ ! -f /boot/firmware/overlays/gt911_btt_tft43_dip.dtbo ] && [ ! -f /boot/overlays/gt911_btt_tft43_dip.dtbo ]; then
    wget -q \
      https://raw.githubusercontent.com/bigtreetech/TFT43-DIP/master/gt911_btt_tft43_dip.dtbo \
      -O /boot/firmware/overlays/gt911_btt_tft43_dip.dtbo || \
    wget -q \
      https://raw.githubusercontent.com/bigtreetech/TFT43-DIP/master/gt911_btt_tft43_dip.dtbo \
      -O /boot/overlays/gt911_btt_tft43_dip.dtbo
  fi
else
  log "WARNING: BOOT_CONFIG not found; skipping display overlay configuration"
fi

# --- User groups -------------------------------------------------------------

log "Ensuring user groups for serial/MCU access"
usermod -a -G tty,dialout "${USERNAME}" || true

# --- Klipper + Moonraker -----------------------------------------------------

log "Setting up Klipper (venv + checkout)"
clone_repo https://github.com/Klipper3d/klipper.git /opt/klipper "${KLIPPER_COMMIT:-}"
python3 -m venv /opt/klipper-env
/opt/klipper-env/bin/pip install --upgrade pip wheel
/opt/klipper-env/bin/pip install -r /opt/klipper/scripts/klippy-requirements.txt
chown -R "${USERNAME}:${USERNAME}" /opt/klipper /opt/klipper-env

log "Setting up Moonraker (venv + checkout)"
clone_repo https://github.com/Arksine/moonraker.git /opt/moonraker "${MOONRAKER_COMMIT:-}"
python3 -m venv /opt/moonraker-env
/opt/moonraker-env/bin/pip install --upgrade pip wheel
/opt/moonraker-env/bin/pip install -r /opt/moonraker/scripts/moonraker-requirements.txt
chown -R "${USERNAME}:${USERNAME}" /opt/moonraker /opt/moonraker-env

# --- Mainsail ----------------------------------------------------------------

log "Deploying Mainsail v${MAINSAIL_VERSION}"
MAINSAIL_ASSET="${MAINSAIL_ASSET:-mainsail.zip}"
MAINSAIL_URL="https://github.com/mainsail-crew/mainsail/releases/download/v${MAINSAIL_VERSION}/${MAINSAIL_ASSET}"

TMP_ZIP="/tmp/mainsail.zip"
rm -rf /var/www/mainsail
mkdir -p /var/www/mainsail

wget -q "${MAINSAIL_URL}" -O "${TMP_ZIP}"
unzip -q "${TMP_ZIP}" -d /var/www/mainsail
rm -f "${TMP_ZIP}"

# Some releases wrap under /mainsail
if [ -d /var/www/mainsail/mainsail ]; then
  mv /var/www/mainsail/mainsail/* /var/www/mainsail/
  rmdir /var/www/mainsail/mainsail
fi

chown -R www-data:www-data /var/www/mainsail

# --- KlipperScreen -----------------------------------------------------------

log "Installing KlipperScreen"
clone_repo https://github.com/jordanruthe/KlipperScreen.git /opt/klipperscreen "${KLIPPERSCREEN_COMMIT:-}"
python3 -m venv /opt/klipperscreen/.venv
/opt/klipperscreen/.venv/bin/pip install --upgrade pip setuptools wheel

# pick the best requirements file available
KS_REQ=""
if [ -f /opt/klipperscreen/requirements.txt ]; then
  KS_REQ=/opt/klipperscreen/requirements.txt
elif [ -f /opt/klipperscreen/scripts/KlipperScreen-requirements.txt ]; then
  KS_REQ=/opt/klipperscreen/scripts/KlipperScreen-requirements.txt
elif [ -f /opt/klipperscreen/scripts/requirements.txt ]; then
  KS_REQ=/opt/klipperscreen/scripts/requirements.txt
fi

if [ -n "${KS_REQ}" ]; then
  /opt/klipperscreen/.venv/bin/pip install -r "${KS_REQ}"
else
  echo "WARNING: No KlipperScreen requirements file found; skipping dependency install" >&2
fi

chown -R "${USERNAME}:${USERNAME}" /opt/klipperscreen

log "Creating klipperscreen-xsession launcher"
cat >/usr/local/bin/klipperscreen-xsession <<'EOF'
#!/usr/bin/env bash
set -e
export DISPLAY=:0
export XDG_SESSION_TYPE=x11
export GDK_BACKEND=x11

# Disable X screensaver and DPMS (ignore errors if X not ready yet)
xset s off 2>/dev/null || true
xset s noblank 2>/dev/null || true
xset -dpms 2>/dev/null || true

# Start lightweight window manager for fullscreen handling
matchbox-window-manager -use_titlebar no &

# KlipperScreen uses screen.py as the main entry point
exec /opt/klipperscreen/.venv/bin/python /opt/klipperscreen/screen.py
EOF
chmod 0755 /usr/local/bin/klipperscreen-xsession

log "Creating log directory for KlipperScreen"
install -d -m 0755 -o "${USERNAME}" -g "${USERNAME}" /var/log/klipperscreen

# --- Final enablement sanity -------------------------------------------------

log "Enablement sanity check"
systemctl_enable_safe ssh
systemctl_enable_safe avahi-daemon
systemctl_enable_safe nginx
systemctl_enable_safe klipper
systemctl_enable_safe moonraker
# Note: klipperscreen runs via LightDM session, not as a systemd service

# Optional: record build info for later debugging
log "Writing build info"
{
  echo "hostname=${HOSTNAME}"
  echo "username=${USERNAME}"
  echo "klipper_commit=${KLIPPER_COMMIT:-}"
  echo "moonraker_commit=${MOONRAKER_COMMIT:-}"
  echo "mainsail_version=${MAINSAIL_VERSION}"
  echo "build_time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >/etc/klipperpi-buildinfo

# --- Cleanup ----------------------------------------------------------------

log "Cleanup apt caches"
apt-get clean
rm -rf /var/lib/apt/lists/*

log "Done"
