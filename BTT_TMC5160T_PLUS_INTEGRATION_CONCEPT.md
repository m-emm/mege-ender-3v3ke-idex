# BTT TMC5160T Plus Y-Axis Integration Concept

Status: decision-complete integration concept. The design choices and sequencing-circuit component values are closed; physical measurements, continuity checks, component verification, and bench validation remain implementation gates. This document intentionally defines the work without implementing CAD, assembly YAML, wiring YAML, Klipper configuration, or tests.

## 1. Purpose

Replace the external TB6600-style Y-axis driver with a BIGTREETECH TMC5160T Plus controlled by a dedicated RP2040/Pico-class Klipper MCU.

The new Y-axis unit will contain:

- the TMC5160T Plus in its factory heat-sink/case assembly;
- the supplied ordinary TMC Driver Adaptor, which presents the control interface in a StepStick-like format;
- the newly flashed RP2040Plus/Pico-class USB MCU;
- a wire-wrap-friendly logic carrier and interconnect area;
- active cooling;
- protected and strain-relieved connections for USB, Y endstop, 24 V power, and the Y motor.

The existing `y_z_axis_mcu_holder_assembly` remains physically installed. It continues to control the two Z drivers, heatbed MOSFET/SSR and thermistor, and vision-light interface. Its former Y StepStick remains wired and powered as a disabled rollback path, but has no motor and no active Klipper section.

## 2. High-Level Decision

The TMC5160T Plus should be implemented as a dedicated Y-axis subsystem, not forced into the generic three-StepStick Y/Z holder.

```text
                                      dedicated Y controller housing
                                      ------------------------------
menderpi powered USB ---------------> Waveshare RP2040-Plus / y_pico
                                         |       |              |
                                         |       |              +--> physical Y endstop
                                         |       +--> GPIO5 <-------- switched-24-V power-good
                                         |
                                         +--> SN7407N open-collector buffer
                                                   |
                                  sequenced VIO pull-ups
                                                   |
                                                   +--> STEP / DIR / EN command
                                                   +--> SPI: CS / SCK / MOSI
adapter MISO / DIAG1 --> protected direct inputs --> Pico
switched 24 V --> thresholded dual optocoupler ----> GPIO5
                    |
                    +--> BC327 high-side switch on Pico USB VBUS
                              |
                              +--> 3.3 V zener shunt --> adapter VIO
                                                                       |
                                                            TMC Driver Adaptor
                                                           |
                                                  supplied 12-wire cable
                                                           |
                                                           v
switched 24 V auxiliary branch ------------------> TMC5160T Plus control + 24 V fan

fused switched 24 V motor branch ----------------> TMC5160T Plus HVIN screw terminal
TMC5160T Plus motor screw terminals --------------> Y motor phases
```

The adapter and ribbon cable carry logic and auxiliary power. High-current motor power and motor phases must use the large driver's screw terminals directly; they must not be routed through StepStick pins, the Pico carrier, or wire-wrap wiring.

## 3. Current System and Migration Boundary

### 3.1 Current Y/Z box

The current `pico_w_btt_tmc2226_y_z.yaml` and `printer.cfg.template` describe:

- active Y through an external TB6600-style interface using GPIO0/1/2 for STEP/DIR/ENABLE;
- the Y endstop on GPIO4;
- a local TMC2226 in the first driver position as a reserved Y fallback;
- TMC2226 drivers 2 and 3 as the live Z-left and Z-right drivers;
- heatbed, heatbed boost, thermistor, and vision-light functions on the same Pico.

The physical Y/Z housing is generated through the generic `board_holder_assembly.py`, configured with one Pico, three StepStick-format drivers, additional wire-wrap pins, and the heatbed MOSFET board. `y_z_axis_mcu_holder_fan_joiner.py` then replaces only the top lid/fan arrangement.

### 3.2 Final responsibility split

| Function | Existing Y/Z box after migration | New Y controller |
| --- | --- | --- |
| Z-left and Z-right motors/endstops | Remains | No |
| Heatbed MOSFET, boost, thermistor | Remains | No |
| Vision light | Remains | No |
| Old local Y StepStick | Wired and powered for rollback, disabled by its enable pull-up, no motor or active config | No |
| TB6600 interface | Retired | No |
| Y STEP/DIR/ENABLE | Removed from active old-box wiring | Yes |
| Y physical endstop | Moved from old-box Pico | Yes |
| TMC SPI and diagnostics | No | Yes |
| Y motor power and phases | No | Yes, directly at TMC5160T Plus |

Moving the physical Y endstop to the same MCU as the Y step pulses is preferred. Klipper supports multi-MCU homing, but it can add communication-dependent homing overshoot; there is no benefit to accepting that complication when the new housing already contains a dedicated Pico.

The unused StepStick in the existing box keeps its present low-current power and signal wiring for rollback. It has no active Klipper section and no motor connected. Its enable pull-up keeps it disabled. The existing wiring diagram must label it clearly as a powered-but-disabled rollback device so it is not mistaken for the active Y driver.

## 4. Confirmed TMC5160T Plus Constraints

The following are requirements from the BTT TMC5160T Plus V1.0 manual and schematic, not design guesses:

| Property | Requirement |
| --- | --- |
| Overall size | 64 x 56 x 32.55 mm with factory case/heat sink |
| Board size without case | 58 x 50 x 28 mm |
| HVIN range | 8-60 V |
| Current capability | Up to 10.6 A RMS / 15 A sine-wave peak, subject to cooling and motor limits |
| Sense resistors | 0.022 ohm |
| Control mode for Klipper | SPI |
| TMC5160 VCC_IO operating range | 3.00-5.25 V |
| Cooling | Active cooling required by BTT above 3 A |
| Fan interface | On-board always-on 24 V fan output |
| Heat sink | Factory heat sink must remain installed |
| Power sequence | Driver power before logic power |
| Adapter/control supply | Main-control-board output to the driver must not exceed 24 V |

The printer's existing 24 V supply is within the driver's HVIN range, but branch current capacity, fuse size, conductor gauge, connector ratings, and motor current still require explicit engineering checks. The driver's headline maximum is not a target current.

## 5. Adapter and Signal Concept

### 5.1 Provisional StepStick-side pin mapping

The supplied non-Plus TMC5160T Pro pinout provided for this project matches the Plus schematic's SPI signal naming. It is a useful provisional map for the ordinary TMC Driver Adaptor:

