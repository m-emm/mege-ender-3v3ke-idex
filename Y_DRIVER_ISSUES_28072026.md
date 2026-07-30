# Y Driver Issues — 28–29 July 2026

## Purpose

This is a lab journal for the intermittent Y-axis TMC5160T Plus communication
and power fault observed on `menderpi.local` on 28 July 2026.

The immediate goals are:

1. Preserve the exact symptoms and register values seen before disassembly.
2. Separate confirmed observations from hypotheses.
3. Define repeatable bench and printer-side tests.
4. Provide objective acceptance criteria for deciding whether a repair worked.

## Executive summary

The Y driver has an intermittent hardware or power-path fault. It is not
explained by Klipper configuration drift.

The strongest observations are:

- Klipper intermittently cannot initialize the driver:
  `Unable to write tmc spi 'stepper_y' register GLOBALSCALER`.
- Repeated reads can return exact all-ones values:
  `IOIN=0xffffffff` and `DRV_STATUS=0xffffffff`.
- In one idle burst, 17 consecutive read pairs returned `0xffffffff`; the next
  three read pairs became valid without any configuration or state change.
- The driver reported `GSTAT=0x00000005`, decoded as `reset=1` and
  `uv_cp=1 (Undervoltage!)`.
- Homing sometimes completes and sometimes ends in a Klipper shutdown.
- Reducing current from 3.0 A to 1.5 A produced a temporarily clean test window,
  but the all-ones/GSTAT fault returned while the runtime current was still
  1.5 A.
- A separate long-idle failure occurred when Y was not moving. Motor current,
  motor cable gauge, and simple 24 V PSU overload therefore cannot be the sole
  cause.

The current leading candidates are an intermittent local power path, connector,
VM/charge-pump circuit, VIO supply or power-sequencing circuit, or a faulty
driver board. A main 24 V PSU brownout remains possible but has not been
demonstrated.

Do not print with this hardware until it passes the acceptance tests below.

Update from the 29 July bench repair: removing the R19/R21 MISO network and
adding a direct MISO/logic-ground twisted pair restored stable SPI at both
500 kHz and 3 MHz. The repaired assembly then passed the 2.489 A long-leg
stress test. This is strong evidence for a defective or marginal physical MISO
and return path, but printer-side acceptance is still pending after
reinstallation.

## Hardware and software under test

- Printer host: `menderpi.local`
- Y MCU: dedicated RP2040, Klipper name `y_pico`
- Driver: BTT TMC5160T Plus
- Motor: Y-axis NEMA 23 installation
- Klipper MCU version observed:
  `v0.13.0-650-gca8230d50`
- Printer configuration SHA-256:
  `006ca0ab0cfecd2c06004548a78d3c2cf6c12a0448258f48974e8f3b8725b89f`
- The deployed and repository-generated `printer.cfg` hashes were identical.

Relevant configuration:

```ini
[stepper_y]
step_pin: y_pico:gpio0
dir_pin: !y_pico:gpio1
enable_pin: !y_pico:gpio2
microsteps: 16
rotation_distance: 60
full_steps_per_rotation: 200
step_pulse_duration: 0.000005
endstop_pin: ^!y_pico:gpio4
position_endstop: -14.800
position_min: -14.800
position_max: 296.000
homing_positive_dir: false
homing_speed: 10
second_homing_speed: 3
homing_retract_dist: 5

[tmc5160 stepper_y]
cs_pin: y_pico:gpio9
spi_software_miso_pin: y_pico:gpio8
spi_software_mosi_pin: y_pico:gpio11
spi_software_sclk_pin: y_pico:gpio10
spi_speed: 500000
interpolate: true
run_current: 3.0
sense_resistor: 0.022
stealthchop_threshold: 0
```

The SPI pins and 500 kHz rate have not drifted. The TMC5160 Y configuration was
introduced on 26 July 2026. The configured current was changed to 3.0 A later
that evening. The printer reportedly worked reliably on Monday night with this
configuration.

During an earlier degraded VIO/wiring state, 500 kHz was the only demonstrated
working rate and tests at 1 kHz, 10 kHz, and 100 kHz failed before obtaining a
usable TMC identity. After the direct twisted-pair MISO repair, both 500 kHz
and 3 MHz passed. SPI rate must therefore not be treated as the root cause or
as a substitute for fixing the physical signal and return path.

