#!/bin/bash -e
# Runs inside the target rootfs during pi-gen build.

set -euo pipefail

FILES_DIR="/opt/klipperpi-files"
BUILD_ENV="${FILES_DIR}/build.env"

if [ ! -f "${BUILD_ENV}" ]; then
  echo "Missing ${BUILD_ENV}; render_overlay should have copied it." >&2
  exit 1
fi

set -a
source "${BUILD_ENV}"
set +a

if [ -z "${MAINSAIL_VERSION:-}" ]; then
  echo "MAINSAIL_VERSION is required in build.env" >&2
  exit 1
fi

if ! id "${USERNAME}" >/dev/null 2>&1; then
  echo "User ${USERNAME} not found; ensure FIRST_USER_NAME matches USERNAME." >&2
  exit 1
fi

USER_HOME="/home/${USERNAME}"
PRINTER_DATA="${USER_HOME}/printer_data"
CONFIG_DIR="${PRINTER_DATA}/config"
LOG_DIR="${PRINTER_DATA}/logs"
COMMS_DIR="${PRINTER_DATA}/comms"
BOOT_CONFIG="/boot/firmware/config.txt"
[ -f "${BOOT_CONFIG}" ] || BOOT_CONFIG="/boot/config.txt"

clone_repo() {
  local url="$1" dir="$2" ref="$3"
  if [ ! -d "${dir}/.git" ]; then
    git clone "${url}" "${dir}"
  fi
  git -C "${dir}" fetch origin
  if [ -n "${ref}" ]; then
    git -C "${dir}" checkout "${ref}"
  else
    git -C "${dir}" checkout origin/master || git -C "${dir}" checkout origin/main || true
  fi
}

echo "Setting hostname to ${HOSTNAME}"
echo "${HOSTNAME}" > /etc/hostname
sed -i "s/127.0.1.1.*/127.0.1.1\t${HOSTNAME}/" /etc/hosts || true

if [ -n "${TIMEZONE:-}" ]; then
  ln -sf "/usr/share/zoneinfo/${TIMEZONE}" /etc/localtime
  dpkg-reconfigure -f noninteractive tzdata
fi

if [ -n "${LOCALE:-}" ]; then
  echo "${LOCALE} UTF-8" >> /etc/locale.gen
  locale-gen "${LOCALE}"
  update-locale LANG="${LOCALE}"
fi

echo "Applying SSH hardening and keys"
# Ensure openssh-server is installed
apt-get update
apt-get install -y --no-install-recommends openssh-server

rm -f /etc/ssh/ssh_host_* || true
ssh-keygen -A
ls -l /etc/ssh/ssh_host_* || true

install -d /etc/ssh/sshd_config.d
install -m 644 "${FILES_DIR}/sshd_hardening.conf" /etc/ssh/sshd_config.d/99-klipper-hardening.conf
# Disable sshswitch.service completely - we manage SSH directly
systemctl disable sshswitch.service || true
systemctl mask sshswitch.service || true
# Enable and unmask SSH service directly
systemctl unmask ssh || true
systemctl enable ssh
install -d -m 700 "${USER_HOME}/.ssh"
install -m 600 "${FILES_DIR}/authorized_keys" "${USER_HOME}/.ssh/authorized_keys"
chown -R "${USERNAME}:${USERNAME}" "${USER_HOME}/.ssh"

echo "Configuring Avahi"
install -m 644 "${FILES_DIR}/avahi-daemon.conf" /etc/avahi/avahi-daemon.conf
systemctl enable avahi-daemon

echo "Creating printer_data layout"
install -d -o "${USERNAME}" -g "${USERNAME}" "${CONFIG_DIR}" "${LOG_DIR}" "${COMMS_DIR}"
install -m 644 "${FILES_DIR}/printer.cfg" "${CONFIG_DIR}/printer.cfg"
install -m 644 "${FILES_DIR}/moonraker.conf" "${CONFIG_DIR}/moonraker.conf"
chown -R "${USERNAME}:${USERNAME}" "${PRINTER_DATA}"

echo "Configuring X wrapper for KlipperScreen"
install -d /etc/X11
install -m 644 "${FILES_DIR}/Xwrapper.config" /etc/X11/Xwrapper.config

echo "Configuring nginx for Mainsail"
install -m 644 "${FILES_DIR}/nginx-mainsail.conf" /etc/nginx/sites-available/mainsail
ln -sf /etc/nginx/sites-available/mainsail /etc/nginx/sites-enabled/mainsail
rm -f /etc/nginx/sites-enabled/default

echo "Installing systemd units"
install -m 644 "${FILES_DIR}/klipper.service" /etc/systemd/system/klipper.service
install -m 644 "${FILES_DIR}/moonraker.service" /etc/systemd/system/moonraker.service
install -m 644 "${FILES_DIR}/klipperscreen.service" /etc/systemd/system/klipperscreen.service
sed -i "s/__USER__/${USERNAME}/g" /etc/systemd/system/klipper.service /etc/systemd/system/moonraker.service /etc/systemd/system/klipperscreen.service
systemctl daemon-reload

