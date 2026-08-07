# Interactive Eddy tap measurement helper.
#
# Copyright (C) 2026 Markus Emmenegger
# This file may be distributed under the terms of the GNU GPLv3 license.

import statistics

COMPARISON_XY_TOLERANCE = 0.020


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
        self.gcode.register_command(
            "_EDDY_TAP_MEASURE",
            self.cmd_EDDY_TAP_MEASURE,
            desc="Measure repeated Eddy tap contacts at the canonical reference.",
        )

    def get_status(self, eventtime):
        return {
            "reference_x": self.reference_x,
            "reference_y": self.reference_y,
            "tap_threshold": self.tap_threshold,
            "default_count": self.default_count,
        }

    def _require_homed(self):
        toolhead = self.printer.lookup_object("toolhead")
        homed_axes = toolhead.get_status(self.printer.get_reactor().monotonic()).get(
            "homed_axes", ""
        )
        if not all(axis in homed_axes for axis in "xyz"):
            raise self.gcode.error(
                "EDDY_TAP_MEASURE requires XYZ homing; homed_axes=%s" % homed_axes
            )
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
        toolhead = self._require_homed()
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


def load_config(config):
    return EddyTapMeasure(config)