## Register reference values

### Valid values observed

Typical valid IOIN while disabled:

```text
IOIN: 30000050 drv_enn=1 sd_mode=1 version=0x30
```

Typical valid IOIN while enabled:

```text
IOIN: 30000040 sd_mode=1 version=0x30
```

Typical valid DRV_STATUS while disabled:

```text
DRV_STATUS: 80080000 cs_actual=8 stst=1
```

Typical valid DRV_STATUS while enabled:

```text
DRV_STATUS: 801f005d sg_result=93 cs_actual=31 stst=1
```

The exact `sg_result` varies and is not itself evidence of the communication
fault. A valid IOIN identity has `version=0x30`.

### Invalid values observed

Exact all-ones response:

```text
IOIN: ffffffff ... version=0xff
DRV_STATUS: ffffffff ... all status flags asserted
GSTAT: ffffffff reset=1 drv_err=1 uv_cp=1
```

Partially corrupted response seen during a failed home:

```text
DRV_STATUS: 7bbfc000
```

Klipper decoded `0x7bbfc000` as simultaneously asserting overtemperature,
short-to-ground on both phases, and open-load on both phases. That combination
is not a credible physical motor state and is treated as corrupted SPI data.

Power-related status:

```text
GSTAT: 00000005 reset=1 uv_cp=1(Undervoltage!)
GSTAT: 00000000
```

According to the TMC5160 datasheet, `uv_cp` indicates charge-pump undervoltage;
the driver is disabled while that condition is present and the flag is latched
for diagnosis.

## Chronology and live observations

### Initial condition

- The printer had reportedly worked without Y-driver faults on Monday night.
- On Tuesday morning, Y SPI/homing failures returned.
- At the beginning of diagnosis, Klipper was ready, the printer was unhomed,
  and the deployed configuration matched the repository exactly.

### First isolated Y home

Command:

```gcode
G28 Y
```

Result:

- Y physically reached the configured endstop at `Y=-14.8`.
- Klipper then shut down while checking the TMC status/phase.
- Reported status:

```text
DRV_STATUS: 7bbfc000
stealth=1 fsactive=1 cs_actual=31 stallguard=1
ot=1 s2ga=1 s2gb=1 ola=1 olb=1
```

This proved that the motion pins, direction, enable, endstop, and basic driver
operation were functional at least temporarily. The failure occurred during a
subsequent SPI status read.

### Firmware restart and host disappearance

After `FIRMWARE_RESTART`, `menderpi.local` temporarily disappeared from
Bonjour and from a LAN SSH scan. It returned only after a user power cycle.

This is recorded as an observation, not as a proven causal relationship. A
printer-side power event is possible, but a separate host/network event was not
ruled out.

### Power-cycle startup

After the host and printer were power-cycled:

- Klipper logged:

```text
TMC stepper_y failed to init:
Unable to write tmc spi 'stepper_y' register GLOBALSCALER
```

- A later initialization attempt succeeded and the printer reached `ready`.

An intermittent initialization write failure before any commanded motion is
strong evidence against a motion-profile or homing configuration problem.

### Idle SPI burst at configured 3.0 A

Twenty IOIN/DRV_STATUS pairs were requested while Y was idle.

| Samples | IOIN | DRV_STATUS | Classification |
|---:|---|---|---|
| 1–17 | `0xffffffff` | `0xffffffff` | Invalid, MISO/all-high |
| 18–20 | `0x30000050` | `0x80080000` | Valid |

The transition happened spontaneously within the same command burst. No
configuration, current, enable, or motion state changed between sample 17 and
sample 18.

This is direct evidence of an intermittent electrical condition rather than a
fixed pin mapping or SPI mode error.

### Enabled SPI burst at configured 3.0 A

Y was manually enabled briefly. Twenty IOIN/DRV_STATUS pairs were collected and
Y was immediately disabled afterward.

Result:

- 20/20 IOIN reads had valid `version=0x30`.
- 20/20 DRV_STATUS reads were plausible.
- Klipper nevertheless logged:

```text
GSTAT: 00000005 reset=1 uv_cp=1(Undervoltage!)
GSTAT: 00000000
```

