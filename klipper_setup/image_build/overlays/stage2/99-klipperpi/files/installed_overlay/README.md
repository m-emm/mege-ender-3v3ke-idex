# Installed-file overlay

`rootfs/` is copied directly onto `/` after the upstream Mainsail release has
been unpacked. It contains deliberate, complete replacements for installed
regular files. There is no parser or generic upstream patcher.

The Mainsail index and service worker are from release `v2.9.1` and must stay
aligned with the `MAINSAIL_VERSION` used to build the image. The service worker
also excludes the custom `/calibration/`, `/eddy/`, and `/vision/` navigations
from Mainsail's SPA fallback.

When upgrading Mainsail, replace the complete
`rootfs/var/www/mainsail/index.html` and
`rootfs/var/www/mainsail/sw.js` files from the matching release, re-apply the
documented deliberate changes, and update the version in the same commit. Do
not deploy files from one release onto the assets of another release.

The nginx file deliberately sets `X-Forwarded-For` and `X-Real-IP` to
`$remote_addr` for Moonraker. This removes Caddy's public client address from
the forwarded request while preserving the actual local client address.