| StepStick-style pin | Provisional TMC5160T Plus meaning | Planned use |
| --- | --- | --- |
| EN | Driver enable, active-low at the TMC chip | Non-inverting open-collector output with a VIO pull-up; defaults high/disabled |
| CFG1 / MOSI | SPI MOSI | Pico SPI output |
| CFG2 / SCK | SPI clock | Pico SPI clock |
| CFG3 / CS | SPI chip select | Pico chip-select output |
| CFG0 / MISO | SPI MISO | Pico SPI input |
| CLK | External driver clock | Leave unused unless Plus adapter continuity proves otherwise |
| STEP | Step pulse | Pico step output |
| DIR | Direction | Pico direction output |
| VM | Likely adapter cable's auxiliary `24V` input | Never assume this is HVIN; verify continuity |
| GND | Control/auxiliary ground | Common logic/power reference |
| A2, A1, B2, B1 | Conventional StepStick motor-output positions | Expected not to carry Plus motor current; verify and leave unused |
| VIO | Logic voltage | Sequenced approximately 3.3 V from Pico USB VBUS through the BC327/zener branch |
| GND | Logic ground | Common logic reference |
| DIAG0 header pin | Second physical adapter diagnostic pin | Leave electrically unconnected initially; still provide a carrier pass-through hole |
| DIAG1 header pin | TMC diagnostic output | Protected direct Pico diagnostic input; not a production endstop; provide a carrier pass-through hole |

The Plus schematic shows the driver's 12-pin ordinary-control connector as:

1. DIAG1
2. CS
3. SCK
4. MOSI
5. MISO
6. EN
7. STEP
8. DIR
9. GND
10. VCC_IO
11. 24V
12. GND

Before any power is applied, the actual adapter and supplied cable must be continuity-tested pin by pin. The result, including connector orientation and pin-1 markings, becomes the source of truth for the wiring YAML. The adapter has a separate two-pin `DIAG0`/`DIAG1` through-header in addition to its J1/J2 rows; both physical pins need holes in the carrier even though only `DIAG1` is wired initially. In particular, the adapter `VM`, conventional A/B pins, `CLK`, and diagnostic routing must not be inferred solely from the older module image.

### 5.2 Driver mode and jumpers

- Configure the TMC5160T Plus mode selector for SPI.
- Record the physical jumper/selector state in the wiring diagram and build notes.
- Treat CFG0-CFG3 as SPI signals, not standalone microstep configuration, while SPI mode is selected.
- Do not depend on UART mode for this integration; Klipper's TMC5160 section is SPI-based.
- Retain the physical Y endstop for production homing.
- Wire DIAG1 through a 1 kohm series resistor to GPIO3, with a 47 kohm Pico-side pull-down, for diagnostics and later experiments. Do not configure it as the TMC virtual endstop in the initial integration.
- Sensorless homing is out of scope for the first integration.

### 5.3 Final Pico pin allocation

Use the following allocation. The carrier layout must follow it rather than reassigning pins for convenience:

| Function | RP2040 pin | Klipper/wiring role |
| --- | --- | --- |
| Y STEP | GPIO0 | Non-inverting open-collector step output |
| Y DIR | GPIO1 | Non-inverting open-collector direction output |
| Y ENABLE | GPIO2 | Non-inverting open-collector active-low enable output |
| DIAG1 | GPIO3 | Protected direct diagnostic input only |
| Y physical endstop | GPIO4 | Preserves the current logical assignment |
| Driver power-good | GPIO5 | Active-low power-valid input; power loss triggers `M112` |
| SPI MISO | GPIO8 | Protected direct hardware-SPI input |
| SPI CS | GPIO9 | Non-inverting open-collector chip select |
| SPI SCLK | GPIO10 | Non-inverting open-collector hardware-SPI clock |
| SPI MOSI | GPIO11 | Non-inverting open-collector hardware-SPI output |

Use the Waveshare board's physical pin 40, labeled `VBUS`, only as the approximately 5 V source for the sequenced VIO circuit. Do not confuse it with physical pin 39 `VSYS` or physical pin 36 `3V3(OUT)`.

Use RP2040 hardware SPI with the canonical Klipper bus name `spi1_gpio8_gpio11_gpio10` (MISO GPIO8, MOSI GPIO11, SCLK GPIO10). The older alias `spi1a` describes the same pins but is deprecated in current Klipper. Use `cs_pin: y_pico:gpio9`; do not fall back to software SPI.

### 5.4 Open-collector channel allocation and safe defaults

Use one `SN7407N` PDIP-14 on the wire-wrap carrier. Its six non-inverting open-collector channels are allocated as follows:

| U1 channel | DIP pins | Signal | Collector pull-up |
| --- | --- | --- | --- |
| 1A/1Y | 1/2 | STEP | R13 4.7 kohm to sequenced VIO |
| 2A/2Y | 3/4 | DIR | R14 4.7 kohm to sequenced VIO |
| 3A/3Y | 5/6 | ENABLE_N | R15 4.7 kohm to sequenced VIO |
| 4A/4Y | 9/8 | CS_N | R16 2.2 kohm to sequenced VIO |
| 5A/5Y | 11/10 | SCLK | R17 2.2 kohm to sequenced VIO |
| 6A/6Y | 13/12 | MOSI | R18 2.2 kohm to sequenced VIO |

Power U1 pin 14 continuously from Pico USB `VBUS` and connect pin 7 to common ground. Add `C2`, 100 nF, directly between pins 14 and 7. The SN7407's TTL-compatible inputs accept the Pico's 3.3 V high level while the open collectors tolerate the sequenced approximately 3.3 V output pull-ups.

Give all six U1 inputs a 10 kohm pull-up to Pico 3.3 V (`R7-R12`). The resulting collector outputs default high whenever VIO exists: ENABLE is disabled, CS is deselected, and SCLK is at the mode-3 idle level. STEP being high is harmless while ENABLE is disabled; DIR and MOSI have no independent effect. This common-high scheme also avoids floating TTL inputs during Pico reset.

The collector pull-ups are supplied only by `TMC_VIO_3V3`. When switched 24 V is absent, VIO is absent and U1 cannot source voltage into an unpowered driver; it can only pull a collector toward common ground. No tri-state buffer and no output-enable timing network are required. The open-collector interface adds passive rising edges, so start SPI at 500 kHz and validate SCLK, MOSI, CS, STEP, and ENABLE at the adapter with an oscilloscope before increasing speed.