The driver therefore experienced a reset/charge-pump undervoltage event even
during a window in which SPI reads appeared valid.

### Y home after recovery

A subsequent `G28 Y` completed successfully:

- Klipper remained ready.
- Y was homed at `-14.8`.
- The final read-only snapshot was valid:

```text
GSTAT: 00000000
IOIN: 30000040 sd_mode=1 version=0x30
DRV_STATUS: 811f0048 sg_result=72 cs_actual=31 stallguard=1 stst=1
```

This successful home does not contradict the fault. It confirms that the fault
is intermittent and that the system can temporarily recover.

### Later shutdown without commanded motion

Before the planned 1.5 A test could begin, Klipper had already shut down again:

```text
DRV_STATUS: ffffffff
```

Y had not been commanded to move. The runtime current was still the configured
3.0195 A, but an inactive or disabled stepper does not draw that run current.

This is important evidence that motor load is not required to trigger the
communication fault.

## Temporary 1.5 A A/B test

No persistent configuration was changed.

After `FIRMWARE_RESTART`, the runtime current was set with:

```gcode
SET_TMC_CURRENT STEPPER=stepper_y CURRENT=1.5 HOLDCURRENT=1.5
```

Klipper reported:

```text
run_current: 1.509758 A
hold_current: 1.509758 A
```

### Immediate 1.5 A results

| Test | Result |
|---|---:|
| Idle IOIN/DRV_STATUS pairs | 20/20 valid |
| Enabled IOIN/DRV_STATUS pairs | 20/20 valid |
| Y home attempts | 5/5 passed |
| `uv_cp`, reset, or all-ones during immediate burst | None |

This showed a temporarily clean operating window at 1.5 A.

### Failure while still at 1.5 A

The next command attempted to restore the configured 3.0 A runtime current.
That command never took effect. Klipper was already unable to communicate
reliably and shut down with:

```text
GSTAT: ffffffff reset=1 drv_err=1 uv_cp=1
```

The TMC object still reported approximately 1.5098 A after shutdown, proving
that the return to 3.0 A had not been applied.

Interpretation:

- Lower current may improve operating margin or merely coincide with a
  temporary recovery window.
- Lower current does not eliminate the underlying fault.
- A current/load-sensitive contribution may exist, but load is not the sole
  trigger.

After any firmware or printer restart, the unmodified configuration will load
the normal 3.0 A value again.

## Configuration and transport findings

### Configuration drift ruled out

- Remote and local `printer.cfg` SHA-256 hashes matched.
- The active pins, SPI speed, sense resistor, current, and homing settings
  matched the repository-generated configuration.
- No persistent configuration was changed during these diagnostics.
- A wrong CS/MISO/MOSI/SCLK mapping would be expected to fail consistently,
  not produce 17 all-high reads followed immediately by three correct reads.

### RP2040 USB transport did not show data corruption

During a valid diagnostic window, the `mcu y_pico` statistics included:

```text
bytes_invalid: 0
```

The host-to-RP2040 Klipper transport remained synchronized while the RP2040's
downstream TMC SPI reads alternated between invalid and valid values. This
points below the host USB protocol layer.

The printer also emitted USB bandwidth warnings associated with webcam traffic.
Those warnings were not correlated with RP2040 protocol corruption and are not
currently treated as the Y-driver root cause.

## What the evidence rules out

### Ruled out as sole causes

- Fixed Klipper pin/configuration error.
- A newly changed SPI frequency.
- Homing speed or acceleration.
- Motor motion being required to trigger the fault.
- 3.0 A motor current being required to trigger the fault.
- Motor cable gauge alone.
- Genuine simultaneous overtemperature, both-phase short, and both-phase
  open-load faults.

### Not ruled out

- Intermittent 24 V PSU output.
- High resistance or intermittent contact in the 24 V feed, fuse, connector,
  switch, or ground return.
- Local driver VM decoupling.
- TMC5160 charge-pump components or driver-board damage.
- VIO collapse or bad VIO power sequencing.
- Q1/R3 orientation, saturation, health, or associated connector/load path.
- Intermittent CS, SCLK, MOSI, MISO, or ground connection.
- A marginal condition that becomes more likely at higher current.

