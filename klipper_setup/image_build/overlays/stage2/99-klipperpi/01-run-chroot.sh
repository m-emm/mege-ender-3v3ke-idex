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

ensure_boot_config_in_all() {
  local setting="$1"
  local comment="${2:-}"

  if awk -v setting="${setting}" '
    /^\[/ { section=$0 }
    section == "[all]" && $0 == setting { found=1 }
    END { exit found ? 0 : 1 }
  ' "${BOOT_CONFIG}"; then
    return 0
  fi

  if grep -q '^\[all\]' "${BOOT_CONFIG}"; then
    if [ -n "${comment}" ]; then
      sed -i "/^\\[all\\]/a ${setting}" "${BOOT_CONFIG}"
      sed -i "/^\\[all\\]/a # ${comment}" "${BOOT_CONFIG}"
    else
      sed -i "/^\\[all\\]/a ${setting}" "${BOOT_CONFIG}"
    fi
  else
    {
      echo
      echo "[all]"
      if [ -n "${comment}" ]; then
        echo "# ${comment}"
      fi
      echo "${setting}"
    } >> "${BOOT_CONFIG}"
  fi
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
  acl \
  sudo \
  openssh-server \
  avahi-daemon \
  nginx \
  crudini \
  v4l-utils \
  python3 \
  python3-venv \
  python3-pip \
  python3-dev \
  python3-numpy \
  python3-matplotlib \
  python3-scipy \
  python3-yaml \
  build-essential \
  libatlas-base-dev \
  libopenblas-dev \
  libsodium23
python3 -c 'from scipy.stats import theilslopes'

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

# --- Disk space protection ---------------------------------------------------

log "Configuring journal size limits to prevent disk exhaustion"
require_file "${FILES_DIR}/journald-size-limit.conf"
install -d -m 0755 /etc/systemd/journald.conf.d
install -m 0644 "${FILES_DIR}/journald-size-limit.conf" /etc/systemd/journald.conf.d/size-limit.conf

log "Configuring APT auto-clean to prevent cache buildup"
require_file "${FILES_DIR}/99-auto-clean.conf"
install -d -m 0755 /etc/apt/apt.conf.d
install -m 0644 "${FILES_DIR}/99-auto-clean.conf" /etc/apt/apt.conf.d/99-auto-clean

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

# --- WiFi country configuration ----------------------------------------------

if [ -n "${WIFI_COUNTRY:-}" ]; then
  log "Configuring WiFi country: ${WIFI_COUNTRY}"
  # Set regulatory domain for WiFi
  if command -v raspi-config >/dev/null 2>&1; then
    raspi-config nonint do_wifi_country "${WIFI_COUNTRY}"
  else
    # Fallback: write directly to wpa_supplicant.conf if raspi-config not available
    install -d -m 0755 /etc/wpa_supplicant
    if ! grep -q "^country=" /etc/wpa_supplicant/wpa_supplicant.conf 2>/dev/null; then
      echo "country=${WIFI_COUNTRY}" > /etc/wpa_supplicant/wpa_supplicant.conf
      echo "ctrl_interface=DIR=/var/run/wpa_supplicant GROUP=netdev" >> /etc/wpa_supplicant/wpa_supplicant.conf
      echo "update_config=1" >> /etc/wpa_supplicant/wpa_supplicant.conf
    fi
  fi
  # Unblock WiFi (rfkill might not work in chroot, but doesn't hurt to try)
  rfkill unblock wifi 2>/dev/null || true
fi

if [ -f "${BOOT_CONFIG}" ]; then
  log "Disabling onboard Raspberry Pi WiFi; external USB WiFi remains available"
  ensure_boot_config_in_all \
    "dtoverlay=disable-wifi" \
    "Disable the onboard Raspberry Pi WiFi radio; use the external USB WiFi adapter."
fi

wifi_profiles=("${FILES_DIR}"/klipperpi-wifi*.nmconnection)
if [ -e "${wifi_profiles[0]}" ]; then
  log "Installing NetworkManager WiFi profiles"
  install -d -m 0700 /etc/NetworkManager/system-connections
  for wifi_profile in "${wifi_profiles[@]}"; do
    install -m 0600 "${wifi_profile}" \
      "/etc/NetworkManager/system-connections/$(basename "${wifi_profile}")"
  done

  install -d -m 0755 /var/lib/NetworkManager
  cat > /var/lib/NetworkManager/NetworkManager.state <<'EOF'
[main]
NetworkingEnabled=true
WirelessEnabled=true
WWANEnabled=true
EOF

  if [ -f /lib/systemd/system/NetworkManager.service ] || [ -f /etc/systemd/system/NetworkManager.service ]; then
    systemctl_enable_safe NetworkManager
  fi
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

# --- PolicyKit rules (Moonraker permissions) ---------------------------------

log "Configuring PolicyKit rules for Moonraker"
require_file "${FILES_DIR}/moonraker.pkla"
install -d -m 0755 /etc/polkit-1/localauthority/50-local.d
install -m 0644 "${FILES_DIR}/moonraker.pkla" /etc/polkit-1/localauthority/50-local.d/moonraker.pkla

# --- USB serial hygiene ------------------------------------------------------

log "Configuring USB serial stability"
require_file "${FILES_DIR}/99-klipper-no-modemmanager.rules"
install -d -m 0755 /etc/udev/rules.d
install -m 0644 "${FILES_DIR}/99-klipper-no-modemmanager.rules" /etc/udev/rules.d/99-klipper-no-modemmanager.rules

# ModemManager probing USB CDC ACM devices is hostile to Klipper MCUs. The unit
# may not be installed on all image variants, so mask it opportunistically.
systemctl disable ModemManager.service >/dev/null 2>&1 || true
systemctl mask ModemManager.service >/dev/null 2>&1 || true

# --- printer_data layout -----------------------------------------------------

log "Creating printer_data layout under ${PRINTER_DATA}"

require_file "${FILES_DIR}/printer.cfg"
require_file "${FILES_DIR}/moonraker.conf"
require_file "${FILES_DIR}/resonance/run_resonance_plot.py"

install -d -m 0755 -o "${USERNAME}" -g "${USERNAME}" \
  "${CONFIG_DIR}" "${CONFIG_DIR}/resonance" "${LOG_DIR}" "${COMMS_DIR}" \
  "${PRINTER_DATA}/systemd" "${PRINTER_DATA}/vision" "${PRINTER_DATA}/vision/nozzle_cam"

install -m 0644 "${FILES_DIR}/printer.cfg" "${CONFIG_DIR}/printer.cfg"
install -m 0644 "${FILES_DIR}/moonraker.conf" "${CONFIG_DIR}/moonraker.conf"
install -m 0755 \
  "${FILES_DIR}/resonance/run_resonance_plot.py" \
  "${CONFIG_DIR}/resonance/run_resonance_plot.py"
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
require_file "${FILES_DIR}/menderpi-wlan-ready.service"
require_file "${FILES_DIR}/menderpi-wlan-ready.sh"
require_file "${FILES_DIR}/vision-framebuffer.service"
require_file "${FILES_DIR}/vision-framebuffer-nozzle-cam.service"
require_file "${FILES_DIR}/vision-capture.service"
require_file "${FILES_DIR}/vision-capture-nozzle-cam.service"
require_file "${FILES_DIR}/vision_framebuffer.py"
require_file "${FILES_DIR}/vision_capture.py"
require_file "${FILES_DIR}/vision_calibration.py"
require_file "${FILES_DIR}/calib_dao.py"
require_file "${FILES_DIR}/vision_calibration_graph.py"
require_file "${FILES_DIR}/vision_bed_fiducial.py"
require_file "${FILES_DIR}/vision_four_fiducials.py"
require_file "${FILES_DIR}/vision_eddy_fiducial_xz.py"
require_file "${FILES_DIR}/eddy_sift_body_template.png"
require_file "${FILES_DIR}/vision_fine_tool_calibration.py"
require_file "${FILES_DIR}/vision_nozzle_fine_xz.py"
require_file "${FILES_DIR}/vision_nozzle_tip_localization.py"
require_file "${FILES_DIR}/vision_tool_xy_calibration.py"
require_file "${FILES_DIR}/vision_tool_xz_sweep.py"
require_file "${FILES_DIR}/vision_red_marker_x_sweep.py"
require_file "${FILES_DIR}/vision_rough_x_verification.py"
require_file "${FILES_DIR}/vision_job_types.json"
require_file "${FILES_DIR}/calib.yaml"
require_file "${FILES_DIR}/priors.yaml"
require_file "${FILES_DIR}/webcam_health_probe.py"
require_file "${FILES_DIR}/nozzle_cam_profiles.json"
require_file "${FILES_DIR}/klipperpi-expand-rootfs.service"
require_file "${FILES_DIR}/klipperpi-expand-rootfs-once.sh"
# Note: klipperscreen.service not needed - LightDM handles KlipperScreen

install -m 0644 "${FILES_DIR}/klipper.service" /etc/systemd/system/klipper.service
install -m 0644 "${FILES_DIR}/moonraker.service" /etc/systemd/system/moonraker.service
install -m 0644 "${FILES_DIR}/menderpi-wlan-ready.service" /etc/systemd/system/menderpi-wlan-ready.service
install -m 0755 "${FILES_DIR}/menderpi-wlan-ready.sh" /usr/local/sbin/menderpi-wlan-ready.sh
install -m 0644 "${FILES_DIR}/vision-framebuffer.service" /etc/systemd/system/vision-framebuffer.service
install -m 0644 "${FILES_DIR}/vision-framebuffer-nozzle-cam.service" /etc/systemd/system/vision-framebuffer-nozzle-cam.service
install -m 0644 "${FILES_DIR}/vision-capture.service" /etc/systemd/system/vision-capture.service
install -m 0644 "${FILES_DIR}/vision-capture-nozzle-cam.service" /etc/systemd/system/vision-capture-nozzle-cam.service
install -m 0644 "${FILES_DIR}/klipperpi-expand-rootfs.service" /etc/systemd/system/klipperpi-expand-rootfs.service
install -m 0755 "${FILES_DIR}/klipperpi-expand-rootfs-once.sh" /usr/local/sbin/klipperpi-expand-rootfs-once.sh
install -m 0755 "${FILES_DIR}/vision_framebuffer.py" /usr/local/bin/vision_framebuffer.py
install -m 0755 "${FILES_DIR}/vision_capture.py" /usr/local/bin/vision_capture.py
install -m 0755 "${FILES_DIR}/vision_calibration.py" /usr/local/bin/vision_calibration.py
install -m 0644 "${FILES_DIR}/calib_dao.py" /usr/local/bin/calib_dao.py
install -m 0644 "${FILES_DIR}/vision_calibration_graph.py" /usr/local/bin/vision_calibration_graph.py
install -m 0644 "${FILES_DIR}/vision_bed_fiducial.py" /usr/local/bin/vision_bed_fiducial.py
install -m 0644 "${FILES_DIR}/vision_four_fiducials.py" /usr/local/bin/vision_four_fiducials.py
install -m 0644 "${FILES_DIR}/vision_eddy_fiducial_xz.py" /usr/local/bin/vision_eddy_fiducial_xz.py
install -m 0644 "${FILES_DIR}/vision_fine_tool_calibration.py" /usr/local/bin/vision_fine_tool_calibration.py
install -m 0644 "${FILES_DIR}/vision_nozzle_fine_xz.py" /usr/local/bin/vision_nozzle_fine_xz.py
install -m 0644 "${FILES_DIR}/vision_nozzle_tip_localization.py" /usr/local/bin/vision_nozzle_tip_localization.py
install -m 0644 "${FILES_DIR}/vision_tool_xy_calibration.py" /usr/local/bin/vision_tool_xy_calibration.py
install -m 0644 "${FILES_DIR}/vision_tool_xz_sweep.py" /usr/local/bin/vision_tool_xz_sweep.py
install -m 0644 "${FILES_DIR}/vision_red_marker_x_sweep.py" /usr/local/bin/vision_red_marker_x_sweep.py
install -m 0644 "${FILES_DIR}/vision_rough_x_verification.py" /usr/local/bin/vision_rough_x_verification.py
install -m 0755 "${FILES_DIR}/webcam_health_probe.py" /usr/local/bin/webcam_health_probe.py
install -d -m 0755 /usr/local/share/vision
install -m 0644 "${FILES_DIR}/nozzle_cam_profiles.json" /usr/local/share/vision/nozzle_cam_profiles.json
install -m 0644 "${FILES_DIR}/vision_job_types.json" /usr/local/share/vision/vision_job_types.json
install -m 0644 "${FILES_DIR}/calib.yaml" /usr/local/share/vision/calib.yaml
install -m 0644 "${FILES_DIR}/priors.yaml" /usr/local/share/vision/priors.yaml
install -m 0644 "${FILES_DIR}/eddy_sift_body_template.png" /usr/local/share/vision/eddy_sift_body_template.png
setfacl -m u:www-data:--x "${USER_HOME}"

# Replace __USER__ placeholder
sed -i "s/__USER__/${USERNAME}/g" \
  /etc/systemd/system/klipper.service \
  /etc/systemd/system/moonraker.service

systemctl daemon-reload

# Enable units (after they exist)
systemctl_enable_safe klipperpi-expand-rootfs
systemctl_enable_safe menderpi-wlan-ready
systemctl_enable_safe klipper
systemctl_enable_safe moonraker
systemctl_enable_safe vision-framebuffer
systemctl_enable_safe vision-framebuffer-nozzle-cam
systemctl_enable_safe vision-capture
systemctl_enable_safe vision-capture-nozzle-cam
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

log "Ensuring user groups for serial/MCU and camera access"
usermod -a -G tty,dialout,video "${USERNAME}" || true

# --- Klipper + Moonraker -----------------------------------------------------

log "Setting up Klipper (venv + checkout)"
clone_repo https://github.com/Klipper3d/klipper.git /opt/klipper "${KLIPPER_COMMIT:-}"
python3 -m venv /opt/klipper-env
/opt/klipper-env/bin/pip install --upgrade pip wheel
/opt/klipper-env/bin/pip install -r /opt/klipper/scripts/klippy-requirements.txt
/opt/klipper-env/bin/pip install "numpy<1.26"
/opt/klipper-env/bin/pip install "matplotlib<3.11"
/opt/klipper-env/bin/python -c 'import numpy, matplotlib'

log "Installing custom Klipper host extras"
require_file "${FILES_DIR}/klipper_host/klippy/extras/heaters.py"
require_file "${FILES_DIR}/klipper_host/klippy/extras/vision.py"
require_file "${FILES_DIR}/klipper_host/klippy/extras/idex_manual_tuning.py"
install -m 0644 \
  "${FILES_DIR}/klipper_host/klippy/extras/heaters.py" \
  /opt/klipper/klippy/extras/heaters.py
install -m 0644 \
  "${FILES_DIR}/klipper_host/klippy/extras/vision.py" \
  /opt/klipper/klippy/extras/vision.py
install -m 0644 \
  "${FILES_DIR}/klipper_host/klippy/extras/idex_manual_tuning.py" \
  /opt/klipper/klippy/extras/idex_manual_tuning.py

chown -R "${USERNAME}:${USERNAME}" /opt/klipper /opt/klipper-env

log "Pre-building Klipper host C helper"
runuser -u "${USERNAME}" -- bash -lc 'cd /opt/klipper && /opt/klipper-env/bin/python - <<'"'"'PY'"'"'
import sys
sys.path.insert(0, "/opt/klipper")
from klippy import chelper
chelper.get_ffi()
PY'

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
systemctl_enable_safe klipperpi-expand-rootfs
systemctl_enable_safe menderpi-wlan-ready
systemctl_enable_safe klipper
systemctl_enable_safe moonraker
systemctl disable crowsnest >/dev/null 2>&1 || true
systemctl_enable_safe vision-framebuffer
systemctl_enable_safe vision-framebuffer-nozzle-cam
systemctl_enable_safe vision-capture
systemctl_enable_safe vision-capture-nozzle-cam
# Note: klipperscreen runs via LightDM session, not as a systemd service

# Optional: record build info for later debugging
log "Writing build info"
{
  echo "hostname=${HOSTNAME}"
  echo "username=${USERNAME}"
  echo "klipper_commit=${KLIPPER_COMMIT:-}"
  echo "klipper_host_extras=vision.py,idex_manual_tuning.py"
  echo "moonraker_commit=${MOONRAKER_COMMIT:-}"
  echo "mainsail_version=${MAINSAIL_VERSION}"
  echo "build_time_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
} >/etc/klipperpi-buildinfo

# --- Cleanup ----------------------------------------------------------------

log "Cleanup apt caches"
apt-get clean
rm -rf /var/lib/apt/lists/*

log "Done"
