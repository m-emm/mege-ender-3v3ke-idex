# Synchronous printer vision commands
#
# Copyright (C) 2026  Markus Emmenegger
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import errno
import json
import socket


class Vision:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.reactor = self.printer.get_reactor()
        self.socket_path = config.get(
            "socket_path", "/run/vision-capture-nozzle_cam/visiond.sock"
        )
        self.timeout = config.getfloat("timeout", 15.0, above=0.0)
        self.bed_y_calibrated = config.getboolean("bed_y_calibrated", False)
        self.bed_y_calibration = {
            "camera": config.get("bed_y_camera", "nozzle_cam"),
            "profile": config.get("bed_y_profile", "analysis"),
            "image_width": config.getint("bed_y_image_width", 1, minval=1),
            "image_height": config.getint("bed_y_image_height", 1, minval=1),
            "reference_y_mm": config.getfloat("bed_y_reference_y", 0.0),
            "reference_pixel_x": config.getfloat("bed_y_reference_pixel_x", 0.0),
            "reference_pixel_y": config.getfloat("bed_y_reference_pixel_y", 0.0),
            "axis_vector_x": config.getfloat("bed_y_axis_vector_x", 0.0),
            "axis_vector_y": config.getfloat("bed_y_axis_vector_y", 1.0),
            "template_path": config.get("bed_y_template_path", ""),
            "template_sha256": config.get("bed_y_template_sha256", ""),
            "template_width": config.getint("bed_y_template_width", 1, minval=1),
            "template_height": config.getint("bed_y_template_height", 1, minval=1),
            "feature_mode": config.get("bed_y_feature_mode", "gray_norm"),
            "min_correlation": config.getfloat(
                "bed_y_min_correlation", 0.95, minval=0.0, maxval=1.0
            ),
            "max_cross_axis_px": config.getfloat(
                "bed_y_max_cross_axis_px", 3.0, minval=0.0
            ),
            "search_radius_mm": config.getfloat(
                "bed_y_search_radius_mm", 5.0, above=0.0
            ),
        }
        self.last_bed_y_reference = None
        self.last_bed_y_measurement = None
        self.gcode = self.printer.lookup_object("gcode")
        self.gcode.register_command(
            "VISION_JOB_BEGIN",
            self.cmd_VISION_JOB_BEGIN,
            desc="Begin a synchronous vision acquisition job.",
        )
        self.gcode.register_command(
            "VISION_PROFILE",
            self.cmd_VISION_PROFILE,
            desc="Apply and verify a blocking vision camera profile.",
        )
        self.gcode.register_command(
            "VISION_CAPTURE_SYNC",
            self.cmd_VISION_CAPTURE_SYNC,
            desc="Synchronously commit one vision job frame.",
        )
        self.gcode.register_command(
            "VISION_JOB_END",
            self.cmd_VISION_JOB_END,
            desc="Finish and verify a synchronous vision acquisition job.",
        )
        self.gcode.register_command(
            "VISION_EDDY_SAMPLE_SYNC",
            self.cmd_VISION_EDDY_SAMPLE_SYNC,
            desc="Collect and commit one synchronized raw Eddy sample window.",
        )
        self.gcode.register_command(
            "VISION_MEASURE_BED_Y",
            self.cmd_VISION_MEASURE_BED_Y,
            desc="Synchronously measure physical bed Y with the nozzle camera.",
        )
        self.gcode.register_command(
            "VISION_BED_Y_REFERENCE",
            self.cmd_VISION_BED_Y_REFERENCE,
            desc="Capture a fresh run-local bed Y reference.",
        )
        self.gcode.register_command(
            "VISION_VALIDATE_BED_Y_REFERENCE",
            self.cmd_VISION_VALIDATE_BED_Y_REFERENCE,
            desc="Validate a run-local bed Y reference with a known move.",
        )
        self.gcode.register_command(
            "VISION_MEASURE_BED_Y_RELATIVE",
            self.cmd_VISION_MEASURE_BED_Y_RELATIVE,
            desc="Measure bed Y against the validated run-local reference.",
        )

    def get_status(self, eventtime):
        return {
            "bed_y_calibrated": self.bed_y_calibrated,
            "last_bed_y_reference": self.last_bed_y_reference,
            "last_bed_y_measurement": self.last_bed_y_measurement,
        }

    def _wait_moves(self):
        self.printer.lookup_object("toolhead").wait_moves()

    def _toolhead_position(self):
        toolhead = self.printer.lookup_object("toolhead", None)
        if toolhead is None or not hasattr(toolhead, "get_position"):
            return None
        pos = toolhead.get_position()
        return [float(v) for v in pos]

    def _gcode_position(self):
        gcode_move = self.printer.lookup_object("gcode_move", None)
        if gcode_move is None or not hasattr(gcode_move, "get_status"):
            return None
        status = gcode_move.get_status(self.reactor.monotonic())
        pos = status.get("gcode_position")
        if pos is None:
            return None
        return [float(v) for v in pos]

    def _homed_axes(self):
        toolhead = self.printer.lookup_object("toolhead", None)
        if toolhead is None or not hasattr(toolhead, "get_status"):
            return None
        status = toolhead.get_status(self.reactor.monotonic())
        return status.get("homed_axes")

    def _request_visiond(self, action, params):
        payload = (
            json.dumps({"action": action, "params": params}, separators=(",", ":"))
            + "\n"
        ).encode()
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.setblocking(False)
        fd_handle = None
        completion = self.reactor.completion()
        state = {"out": payload, "in": b"", "done_sending": False}

        def complete(result):
            if not completion.test():
                completion.complete(result)

        def read_callback(eventtime):
            try:
                data = sock.recv(4096)
            except socket.error as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                    return
                complete({"ok": False, "error": str(exc)})
                return
            if not data:
                complete({"ok": False, "error": "visiond socket closed"})
                return
            state["in"] += data
            if b"\n" not in state["in"]:
                return
            line, _remaining = state["in"].split(b"\n", 1)
            try:
                complete(json.loads(line.decode()))
            except Exception as exc:
                complete({"ok": False, "error": f"bad visiond response: {exc}"})

        def write_callback(eventtime):
            if not state["out"]:
                if not state["done_sending"]:
                    state["done_sending"] = True
                    self.reactor.set_fd_wake(fd_handle, True, False)
                return
            try:
                sent = sock.send(state["out"])
            except socket.error as exc:
                if exc.errno in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINPROGRESS):
                    return
                complete({"ok": False, "error": str(exc)})
                return
            state["out"] = state["out"][sent:]
            if not state["out"]:
                state["done_sending"] = True
                self.reactor.set_fd_wake(fd_handle, True, False)

        try:
            try:
                sock.connect(self.socket_path)
            except socket.error as exc:
                if exc.errno not in (
                    errno.EINPROGRESS,
                    errno.EAGAIN,
                    errno.EWOULDBLOCK,
                ):
                    raise
            fd_handle = self.reactor.register_fd(
                sock.fileno(), read_callback, write_callback
            )
            self.reactor.set_fd_wake(fd_handle, True, True)
            deadline = self.reactor.monotonic() + self.timeout
            response = completion.wait(deadline, None)
        except Exception as exc:
            response = {"ok": False, "error": str(exc)}
        finally:
            if fd_handle is not None:
                self.reactor.unregister_fd(fd_handle)
            sock.close()

        if response is None:
            raise self.gcode.error(
                "Vision command %s timed out after %.3fs" % (action, self.timeout)
            )
        if not response.get("ok"):
            raise self.gcode.error(
                "Vision command %s failed: %s"
                % (action, response.get("error", "unknown error"))
            )
        return response

    def cmd_VISION_JOB_BEGIN(self, gcmd):
        self._wait_moves()
        return self._request_visiond(
            "job_begin",
            {
                "job": gcmd.get("JOB"),
                "manifest_hash": gcmd.get("MANIFEST_HASH"),
                "gcode_hash": gcmd.get("GCODE_HASH"),
            },
        )

    def cmd_VISION_PROFILE(self, gcmd):
        return self._request_visiond(
            "profile",
            {
                "camera": gcmd.get("CAMERA"),
                "profile": gcmd.get("PROFILE"),
            },
        )

    def cmd_VISION_CAPTURE_SYNC(self, gcmd):
        self._wait_moves()
        params = {
            "job": gcmd.get("JOB"),
            "seq": gcmd.get_int("SEQ", minval=0),
            "frame": gcmd.get("FRAME"),
            "camera": gcmd.get("CAMERA"),
            "profile": gcmd.get("PROFILE"),
            "tool": gcmd.get("TOOL", None),
            "toolhead_position": self._toolhead_position(),
            "gcode_position": self._gcode_position(),
            "homed_axes": self._homed_axes(),
        }
        return self._request_visiond("capture", params)

    def cmd_VISION_JOB_END(self, gcmd):
        self._wait_moves()
        return self._request_visiond(
            "job_end",
            {
                "job": gcmd.get("JOB"),
                "expected_frames": gcmd.get_int("EXPECTED_FRAMES", minval=0),
            },
        )

    def _object_status(self, name):
        obj = self.printer.lookup_object(name, None)
        if obj is None or not hasattr(obj, "get_status"):
            return None
        try:
            return obj.get_status(self.reactor.monotonic())
        except Exception:
            return None

    def cmd_VISION_EDDY_SAMPLE_SYNC(self, gcmd):
        self._wait_moves()
        probe = self.printer.lookup_object("probe", None)
        if probe is None or not hasattr(probe, "add_client"):
            raise gcmd.error(
                "VISION_EDDY_SAMPLE_SYNC requires an Eddy probe with add_client"
            )
        settle_ms = gcmd.get_int("SETTLE_MS", 100, minval=0)
        duration_ms = gcmd.get_int("DURATION_MS", 250, minval=100)
        toolhead = self.printer.lookup_object("toolhead")
        batches = []
        collection = {"finished": False}
        batch_completion = self.reactor.completion()
        window_origin = toolhead.get_last_move_time()
        window_start = window_origin + settle_ms / 1000.0
        window_end = window_start + duration_ms / 1000.0

        def handle_batch(msg):
            if collection["finished"]:
                return False
            batches.append(msg)
            data = msg.get("data") or []
            if data and float(data[-1][0]) >= window_end:
                collection["finished"] = True
                if not batch_completion.test():
                    batch_completion.complete(True)
                return False
            return True

        probe.add_client(handle_batch)
        toolhead.dwell((settle_ms + duration_ms) / 1000.0)
        toolhead.wait_moves()
        batch_received = batch_completion.wait(
            self.reactor.monotonic() + 2.0, None
        )
        collection["finished"] = True
        if batch_received is None:
            raise gcmd.error(
                "Eddy sample %s timed out waiting for a sensor batch"
                % (gcmd.get("SAMPLE"),)
            )

        raw_samples = []
        error_count = 0
        overflow_count = 0
        for batch in batches:
            error_count = max(error_count, int(batch.get("errors") or 0))
            overflow_count = max(
                overflow_count, int(batch.get("overflows") or 0)
            )
            for sample in batch.get("data") or []:
                sample_time = float(sample[0])
                if window_start <= sample_time <= window_end:
                    raw_samples.append(
                        [
                            round(sample_time, 6),
                            round(float(sample[1]), 3),
                            round(float(sample[2]), 6),
                        ]
                    )

        expected_count = duration_ms * 0.4
        complete = (
            len(raw_samples) >= max(1, int(expected_count * 0.80))
            and error_count == 0
            and overflow_count == 0
        )
        params = {
            "job": gcmd.get("JOB"),
            "seq": gcmd.get_int("SEQ", minval=0),
            "sample": gcmd.get("SAMPLE"),
            "manifest_hash": gcmd.get("MANIFEST_HASH"),
            "approach": gcmd.get("APPROACH"),
            "commanded_z": gcmd.get_float("COMMANDED_Z"),
            "nozzle_gap": gcmd.get_float("NOZZLE_GAP"),
            "coil_gap": gcmd.get_float("COIL_GAP"),
            "settle_ms": settle_ms,
            "duration_ms": duration_ms,
            "sample_rate_hz": 400,
            "sample_window": [round(window_start, 6), round(window_end, 6)],
            "samples": raw_samples,
            "errors": error_count,
            "overflows": overflow_count,
            "complete": complete,
            "toolhead_position": self._toolhead_position(),
            "gcode_position": self._gcode_position(),
            "homed_axes": self._homed_axes(),
            "temperatures": {
                "coil": self._object_status("temperature_probe btt_eddy"),
                "mcu": self._object_status("temperature_sensor btt_eddy_mcu"),
            },
        }
        response = self._request_visiond("eddy_sample", params)
        result = response.get("result") or {}
        gcmd.respond_info(
            "Eddy sample %s: n=%d errors=%d overflows=%d median=%.3fHz"
            % (
                params["sample"],
                len(raw_samples),
                error_count,
                overflow_count,
                float(result.get("median_frequency_hz") or 0.0),
            )
        )
        if not complete:
            raise gcmd.error(
                "Eddy sample %s incomplete: n=%d errors=%d overflows=%d"
                % (
                    params["sample"],
                    len(raw_samples),
                    error_count,
                    overflow_count,
                )
            )
        return result

    def _bed_y_common_params(self, gcmd):
        params = dict(self.bed_y_calibration)
        params.update(
            {
                "run": gcmd.get("RUN", "manual"),
                "step": gcmd.get_int("STEP", 0, minval=0),
                "toolhead_position": self._toolhead_position(),
                "gcode_position": self._gcode_position(),
                "homed_axes": self._homed_axes(),
            }
        )
        return params

    def _bed_y_light_off(self):
        try:
            self.gcode.run_script_from_command("VISION_LIGHT_OFF")
        except Exception:
            pass

    def _respond_bed_y_measurement(self, gcmd, result, params, label):
        gcmd.respond_info(
            "%s: measured=%.4f expected=%.4f error=%+.4f "
            "correlation=%.4f retry=%s run=%s step=%s"
            % (
                label,
                float(result.get("measured_y_mm")),
                float(result.get("expected_y_mm")),
                float(result.get("error_mm")),
                float(result.get("correlation")),
                result.get("retry_used"),
                params["run"],
                params["step"],
            )
        )

    def _require_bed_y_reference(self, gcmd, run):
        reference = self.last_bed_y_reference
        if reference is None:
            raise gcmd.error(
                "Run-local bed Y measurement requires VISION_BED_Y_REFERENCE"
            )
        if reference.get("run") != run:
            raise gcmd.error(
                "Run-local bed Y reference RUN=%s does not match RUN=%s"
                % (reference.get("run"), run)
            )
        return reference

    def cmd_VISION_BED_Y_REFERENCE(self, gcmd):
        if not self.bed_y_calibrated:
            raise gcmd.error(
                "VISION_BED_Y_REFERENCE requires cameras.nozzle_cam calibration"
            )
        self._wait_moves()
        params = self._bed_y_common_params(gcmd)
        params["run_reference_y_mm"] = gcmd.get_float("REFERENCE_Y")
        try:
            response = self._request_visiond("bed_y_reference", params)
            result = response.get("result") or {}
            self.last_bed_y_reference = result
            self.last_bed_y_measurement = None
        finally:
            self._bed_y_light_off()
        gcmd.respond_info(
            "Run-local bed Y reference: Y=%.4f anchor=(%.3f, %.3f) "
            "correlation=%.4f run=%s session=%s"
            % (
                float(result["reference_y_mm"]),
                float(result["reference_anchor_px"][0]),
                float(result["reference_anchor_px"][1]),
                float(result["bootstrap_correlation"]),
                result["run"],
                result["session_id"],
            )
        )
        return result

    def cmd_VISION_VALIDATE_BED_Y_REFERENCE(self, gcmd):
        if not self.bed_y_calibrated:
            raise gcmd.error(
                "VISION_VALIDATE_BED_Y_REFERENCE requires cameras.nozzle_cam calibration"
            )
        self._wait_moves()
        params = self._bed_y_common_params(gcmd)
        reference = self._require_bed_y_reference(gcmd, params["run"])
        params.update(
            {
                "session_id": reference["session_id"],
                "expected_delta_mm": gcmd.get_float("EXPECTED_DELTA"),
                "tolerance_mm": gcmd.get_float("TOLERANCE", 0.1, above=0.0),
                "confirm": gcmd.get_int("CONFIRM", 1, minval=0, maxval=2),
                "phase": gcmd.get("PHASE", "startup_validation"),
            }
        )
        try:
            response = self._request_visiond("validate_bed_y_reference", params)
            result = response.get("result") or {}
            self.last_bed_y_measurement = result
            if result.get("accepted"):
                updated = dict(reference)
                updated["validated"] = True
                updated["live_axis_vector_px_per_mm"] = result.get(
                    "live_axis_vector_px_per_mm"
                )
                self.last_bed_y_reference = updated
        finally:
            self._bed_y_light_off()
        self._respond_bed_y_measurement(
            gcmd, result, params, "Run-local bed Y 1 mm validation"
        )
        if not result.get("accepted"):
            raise gcmd.error(
                "Run-local bed Y 1 mm validation failed: %s"
                % result.get("failure_reason", "measurement rejected")
            )
        gcmd.respond_info(
            "Run-local bed Y pixel vector: (%.6f, %.6f) px/mm"
            % tuple(float(value) for value in result["live_axis_vector_px_per_mm"])
        )
        return result

    def cmd_VISION_MEASURE_BED_Y_RELATIVE(self, gcmd):
        if not self.bed_y_calibrated:
            raise gcmd.error(
                "VISION_MEASURE_BED_Y_RELATIVE requires cameras.nozzle_cam calibration"
            )
        self._wait_moves()
        params = self._bed_y_common_params(gcmd)
        reference = self._require_bed_y_reference(gcmd, params["run"])
        if not reference.get("validated"):
            raise gcmd.error(
                "Run-local bed Y reference has not passed its 1 mm validation"
            )
        params.update(
            {
                "session_id": reference["session_id"],
                "expected_delta_mm": gcmd.get_float("EXPECTED_DELTA", 0.0),
                "tolerance_mm": gcmd.get_float("TOLERANCE", 0.25, above=0.0),
                "confirm": gcmd.get_int("CONFIRM", 1, minval=0, maxval=2),
                "assert_position": bool(gcmd.get_int("ASSERT", 1, minval=0, maxval=1)),
                "phase": gcmd.get("PHASE", "repeatability"),
            }
        )
        try:
            response = self._request_visiond("measure_bed_y_relative", params)
            result = response.get("result") or {}
            self.last_bed_y_measurement = result
        finally:
            self._bed_y_light_off()
        self._respond_bed_y_measurement(
            gcmd, result, params, "Run-local bed Y measurement"
        )
        if params["assert_position"] and not result.get("accepted"):
            raise gcmd.error(
                "Run-local bed Y check failed: %s"
                % result.get("failure_reason", "measurement rejected")
            )
        return result

    def cmd_VISION_MEASURE_BED_Y(self, gcmd):
        if not self.bed_y_calibrated:
            raise gcmd.error(
                "VISION_MEASURE_BED_Y requires cameras.nozzle_cam calibration"
            )
        self._wait_moves()
        params = dict(self.bed_y_calibration)
        params.update(
            {
                "expected_y_mm": gcmd.get_float("EXPECTED_Y"),
                "tolerance_mm": gcmd.get_float("TOLERANCE", 0.25, above=0.0),
                "confirm": gcmd.get_int("CONFIRM", 1, minval=0, maxval=2),
                "assert_position": bool(gcmd.get_int("ASSERT", 1, minval=0, maxval=1)),
                "run": gcmd.get("RUN", "manual"),
                "step": gcmd.get_int("STEP", 0, minval=0),
                "toolhead_position": self._toolhead_position(),
                "gcode_position": self._gcode_position(),
                "homed_axes": self._homed_axes(),
            }
        )
        try:
            response = self._request_visiond("measure_bed_y", params)
            result = response.get("result") or {}
            self.last_bed_y_measurement = result
        finally:
            try:
                self.gcode.run_script_from_command("VISION_LIGHT_OFF")
            except Exception:
                pass
        measured = result.get("measured_y_mm")
        error = result.get("error_mm")
        correlation = result.get("correlation")
        retry = result.get("retry_used")
        gcmd.respond_info(
            "Bed Y camera measurement: measured=%.4f expected=%.4f "
            "error=%+.4f correlation=%.4f retry=%s run=%s step=%s"
            % (
                float(measured),
                float(params["expected_y_mm"]),
                float(error),
                float(correlation),
                retry,
                params["run"],
                params["step"],
            )
        )
        if params["assert_position"] and not result.get("accepted"):
            raise gcmd.error(
                "Bed Y camera check failed: %s"
                % result.get("failure_reason", "measurement rejected")
            )
        return result


def load_config(config):
    return Vision(config)