## Current hypothesis ranking

1. Local driver power, VIO, or power-sequencing fault.
2. Intermittent connector, ground, or 24 V feed local to the Y assembly.
3. Driver-board VM decoupling or charge-pump circuit fault.
4. TMC5160T Plus board damage.
5. Main 24 V PSU brownout or regulation fault.
6. Pure SPI signal-integrity problem without an associated power fault.
7. Klipper configuration error.

Items 1–4 are ranked above the main PSU because failures occurred during
startup and idle conditions, while the rest of the printer host remained
operational during the later tests. The main PSU still needs direct
measurement before it can be excluded.

## Tests possible with only a DMM

An oscilloscope would help capture fast transients, but the following tests
provide useful evidence with a normal multimeter.

### Measure voltage drop across the positive feed

With the driver powered and enabled:

1. Put one probe on PSU `+24 V`.
2. Put the other probe on driver `VM+`.
3. Read the voltage difference directly.

This measures cable, connector, fuse, and switch drop without subtracting two
separate measurements.

Repeat at 1.5 A and 3.0 A. A large or unstable drop implicates the positive
feed. Tens of millivolts may be normal depending on cable length and
connectors; hundreds of millivolts deserve investigation.

### Measure ground-return drop

With the driver powered and enabled:

1. Put one probe on driver ground.
2. Put the other probe on PSU ground.
3. Read the return-path voltage difference.

A large or unstable ground drop can corrupt both power and SPI signaling.

### Measure the actual rails

Record:

- 24 V at the PSU.
- VM directly at the driver.
- Driver VIO.
- RP2040-side logic supply if accessible.

Use the meter's min/max capture if available.

### Motor-disconnected isolation

1. Fully power off the printer, AUX supply, HV/VM, and USB.
2. Disconnect the motor phases.
3. Power the MCU/driver normally.
4. Repeat the idle SPI test for at least ten minutes.

If `0xffffffff` still occurs with the motor physically disconnected, the motor
and motor cable are fully ruled out.

Never connect or disconnect stepper motor phases while the driver is powered.

### Connector manipulation

Run repeated IOIN reads while gently manipulating one connector or harness at a
time. An immediate transition between `version=0x30` and `version=0xff` is
strong evidence for the manipulated path.

Do not manipulate exposed 24 V conductors in a way that can short them.

## Bench-test sequence

Use the repository's existing tools:

```text
klipper_setup/klipper_config/wiring/bench_tests/
```

Relevant entry points:

```text
run_rp2040plus_tmc5160t_plus_y_bench.sh
run_rp2040plus_tmc5160t_plus_y_motor_bench.sh
```

### Stage 0 — Visual and passive inspection

- Fully remove all power before handling the assembly.
- Photograph wiring and connector orientation before changing anything.
- Check driver seating, terminal screws, crimps, ferrules, fuses, and grounds.
- Verify Q1 orientation and part identity.
- Record the installed R3 value.
- Inspect charge-pump and VM decoupling capacitors for damage or poor joints.
- Check for flux contamination, conductive debris, or strained headers.

### Stage 1 — No HV/VM

- Run the no-HV bench test.
- Confirm the expected `PWR_OK` state.
- Confirm STEP propagation and the driver-side STEP probe state.
- Confirm no unexpected back-powering.

### Stage 2 — Driver powered, motor disconnected

- Measure PSU 24 V, driver VM, and VIO.
- Confirm `IOIN version=0x30`.
- Run at least 1,000 IOIN/DRV_STATUS read pairs.
- Leave the system powered for at least ten minutes while continuing periodic
  reads.
- Perform a careful connector wiggle test.

Any `0xff`, `0x00`, impossible DRV_STATUS combination, `uv_cp`, unexpected
reset, or SPI write failure is a failed stage.

### Stage 3 — Motor connected at 1.5 A

- Power off before connecting the motor.
- Recheck all rails after power-up.
- Run the established 1.51 A repeated-motion baseline.
- Run at least 1,000 register pairs while disabled, enabled, and moving.
- Exercise enable/disable transitions.
- Check positive-feed and ground-return voltage drops.

### Stage 4 — Motor connected at 3.0 A

Only proceed if Stages 1–3 pass completely.

