# Active Wiring Diagrams

This directory is the active wiring source for the custom Pico W, external
TB6600-style Y driver, and BTT TMC2226 Z electronics used by the printer
Klipper config.

- `pico_w_btt_tmc2226_x.yaml` is the X-axis Pico wiring source.
- `pico_w_btt_tmc2226_y_z.yaml` is the Y/Z/heatbed Pico wiring source.
- `pico_tb6600_stripboard_interface.py` and
  `pico_tb6600_stripboard_layout.py` generate the live external Y
  TB6600 interface schematic and verified stripboard assembly.
- `pico_tb6600_stripboard_interface.md` documents that interface.
- `diagrams/*.svg` are generated artifacts committed for review.
- `../printer.cfg.template` is the active Klipper config source.

The YAML files own physical wiring: Pico pins, driver pins, connector pins,
motor coils, power rails, pull-ups, endstops, MOSFET, SSR boost output, and
thermistor wiring.
The generic pinout renderer is provided by
[`mege-circuits`](https://github.com/m-emm/mege-circuits); this repository owns
the Ender-specific wiring sources, including the IDEX TB6600 interface source,
and generated review artifacts.
The Klipper template owns firmware modifiers such as `!` direction inversion
and `^` pull-ups.

## Generate Diagrams

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex
./klipper_setup/klipper_config/wiring/generate_wiring_svgs.sh
./klipper_setup/klipper_config/wiring/generate_wiring_svgs.sh --check
```

`--check` regenerates into a temporary directory and diffs the result against
the committed SVGs.

## Check Klipper Consistency

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex
python klipper_setup/klipper_config/wiring/validate_wiring.py
```

Only wires with `klipper:` metadata are checked against `printer.cfg.template`.
For the heatbed, both `heater_bed.heater_pin` and `heater_bed.boost_pin` are
checked so the 24V MOSFET and SSR boost output cannot drift silently.
The X-axis SFS and CR Touch wires are documented here as wired/reserved hardware,
but they are not active Klipper config and intentionally have no `klipper:` tag.
The Y-axis TB6600 interface connector is the active Y motion path. TMC1 remains
documented as a reserved rollback path, but its Klipper tags are intentionally
inactive while TB6600 is live.

The Nitehawk toolhead boards also have Klipper pins in `printer.cfg.template`,
but they are not part of these custom Pico/TMC wiring diagrams.

## Non-Active Configs

`klipper_setup/image_build/overlays/stage2/99-klipperpi/files/printer.cfg` is a
minimal image boot stub so Klipper can start on a fresh image. It is not the
active printer config and must not be used for wiring review.