MISO and DIAG1 are driver-to-Pico signals and do not pass through U1. Route them through `R19` and `R20`, 1 kohm series resistors, and fit `R21` and `R22`, 47 kohm Pico-side pull-downs. VIO itself is derived from Pico VBUS, so those driver outputs cannot be powered by this circuit when Pico USB/VBUS is absent.

## 6. Power Architecture and Safety Gate

### 6.1 Separate current paths

The housing must visibly and physically separate these paths:

1. **High-current motor power:** fused printer 24 V and ground directly to the driver's HVIN screw terminal.
2. **Motor phases:** direct from the driver's 1A/2A/1B/2B screw terminals to the Y motor cable.
3. **Auxiliary/control 24 V:** low-current 24 V through the adapter cable for the driver control circuitry and on-board fan output.
4. **Always-on USB logic:** USB-powered Pico, its 3.3 V rail, VBUS-powered `SN7407N`, physical endstop, and power-good input.
5. **Sequenced VIO:** the Pico's USB `VBUS` pin 40 through the inventory BC327 high-side switch, 39 ohm feed resistor, and inventory 3.3 V zener shunt to adapter VIO; the six driver-facing collector pull-ups are fed only from this rail.
6. **USB:** an ordinary data-and-power USB cable between `menderpi` and the dedicated Pico.

Use one dedicated, serviceable 5 A automotive or time-delay fuse in the switched 24 V driver branch. The branch conductors, terminals, ferrules, and connectors must all be rated above 5 A. Verify measured steady-state input current and power-on inrush during commissioning; change the fuse only if measurements justify it and the full conductor path remains protected.

### 6.2 Driver-before-logic power sequence

This is a hard design gate. The BTT manual requires driver power before logic power. The emergency-stop button removes the switched 24 V motor supply but leaves `menderpi` and USB powered, so the Pico intentionally remains online while the driver is electrically isolated.

The selected all-through-hole architecture is:

1. Keep the Waveshare RP2040-Plus powered normally from an unmodified USB cable. Do not use a data-only USB cable and do not power the Pico from the motor rail.
2. Apply switched 24 V directly to both HVIN and the driver's auxiliary/control 24 V input. The driver and its fan therefore lose power with the motor branch.
3. Detect valid switched 24 V with the inventory Vishay `ILD74` dual optocoupler, inventory 12 V/0.5 W zener, and one series resistor. The detector does not conduct until the 24 V rail is approximately 14 V, so HVIN is already safely above its 8 V minimum before VIO can be applied.
4. Use one inventory `BC327` PNP transistor as a high-side switch from the Pico's USB `VBUS` pin 40. The first ILD74 output pulls its base low only after switched 24 V is valid. A base-emitter pull-up makes the switch default off.
5. Feed the BC327 collector through 39 ohms into the VIO node and shunt that node with one inventory 3.3 V/0.5 W zener. The PNP saturation drop is taken from the approximately 5 V USB rail, not from the 3.3 V output; there is therefore ample headroom for a regulated approximately 3.3 V VIO.
6. Use the ILD74's second output as the active-low `PWR_OK_N` signal to GPIO5. It reports the hardware power state but does not participate in signal gating.
7. Feed every SN7407 collector pull-up from the sequenced VIO rail. Connect the ENABLE collector directly to adapter EN through its 4.7 kohm VIO pull-up. With VIO present it defaults high/disabled; with VIO absent there is no logic source capable of back-powering EN. In Klipper the direct active-low hardware path is represented by an inverted enable pin.
8. A Klipper `gcode_button` transition on GPIO5 power loss issues `M112`. Restoring 24 V does not resume motion; a deliberate `FIRMWARE_RESTART` is required.

This corrects the earlier PNP rejection. A PNP supplied from the Pico's 3.3 V rail would indeed lose unwanted headroom, but that is not the selected circuit. The RP2040-Plus exposes USB `VBUS` at physical pin 40, and the TMC5160 operational range for VCC_IO is 3.00-5.25 V. The stock 3.3 V zener branch is therefore valid when its assembled output is verified in the acceptance band below.

A second bipolar transistor plus zener as a series regulator is unnecessary and would be less predictable with only about 5 V available. The BC327, 39 ohm resistor, and zener already form a switched shunt regulator. The inventory IRF5210, BC547B, 1.8 V MCP1700, DFRobot relay, spare step-down module, and previously proposed ordered LP2950 are not used. The only semiconductor still to order for this circuit is the `SN7407N`.

### 6.3 Exact sequencing circuit and BOM

Use the following circuit. Component designators must carry through into the wiring YAML and diagrams.

#### 6.3.1 Switched-24-V detector

```text
+24V_SW -- R1 620 ohm/0.5 W -- DZ1 12 V zener -- U2A LED -- U2B LED -- GND
```

- `DZ1` is reverse-biased in normal operation: cathode toward `R1`, anode toward the optocoupler LEDs.
- U2 is the inventory Vishay `ILD74` (item 221). Link pin 2 to pin 4 so its two LEDs are in series: pin 1 is the chain anode and pin 3 is the chain cathode.
- Add `D1`, a `1N4148`, antiparallel across the complete LED chain, with anode at ILD74 pin 3 and cathode at pin 1, to limit accidental reverse LED voltage.
- At 24.0 V, the nominal detector current is approximately `(24 - 12 - 2.4) / 620 = 15.5 mA`. At a conservative 26.4 V rail it is approximately 19.4 mA. The 620 ohm resistor and zener each dissipate approximately 0.23 W at 26.4 V, within their 0.5 W ratings but deserving free air around the axial parts.
- The exact assertion voltage depends on zener knee, LED forward voltage, and optocoupler CTR. The intended approximately 14-17 V assertion/release band must be measured on the assembled circuit. It is intentionally well above the TMC5160T Plus 8 V HVIN minimum.

#### 6.3.2 BC327 VBUS high-side switch and zener regulator

```text
PICO_VBUS_5V (RP2040-Plus pin 40) -- Q1 emitter
Q1 emitter -- R2 47 kohm ----------- Q1 base
Q1 base -- R3 2.7 kohm ------------- U2A collector (pin 7)
GND -------------------------------- U2A emitter (pin 8)

Q1 collector -- R4 39 ohm/0.5 W ---- TMC_VIO_3V3 ---- adapter VIO
TMC_VIO_3V3 -- DZ2 3.3 V zener ----- GND
TMC_VIO_3V3 -- R5 2.2 kohm --------- GND
TMC_VIO_3V3 -- C1 100 nF ----------- GND
```