- Increase current to 3.0 A.
- Repeat the same register, enable/disable, and motion tests.
- Compare cable and return-path voltage drops with the 1.5 A values.
- Monitor connector and driver temperature.

### Stage 5 — Reinstall and printer validation

- Reinstall the assembly with strain relief.
- Confirm local and deployed configuration hashes.
- Perform ten cold printer/driver power cycles.
- Run repeated idle SPI reads before motion.
- Run ten Y homes at 1.5 A.
- Run ten Y homes at 3.0 A.
- Run the existing Y repeated-motion test in increasing stress stages.
- Only resume calibration or printing after all acceptance criteria pass.

## Acceptance criteria

The repair is accepted only if all of the following are true:

- Zero TMC initialization failures over ten cold power cycles.
- Every IOIN read reports `version=0x30`.
- Zero `0xffffffff` or `0x00000000` register responses.
- Zero impossible multi-fault DRV_STATUS values.
- Zero unexpected `uv_cp`, `drv_err`, or reset flags after initialization.
- At least 1,000 valid read pairs with the driver disabled.
- At least 1,000 valid read pairs with the driver enabled.
- At least 1,000 valid read pairs during or between motion cycles.
- The ten-minute powered-idle test completes without a shutdown.
- The repeated-motion bench test passes at 1.5 A.
- The repeated-motion bench test passes at 3.0 A if 3.0 A remains the intended
  production current.
- Ten consecutive Y homes pass after reinstallation.
- No unexpected voltage drop, connector heating, or VIO collapse is observed.

A successful single home or a few valid reads is not sufficient; the present
fault has repeatedly recovered for short windows.

## Post-repair result template

Date:

Repair performed:

Installed R3:

Q1 identity/orientation:

PSU model and nominal voltage:

Motor connected during test:

| Measurement | Disabled | Enabled 1.5 A | Moving 1.5 A | Enabled 3.0 A | Moving 3.0 A |
|---|---:|---:|---:|---:|---:|
| PSU voltage | | | | | |
| Driver VM | | | | | |
| PSU+ to VM+ drop | | | | | |
| Driver GND to PSU GND drop | | | | | |
| Driver VIO | | | | | |

| Test | Result | Invalid reads | Notes |
|---|---|---:|---|
| No-HV assertions | | | |
| Motor disconnected, 1,000 SPI pairs | | | |
| Motor disconnected, ten-minute idle | | | |
| 1.5 A enabled, 1,000 SPI pairs | | | |
| 1.5 A repeated motion | | | |
| 3.0 A enabled, 1,000 SPI pairs | | | |
| 3.0 A repeated motion | | | |
| Ten cold power cycles | | | |
| Ten printer Y homes | | | |

Final disposition:

## Safety and state at the end of 28 July diagnostics

- Klipper was in shutdown after another all-ones GSTAT response.
- The attempted runtime return from 1.5 A to 3.0 A did not complete.
- No persistent configuration was changed.
- A firmware or printer restart will reload the configured 3.0 A current.
- Do not hot-plug the stepper motor.
- Remove printer power, AUX/VM power, and USB before extracting the Y MCU/driver
  assembly.

## 29 July MISO-path repair and bench validation

### Repair performed

The following physical changes were made to the return side of the TMC5160 SPI
bus:

- Removed R19, the 1 kΩ series resistor between TMC MISO and Pico GPIO8.
- Removed R21, the 47 kΩ Pico-side MISO pulldown.
- Left Socket C contacts 5/16 and 9/12 empty.
- Connected `TMC1_J1_MISO_CFG0_5` directly to `PICO_GPIO_8`.
- Added a direct ground conductor from `TMC1_J2_GND_LOGIC_8` to
  `PICO_GND_13`, which is Pico physical header pin 13.
- Twisted that new logic-ground conductor with the direct MISO conductor for
  the entire TMC-to-Pico run.
- Retained the original `TMC1_J2_GND_LOGIC_8` branch to the two-post ground
  star. The new conductor is a dedicated local high-frequency return for MISO,
  not a replacement for the power/logic ground branch.

The resulting signal pair is:

```text
TMC1 J1-5 MISO  ---------------------------  Pico GPIO8
                       twisted pair
TMC1 J2-8 logic GND  ----------------------  Pico GND, physical pin 13
```

