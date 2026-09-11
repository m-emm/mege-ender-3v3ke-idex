# Installed-file overlay

`rootfs/` is copied directly onto `/` after the upstream Mainsail release has
been unpacked. It contains deliberate, complete replacements for installed
regular files. There is no parser or generic upstream patcher.

The Mainsail index is from release `v2.9.1` and must stay aligned with the
`MAINSAIL_VERSION` used to build the image. When upgrading Mainsail, replace
the complete `rootfs/var/www/mainsail/index.html` from the matching release,
add `crossorigin="use-credentials"` to its manifest link, and update the
version in the same change. Do not deploy an index from one release onto the
assets of another release.

The nginx file deliberately sets `X-Forwarded-For` and `X-Real-IP` to
`$remote_addr` for Moonraker. This removes Caddy's public client address from
the forwarded request while preserving the actual local client address.