- Q1 is one inventory `BC327` from transistor-set item 655. It is a TO-92 PNP part rated for substantially more than this branch's approximately 60 mA worst-case current. Confirm the actual lead order with a transistor tester because the set does not identify the manufacturer.
- `R2` makes Q1 default off. When U2A conducts, `R3` permits approximately 1.3-1.6 mA of base current from a 4.75-5.25 V VBUS rail. The ILD74's 12.5% minimum CTR at 16 mA gives approximately 2 mA collector capability, so the optocoupler can pull the base low without another transistor.
- `R4` and `DZ2` are the regulator. DZ2 is reverse-biased in normal operation, with cathode at VIO and anode at ground. Use the 3.3 V/0.5 W axial part from inventory item 180, and identify it by its compartment marking and a current-limited bench test before installation.
- At nominal 5.0 V VBUS, a 0.1 V Q1 drop and 3.3 V VIO put approximately 41 mA through `R4`. Across a conservative 4.75-5.25 V VBUS range and measured 3.0-3.6 V zener range, the branch is approximately 24-56 mA. Normal `R4` dissipation remains below approximately 0.13 W and worst no-load zener dissipation below approximately 0.18 W, so the specified 0.5 W axial parts have margin.
- The official Plus schematic shows VIO feeding the TMC5160 VCC_IO pin, a 220 ohm indicator-LED branch, mode pull resistors, and decoupling. The IC itself draws only tens of microamps from VCC_IO. The expected complete adapter/driver load is below 10 mA; commissioning acceptance for the adapter alone is at most 12 mA. `R5` draws about 1.5 mA. If all six SN7407 outputs are low simultaneously, the three 4.7 kohm and three 2.2 kohm collector pull-ups add approximately 6.6 mA. The assembled non-zener VIO load must therefore remain at or below 21 mA, leaving deliberate zener current at the conservative low-supply corner.
- `C1` sits directly across adapter VIO and ground. Do not add a large output capacitor. The assembled VIO acceptance band is 3.1-3.6 V with the real adapter attached and VBUS tested at its measured minimum and maximum. If either VIO or the measured load misses those limits, do not connect the Pico signals; identify the zener and retune `R4` on the bench.
- Route MISO and DIAG1 through `R19` and `R20`, respectively, to the Pico, with `R21` and `R22` as 47 kohm Pico-side pull-downs. These preserve defined lows while the driver is off and limit transient current without materially loading the short return paths.

#### 6.3.3 Power-good and open-collector interface

```text
PICO_3V3 -- R6 4.7 kohm -- PWR_OK_N
PWR_OK_N -- U2B phototransistor collector (ILD74 pin 6)
GND      -- U2B phototransistor emitter   (ILD74 pin 5)
PWR_OK_N -------------------------------> y_pico:gpio5

PICO_VBUS_5V --------------------------> U1 SN7407N pin 14
GND -----------------------------------> U1 SN7407N pin 7
C2 100 nF between U1 pins 14 and 7

PICO_3V3 -- R7-R12 10 kohm -----------> U1 inputs 1A-6A
U1 collectors 1Y-3Y -- R13-R15 4.7 kohm -> TMC_VIO_3V3
U1 collectors 4Y-6Y -- R16-R18 2.2 kohm -> TMC_VIO_3V3
U1 collectors ------------------------> STEP, DIR, ENABLE_N, CS_N, SCLK, MOSI

adapter MISO  -- R19 1 kohm ----------> y_pico:gpio8
y_pico:gpio8 -- R21 47 kohm ----------> GND
adapter DIAG1 -- R20 1 kohm ----------> y_pico:gpio3
y_pico:gpio3 -- R22 47 kohm ----------> GND
```

- When switched 24 V becomes valid, U2A enables Q1 and establishes VIO. The signal high levels rise from that same VIO rail through the collector pull-ups; there is no separately powered driver-facing output and therefore no enable-delay race.
- When switched 24 V is removed, Q1 turns off and `R5`, the adapter, and any low collector outputs discharge VIO. U1 remains powered from USB VBUS but its outputs are open collectors, so it cannot source current into the falling or unpowered VIO rail. The former delayed-on/fast-off OE resistor-capacitor-diode network is intentionally removed.
- GPIO5 reads `PWR_OK_N` directly: low means switched 24 V valid; high means absent. It is only a reporting/emergency input—the hardware isolation does not depend on Klipper.
- The SPI collector pull-ups are 2.2 kohm rather than 4.7 kohm to reduce passive rise time. Begin with `spi_speed: 500000` and verify mode-3 SCLK and data margins at the adapter. Do not raise SPI speed until measured edges are clean under the real cable capacitance.

#### 6.3.4 Exact electronics BOM

| Ref. | Exact part/value | Source | Function |
| --- | --- | --- | --- |
| U1 | Texas Instruments `SN7407N`, PDIP-14 | Electronics distributor | Six non-inverting open-collector channels |
| U2 | Vishay `ILD74`, PDIP-8 | Inventory item 221 | Dual 24 V-valid detector output |
| Q1 | `BC327`, TO-92 PNP transistor | Inventory item 655 | USB-VBUS high-side VIO switch |
| DZ1 | 12 V, 0.5 W axial zener | Inventory item 180; identify/measure before use | Switched-24-V detector threshold |
| DZ2 | 3.3 V, 0.5 W axial zener | Inventory item 180; identify/measure before use | VIO shunt regulator |
| D1 | `1N4148` | Parts stock | Optocoupler reverse protection |
| R1 | 620 ohm, 0.5 W | Parts stock | Optocoupler/zener detector current limit |
| R2 | 47 kohm, 0.25 W | Parts stock | Q1 emitter-base default-off pull-up |
| R3 | 2.7 kohm, 0.25 W | Parts stock | Optocoupler/Q1 base-current limit |
| R4 | 39 ohm, 0.5 W | Parts stock | VIO zener-feed/current-limit resistor |
| R5 | 2.2 kohm, 0.25 W | Parts stock | VIO discharge/minimum load |
| R6 | 4.7 kohm, 0.25 W | Parts stock | `PWR_OK_N` pull-up |
| R7-R12 | Six 10 kohm, 0.25 W | Parts stock | High safe-state pulls on all six U1 inputs |
| R13-R15 | Three 4.7 kohm, 0.25 W | Parts stock | STEP, DIR, and ENABLE collector pull-ups to sequenced VIO |
| R16-R18 | Three 2.2 kohm, 0.25 W | Parts stock | CS, SCLK, and MOSI collector pull-ups to sequenced VIO |
| R19, R20 | Two 1 kohm, 0.25 W | Parts stock | MISO and DIAG1 series protection |
| R21, R22 | Two 47 kohm, 0.25 W | Parts stock | MISO and DIAG1 Pico-side pull-downs |
| C1 | 100 nF ceramic, at least 10 V | Parts stock | VIO bypass |
| C2 | 100 nF ceramic, at least 10 V | Parts stock | U1 supply decoupling at pins 14 and 7 |

