# Interactive Eddy tap measurement helper.
#
# Copyright (C) 2026 Markus Emmenegger
# This file may be distributed under the terms of the GNU GPLv3 license.

import statistics


COMPARISON_XY_TOLERANCE = 0.020
DEFAULT_RAW_DURATION = 0.200


class RawEddySamples:
    """Collect native LDC batches without changing their calibration path."""

    def __init__(self):
        self.samples = []
        self.closed = False

    def __call__(self, message):
        if self.closed:
            return False
        for sample in message.get("data", []):
            if len(sample) >= 3:
                self.samples.append(
                    (float(sample[0]), float(sample[1]), float(sample[2]))
                )
        return True

    def close(self):
        self.closed = True


class EddyTapMeasure:
    """Run repeated Eddy tap probes at the canonical bed reference point."""

    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.reference_x = config.getfloat("reference_x")
        self.reference_y = config.getfloat("reference_y")
        self.move_z = config.getfloat("move_z", 5.0, above=0.0)
        self.move_speed = config.getfloat("move_speed", 20.0, above=0.0)
        probe_config = config.getsection("probe_eddy_current btt_eddy")
        self.tap_threshold = probe_config.getfloat("tap_threshold", 0.0, minval=0.0)
        self.default_count = config.getint("default_count", 7, minval=1)
        self.default_scan_nozzle_zs = config.get("scan_nozzle_zs", "3,2,1,0.5")
        self.last_raw_measurement = None
        self.last_scan_height_test = None
        self.gcode.register_command(
            "_EDDY_TAP_MEASURE",
            self.cmd_EDDY_TAP_MEASURE,
            desc="Measure repeated Eddy tap contacts at the canonical reference.",
        )
        self.gcode.register_command(
            "_EDDY_RAW_MEASURE",
            self.cmd_EDDY_RAW_MEASURE,
            desc="Report native Eddy frequency and built-in conversion at one point.",
        )
        self.gcode.register_command(
            "_EDDY_SCAN_HEIGHT_TEST",
            self.cmd_EDDY_SCAN_HEIGHT_TEST,
            desc="Verify stationary Eddy scan conversion across nozzle heights.",
        )

    def get_status(self, eventtime):
        return {
            "reference_x": self.reference_x,
            "reference_y": self.reference_y,
            "tap_threshold": self.tap_threshold,
            "default_count": self.default_count,
            "default_scan_nozzle_zs": self.default_scan_nozzle_zs,
            "last_raw_measurement": self.last_raw_measurement,
            "last_scan_height_test": self.last_scan_height_test,
        }

    def _require_homed(self, command_name):
        toolhead = self.printer.lookup_object("toolhead")
        homed_axes = toolhead.get_status(self.printer.get_reactor().monotonic()).get(
            "homed_axes", ""
        )
        if not all(axis in homed_axes for axis in "xyz"):
            raise self.gcode.error(
                "%s requires XYZ homing; homed_axes=%s" % (command_name, homed_axes)
            )
        return toolhead

    def _require_t0_and_clear_mesh(self, command_name):
        eventtime = self.printer.get_reactor().monotonic()
        try:
            tool_state = self.printer.lookup_object("idex_manual_tuning")
        except Exception as exc:
            raise self.gcode.error(
                "%s cannot read the active IDEX tool" % command_name
            ) from exc
        active_tool = tool_state.get_status(eventtime).get("active_tool")
        if active_tool != 0:
            raise self.gcode.error(
                "%s requires T0; active tool is %s" % (command_name, active_tool)
            )
        try:
            bed_mesh = self.printer.lookup_object("bed_mesh")
        except Exception as exc:
            raise self.gcode.error(
                "%s cannot read bed mesh state" % command_name
            ) from exc
        mesh_status = bed_mesh.get_status(eventtime)
        mesh_matrix = mesh_status.get("mesh_matrix", [])
        if mesh_status.get("profile_name") or any(mesh_matrix):
            raise self.gcode.error(
                "%s requires no active bed mesh; run BED_MESH_CLEAR first"
                % command_name
            )

    def _require_scan_ready(self, command_name):
        toolhead = self._require_homed(command_name)
        self._require_t0_and_clear_mesh(command_name)
        return toolhead

    def _move_to_reference(self, toolhead, x, y):
        self.gcode.run_script_from_command(
            "G90\nG1 X%.3f Y%.3f Z%.3f F%.0f"
            % (
                x,
                y,
                self.move_z,
                self.move_speed * 60.0,
            )
        )
        toolhead.wait_moves()

    @staticmethod
    def _axis_value(value, axis_index, axis_name):
        if isinstance(value, dict):
            return float(value[axis_name])
        axis_value = getattr(value, axis_name, None)
        if axis_value is not None:
            return float(axis_value)
        return float(value[axis_index])

    def _coil_over_target_pose(self, toolhead, probe, x, y):
        offsets = probe.get_offsets()
        nozzle_x = x - float(offsets[0])
        nozzle_y = y - float(offsets[1])
        status = toolhead.get_status(self.printer.get_reactor().monotonic())
        axis_minimum = status.get("axis_minimum")
        axis_maximum = status.get("axis_maximum")
        if axis_minimum is None or axis_maximum is None:
            return None, (nozzle_x, nozzle_y), None
        bounds = (
            self._axis_value(axis_minimum, 0, "x"),
            self._axis_value(axis_maximum, 0, "x"),
            self._axis_value(axis_minimum, 1, "y"),
            self._axis_value(axis_maximum, 1, "y"),
        )
        if not (
            bounds[0] <= nozzle_x <= bounds[1] and bounds[2] <= nozzle_y <= bounds[3]
        ):
            return None, (nozzle_x, nozzle_y), bounds
        return (nozzle_x, nozzle_y), (nozzle_x, nozzle_y), bounds

    def _move_to_coil_target(self, toolhead, nozzle_x, nozzle_y):
        self.gcode.run_script_from_command(
            "G90\nG1 Z%.3f F%.0f\nG1 X%.3f Y%.3f F%.0f"
            % (
                self.move_z,
                self.move_speed * 60.0,
                nozzle_x,
                nozzle_y,
                self.move_speed * 60.0,
            )
        )
        toolhead.wait_moves()

    def _move_to_scan_target(self, toolhead, nozzle_x, nozzle_y, nozzle_z):
        self.gcode.run_script_from_command(
            "G90\nG1 Z%.3f F%.0f\nG1 X%.3f Y%.3f F%.0f\n"
            "G1 Z%.3f F%.0f"
            % (
                self.move_z,
                self.move_speed * 60.0,
                nozzle_x,
                nozzle_y,
                self.move_speed * 60.0,
                nozzle_z,
                self.move_speed * 60.0,
            )
        )
        toolhead.wait_moves()

    def _require_nozzle_z_in_limits(self, toolhead, nozzle_z, command_name):
        status = toolhead.get_status(self.printer.get_reactor().monotonic())
        axis_minimum = status.get("axis_minimum")
        axis_maximum = status.get("axis_maximum")
        if axis_minimum is None or axis_maximum is None:
            raise self.gcode.error("%s cannot determine Z motion limits" % command_name)
        z_min = self._axis_value(axis_minimum, 2, "z")
        z_max = self._axis_value(axis_maximum, 2, "z")
        if not z_min <= nozzle_z <= z_max:
            raise self.gcode.error(
                "%s nozzle Z %.3f is outside limits [%.3f, %.3f]"
                % (command_name, nozzle_z, z_min, z_max)
            )

    def _lift_to_safe_z(self, toolhead):
        self.gcode.run_script_from_command(
            "G90\nG1 Z%.3f F%.0f" % (self.move_z, self.move_speed * 60.0)
        )
        toolhead.wait_moves()

    def _temperature(self):
        try:
            temperature_probe = self.printer.lookup_object("temperature_probe btt_eddy")
        except Exception:
            return None
        status = temperature_probe.get_status(self.printer.get_reactor().monotonic())
        value = status.get("temperature")
        return None if value is None else float(value)

    @staticmethod
    def _probe_position(status):
        position = status.get("last_probe_position")
        if position is None or len(position) < 3:
            raise ValueError("probe did not report last_probe_position")
        return float(position[0]), float(position[1]), float(position[2])

    def _eddy_sensor(self):
        try:
            return self.printer.lookup_object("probe_eddy_current btt_eddy")
        except Exception as exc:
            raise self.gcode.error("Eddy probe object is unavailable") from exc

    def _capture_raw_measurement(self, toolhead, duration):
        eddy_sensor = self._eddy_sensor()
        collector = RawEddySamples()
        eddy_sensor.add_client(collector)
        try:
            toolhead.dwell(duration)
            toolhead.wait_moves()
        finally:
            collector.close()
        if not collector.samples:
            raise self.gcode.error("EDDY raw measurement received no sensor samples")
        frequencies = [sample[1] for sample in collector.samples]
        stream_heights = [sample[2] for sample in collector.samples]
        raw_frequency = statistics.median(frequencies)
        sensor_height = float(eddy_sensor.calibration.freq_to_height(raw_frequency))
        toolhead_position = [float(value) for value in toolhead.get_position()]
        toolhead_z = toolhead_position[2]
        return {
            "sample_count": len(collector.samples),
            "raw_frequency_hz": raw_frequency,
            "raw_frequency_span_hz": max(frequencies) - min(frequencies),
            "stream_height": statistics.median(stream_heights),
            "built_in_sensor_height": sensor_height,
            "toolhead_z": toolhead_z,
            "toolhead_position": toolhead_position,
            "implied_bed_z": toolhead_z - sensor_height,
            "temperature": self._temperature(),
        }

    @staticmethod
    def _parse_nozzle_zs(value, gcmd):
        try:
            values = tuple(float(part.strip()) for part in value.split(","))
        except (AttributeError, ValueError) as exc:
            raise gcmd.error(
                "NOZZLE_ZS must be a comma-separated list of positive heights"
            ) from exc
        if not values or len(values) > 16 or any(height <= 0.0 for height in values):
            raise gcmd.error("NOZZLE_ZS must contain 1..16 positive nozzle heights")
        return values

    def _raw_measurement_report(self, label, bed_x, bed_y, nozzle_x, nozzle_y, raw):
        return (
            "%s: bed=(%.3f, %.3f) nozzle=(%.3f, %.3f) nozzle_z=%.6f "
            "raw_frequency_hz=%.3f raw_frequency_span_hz=%.3f samples=%d "
            "built_in_sensor_height=%.6f stream_height=%.6f "
            "implied_bed_z=%.6f temperature=%s"
            % (
                label,
                bed_x,
                bed_y,
                nozzle_x,
                nozzle_y,
                raw["toolhead_z"],
                raw["raw_frequency_hz"],
                raw["raw_frequency_span_hz"],
                raw["sample_count"],
                raw["built_in_sensor_height"],
                raw["stream_height"],
                raw["implied_bed_z"],
                (
                    "unknown"
                    if raw["temperature"] is None
                    else "%.3f" % raw["temperature"]
                ),
            )
        )

    def _scan_at_height(
        self,
        gcmd,
        toolhead,
        bed_x,
        bed_y,
        nozzle_x,
        nozzle_y,
        nozzle_z,
        duration,
    ):
        self._move_to_scan_target(toolhead, nozzle_x, nozzle_y, nozzle_z)
        eddy_sensor = self._eddy_sensor()
        collector = RawEddySamples()
        eddy_sensor.add_client(collector)
        try:
            self.gcode.run_script_from_command("PROBE METHOD=scan SAMPLES=1")
            toolhead.dwell(duration)
            toolhead.wait_moves()
        finally:
            collector.close()
        if not collector.samples:
            raise self.gcode.error("EDDY scan received no raw sensor samples")
        try:
            probe_x, probe_y, scan_bed_z = self._probe_position(
                self.printer.lookup_object("probe").get_status(
                    self.printer.get_reactor().monotonic()
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise self.gcode.error("EDDY scan did not return a probe result") from exc
        if (
            abs(probe_x - bed_x) > COMPARISON_XY_TOLERANCE
            or abs(probe_y - bed_y) > COMPARISON_XY_TOLERANCE
        ):
            raise self.gcode.error(
                "EDDY scan physical point mismatch: expected=(%.3f, %.3f), "
                "got=(%.3f, %.3f)" % (bed_x, bed_y, probe_x, probe_y)
            )
        frequencies = [sample[1] for sample in collector.samples]
        stream_heights = [sample[2] for sample in collector.samples]
        raw_frequency = statistics.median(frequencies)
        sensor_height = float(eddy_sensor.calibration.freq_to_height(raw_frequency))
        toolhead_position = [float(value) for value in toolhead.get_position()]
        toolhead_z = toolhead_position[2]
        return {
            "sample_count": len(collector.samples),
            "raw_frequency_hz": raw_frequency,
            "raw_frequency_span_hz": max(frequencies) - min(frequencies),
            "stream_height": statistics.median(stream_heights),
            "built_in_sensor_height": sensor_height,
            "toolhead_z": toolhead_z,
            "toolhead_position": toolhead_position,
            "implied_bed_z": toolhead_z - sensor_height,
            "scan_bed_x": probe_x,
            "scan_bed_y": probe_y,
            "scan_bed_z": scan_bed_z,
            "scan_minus_implied": scan_bed_z - (toolhead_z - sensor_height),
            "temperature": self._temperature(),
        }

    def _regular_probe(self, gcmd):
        probe = self.printer.lookup_object("probe")
        params = {"METHOD": "probe", "SAMPLES": "1"}
        probe_gcmd = self.gcode.create_gcode_command(
            "_EDDY_TAP_MEASURE_PROBE", "_EDDY_TAP_MEASURE_PROBE", params
        )
        probe_session = probe.start_probe_session(probe_gcmd)
        try:
            probe_session.run_probe(probe_gcmd)
            sample = probe_session.pull_probed_results()
            if len(sample) != 1:
                raise gcmd.error(
                    "EDDY_TAP_MEASURE expected one regular probe result, got %d"
                    % len(sample)
                )
            return sample[0]
        finally:
            probe_session.end_probe_session()

    def cmd_EDDY_TAP_MEASURE(self, gcmd):
        toolhead = self._require_homed("EDDY_TAP_MEASURE")
        x = gcmd.get_float("X", self.reference_x)
        y = gcmd.get_float("Y", self.reference_y)
        threshold = gcmd.get_float("THRESHOLD", self.tap_threshold, above=0.0)
        count = gcmd.get_int("COUNT", self.default_count, minval=1, maxval=100)

        self._move_to_reference(toolhead, x, y)
        gcmd.respond_info(
            "EDDY_TAP_MEASURE: reference=(%.3f, %.3f), taps=%d, threshold=%.3f"
            % (x, y, count, threshold)
        )

        params = dict(gcmd.get_command_parameters())
        params.update(
            {
                "METHOD": "tap",
                "TAP_THRESHOLD": "%.3f" % threshold,
                "SAMPLES": "1",
            }
        )
        probe_gcmd = self.gcode.create_gcode_command(
            "_EDDY_TAP_MEASURE", "_EDDY_TAP_MEASURE", params
        )
        probe = self.printer.lookup_object("probe")
        probe_session = probe.start_probe_session(probe_gcmd)
        results = []
        try:
            for index in range(count):
                probe_session.run_probe(probe_gcmd)
                sample = probe_session.pull_probed_results()
                if len(sample) != 1:
                    raise gcmd.error(
                        "EDDY_TAP_MEASURE expected one result, got %d" % len(sample)
                    )
                result = sample[0]
                results.append(float(result.bed_z))
                gcmd.respond_info(
                    "EDDY_TAP_MEASURE tap %d/%d: contact_z=%.6f post_retract_z=%.6f"
                    % (index + 1, count, result.bed_z, toolhead.get_position()[2])
                )
        finally:
            probe_session.end_probe_session()

        mean = statistics.fmean(results)
        median = statistics.median(results)
        minimum = min(results)
        maximum = max(results)
        span = maximum - minimum
        standard_deviation = statistics.pstdev(results)
        gcmd.respond_info(
            "EDDY_TAP_MEASURE statistics: mean=%.6f median=%.6f "
            "min=%.6f max=%.6f span=%.6f stddev=%.6f"
            % (mean, median, minimum, maximum, span, standard_deviation)
        )

        probe = self.printer.lookup_object("probe")
        coil_pose, requested_pose, bounds = self._coil_over_target_pose(
            toolhead, probe, x, y
        )
        if coil_pose is None:
            if bounds is None:
                gcmd.respond_info(
                    "EDDY_TAP_MEASURE warning: cannot determine motion limits; "
                    "skipping same-point Eddy PROBE"
                )
            else:
                gcmd.respond_info(
                    "EDDY_TAP_MEASURE warning: Eddy coil target is unreachable; "
                    "tap=(%.3f, %.3f) requires nozzle=(%.3f, %.3f), "
                    "limits x=[%.3f, %.3f] y=[%.3f, %.3f]; skipping Eddy PROBE"
                    % (x, y, requested_pose[0], requested_pose[1], *bounds)
                )
            return

        nozzle_x, nozzle_y = coil_pose
        self._move_to_coil_target(toolhead, nozzle_x, nozzle_y)
        result = self._regular_probe(gcmd)
        if (
            abs(float(result.bed_x) - x) > COMPARISON_XY_TOLERANCE
            or abs(float(result.bed_y) - y) > COMPARISON_XY_TOLERANCE
        ):
            raise gcmd.error(
                "EDDY_TAP_MEASURE regular probe physical point mismatch: "
                "expected=(%.3f, %.3f), got=(%.3f, %.3f)"
                % (x, y, result.bed_x, result.bed_y)
            )
        self.gcode.run_script_from_command(
            "G90\nG1 Z%.3f F%.0f" % (self.move_z, self.move_speed * 60.0)
        )
        toolhead.wait_moves()
        eddy_probe_z = float(result.bed_z)
        gcmd.respond_info(
            "EDDY_TAP_MEASURE comparison: tap_median=%.6f eddy_probe=%.6f "
            "delta_probe_minus_tap=%.6f bed=(%.3f, %.3f) nozzle=(%.3f, %.3f)"
            % (median, eddy_probe_z, eddy_probe_z - median, x, y, nozzle_x, nozzle_y)
        )

    def cmd_EDDY_RAW_MEASURE(self, gcmd):
        command_name = "EDDY_RAW_MEASURE"
        toolhead = self._require_scan_ready(command_name)
        bed_x = gcmd.get_float("X", self.reference_x)
        bed_y = gcmd.get_float("Y", self.reference_y)
        nozzle_z = gcmd.get_float("Z", 1.0, above=0.0)
        duration = gcmd.get_float("DURATION", DEFAULT_RAW_DURATION, above=0.0)
        probe = self.printer.lookup_object("probe")
        pose, requested_pose, bounds = self._coil_over_target_pose(
            toolhead, probe, bed_x, bed_y
        )
        if pose is None:
            raise self.gcode.error(
                "%s coil target is unreachable: bed=(%.3f, %.3f) "
                "requires nozzle=(%.3f, %.3f), limits=%s"
                % (
                    command_name,
                    bed_x,
                    bed_y,
                    requested_pose[0],
                    requested_pose[1],
                    bounds,
                )
            )
        nozzle_x, nozzle_y = pose
        try:
            self._require_nozzle_z_in_limits(toolhead, nozzle_z, command_name)
            self._move_to_scan_target(toolhead, nozzle_x, nozzle_y, nozzle_z)
            raw = self._capture_raw_measurement(toolhead, duration)
            self.last_raw_measurement = {
                "bed_x": bed_x,
                "bed_y": bed_y,
                "nozzle_x": nozzle_x,
                "nozzle_y": nozzle_y,
                "requested_nozzle_z": nozzle_z,
                "duration": duration,
                **raw,
            }
            gcmd.respond_info(
                self._raw_measurement_report(
                    command_name, bed_x, bed_y, nozzle_x, nozzle_y, raw
                )
            )
        finally:
            self._lift_to_safe_z(toolhead)

    def cmd_EDDY_SCAN_HEIGHT_TEST(self, gcmd):
        command_name = "EDDY_SCAN_HEIGHT_TEST"
        toolhead = self._require_scan_ready(command_name)
        bed_x = gcmd.get_float("X", self.reference_x)
        bed_y = gcmd.get_float("Y", self.reference_y)
        duration = gcmd.get_float("DURATION", DEFAULT_RAW_DURATION, above=0.0)
        nozzle_zs = self._parse_nozzle_zs(
            gcmd.get("NOZZLE_ZS", self.default_scan_nozzle_zs), gcmd
        )
        probe = self.printer.lookup_object("probe")
        pose, requested_pose, bounds = self._coil_over_target_pose(
            toolhead, probe, bed_x, bed_y
        )
        if pose is None:
            raise self.gcode.error(
                "%s coil target is unreachable: bed=(%.3f, %.3f) "
                "requires nozzle=(%.3f, %.3f), limits=%s"
                % (
                    command_name,
                    bed_x,
                    bed_y,
                    requested_pose[0],
                    requested_pose[1],
                    bounds,
                )
            )
        nozzle_x, nozzle_y = pose
        gcmd.respond_info(
            "%s: bed=(%.3f, %.3f) nozzle=(%.3f, %.3f) nozzle_zs=%s"
            % (
                command_name,
                bed_x,
                bed_y,
                nozzle_x,
                nozzle_y,
                ",".join("%.3f" % height for height in nozzle_zs),
            )
        )
        results = []
        try:
            for nozzle_z in nozzle_zs:
                self._require_nozzle_z_in_limits(toolhead, nozzle_z, command_name)
                result = self._scan_at_height(
                    gcmd,
                    toolhead,
                    bed_x,
                    bed_y,
                    nozzle_x,
                    nozzle_y,
                    nozzle_z,
                    duration,
                )
                results.append(result)
                gcmd.respond_info(
                    "%s point: nozzle_z=%.6f raw_frequency_hz=%.3f "
                    "raw_frequency_span_hz=%.3f samples=%d "
                    "built_in_sensor_height=%.6f stream_height=%.6f "
                    "implied_bed_z=%.6f scan_probe=(%.3f, %.3f, %.6f) "
                    "scan_minus_implied=%.6f temperature=%s"
                    % (
                        command_name,
                        result["toolhead_z"],
                        result["raw_frequency_hz"],
                        result["raw_frequency_span_hz"],
                        result["sample_count"],
                        result["built_in_sensor_height"],
                        result["stream_height"],
                        result["implied_bed_z"],
                        result["scan_bed_x"],
                        result["scan_bed_y"],
                        result["scan_bed_z"],
                        result["scan_minus_implied"],
                        (
                            "unknown"
                            if result["temperature"] is None
                            else "%.3f" % result["temperature"]
                        ),
                    )
                )
        finally:
            self._lift_to_safe_z(toolhead)
        scan_values = [result["scan_bed_z"] for result in results]
        temperatures = [result["temperature"] for result in results]
        known_temperatures = [value for value in temperatures if value is not None]
        temperature_span = (
            None
            if not known_temperatures
            else max(known_temperatures) - min(known_temperatures)
        )
        self.last_scan_height_test = {
            "bed_x": bed_x,
            "bed_y": bed_y,
            "nozzle_x": nozzle_x,
            "nozzle_y": nozzle_y,
            "requested_nozzle_zs": list(nozzle_zs),
            "duration": duration,
            "results": results,
            "scan_bed_z_median": statistics.median(scan_values),
            "scan_bed_z_span": max(scan_values) - min(scan_values),
            "temperature_span": temperature_span,
        }
        gcmd.respond_info(
            "%s summary: scan_bed_z_median=%.6f scan_bed_z_span=%.6f "
            "temperature_span=%s"
            % (
                command_name,
                statistics.median(scan_values),
                max(scan_values) - min(scan_values),
                "unknown" if temperature_span is None else "%.6f" % temperature_span,
            )
        )


def load_config(config):
    return EddyTapMeasure(config)
