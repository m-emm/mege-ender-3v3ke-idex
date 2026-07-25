# Active Wiring Diagrams

This directory is the active wiring source for the custom Pico W, external
TB6600-style Y driver, and BTT TMC2226 Z electronics used by the printer
Klipper config.

- `pico_w_btt_tmc2226_x.yaml` is the X-axis Pico wiring source.
- `pico_w_btt_tmc2226_y_z.yaml` is the Y/Z/heatbed Pico wiring source.
- `rp2040plus_btt_tmc5160t_plus_y.yaml` is the review-only physical wiring
  source for the proposed RP2040-Plus/TMC5160T Plus Y controller. Its generated
  top, discrete-component top, and underside SVGs model the adapter boundary,
  four AR20 wire-wrap carriers, the isolated high-current terminal zone, and
  the exact 64x57mm driver outline. All three views use one shared set of YAML
  coordinates; the underside view mirrors that same physical arrangement.
  One AR20 is dedicated to the ILD74 and 24-to-48 V `MOTOR_HVIN` detector. Three
  parallel 8.2 kΩ, ¼ W resistors share its detector load while one socket row
  remains empty as a guard. The ILD74's second channel independently detects
  regulated `AUX_24V` through a 1.5 kΩ resistor and 15 V zener in Socket B.
  The two output transistors form a series hardware AND. Socket A carries the
  VBUS-gated UTC LP2950L-3.3 regulator using its `1=OUT`, `2=GND`, `3=IN`
  TO-92 pinout; GPIO5 reports the resulting VIO directly as active-high
  `VIO_OK`. `LINE18_PWR_GND_A` and `LINE18_PWR_GND_B` form a joined two-post
  ground hub, with every other ground contact wired directly to one hub post.
  The artifact is not registered as active Klipper wiring. Its retained 18-pin
  external-I/O row keeps `MOTOR_HVIN` and regulated 24 V adapter auxiliary power
  separate. It includes `F1_5A_IN` and `F1_5A_OUT`; install the serviceable
  external 5 A fuse between those contacts, with no separate carrier-mounted
  fuse holder. The row uses a bottom-mounted upholder in the generated carrier:
  its long wire-wrap tails remain downward while the printed base plate itself
  has no fused underside protrusions.
- `pico_tb6600_stripboard_interface.py` and
  `pico_tb6600_stripboard_layout.py` generate the live external Y
  TB6600 interface schematic and verified stripboard assembly.
- `pico_tb6600_stripboard_interface.md` documents that interface.
- `tmc5160t_plus_power_sequencing.py` generates the standalone TMC5160T Plus
  driver-before-logic concept-review schematic. Independent HVIN and AUX24
  detectors gate Pico VBUS through Q1, and the LP2950L-3.3 provides sequenced
  VIO to the SN7407N open-collector interface. It is not active printer wiring.
- `tmc5160t_plus_84dd4cb_delta.py` generates two one-off board-rework aids for
  redesign commit `84dd4cb` relative to its first parent:
  - `rp2040plus_btt_tmc5160t_plus_y_top_discrete_84dd4cb_delta.svg` shows
    installed or replaced components with bold purple strokes and obsolete
    components as dashed purple ghosts.
  - `rp2040plus_btt_tmc5160t_plus_y_bottom_84dd4cb_delta.svg` compares wiring
    as a coordinate graph. Thick solid edges are new or changed wraps, purple
    dashed edges are obsolete wraps to remove, and dim thin edges are retained.
  The ordinary component and wiring diagrams remain unmodified references.
- `tmc5160t_plus_dual_rail_delta.py` generates the follow-up rework aids from
  baseline commit `ece0565` to the dual-rail VIO gate:
  - `rp2040plus_btt_tmc5160t_plus_y_top_discrete_dual_rail_delta.svg` highlights
    the added DZ2 at Socket B row 9 and R23 at the bottom row 10.
  - `rp2040plus_btt_tmc5160t_plus_y_bottom_dual_rail_delta.svg` shows only the
    wraps to remove and add for the independent optocoupler inputs, series
    output-transistor AND, VIO-derived GPIO5 reporting, and the two-post
    ground-star conversion.
- `diagrams/*.svg` and selected `diagrams/*.png` files are generated artifacts
  committed for review.
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

For the TMC5160T Plus review board, use
`rp2040plus_btt_tmc5160t_plus_y_top_discrete.svg` from the component side to
select and insert U1/U2, Q1, resistors, capacitors, diodes, and zener diodes.
It intentionally shows all contact dots but only compact group and orientation
labels; wire-wrap conductors are omitted. After insertion, turn the board over
and use `rp2040plus_btt_tmc5160t_plus_y_bottom.svg` for wire wrapping.

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