The order adds exactly one semiconductor line item for this circuit: the `SN7407N`. Q1, the optocoupler, both zeners, and the ordinary passives come from inventory. No SMD mounting, relay, MOSFET, separate voltage regulator, adjustable network, logic-branch fuse, tri-state OE network, or step-down module is required; `R4` limits the VBUS branch current by construction.

### 6.4 Circuit timing and acceptance

- **Power-on:** HVIN and auxiliary 24 V rise first. The detector begins conducting only around 14-17 V; U2A then turns on Q1 and the R4/DZ2 shunt establishes VIO. The six collector pull-ups rise from that rail, with EN and CS defaulting high.
- **Power-off or emergency stop:** U2A releases Q1 and R5 plus the driver and collector loads discharge VIO while the large driver's HVIN capacitors are still charged. The always-powered SN7407 collectors cannot source the driver nets; the Pico remains enumerated over USB and reports the loss to Klipper.
- **USB reconnect or Pico reset while 24 V is present:** the 10 kohm input pulls make all U1 outputs default high whenever VIO exists, so EN remains disabled and CS deselected. If USB/VBUS is absent, this circuit cannot generate VIO.

Before Pico signals are connected to the adapter, verify detector threshold, Q1 switching, VIO voltage and current under the real adapter plus collector-pull-up load, VIO collapse, absence of signal back-powering, GPIO5 polarity, EN default state, and 500 kHz SPI rise/fall timing with a meter and oscilloscope. Bench acceptance—not calculation alone—is the final gate.

### 6.5 General electrical safeguards

- Never connect or disconnect the driver, motor, adapter, or ribbon cable while powered.
- Verify HVIN polarity and motor phase pairs before first power.
- Use a common control reference without routing motor return current through Pico ground wiring.
- Add strain relief for 24 V, motor, endstop, fan, ribbon, and USB cables.
- Guard screw terminals against loose wire-wrap wire and conductive debris.
- Keep logic/ribbon wiring away from motor-phase and HVIN wiring where the enclosure allows.
- Verify continuity from every collector pull-up to sequenced VIO before fitting U1; none of `R13-R18` may connect to Pico VBUS or Pico 3.3 V. Include U1's 5 V supply current in the USB power budget.
- Preserve access to the driver's LEDs and screw terminals for diagnosis.

## 7. Dedicated Housing Concept

### 7.1 New assembly generator

Create the dedicated generator:

`src/mege_ender_3v3ke_idex/designs/assemblies/y_axis_tmc5160t_plus_holder_assembly.py`

It should be heavily inspired by `board_holder_assembly.py` in construction language and user experience, but it should not pretend the TMC5160T Plus is another repeated DIL/StepStick board. The dedicated generator should own the fixed Y-only layout and explicitly model the large driver, actual RP2040Plus board, adapter, fan, terminals, and cable service volumes.

Mount the new module at the current external TB6600 location and reuse the existing 24 V and motor-cable approach directions. The old TB6600 outline is not a hard envelope: size the enclosure from the real components and service clearances. Use slotted M5 frame-mount flanges/eyes so the final position can be adjusted on the extrusion without redesigning the electronics layout.

Reusable ideas from the generic holder include:

- enclosing-base-plate construction from component keepouts;
- removable driver guard and service covers;
- side-wall cable openings;
- lid retention and hardware clearances;
- M5 frame-mount eyes;
- visualization-only electronics and hardware;
- PETG-CF production layout and a TPU wire-wrap cover/cable-grommet plate.

The first implementation should copy or reuse established local patterns narrowly. It should not begin with a broad refactor of the mature generic holder.

### 7.2 Component models

The housing layout should be based on real component geometry:
- import or wrap BTT's official TMC5160T Plus STEP model for visualization and keepouts;
- import or wrap BTT's official ordinary TMC Driver Adaptor STEP model;
- model the actual supplied RP2040Plus USB-C board, not the existing Pico W micro-USB approximation, after measuring board outline, connector, buttons, headers, and underside components;
- model the supplied 12-wire connector and minimum bend/service envelope;
- measure the physical driver's mounting holes and terminal/tool clearances even when an official STEP is used.

Official models are useful references, but physical dimensions from the received parts remain authoritative for print clearances.

### 7.3 Proposed internal layout

The enclosure should have two functional zones:

- **driver/airflow zone:** the TMC5160T Plus is the dominant component, mounted by its four board/case holes with the factory heat sink facing the airflow and the HVIN/motor terminals at an enclosure edge;
- **logic/wire-wrap zone:** the RP2040Plus, ordinary adapter, `SN7407N`, sequencing components, and wire-wrap field sit away from the motor terminals with clear access to USB-C, BOOT/RESET, the adapter cable latch, and underside wrap pins. Reserve upright through-hole positions for the BC327, two axial zeners, and the 39 ohm/0.5 W resistor, with short VBUS/VIO wiring and meter access to the VIO test point.

Build the low-voltage electronics carrier the same way as the existing Y/Z holder: a removable carrier board with wire-wrap-pin slits and a removable TPU underside/pin cover. The carrier must lift out without disturbing HVIN or motor-phase terminals.

The driver should not be buried under the Pico carrier or an opaque unventilated lid. Keep the large BTT assembly visually identifiable through a guarded ventilated opening. The rigid guard must prevent fingers, dropped fasteners, and loose wrap wire from reaching live terminals while leaving the driver LEDs, heat sink, and terminal screws serviceable.

### 7.4 Cooling

Active cooling is part of the baseline design, not a later option, because the intended NEMA23 application may exceed BTT's 3 A passive-cooling threshold.

Use one existing Creality-style 4010 radial part-cooling blower represented by the local `single_part_fan_assembly` dimensions (approximately 40.2 x 40.2 x 10.5 mm). It is quieter than the small axial fans and must run whenever switched 24 V is present. Power it from the TMC5160T Plus always-on 24 V fan output after verifying the fan nameplate voltage, polarity, current, and connector pinout.

The housing needs:

