# Interactive Eddy tap measurement helper.
#
# Copyright (C) 2026 Markus Emmenegger
# This file may be distributed under the terms of the GNU GPLv3 license.

import statistics


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
        self.tap_threshold = probe_config.getfloat(
            "tap_threshold", 0.0, minval=0.0
        )
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


def load_config(config):
    return EddyTapMeasure(config)
