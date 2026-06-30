# Active Wiring Diagrams

This directory is the active wiring source for the custom Pico W + BTT TMC2226
electronics used by the printer Klipper config.

- `pico_w_btt_tmc2226_x.yaml` is the X-axis Pico wiring source.
- `pico_w_btt_tmc2226_y_z.yaml` is the Y/Z/heatbed Pico wiring source.
- `pico_tb6600_stripboard_interface.md` documents the planned non-live
  external Y TB6600 interface connector and stripboard transistor schematic.
  The schematic/stripboard source example now lives in
  [`mege-circuits`](https://github.com/m-emm/mege-circuits).
- `diagrams/*.svg` are generated artifacts committed for review.
- `../printer.cfg.template` is the active Klipper config source.

The YAML files own physical wiring: Pico pins, driver pins, connector pins,
motor coils, power rails, pull-ups, endstops, MOSFET, SSR boost output, and
thermistor wiring.
The generic pinout renderer is provided by
[`mege-circuits`](https://github.com/m-emm/mege-circuits); this repository owns
only the Ender-specific wiring sources and generated review artifacts.
The Klipper template owns firmware modifiers such as `!` direction inversion
and `^` pull-ups.

## Generate Diagrams

```bash
cd /Users/mege/git/mege-ender-3v3ke-idex/klipper_setup/klipper_config/wiring
./generate_wiring_svgs.sh
./generate_wiring_svgs.sh --check
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
The Y-axis TB6600 interface connector follows the same planned/non-live pattern:
it is documented in the pinout diagram, but active Y motion remains on TMC1
until the commented Klipper draft is deliberately activated.

The Nitehawk toolhead boards also have Klipper pins in `printer.cfg.template`,
but they are not part of these custom Pico/TMC wiring diagrams.

## Non-Active Configs

`klipper_setup/image_build/overlays/stage2/99-klipperpi/files/printer.cfg` is a
minimal image boot stub so Klipper can start on a fresh image. It is not the
active printer config and must not be used for wiring review.
