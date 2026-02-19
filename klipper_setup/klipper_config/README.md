# Klipper Configuration for IDEX Ender 3V3 KE

This directory contains Klipper configuration files for the IDEX conversion of the Creality Ender 3V3 KE.

## Hardware Setup

### MCUs
- **Main Board** (`/dev/ttyACM0`): RP2040-based controller - Serial: `E6633861A3673038`
- **Toolhead** (`/dev/ttyACM1`): Nitehawk 36 - Serial: `30333938340637C1`

### Nitehawk 36 Pinout Reference

| Device/Port | PCB Label | Connector | Pin | Description |
|-------------|-----------|-----------|-----|-------------|
| E Motor | MOTOR | JST-XH2.5 4P | gpio23/24/25/0/1 | TMC2209 extruder (step/dir/ena/uart/tx) |
| Filament Sensor | - | JST-PH2.0 2P | gpio3 | Switch-based sensor |
| Probe | PRB | JST-PH2.0 3P | gpio10 | Bed leveling/Z sensing |
| X Endstop | X-STOP | JST-PH2.0 2P | gpio13 | Switch-based endstop |
| Part Fan | PCF | JST-PH2.0 2P | gpio6 | Part cooling (24V/5V selectable) |
| Hotend Fan | HEF | JST-PH2.0 3P | gpio5/16 | Fan + tacho (24V/5V selectable) |
| Neopixel | - | JST-PH2.0 3P | gpio7 | LED strip |
| Hotend Heater | HE0 | E0506 Ferrule | gpio9 | Heater cartridge |
| Thermistor | TH0 | JST-PH2.0 2P | gpio29 | 2.2kΩ pullup |
| Activity LED | ACT | Onboard | gpio8 | Active low |
| Accelerometer | - | Onboard | gpio27/18/20/19 | ADXL345 (CS/CLK/MOSI/MISO) |

### Voltage Selectors (Jumpers)
- **PCF**: Part fan voltage (24V or 5V)
- **HEF**: Hotend fan voltage (24V or 5V)  
- **Probe**: Probe voltage (24V or 5V)

## Installation

### On Raspberry Pi

```bash
# Navigate to printer_data config directory
cd ~/printer_data/config

# Pull latest config from git
cd ~/mege-ender-3v3ke-idex  # Or wherever you cloned the repo
git pull

# Copy config to Klipper config directory
cp klipper_setup/klipper_config/printer.cfg ~/printer_data/config/printer.cfg

# Restart Klipper
sudo systemctl restart klipper
```

### Quick Install Script

You can also use this one-liner:

```bash
cd ~/mege-ender-3v3ke-idex && git pull && cp klipper_setup/klipper_config/printer.cfg ~/printer_data/config/printer.cfg && sudo systemctl restart klipper
```

## Configuration Steps

### 1. Verify MCU Serial IDs

Check that your MCU serial IDs match:

```bash
ls -l /dev/serial/by-id/
```

Update the `[mcu]` and `[mcu nitehawk]` sections in `printer.cfg` if different.

### 2. Calibrate Stepper Motors

Adjust these values in `printer.cfg` for your specific hardware:
- `rotation_distance` for X, Y, Z, and extruder
- `run_current` for TMC drivers
- Endstop positions and limits

### 3. PID Tuning

Run PID autotune for hotend and bed:

```gcode
# Hotend (example for 200°C)
PID_CALIBRATE HEATER=extruder TARGET=200

# Bed (example for 60°C)
PID_CALIBRATE HEATER=heater_bed TARGET=60
```

Save results with `SAVE_CONFIG`

### 4. Probe Calibration

If using a probe:

```gcode
PROBE_CALIBRATE
```

### 5. Input Shaping (Optional)

Run resonance tests using the onboard ADXL345:

```gcode
SHAPER_CALIBRATE
```

Then uncomment and configure the `[input_shaper]` section.

## IDEX Conversion TODO

The current configuration is set up for a single toolhead. To enable IDEX mode:

1. **Add second X stepper** from main board
2. **Configure `[dual_carriage]`** section
3. **Add IDEX macros** (T0, T1, duplication mode, mirror mode)
4. **Wire second toolhead** with its own extruder/heater
5. **Tune carriage parking positions**

See comments in `printer.cfg` for dual_carriage example.

## Troubleshooting

### Klipper Won't Start

Check logs:
```bash
tail -f ~/printer_data/logs/klippy.log
```

### MCU Connection Issues

```bash
# Check which devices are connected
ls -l /dev/ttyACM*
lsusb | grep -i klipper

# Verify MCU communication
~/klipper/scripts/canbus_query.py can0  # If using CAN
```

### TMC UART Communication Failed

- Verify jumper settings on Nitehawk 36
- Check wiring of UART pins (gpio0/gpio1)
- Ensure `sense_resistor: 0.100` matches your hardware (100mΩ for Nitehawk)

## References

- [Nitehawk 36 Documentation](https://github.com/LDO-Motors/Nitehawk-36)
- [Klipper Documentation](https://www.klipper3d.org/)
- [Klipper IDEX Support](https://www.klipper3d.org/Config_Reference.html#dual_carriage)
