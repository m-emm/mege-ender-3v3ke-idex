# Wiring Bench Tests

Small local hardware probes for wiring experiments.

## RP2040-Plus / TMC5160T Plus Y Power Tests

This test uses native Klipper MCU commands over the Pico USB serial connection.
It covers the temporary bench-probe wiring in
`rp2040plus_btt_tmc5160t_plus_y.yaml`:

- `gpio0` drives `U1_01_1A_STEP`
- `gpio5` reads `B19_R6_VIO_OK`
- `gpio17` (physical Pico header pin 22, `PICO_GPIO_17_22`) reads the temporary
  `U1_01_1A_STEP` probe
- `gpio16` (physical Pico header pin 21, `PICO_GPIO_16_21`) reads the temporary
  `C14_R13_STEP` probe

With high-voltage power disconnected, first inspect the dry-run plan:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_rp2040plus_tmc5160t_plus_y_bench.sh
```

Then confirm HV is still off and run the assertions:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_rp2040plus_tmc5160t_plus_y_bench.sh \
  --armed
```

The armed test asserts that `PWR_OK` is LOW, toggles STEP LOW/HIGH/LOW and
asserts that the `gpio17` probe follows it, and continuously requires the
`gpio16` / `C14_R13_STEP` probe to remain LOW. STEP is restored LOW on exit.

With the intended HV inputs connected and VIO expected to be up, select the
HV-on assertions explicitly:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_rp2040plus_tmc5160t_plus_y_bench.sh \
  --hv-on --armed
```

This mode requires `PWR_OK` to remain HIGH. It toggles STEP LOW/HIGH/LOW and
requires both the `gpio17` input-side probe and the `gpio16` /
`C14_R13_STEP` output-side probe to follow it. STEP is restored LOW on exit.

The runner uses the existing bench-test `.venv` and downloads one pinned,
checksum-verified Klipper `msgproto.py` file into the repository's ignored
`.cache/` directory. The small macOS transport in the bench script is used
because Klipper's normal host serial helper contains Linux-specific code.

## Current FT232H Bench Wiring

Stepper/TB6600 bench wiring:

- `D4` -> stripboard `STEP_gpio`
- `D5` -> stripboard `DIR_gpio`
- `D6` -> stripboard `ENA_gpio`
- FT232H `GND` -> stripboard/control `GND`

Vision-light bench wiring:

- `D4` -> level-shifter clock input -> APA102 `CI`
- `D5` -> level-shifter data input -> APA102 `DI`
- FT232H `GND` -> level-shifter/APA102 common `GND`
- 5V strip power -> APA102 `5V`, with a common ground to the FT232H side

The FT232H `C8`/`C9` pins are CBUS pins on this board. The detected EEPROM
configuration has `C8=DRIVE1` and `C9=DRIVE0`, so they are fixed-function pins
and are not usable for these GPIO scripts without deliberate EEPROM
reconfiguration.

## FT232H Probe

From the IDEX repo root:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_probe.sh
```

The probe checks:

- macOS USB visibility for FTDI vendor `0x0403`, product `0x6014`
- the serial device node, usually `/dev/cu.usbserial-*`
- PyFtdi user-space access through `ftdi://ftdi:232h/1`

The script does not toggle GPIO pins or write serial bytes.

## Tiny Stepper Jog

Run a dry check:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_stepper_jog.sh
```

Then generate 25 slow STEP pulses:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_stepper_jog.sh --armed
```

Flip direction with:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_stepper_jog.sh --armed --direction 1
```

For realistic belt-axis STEP-rate bench tests, use FTDI stream mode. This
precomputes a square-wave buffer and lets the FT232H clock it out, rather than
sleeping once per edge in Python:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_stepper_jog.sh \
  --armed --mode stream --steps 16000 --rate-hz 40000 --direction 0
```

The live Y-axis config currently uses a 20T GT2 pulley,
`rotation_distance: 40`, and 8 microsteps:

```text
steps_per_mm = 200 full_steps/rev * 8 microsteps / 40 mm = 40 steps/mm
500 mm/s = 20,000 STEP pulses/s
```

At 16 microsteps the same 500 mm/s travel move needs about 40 kHz STEP; at 32
microsteps it needs about 80 kHz STEP. Stream mode is useful for
fixed-frequency bench bursts through the stripboard and driver, not for
production motion planning with acceleration.

To move roughly 200 mm equivalent in each direction at the 500 mm/s target:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_stepper_jog.sh \
  --armed --mode stream --steps 10667 --rate-hz 26666.667 --direction 0
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_stepper_jog.sh \
  --armed --mode stream --steps 10667 --rate-hz 26666.667 --direction 1
```

## GPIO Scope Wiggle

To scope one FT232H output without involving step timing, toggle the DIR test
pin `D5` for one minute:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_gpio_wiggle.sh --armed
```

Default output is a slow `2 Hz` square wave on `D5`.

## Static GPIO Level

For scope checks where you want one pin to stay still:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_gpio_set.sh --pin D4 --level high
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_gpio_set.sh --pin D4 --level low
```

## Timed GPIO Sequence

For pins where the process should stay open while you observe the hardware, use
the sequence helper. The enable test uses `D6`:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_gpio_sequence.sh \
  --armed --pin D6 --sequence low:8,high:8,low:8,high:8
```

Verified enable polarity for the tested stripboard/TB6600 setup:

```text
D6 low  = driver disabled, motor free
D6 high = driver enabled, motor holding
```

## Vision Light APA102 Pattern

For an 8-pixel APA102/DotStar vision-light strip with clock on `D4` and data
on `D5`, run a dry check:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_vision_light.sh
```

Then light the strip:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_vision_light.sh --armed
```

The default pattern is:

```text
green, red, blue, white, green, red, blue, white
```

To set all 8 LEDs to the same color:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_vision_light.sh \
  --armed --all-color green
```

Named colors are `red`, `green`, `blue`, `white`, `off`, and `black`.
`#RRGGBB` values are also accepted.

The script defaults to `--intensity 0.25` for bench power margin. Use a higher
intensity only when the 5V supply is stable:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_vision_light.sh \
  --armed --intensity 1.0
```