- a removable duct from the blower outlet across the length of the integrated heat sink/MOSFET area;
- a real inlet-to-outlet path rather than adjacent holes that recirculate air;
- a guarded exhaust on the opposite side of the driver;
- fan replacement without removing high-current wiring;
- a guard and finger-safe spacing;
- enough exhaust area that the printed shell is not the dominant restriction.

The physical blower and driver's fan-header capability remain measurement/continuity checks, not open design choices. Thermal acceptance is based on sustained Y motion with no TMC overtemperature warning or shutdown, not merely on whether the fan spins.

### 7.5 Service and cable access

The CAD must reserve access volumes for:

- screwdriver access to HVIN and four motor terminal screws;
- wire entry, ferrules, and bend radius at both terminal blocks;
- USB-C plug shell and cable strain relief;
- Y endstop connector;
- adapter ribbon connector and latch/removal direction;
- mode jumpers and diagnostic LEDs;
- fan connector;
- BOOT and RESET buttons on the actual RP2040Plus.

The enclosure should be removable from the printer frame as a wired module where practical. External openings and connectors should be labeled in the model or assembly documentation.

### 7.6 Expected printable parts

The assembly should produce:

- a PETG-CF structural base/body with M5 mounting flanges, zone divider, terminal guards, and cable-strain-relief features;
- a removable PETG-CF ventilated driver guard, blower mount, and airflow duct;
- a removable low-voltage carrier using the established board/slit construction;
- a TPU wire-wrap pin cover plus any required cable grommets;
- non-production visualization parts for driver, Pico, adapter, fan, connectors, screws, and nuts.

The assembly should produce a normal visualization target and explicit production plates, following the current PETG-CF electronics-housing conventions.

## 8. Wiring Diagram Work

The standalone generated concept-review schematic is `klipper_setup/klipper_config/wiring/diagrams/tmc5160t_plus_power_sequencing.svg` (with a PNG companion). It documents the detector, VIO shunt regulator, `PWR_OK_N`, all six open-collector channels, and the protected MISO/DIAG1 returns. It is not active printer wiring and must not be treated as a construction release before the Section 6.4 bench checks pass.

Create the new active wiring source:

`klipper_setup/klipper_config/wiring/rp2040plus_btt_tmc5160t_plus_y.yaml`

It should generate top and underside diagrams suitable for actual wire wrapping. It must show:

- both Pico header rows with physical pin numbers;
- the ordinary adapter's two StepStick rows and its separate two-pin `DIAG0`/`DIAG1` through-header, including the electrically unused but physically present `DIAG0` pin;
- the 12-pin adapter-to-driver connector at both ends, including pin 1;
- the `SN7407N` PDIP pinout, 100 nF decoupling, all six open-collector channel directions, input safe-state pulls, and VIO-side collector pull-ups;
- the exact ILD74, BC327, 12 V detector zener, 3.3 V VIO shunt zener, and power-good network from Section 6.3;
- SPI, STEP, DIR, direct active-low ENABLE, switched VIO, grounds, auxiliary 24 V, DIAG1, and GPIO5 power-good;
- Y endstop connector;
- direct switched-HVIN branch, dedicated 5 A fuse, and ground;
- direct motor phase connections;
- fan connection;
- explicit N/C markings for unused adapter pins;
- wire colors, wire gauges/classes, and high-current versus logic distinction;
- the selected power-sequencing/gating circuit.

The new wiring YAML must be added to the active SVG generator and wiring validator. The existing Y/Z wiring YAML and diagrams must be revised so that they no longer claim ownership of active Y STEP/DIR/ENABLE/endstop pins or a live TB6600 interface. They should continue to show the old local Y StepStick wiring, but label it powered, motor-disconnected, config-disabled, and reserved for rollback. Tests should check source/generated consistency and required net coverage, not freeze tunable current values.

A separate continuity checklist should be derived from the final netlist for bench use. Every adapter and ribbon-cable conductor should be checked before installing either board.

## 9. Klipper Configuration Concept

### 9.1 Dedicated MCU

The dedicated Y controller is the Waveshare RP2040-Plus 4 MB board flashed immediately before this design work. Name it:

`[mcu y_pico]`

Its expected Linux serial path is:

`/dev/serial/by-id/usb-Klipper_rp2040_DE62A87557907227-if00`

The board serial is `DE62A87557907227`. It already has the generic RP2040 Klipper application and Katapult bootloader matching the current `x_pico` firmware generation. No firmware rebuild is expected for the first integration. Confirm the by-id path when it is physically connected to `menderpi`; the currently connected MCUs do not yet expose this serial there.

### 9.2 Y stepper section

The active `[stepper_y]` section should move STEP, DIR, ENABLE, and the physical endstop to `y_pico:` pins. Use GPIO0 STEP, inverted GPIO1 DIR to preserve current direction, inverted GPIO2 ENABLE for the non-inverting open-collector active-low path, and active-low GPIO4 for the physical endstop. Preserve the calibrated Y geometry and travel policy:

- `rotation_distance: 40` unless a mechanical measurement changes it;
- `full_steps_per_rotation: 200` for the current motor, subject to motor verification;
- the existing calibrated endstop position and 296 mm Klipper travel limit;
- existing homing direction and conservative homing speeds.

Use `microsteps: 16` and `interpolate: False`. Do not copy the TB6600-specific `step_pulse_duration: 0.000005`; use Klipper's normal TMC step timing. The RP2040 has ample step-rate headroom at 16 microsteps for the current Y speed policy, while disabling interpolation avoids its small systematic position delay.

### 9.3 TMC5160 section

Add `[tmc5160 stepper_y]` using SPI. The section will require at least:

- `cs_pin: y_pico:gpio9`;
- `spi_bus: spi1_gpio8_gpio11_gpio10`;
- `spi_speed: 500000` for initial passive-rise-time margin;
- `run_current: 2.0` for first motion;
- `sense_resistor: 0.022` as required by BTT;
- no `diag1_pin` in the initial TMC section because the physical endstop remains authoritative.

The installed 76 mm NEMA23 motor is rated 4.2 A/phase. Because Klipper expresses TMC current as RMS, do not treat the nameplate number as `run_current: 4.2`. Start at 2.0 A RMS and increase only in 0.25 A steps when motion testing demonstrates a need. Unless the exact motor datasheet explicitly states that 4.2 A is already an RMS rating, use 2.9 A RMS as the commissioning ceiling (`4.2 / sqrt(2)` is approximately 2.97 A RMS, with a small margin retained). Any higher ceiling requires a motor-datasheet decision and a renewed thermal/current review.

