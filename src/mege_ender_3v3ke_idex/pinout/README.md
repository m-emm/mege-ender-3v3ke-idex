# Pinout Compatibility Package

The generic pinout renderer moved to
[`mege-circuits`](https://github.com/m-emm/mege-circuits).

Use:

```bash
mege-circuits-pinout path/to/pinout.yaml -o output/
python -m mege_circuits.pinout path/to/pinout.yaml -o output/
```

The active printer wiring sources remain under
`klipper_setup/klipper_config/wiring/`. This package only keeps compatibility
imports for older Ender-specific scripts.