This direct connection is nominally voltage-compatible because the adapter's
TMC VIO rail is generated by the LP2950L-3.3. The final installation should
still verify approximately 3.3 V between TMC VIO and the paired logic-ground
conductor before connecting the Pico.

### Before-repair bench reproduction

Immediately before this repair, the returned board reproduced the printer
fault on the bench with the motor disabled:

| Attempt | SPI rate | Recovery before attempt | Result |
|---|---:|---|---|
| Full stress preflight | 3 MHz | Existing powered state | `IOIN VERSION=0xff` |
| Disabled SPI retry | 3 MHz | Native Pico reset | `IOIN VERSION=0xff` |
| Conservative retry | 500 kHz | Native Pico reset | `IOIN VERSION=0xff` |
| Retry after 24 V cycle | 500 kHz | 24 V cycle plus native Pico reset | `IOIN VERSION=0xff` |

In every case, `PWR_OK` was HIGH and DIAG1 was LOW. The test aborted before
motor enable or STEP pulses. This demonstrated that the all-high SPI failure
was present on the bench, survived normal resets, occurred at 500 kHz, and did
not require motor current.

### After-repair SPI gates

The same board and test harness were rerun after the direct twisted-pair change.

At 500 kHz:

```text
IOIN=0x30000050, VERSION=0x30, DRV_ENN=HIGH/disabled
initial GSTAT=0x00000005 flags=reset,uv_cp
post-initialization GSTAT=0x00000000
DRV_STATUS=0x80180000 flags=stst
```

The startup `reset,uv_cp` latch cleared during initialization and did not recur.
All register write echoes verified.

At 3 MHz:

```text
IOIN=0x30000050, VERSION=0x30, DRV_ENN=HIGH/disabled
initial GSTAT=0x00000000
post-initialization GSTAT=0x00000000
DRV_STATUS=0x80180000 flags=stst
```

The 3 MHz disabled-driver gate completed without malformed reads or status
faults.

### After-repair maximum stress run

The maximum bench stress profile then ran with:

- Software SPI: 3 MHz.
- Requested current: 2.5 A RMS.
- Quantized current: 2.489 A RMS with the 22 mΩ sense resistor.
- Microsteps: 16.
- STEP rate: 6,400 pulses/s.
- Per group: 32,000 pulses / 10 revolutions forward over 5 seconds, then
  32,000 pulses / 10 revolutions in reverse over 5 seconds.
- Three enable groups.
- Total travel: 30 revolutions in each direction, 192,000 STEP pulses.
- Live checks during motion: 30 SPI/status samples plus initialization and
  post-group checks.

Result:

- All three groups passed.
- Every IOIN identity remained valid.
- Every in-motion GSTAT sample was `0x00000000`.
- No `0xff`, `0x00`, write failure, `uv_cp`, `drv_err`, DIAG1, PWR_OK,
  overtemperature, or short-circuit fault occurred.
- Every group returned to zero net MCU position.
- The motor was observed turning smoothly.
- Final state was ENABLE HIGH with `CHOPCONF.toff=0`.

### Interpretation and remaining acceptance work

The simultaneous changes prevent a mathematically unique attribution between
R19/R21 contact quality, MISO series impedance, and return-path geometry.
However, the failure changed from persistent at 500 kHz with the motor disabled
to clean at 3 MHz under 2.489 A motion. The physical MISO/logic-ground path is
therefore the strongest demonstrated cause.

This bench result does not yet satisfy the printer acceptance criteria. After
reinstallation, repeat cold power cycles, idle register bursts, ten Y homes,
and the printer-side repeated-motion test before resuming calibration or
printing.

## References

- `klipper_setup/klipper_config/printer.cfg.template`
- `klipper_setup/klipper_config/printer.cfg`
- `klipper_setup/klipper_config/wiring/rp2040plus_btt_tmc5160t_plus_y.yaml`
- `klipper_setup/klipper_config/wiring/bench_tests/README.md`
- `klipper_setup/klipper_config/wiring/bench_tests/TEST_LOG.md`
- TMC5160A datasheet:
  <https://www.analog.com/media/en/technical-documentation/data-sheets/tmc5160a_datasheet_rev1.17.pdf>