Start in spreadCycle mode by leaving `stealthchop_threshold` at its Klipper default of zero or stating zero explicitly. This favors torque and positional accuracy for the large Y axis. Do not copy BTT's generic manual example of `stealthchop_threshold: 999999` without a specific decision to trade accuracy/torque behavior for noise.

Do not add `hold_current` initially. Klipper recommends omitting it unless there is a demonstrated reason. Avoid custom `driver_*` register overrides, CoolStep, and sensorless homing in the initial configuration; establish reliable SPI, motion, current, endstop homing, and cooling first.

### 9.4 Power-loss interlock and DIAG status

Expose the active-low 24 V power-good signal on GPIO5 as a `gcode_button`. Its normal powered state is asserted; its release transition runs `M112` after a 20 ms debounce. Hardware isolation acts independently and immediately, while `M112` prevents automatic re-energization when 24 V returns. Recovery requires a deliberate `FIRMWARE_RESTART` after power and wiring are safe.

Expose the protected direct DIAG1 input on GPIO3 for status/diagnostic reporting only. Do not use `tmc5160_stepper_y:virtual_endstop`, do not change the physical `stepper_y.endstop_pin`, and do not add StallGuard sensitivity tuning to the production configuration.

### 9.5 Configuration source and validation

`printer.cfg.template` plus `calib.yaml` remain the configuration sources of truth, with `printer.cfg` regenerated by `generate_printer_cfg.py`. The implementation should update:

- MCU declarations and Y/TMC sections in `printer.cfg.template`;
- generated `printer.cfg`;
- active wiring-file registration in `wiring/validate_wiring.py`;
- generated wiring SVG registration;
- wiring consistency and Klipper configuration tests;
- comments and diagnostics that currently describe TB6600 or TMC2226 rollback behavior.

The implementation should preserve the existing calibration split between the printable Y limit and Klipper travel limit. Driver integration must not silently change the machine envelope or slicer policy.

## 10. Bring-Up and Commissioning Plan

The later implementation should be commissioned in controlled stages:

1. **Mechanical inspection:** verify fasteners, terminal access, fan clearance, cable retention, and no contact between printed parts and hot/current-carrying components.
2. **Unpowered continuity:** verify adapter orientation, all 12 ribbon conductors, grounds, no short between HVIN and logic rails, motor phase pairs, and N/C pins.
3. **Power-sequence test:** with the motor and adapter initially disconnected, verify the approximately 14-17 V detector threshold, BC327 default-off/turn-on behavior, 3.1-3.6 V shunt output, EN high/disabled default, and GPIO5 state. Then repeat with the adapter connected and `menderpi` USB continuously powered. Confirm adapter-only VIO load is at most 12 mA, total worst-case VIO load is at most 21 mA, and no VIO or signal back-powering exists while switched 24 V is off.
4. **MCU connection:** confirm the `y_pico` USB by-id path and Katapult recovery path.
5. **SPI-only test:** at `spi_speed: 500000`, confirm Klipper can read the TMC5160 registers using `DUMP_TMC STEPPER=stepper_y` and scope CS, SCLK, MOSI, and MISO at the adapter; resolve edge-quality, reset, undervoltage, or SPI errors before enabling motion.
6. **Emergency-stop test:** from Klipper ready and from an enabled-but-stationary motor state, remove switched 24 V. Confirm immediate hardware isolation, `M112`, no motor re-energization when 24 V returns, and required `FIRMWARE_RESTART` recovery.
7. **Low-current motor test:** connect the Y motor at 2.0 A RMS with reduced velocity/acceleration, and verify direction and phase wiring.
8. **Endstop/homing test:** query the physical Y endstop first, then home slowly with adequate mechanical margin.
9. **Thermal test:** run sustained representative Y motion with the blower active and monitor TMC warnings, shutdowns, motor temperature, connectors, and enclosure temperature.
10. **Motion restoration:** increase current only in 0.25 A RMS steps, never above the documented 2.9 A RMS provisional ceiling, and restore speed/acceleration incrementally only after reliable low-stress operation.
11. **Production validation:** run repeatability/step-loss checks and a controlled print before removing the TB6600 hardware from service.

No test step should require a person to touch the motor or driver to decide whether it is safe. Use measured temperatures where thermal limits matter.

## 11. Work Packages

### Package A - Measurements and circuit validation

- Measure and model the confirmed Waveshare RP2040-Plus 4 MB board and document its USB/power circuit.
- Measure the received driver, adapter, cable, connectors, fan holes, and mounting holes.
- Record the exact Y motor model/datasheet and phase pairs; retain 2.0 A RMS start and the 2.9 A RMS provisional ceiling unless the datasheet proves a different RMS interpretation.
- Confirm printer 24 V supply headroom and verify the selected 5 A branch fuse and conductor ratings.
- Continuity-map the actual adapter and cable.
- Verify the Section 6.3 component identities and values against the actual inventory parts, then bench-measure detector threshold, BC327 switching, VBUS range, loaded VIO voltage/current, VIO discharge, absence of back-powering, open-collector edge timing, and safe-state bias networks.

Exit criterion: no unresolved pin, power-domain, or sequencing assumption remains.

### Package B - Electronics reference assemblies

- Add non-production component models for the driver, adapter, actual RP2040Plus, fan, and connectors.
- Prefer BTT official STEP geometry for the driver and adapter, checked against physical parts.
- Define named faces/parts/keepouts needed by the housing generator.

Exit criterion: component visualization and measured keepouts agree with the received hardware.

### Package C - Dedicated housing CAD

- Implement the Y-specific assembly generator and manifest.
- Register parameters and assembly in `assemblies.yaml`/`idex_parameters.yaml`.
- Add frame mounting, lids, ventilation, terminal access, and cable retention.
- Add production plates and process routing.

Exit criterion: visualization shows all components and service envelopes without collisions; test prints fit the real parts.

### Package D - Wiring source and diagrams

- Implement the new Y-controller wiring YAML.
- Revise the existing Y/Z wiring source to decommission Y.
- Generate and review top/bottom SVG diagrams.
- Add continuity and assembly checklists.

Exit criterion: every active Klipper pin and every physical conductor has one unambiguous endpoint and power class.

### Package E - Klipper configuration

- Add `y_pico`, move Y pins/endstop, and add the TMC5160 SPI section.
- Regenerate config and align wiring validation/tests.
- Remove the active TB6600 path while retaining accurate powered-but-disabled local-StepStick rollback documentation.

