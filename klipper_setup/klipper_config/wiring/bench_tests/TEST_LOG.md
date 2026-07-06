# Wiring Bench Test Log

## 2026-07-01 19:49:08 CEST

Bench-tested the soldered `pico_tb6600_stripboard_interface` board with an
Adafruit FT232H, the TB6600-style stepper driver box, and a loose desk stepper.

Final bench wiring:

- `D4` -> stripboard `STEP_gpio`
- `D5` -> stripboard `DIR_gpio`
- `D6` -> stripboard `ENA_gpio`
- FT232H `GND` -> stripboard/control `GND`

Known setup:

- FT232H visible as `ftdi://ftdi:232h/1`
- Driver current set to about 1.5 A
- Driver microstep DIP setting tested at 8 microsteps
- Bench-session Y reference config: `rotation_distance: 60`
- 500 mm/s equivalent at 8 microsteps: about 13.333 kHz STEP

Results:

- STEP output works through the FT232H, transistor interface, and driver input.
- DIR output works; forward and reverse moves both worked.
- Streamed STEP at about 13.333 kHz moved the motor quietly and reliably.
- Five back-and-forth cycles at the 500 mm/s equivalent STEP rate worked.
- ENA on `D6` works.
- Verified enable polarity: `D6 low` disables the driver and frees the motor;
  `D6 high` enables the driver and restores motor holding torque.

Debug notes:

- `C8`/`C9` on this FT232H board are CBUS pins and were not usable as normal
  GPIO without EEPROM reconfiguration.
- A bad solder joint on one transistor emitter initially caused the base signal
  to appear on the emitter. Re-soldering the emitter to ground fixed the signal
  path.
- The motor initially held poorly until the driver current was raised to about
  1.5 A.

Later live-printer note: Y is on a 20T GT2 pulley with
`rotation_distance: 40` and 8 microsteps, so the 500 mm/s target is about
20 kHz STEP.

Representative commands from the successful session:

```bash
./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_stepper_jog.sh \
  --armed --mode stream --steps 5333 --rate-hz 13333.333 --direction 0

./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_stepper_jog.sh \
  --armed --mode stream --steps 5333 --rate-hz 13333.333 --direction 1

./klipper_setup/klipper_config/wiring/bench_tests/run_ft232h_gpio_sequence.sh \
  --armed --pin D6 --sequence low:8,high:8,low:8,high:8
```