echo "Applying PiTFT43 display overlay"
if ! grep -q "gt911_btt_tft43_dip" "${BOOT_CONFIG}"; then
  cat "${FILES_DIR}/pitft43.conf" >> "${BOOT_CONFIG}"
fi
mkdir -p /boot/firmware/overlays /boot/overlays
if [ ! -f /boot/firmware/overlays/gt911_btt_tft43_dip.dtbo ] && [ ! -f /boot/overlays/gt911_btt_tft43_dip.dtbo ]; then
  wget -q https://raw.githubusercontent.com/bigtreetech/TFT43-DIP/master/gt911_btt_tft43_dip.dtbo -O /boot/firmware/overlays/gt911_btt_tft43_dip.dtbo || \
  wget -q https://raw.githubusercontent.com/bigtreetech/TFT43-DIP/master/gt911_btt_tft43_dip.dtbo -O /boot/overlays/gt911_btt_tft43_dip.dtbo
fi

echo "Ensuring user groups"
usermod -a -G tty,dialout "${USERNAME}" || true

echo "Installing OS runtime dependencies"
apt-get install -y --no-install-recommends libsodium23

echo "Setting up Klipper (venv + checkout)"
clone_repo https://github.com/Klipper3d/klipper.git /opt/klipper "${KLIPPER_COMMIT:-}"
python3 -m venv /opt/klipper-env
/opt/klipper-env/bin/pip install --upgrade pip
/opt/klipper-env/bin/pip install -r /opt/klipper/scripts/klippy-requirements.txt
chown -R "${USERNAME}:${USERNAME}" /opt/klipper /opt/klipper-env

echo "Setting up Moonraker (venv + checkout)"
clone_repo https://github.com/Arksine/moonraker.git /opt/moonraker "${MOONRAKER_COMMIT:-}"
python3 -m venv /opt/moonraker-env
/opt/moonraker-env/bin/pip install --upgrade pip
/opt/moonraker-env/bin/pip install -r /opt/moonraker/scripts/moonraker-requirements.txt
chown -R "${USERNAME}:${USERNAME}" /opt/moonraker /opt/moonraker-env

echo "Deploying Mainsail ${MAINSAIL_VERSION:-latest}"
MAINSAIL_ASSET="${MAINSAIL_ASSET:-mainsail.zip}"
if [ -n "${MAINSAIL_VERSION:-}" ]; then
  MAINSAIL_URL="https://github.com/mainsail-crew/mainsail/releases/download/v${MAINSAIL_VERSION}/${MAINSAIL_ASSET}"
else
  MAINSAIL_URL="https://github.com/mainsail-crew/mainsail/releases/latest/download/${MAINSAIL_ASSET}"
fi
TMP_ZIP="/tmp/mainsail.zip"
rm -rf /var/www/mainsail
mkdir -p /var/www/mainsail
wget -q "${MAINSAIL_URL}" -O "${TMP_ZIP}"
unzip -q "${TMP_ZIP}" -d /var/www/mainsail
rm -f "${TMP_ZIP}"
if [ -d /var/www/mainsail/mainsail ]; then
  mv /var/www/mainsail/mainsail/* /var/www/mainsail/
  rmdir /var/www/mainsail/mainsail
fi
chown -R www-data:www-data /var/www/mainsail

echo "Installing KlipperScreen"
clone_repo https://github.com/jordanruthe/KlipperScreen.git /opt/klipperscreen "${KLIPPERSCREEN_COMMIT:-}"
python3 -m venv /opt/klipperscreen/.venv
/opt/klipperscreen/.venv/bin/pip install --upgrade pip setuptools wheel
chown -R "${USERNAME}:${USERNAME}" /opt/klipperscreen

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
  # ensure cairo dev libs are present (belt and suspenders)
  apt-get install -y libcairo2-dev libgirepository1.0-dev libglib2.0-dev libgtk-3-dev gobject-introspection pkg-config ninja-build
  /opt/klipperscreen/.venv/bin/pip install -r "${KS_REQ}"
else
  echo "WARNING: No KlipperScreen requirements file found; skipping dependency install" >&2
fi

cat >/usr/local/bin/klipperscreen-xsession <<EOF
#!/usr/bin/env bash
export DISPLAY=:0
export XAUTHORITY=${USER_HOME}/.Xauthority
export XDG_RUNTIME_DIR=/tmp/xdg-runtime-${USERNAME}
mkdir -p "\${XDG_RUNTIME_DIR}"
chown ${USERNAME}:${USERNAME} "\${XDG_RUNTIME_DIR}"
exec /opt/klipperscreen/.venv/bin/python /opt/klipperscreen/KlipperScreen.py
EOF
chmod +x /usr/local/bin/klipperscreen-xsession

echo "Creating log directory for KlipperScreen"
install -d -o "${USERNAME}" -g "${USERNAME}" /var/log/klipperscreen

echo "Enabling services"
systemctl enable ssh avahi-daemon klipper moonraker nginx klipperscreen

echo "Cleanup apt cache"
apt-get clean