Exit criterion: local generation/wiring checks pass and Klipper reads the driver registers without errors.

### Package F - Bench and printer commissioning

- Execute the staged bring-up plan.
- Tune current and verify cooling.
- Restore motion limits deliberately and verify repeatability.
- Deploy only after bench results are recorded.

Exit criterion: reliable homing/motion at the intended operating envelope with no step loss, TMC fault, connector heating, or cooling problem.

## 12. Likely Future Files

Use the following file/component split during implementation:

```text
src/mege_ender_3v3ke_idex/designs/assemblies/
  y_axis_tmc5160t_plus_holder_assembly.py
  tmc5160t_plus_assembly.py
  tmc5160t_plus_driver_adaptor_assembly.py
  rp2040plus_board_assembly.py

assembling/assemblies/
  y_axis_tmc5160t_plus_holder_assembly.yaml
  tmc5160t_plus_assembly.yaml
  tmc5160t_plus_driver_adaptor_assembly.yaml
  rp2040plus_board_assembly.yaml
  assemblies.yaml
  idex_parameters.yaml

klipper_setup/klipper_config/
  printer.cfg.template
  printer.cfg
  wiring/rp2040plus_btt_tmc5160t_plus_y.yaml
  wiring/pico_w_btt_tmc2226_y_z.yaml
  wiring/validate_wiring.py
  wiring/generate_wiring_svgs.sh
  wiring/diagrams/...

tests/
  housing/component/manifest tests
  Klipper configuration consistency tests
  wiring source/generated-diagram consistency tests
```

Use the component-model split listed above to keep the Y housing generator readable. Do not introduce additional generic abstractions unless implementation reveals a concrete reuse case.

## 13. Closed Review Decisions

All architecture questions are closed:

1. The flashed MCU with serial `DE62A87557907227` is the dedicated `y_pico`.
2. The MCU is a Waveshare RP2040-Plus 4 MB USB-C board; its physical measurements and underside keepouts will be taken from the received board.
3. The 76 mm NEMA23 is rated 4.2 A/phase. Start at 2.0 A RMS, tune in 0.25 A increments, and use 2.9 A RMS as the provisional ceiling unless the exact datasheet explicitly defines 4.2 A as RMS.
4. The housing replaces the TB6600 at its current frame location, reuses the existing power/motor cable directions, and may exceed the old TB6600 outline. Slotted M5 mounts provide adjustment.
5. Cooling uses one always-on 24 V Creality-style 4010 radial part blower with a duct across the heat sink and a guarded opposite-side exhaust.
6. The old local Y StepStick remains wired and powered for rollback, but disabled, motor-disconnected, and absent from active Klipper configuration.
7. The Pico remains powered by ordinary USB. The inventory ILD74 and 12 V zener detect switched 24 V; one ILD74 output directly controls an inventory BC327 high-side switch from RP2040-Plus VBUS pin 40; and a 39 ohm resistor plus inventory 3.3 V zener generate adapter VIO. One VBUS-powered `SN7407N` converts the six Pico outputs to non-inverting open collectors whose pull-ups are supplied only by sequenced VIO. This prevents an always-powered Pico output from sourcing an unpowered driver without a tri-state OE network. ENABLE defaults high/disabled, and power loss also triggers `M112`.
8. MISO and DIAG1 use 1 kohm series protection and 47 kohm Pico-side pull-downs; DIAG1 remains diagnostic-only on GPIO3. Production homing remains on the physical GPIO4 endstop.
9. The BTT driver remains visible and serviceable through a guarded ventilated opening.
10. Hardware SPI is fixed to `spi1_gpio8_gpio11_gpio10`; software SPI is not a fallback.
11. The low-voltage electronics use one removable Y/Z-style carrier board with wire-wrap slits and a TPU pin cover.

Remaining measurements, continuity checks, component identification, fit checks, and bench tests are implementation work with explicit acceptance criteria above; they are not unresolved architecture decisions.

## 14. References

- [BIGTREETECH TMC5160T Plus V1.0 User Manual](https://github.com/bigtreetech/BIGTREETECH-Stepper-Motor-Driver/blob/master/TMC5160T%20Plus/BIGTREETECH%20TMC5160T%20Plus%20User%20Manual.pdf)
- [BIGTREETECH TMC5160T Plus official 3D resources](https://github.com/bigtreetech/BIGTREETECH-Stepper-Motor-Driver/tree/master/TMC5160T%20Plus/3D)
- [BIGTREETECH TMC5160T Plus official hardware resources](https://github.com/bigtreetech/BIGTREETECH-Stepper-Motor-Driver/tree/master/TMC5160T%20Plus/Hardware)
- [BIGTREETECH TMC5160T Plus V1.0 schematic](https://github.com/bigtreetech/BIGTREETECH-Stepper-Motor-Driver/blob/master/TMC5160T%20Plus/Hardware/BIGTREETECH%20TMC5160T%20Plus%20V1.0-SCH.pdf)
- [Waveshare RP2040-Plus board, pinout, and dimensions](https://docs.waveshare.com/RP2040-Plus)
- [Texas Instruments SN7407 hex buffers/drivers datasheet](https://www.ti.com/lit/ds/symlink/sn7407.pdf)
- [Vishay ILD74 datasheet](https://www.mouser.com/datasheet/2/427/ild74-1767408.pdf)
- [onsemi BC327 datasheet](https://www.onsemi.com/pdf/datasheet/bc327-d.pdf)
- [Analog Devices TMC5160A datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/tmc5160a_datasheet_rev1.18.pdf)
- [Klipper TMC5160 configuration reference](https://www.klipper3d.org/Config_Reference.html#tmc5160)
- [Klipper TMC driver guidance](https://www.klipper3d.org/TMC_Drivers.html)
- [Klipper RP2040 hardware-SPI bus definitions](https://github.com/Klipper3d/klipper/blob/master/src/rp2040/spi.c)
- [Klipper multiple-MCU homing considerations](https://www.klipper3d.org/Multi_MCU_Homing.html)
- Existing generic housing reference: `src/mege_ender_3v3ke_idex/designs/assemblies/board_holder_assembly.py`
- Existing Y/Z fan joiner: `src/mege_ender_3v3ke_idex/designs/assemblies/y_z_axis_mcu_holder_fan_joiner.py`
- Existing active Y/Z wiring source: `klipper_setup/klipper_config/wiring/pico_w_btt_tmc2226_y_z.yaml`
