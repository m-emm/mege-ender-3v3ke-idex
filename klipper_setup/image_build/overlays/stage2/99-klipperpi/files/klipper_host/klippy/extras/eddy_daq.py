# Eddy-specific measurement commands backed by the generic DAQ store.
#
# Copyright (C) 2026 Markus Emmenegger
# This file may be distributed under the terms of the GNU GPLv3 license.

import logging
import re


_logger = logging.getLogger(__name__)
XY_TOLERANCE = 0.020


class EddyDaq:
    """Persist Tap and native Eddy samples without changing calibration state."""

    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.tap_threshold = config.getsection("probe_eddy_current btt_eddy").getfloat(
            "tap_threshold", minval=0.0
        )
        self.last_record = None
        self.gcode.register_command(
            "DAQ_EDDY_CONTEXT",
            self.cmd_DAQ_EDDY_CONTEXT,
            desc="Add Eddy-grid metadata to a DAQ job.",
        )
        self.gcode.register_command(
            "DAQ_EDDY_TAP",
            self.cmd_DAQ_EDDY_TAP,
            desc="Acquire one Tap record at the current nozzle position.",
        )
        self.gcode.register_command(
            "DAQ_EDDY_SAMPLE",
            self.cmd_DAQ_EDDY_SAMPLE,
            desc="Acquire one native Eddy record at the current coil position.",
        )

    def _daq_store(self):
        try:
            return self.printer.lookup_object("daq").store
        except Exception as exc:
            raise self.gcode.error("generic DAQ store is unavailable") from exc

    def _eddy_helper(self):
        try:
            return self.printer.lookup_object("eddy_tap_measure")
        except Exception as exc:
            raise self.gcode.error("Eddy native measurement helper is unavailable") from exc

    def _require_ready(self, command_name):
        return self._eddy_helper()._require_scan_ready(command_name)

    @staticmethod
    def _axis(position, index, name):
        if isinstance(position, dict):
            return float(position[name])
        value = getattr(position, name, None)
        return float(value if value is not None else position[index])

    def _position_snapshot(self, toolhead):
        position = [float(value) for value in toolhead.get_position()]
        snapshot = {
            "toolhead_x": position[0],
            "toolhead_y": position[1],
            "toolhead_z": position[2],
        }
        try:
            gcode_move = self.printer.lookup_object("gcode_move")
            gcode_status = gcode_move.get_status(
                self.printer.get_reactor().monotonic()
            )
            for prefix, values in (
                ("gcode", gcode_status.get("gcode_position")),
                ("homing_origin", gcode_status.get("homing_origin")),
            ):
                if values is None:
                    continue
                for index, axis in enumerate("xyz"):
                    snapshot["%s_%s" % (prefix, axis)] = self._axis(
                        values, index, axis
                    )
        except Exception:
            pass
        try:
            for stepper in toolhead.get_kinematics().get_steppers():
                name = re.sub(r"[^A-Za-z0-9_]+", "_", stepper.get_name())
                mcu_position = getattr(stepper, "get_mcu_position", None)
                commanded_position = getattr(stepper, "get_commanded_position", None)
                if mcu_position is not None:
                    snapshot["mcu_stepper_%s" % name] = int(mcu_position())
                if commanded_position is not None:
                    snapshot["commanded_stepper_%s" % name] = float(
                        commanded_position()
                    )
        except Exception:
            pass
        return snapshot

    def _record_error(self, gcmd, record_type, error):
        store = self._daq_store()
        record = {
            "record_type": record_type,
            "point_index": gcmd.get_int("POINT_INDEX", minval=0),
            "requested_bed_x": gcmd.get_float("X"),
            "requested_bed_y": gcmd.get_float("Y"),
            "error": "%s: %s" % (type(error).__name__, error),
        }
        self.last_record = store.write_record(
            gcmd.get("JOB_ID"), gcmd.get_int("RECORD_INDEX", minval=0), record
        )
        gcmd.respond_info(
            "DAQ Eddy %s failed at point=%d: %s"
            % (record_type, record["point_index"], record["error"])
        )

    @staticmethod
    def _assert_close(label, actual, expected):
        if abs(actual - expected) > XY_TOLERANCE:
            raise ValueError(
                "%s mismatch: expected %.3f, got %.3f" % (label, expected, actual)
            )

    def get_status(self, _eventtime):
        return {"last_record": self.last_record}

    def cmd_DAQ_EDDY_CONTEXT(self, gcmd):
        self._require_ready("DAQ_EDDY_CONTEXT")
        offsets = self.printer.lookup_object("probe").get_offsets()
        metadata = {
            "grid_columns": gcmd.get_int("GRID_X", minval=1),
            "grid_rows": gcmd.get_int("GRID_Y", minval=1),
            "grid_x_min": gcmd.get_float("X_MIN"),
            "grid_x_max": gcmd.get_float("X_MAX"),
            "grid_y_min": gcmd.get_float("Y_MIN"),
            "grid_y_max": gcmd.get_float("Y_MAX"),
            "tap_count": gcmd.get_int("TAP_COUNT", minval=1),
            "tap_threshold": gcmd.get_float("TAP_THRESHOLD", above=0.0),
            "eddy_nozzle_zs": gcmd.get("HEIGHTS"),
            "eddy_sample_duration": gcmd.get_float("DURATION", above=0.0),
            "xy_speed": gcmd.get_float("XY_SPEED", above=0.0),
            "safe_z": gcmd.get_float("SAFE_Z", above=0.0),
            "config_fingerprint": gcmd.get("CONFIG_FINGERPRINT"),
            "probe_offset_x": float(offsets[0]),
            "probe_offset_y": float(offsets[1]),
            "probe_offset_z": float(offsets[2]),
            "t0_x_endstop": gcmd.get_float("T0_X_ENDSTOP"),
            "t0_y_endstop": gcmd.get_float("T0_Y_ENDSTOP"),
            "t0_z_endstop": gcmd.get_float("T0_Z_ENDSTOP"),
            "t1_x_endstop": gcmd.get_float("T1_X_ENDSTOP"),
            "t1_y_endstop": gcmd.get_float("T1_Y_ENDSTOP"),
            "t1_z_endstop": gcmd.get_float("T1_Z_ENDSTOP"),
        }
        try:
            self._daq_store().update_job_metadata(gcmd.get("JOB_ID"), metadata)
        except ValueError as exc:
            raise gcmd.error(str(exc)) from exc
        gcmd.respond_info(
            "DAQ Eddy context: job_id=%s grid=%dx%d heights=%s"
            % (
                gcmd.get("JOB_ID"),
                metadata["grid_columns"],
                metadata["grid_rows"],
                metadata["eddy_nozzle_zs"],
            )
        )

    def cmd_DAQ_EDDY_TAP(self, gcmd):
        toolhead = self._require_ready("DAQ_EDDY_TAP")
        requested_x = gcmd.get_float("X")
        requested_y = gcmd.get_float("Y")
        threshold = gcmd.get_float("THRESHOLD", self.tap_threshold, above=0.0)
        try:
            before = self._position_snapshot(toolhead)
            self._assert_close("Tap X", before["toolhead_x"], requested_x)
            self._assert_close("Tap Y", before["toolhead_y"], requested_y)
            params = dict(gcmd.get_command_parameters())
            params.update(
                {"METHOD": "tap", "TAP_THRESHOLD": "%.3f" % threshold, "SAMPLES": "1"}
            )
            probe_gcmd = self.gcode.create_gcode_command(
                "DAQ_EDDY_TAP", "DAQ_EDDY_TAP", params
            )
            probe_session = self.printer.lookup_object("probe").start_probe_session(
                probe_gcmd
            )
            try:
                probe_session.run_probe(probe_gcmd)
                samples = probe_session.pull_probed_results()
            finally:
                probe_session.end_probe_session()
            if len(samples) != 1:
                raise ValueError("Tap returned %d samples, expected one" % len(samples))
            contact = samples[0]
            contact_x = float(contact.bed_x)
            contact_y = float(contact.bed_y)
            self._assert_close("Tap physical X", contact_x, requested_x)
            self._assert_close("Tap physical Y", contact_y, requested_y)
            after = self._position_snapshot(toolhead)
            record = {
                "record_type": "eddy_tap",
                "point_index": gcmd.get_int("POINT_INDEX", minval=0),
                "tap_index": gcmd.get_int("TAP_INDEX", 0, minval=0),
                "requested_bed_x": requested_x,
                "requested_bed_y": requested_y,
                "tap_threshold": threshold,
                "tap_contact_x": contact_x,
                "tap_contact_y": contact_y,
                "tap_contact_z": float(contact.bed_z),
                "post_retract_toolhead_z": after["toolhead_z"],
                "eddy_temperature": self._eddy_helper()._temperature(),
                **before,
                **{"post_retract_%s" % key: value for key, value in after.items()},
            }
            self.last_record = self._daq_store().write_record(
                gcmd.get("JOB_ID"), gcmd.get_int("RECORD_INDEX", minval=0), record
            )
            gcmd.respond_info(
                "DAQ Eddy tap: point=%d contact=(%.3f,%.3f,%.6f)"
                % (record["point_index"], contact_x, contact_y, record["tap_contact_z"])
            )
        except Exception as exc:
            self._record_error(gcmd, "eddy_tap", exc)

    def cmd_DAQ_EDDY_SAMPLE(self, gcmd):
        toolhead = self._require_ready("DAQ_EDDY_SAMPLE")
        requested_x = gcmd.get_float("X")
        requested_y = gcmd.get_float("Y")
        requested_z = gcmd.get_float("Z", above=0.0)
        try:
            before = self._position_snapshot(toolhead)
            offsets = self.printer.lookup_object("probe").get_offsets()
            self._assert_close(
                "Eddy physical X", before["toolhead_x"] + float(offsets[0]), requested_x
            )
            self._assert_close(
                "Eddy physical Y", before["toolhead_y"] + float(offsets[1]), requested_y
            )
            self._assert_close("Eddy nozzle Z", before["toolhead_z"], requested_z)
            raw = self._eddy_helper()._capture_raw_measurement(
                toolhead, gcmd.get_float("DURATION", 0.5, above=0.0)
            )
            record = {
                "record_type": "eddy_native",
                "point_index": gcmd.get_int("POINT_INDEX", minval=0),
                "height_index": gcmd.get_int("HEIGHT_INDEX", minval=0),
                "requested_bed_x": requested_x,
                "requested_bed_y": requested_y,
                "requested_nozzle_z": requested_z,
                "coil_nozzle_x": before["toolhead_x"],
                "coil_nozzle_y": before["toolhead_y"],
                "raw_frequency_hz": raw["raw_frequency_hz"],
                "raw_frequency_span_hz": raw["raw_frequency_span_hz"],
                "raw_sample_count": raw["sample_count"],
                "built_in_sensor_height": raw["built_in_sensor_height"],
                "stream_height": raw["stream_height"],
                "implied_bed_z": raw["implied_bed_z"],
                "eddy_temperature": raw["temperature"],
                **before,
            }
            self.last_record = self._daq_store().write_record(
                gcmd.get("JOB_ID"), gcmd.get_int("RECORD_INDEX", minval=0), record
            )
            gcmd.respond_info(
                "DAQ Eddy sample: point=%d bed=(%.3f,%.3f) nozzle=(%.3f,%.3f,%.3f) "
                "frequency=%.3f height=%.6f implied_bed_z=%.6f"
                % (
                    record["point_index"],
                    requested_x,
                    requested_y,
                    record["coil_nozzle_x"],
                    record["coil_nozzle_y"],
                    requested_z,
                    record["raw_frequency_hz"],
                    record["built_in_sensor_height"],
                    record["implied_bed_z"],
                )
            )
        except Exception as exc:
            self._record_error(gcmd, "eddy_native", exc)


def load_config(config):
    return EddyDaq(config)
