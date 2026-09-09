# Interactive Eddy tap measurement helper.
#
# Copyright (C) 2026 Markus Emmenegger
# This file may be distributed under the terms of the GNU GPLv3 license.

import csv
import datetime
import io
import json
import math
import os
from pathlib import Path
import statistics
import tempfile
import uuid


COMPARISON_XY_TOLERANCE = 0.020
DEFAULT_RAW_DURATION = 0.200
ASCENT_APPROACH_CLEARANCE = 0.100
TRACE_ROOT = Path("/home/pi/printer_data/eddy")
# probe_eddy_current uses +/-99.9 mm as its explicit out-of-calibration
# sentinel.  Keep those values in the CSV for diagnosis, but never let them
# stretch the operator-facing plot axis to an otherwise meaningless 100 mm.
TRACE_INVALID_HEIGHT_LIMIT_MM = 99.0
TRACE_TAP_Z_WINDOW_MM = 0.25
TRACE_COLUMNS = (
    "run_id",
    "tap_index",
    "status",
    "phase",
    "event",
    "mcu_time_s",
    "elapsed_time_s",
    "commanded_x_mm",
    "commanded_y_mm",
    "commanded_z_mm",
    "frequency_hz",
    "stream_height_mm",
    "converted_height_mm",
)


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
        self.default_scan_nozzle_zs = config.get("scan_nozzle_zs", "0.5,1,2,3")
        self.last_raw_measurement = None
        self.last_raw_read = None
        self.last_scan_height_test = None
        self.last_stationary_scan_measurement = None
        self.last_tap_measurement = None
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
            "_EDDY_RAW_READ",
            self.cmd_EDDY_RAW_READ,
            desc="Read current Eddy frequency without moving the toolhead.",
        )
        self.gcode.register_command(
            "_EDDY_SCAN_HEIGHT_TEST",
            self.cmd_EDDY_SCAN_HEIGHT_TEST,
            desc="Verify stationary Eddy scan conversion across nozzle heights.",
        )
        self.gcode.register_command(
            "_EDDY_STATIONARY_SCAN_MEASURE",
            self.cmd_EDDY_STATIONARY_SCAN_MEASURE,
            desc="Repeat stationary Eddy scans at one physical bed point.",
        )

    def get_status(self, eventtime):
        return {
            "reference_x": self.reference_x,
            "reference_y": self.reference_y,
            "tap_threshold": self.tap_threshold,
            "default_count": self.default_count,
            "default_scan_nozzle_zs": self.default_scan_nozzle_zs,
            "last_raw_measurement": self.last_raw_measurement,
            "last_raw_read": self.last_raw_read,
            "last_scan_height_test": self.last_scan_height_test,
            "last_stationary_scan_measurement": self.last_stationary_scan_measurement,
            "last_tap_measurement": self.last_tap_measurement,
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

    @staticmethod
    def _atomic_write(path, payload, binary=False):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = "wb" if binary else "w"
        kwargs = {} if binary else {"encoding": "utf-8"}
        with tempfile.NamedTemporaryFile(
            mode=mode,
            dir=path.parent,
            prefix=".%s." % path.name,
            delete=False,
            **kwargs,
        ) as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, path)
        # The files are served directly by nginx.  NamedTemporaryFile creates
        # mode 0600, which would make the dashboard return HTTP 403 even
        # though the atomic publication itself succeeded.  Keep the atomic
        # replace, then explicitly grant the web server read access.
        os.chmod(path, 0o644)

    @staticmethod
    def _trace_event_for_row(row_time, record):
        events = (
            (record.get("trace_start"), "descent_start"),
            (record.get("trigger_time"), "analog_trigger"),
            (record.get("retract_start_time"), "retract_start"),
            (record.get("retract_end_time"), "retract_end"),
        )
        candidates = [
            (abs(row_time - float(timestamp)), label)
            for timestamp, label in events
            if timestamp is not None
        ]
        if not candidates:
            return ""
        distance, label = min(candidates)
        # Avoid assigning a distant event to an unrelated sample in a failed
        # or very sparse trace.  The exact event times remain in latest.json.
        return label if distance <= 0.020 else ""

    @staticmethod
    def _plot_height(value):
        """Return a finite, in-range converted height for plotting only."""
        if value is None:
            return None
        try:
            height = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(height) or abs(height) >= TRACE_INVALID_HEIGHT_LIMIT_MM:
            return None
        return height

    def _render_trace_plot(self, path, records, run_id, base_time):
        # Matplotlib is intentionally imported only after motion has finished;
        # TRACE must not add startup cost or sampling work to ordinary taps.
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        figure, axes = plt.subplots(4, 1, figsize=(14, 12))
        # The first three panels share elapsed time.  The fourth panel has a
        # deliberately independent X axis: it plots commanded nozzle Z, not
        # time, so sharing it would silently distort the local tap view.
        axes[1].sharex(axes[0])
        axes[2].sharex(axes[0])
        colours = plt.get_cmap("tab10")
        labels = (
            ("commanded_z", "Commanded nozzle Z (mm)"),
            ("frequency", "Native Eddy frequency (Hz)"),
            ("converted", "Frequency-converted Eddy height (mm)"),
        )
        plotted = False
        approach_plotted = False
        retract_plotted = False
        release_marker_plotted = False
        for record_index, record in enumerate(records):
            rows = record.get("rows", [])
            xs = [float(row["mcu_time"]) - base_time for row in rows]
            if not xs:
                continue
            colour = colours(record_index % 10)
            status = record.get("status", "unknown")
            tap_label = "tap %s (%s)" % (record.get("tap_index", "?"), status)
            series = (
                [row.get("commanded_z") for row in rows],
                [row.get("frequency_hz") for row in rows],
                [self._plot_height(row.get("converted_height_mm")) for row in rows],
            )
            for axis, values in zip(axes, series):
                valid = [
                    (x_value, value)
                    for x_value, value in zip(xs, values)
                    if value is not None
                ]
                if valid:
                    axis.plot(
                        [point[0] for point in valid],
                        [point[1] for point in valid],
                        color=colour,
                        label=tap_label,
                    )
                    plotted = True
            for timestamp, event_name in (
                (record.get("trigger_time"), "analog trigger"),
                (record.get("retract_start_time"), "retract start"),
            ):
                if timestamp is not None:
                    event_x = float(timestamp) - base_time
                    # Event times belong only on the elapsed-time panels; the
                    # fourth panel's X axis is commanded Z, not time.
                    for axis in axes[:3]:
                        axis.axvline(event_x, color=colour, alpha=0.25, linewidth=0.8)
                    axes[0].annotate(
                        event_name,
                        xy=(event_x, 0.98),
                        xycoords=("data", "axes fraction"),
                        rotation=90,
                        va="top",
                        fontsize=7,
                        color=colour,
                    )
            # Show the calibrated height against the actual commanded nozzle Z
            # near the trigger.  The approach and retract traces deliberately
            # use fixed colours so the physical hysteresis is easy to compare.
            trigger_z = None
            trigger_time = record.get("trigger_time")
            if trigger_time is not None:
                trigger_candidates = [
                    row for row in rows if row.get("commanded_z") is not None
                ]
                if trigger_candidates:
                    trigger_row = min(
                        trigger_candidates,
                        key=lambda row: abs(
                            float(row["mcu_time"]) - float(trigger_time)
                        ),
                    )
                    trigger_z = float(trigger_row["commanded_z"])
            approach = []
            retract = []
            for row in rows:
                try:
                    commanded_z = float(row["commanded_z"])
                except (KeyError, TypeError, ValueError):
                    continue
                converted_height = self._plot_height(row.get("converted_height_mm"))
                if converted_height is None:
                    continue
                if (
                    trigger_z is not None
                    and abs(commanded_z - trigger_z) > TRACE_TAP_Z_WINDOW_MM
                ):
                    continue
                point = (commanded_z, converted_height)
                if row.get("phase") == "retract":
                    retract.append(point)
                else:
                    approach.append(point)
            if approach:
                marker_stride = max(1, len(approach) // 24)
                axes[3].plot(
                    [point[0] for point in approach],
                    [point[1] for point in approach],
                    color="tab:blue",
                    linestyle="-",
                    linewidth=1.1,
                    marker="o",
                    markersize=4.5,
                    markevery=marker_stride,
                    markerfacecolor="white",
                    markeredgewidth=0.9,
                    label="Approach (circles)" if not approach_plotted else None,
                )
                approach_plotted = True
            if retract:
                marker_stride = max(1, len(retract) // 24)
                axes[3].plot(
                    [point[0] for point in retract],
                    [point[1] for point in retract],
                    color="tab:orange",
                    linestyle="--",
                    linewidth=1.1,
                    marker="x",
                    markersize=5,
                    markevery=marker_stride,
                    markeredgewidth=1.2,
                    label="Retract (crosses)" if not retract_plotted else None,
                )
                retract_plotted = True
            diagnostics = record.get("diagnostics") or {}
            fit_markers = (
                ("release_fit", "z_contact", "tab:green", "-.",
                 "Height-space release fit"),
            )
            for fit_name, value_name, colour, linestyle, label in fit_markers:
                value = (diagnostics.get(fit_name) or {}).get(value_name)
                try:
                    value = float(value)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(value):
                    continue
                if (trigger_z is not None and
                        abs(value - trigger_z) > TRACE_TAP_Z_WINDOW_MM):
                    continue
                show_label = not release_marker_plotted
                release_marker_plotted = True
                axes[3].axvline(
                    value,
                    color=colour,
                    linestyle=linestyle,
                    linewidth=1.1,
                    alpha=0.8,
                    label=label if show_label else None,
                )
        axes[3].set_title(
            "Commanded nozzle Z vs converted Eddy height (within %.2f mm of tap)"
            % TRACE_TAP_Z_WINDOW_MM
        )
        axes[3].set_xlabel("Commanded nozzle Z (mm)")
        axes[3].set_ylabel("Converted Eddy height (mm)")
        axes[3].grid(True, alpha=0.25)
        if (
            approach_plotted
            or retract_plotted
            or release_marker_plotted
        ):
            axes[3].legend(loc="best", fontsize=8)
        else:
            axes[3].text(
                0.5,
                0.5,
                "No in-range converted heights near tap",
                ha="center",
                va="center",
                transform=axes[3].transAxes,
            )
        for axis, (_, label) in zip(axes, labels):
            axis.set_ylabel(label)
            axis.grid(True, alpha=0.25)
        axes[2].set_xlabel("Elapsed time from first tap descent (s)")
        if plotted:
            axes[0].legend(loc="best", fontsize=8)
        else:
            axes[0].text(
                0.5,
                0.5,
                "No sensor samples were captured",
                ha="center",
                va="center",
                transform=axes[0].transAxes,
            )
        figure.suptitle("Eddy tap trace (%s)" % run_id)
        figure.tight_layout()
        figure.savefig(path, dpi=140)
        plt.close(figure)

    def _publish_tap_trace(self, records, *, x, y, count, threshold, error=None):
        now = datetime.datetime.now(datetime.timezone.utc)
        run_id = "%s-%s" % (
            now.strftime("%Y%m%d-%H%M%S"),
            uuid.uuid4().hex[:8],
        )
        root = TRACE_ROOT
        runs = root / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        timestamps = [
            float(record["trace_start"])
            for record in records
            if record.get("trace_start") is not None
        ]
        base_time = min(timestamps) if timestamps else 0.0
        csv_buffer = io.StringIO(newline="")
        writer = csv.DictWriter(csv_buffer, fieldnames=TRACE_COLUMNS)
        writer.writeheader()
        event_manifest = []
        for record_index, record in enumerate(records, start=1):
            record.setdefault("tap_index", record_index)
            for event_key, event_name in (
                ("trace_start", "descent_start"),
                ("trigger_time", "analog_trigger"),
                ("retract_start_time", "retract_start"),
                ("retract_end_time", "retract_end"),
            ):
                timestamp = record.get(event_key)
                if timestamp is not None:
                    event_manifest.append(
                        {
                            "tap_index": record["tap_index"],
                            "event": event_name,
                            "mcu_time_s": float(timestamp),
                            "elapsed_time_s": float(timestamp) - base_time,
                        }
                    )
            for row in record.get("rows", []):
                writer.writerow(
                    {
                        "run_id": run_id,
                        "tap_index": record["tap_index"],
                        "status": record.get("status", "unknown"),
                        "phase": row.get("phase", ""),
                        "event": self._trace_event_for_row(
                            float(row["mcu_time"]), record
                        ),
                        "mcu_time_s": "%.9f" % float(row["mcu_time"]),
                        "elapsed_time_s": "%.9f" % (float(row["mcu_time"]) - base_time),
                        "commanded_x_mm": row.get("commanded_x"),
                        "commanded_y_mm": row.get("commanded_y"),
                        "commanded_z_mm": row.get("commanded_z"),
                        "frequency_hz": row.get("frequency_hz"),
                        "stream_height_mm": row.get("stream_height_mm"),
                        "converted_height_mm": row.get("converted_height_mm"),
                    }
                )
        metadata = {
            "schema_version": 1,
            "run_id": run_id,
            "status": "failed" if error else "completed",
            "error": None if error is None else str(error),
            "reference": {"x": float(x), "y": float(y)},
            "count_requested": int(count),
            "tap_count_recorded": len(records),
            "threshold": float(threshold),
            "created_at": now.isoformat(),
            "base_mcu_time_s": base_time,
            "events": event_manifest,
            "traces": [
                {key: value for key, value in record.items() if key != "rows"}
                for record in records
            ],
        }
        run_csv = runs / (run_id + ".csv")
        latest_csv = root / "latest.csv"
        csv_payload = csv_buffer.getvalue()
        self._atomic_write(run_csv, csv_payload)
        self._atomic_write(latest_csv, csv_payload)
        run_plot = runs / (run_id + ".png")
        plot_error = None
        try:
            self._render_trace_plot(run_plot, records, run_id, base_time)
            self._atomic_write(root / "latest.png", run_plot.read_bytes(), binary=True)
        except Exception as exc:  # plotting must not turn a tap into a failure
            plot_error = str(exc)
        metadata["plot_error"] = plot_error
        metadata["artifacts"] = {
            "csv": "/eddy/latest.csv",
            "plot": "/eddy/latest.png" if plot_error is None else None,
            "run_csv": "/eddy/runs/%s.csv" % run_id,
            "run_plot": "/eddy/runs/%s.png" % run_id if plot_error is None else None,
        }
        metadata_payload = json.dumps(metadata, indent=2, sort_keys=True) + "\n"
        self._atomic_write(runs / (run_id + ".json"), metadata_payload)
        self._atomic_write(root / "latest.json", metadata_payload)
        return metadata

    def _move_to_reference(self, toolhead, x, y, xy_speed=None, start_z=None):
        if xy_speed is None:
            xy_speed = self.move_speed
        if start_z is None:
            start_z = self.move_z
        # METHOD=tap is deliberately unlike normal Eddy height probing:
        # the nozzle itself touches the bed at (x, y).  Eddy only observes
        # the resulting machine deformation and supplies the tap trigger.
        # Therefore these are nozzle coordinates.  Do not apply the Eddy
        # coil's x/y offsets here; doing so moves the nozzle away from the
        # requested physical contact point and corrupts the tap datum.
        self.gcode.run_script_from_command(
            "G90\nG1 Z%.3f F%.0f\nG1 X%.3f Y%.3f F%.0f"
            % (
                start_z,
                self.move_speed * 60.0,
                x,
                y,
                xy_speed * 60.0,
            )
        )
        toolhead.wait_moves()

    def _report_tap_failure(
        self, gcmd, probe, tap_index, count, start_position, target_z
    ):
        """Explain a rejected tap fit using compact aggregate diagnostics."""
        diagnostics = probe.get_last_tap_diagnostics() or {}
        gcmd.respond_info(
            "EDDY_TAP_MEASURE tap %d/%d rejected: planned nozzle descent "
            "start_z=%.6f -> lower_z=%.6f (%.6f mm)"
            % (
                tap_index,
                count,
                start_position[2],
                target_z,
                start_position[2] - target_z,
            )
        )
        if diagnostics:
            gcmd.respond_info(
                "EDDY_TAP_MEASURE pullback summary: samples=%d "
                "toolhead_z=%.6f..%.6f frequency_hz=%.3f..%.3f; "
                "this is the post-trigger retract window, not the descent"
                % (
                    diagnostics.get("sample_count", 0),
                    diagnostics.get("min_toolhead_z", float("nan")),
                    diagnostics.get("max_toolhead_z", float("nan")),
                    diagnostics.get("min_frequency_hz", float("nan")),
                    diagnostics.get("max_frequency_hz", float("nan")),
                )
            )
        if diagnostics:
            release_fit = diagnostics.get("release_fit") or {}
            candidates = diagnostics.get("release_candidates") or {}
            gcmd.respond_info(
                "EDDY_TAP_MEASURE release fit: intersection_z=%s split_z=%s "
                "contact_slope=%s free_slope=%s delta=%s"
                % (
                    self._format_optional_fit_value(release_fit.get("z_contact")),
                    self._format_optional_fit_value(release_fit.get("split_z")),
                    self._format_optional_fit_value(
                        release_fit.get("contact_height_slope")
                    ),
                    self._format_optional_fit_value(
                        release_fit.get("free_height_slope")
                    ),
                    self._format_optional_fit_value(
                        release_fit.get("height_slope_delta")
                    ),
                )
            )
            gcmd.respond_info(
                "EDDY_TAP_MEASURE release candidates: total=%s valid=%s "
                "rejected=%s "
                "status=%s reason=%s"
                % (
                    candidates.get("candidate_count", 0),
                    candidates.get("valid_candidate_count", 0),
                    candidates.get("rejections", {}),
                    diagnostics.get("fit_status", "unknown"),
                    diagnostics.get("fit_failure", "none"),
                )
            )

    @staticmethod
    def _format_optional_fit_value(value):
        return "none" if value is None else "%.6f" % float(value)

    def _active_mesh_transform_z(self, toolhead):
        """Return physical Z minus logical Z at the current XY, if meshed."""
        eventtime = self.printer.get_reactor().monotonic()
        bed_mesh = self.printer.lookup_object("bed_mesh")
        mesh_status = bed_mesh.get_status(eventtime)
        mesh_matrix = mesh_status.get("mesh_matrix", [])
        if not mesh_status.get("profile_name") or not any(mesh_matrix):
            return None

        gcode_move = self.printer.lookup_object("gcode_move")
        gcode_status = gcode_move.get_status(eventtime)
        gcode_position = gcode_status.get("gcode_position")
        toolhead_position = toolhead.get_position()
        if gcode_position is None or len(gcode_position) < 3:
            raise self.gcode.error(
                "EDDY_TAP_MEASURE cannot read logical G-code Z with active bed mesh"
            )
        if len(toolhead_position) < 3:
            raise self.gcode.error(
                "EDDY_TAP_MEASURE cannot read physical toolhead Z with active bed mesh"
            )
        return float(toolhead_position[2]) - float(gcode_position[2])

    @staticmethod
    def _commanded_z_for_tap(tap_z, mesh_transform_z):
        """Map a raw physical tap Z to the logical Z command for that plane."""
        return float(tap_z) - float(mesh_transform_z)

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

    def _move_to_coil_target(self, toolhead, nozzle_x, nozzle_y, xy_speed=None):
        if xy_speed is None:
            xy_speed = self.move_speed
        self.gcode.run_script_from_command(
            "G90\nG1 Z%.3f F%.0f\nG1 X%.3f Y%.3f F%.0f"
            % (
                self.move_z,
                self.move_speed * 60.0,
                nozzle_x,
                nozzle_y,
                xy_speed * 60.0,
            )
        )
        toolhead.wait_moves()

    def _move_z(self, toolhead, nozzle_z):
        self.gcode.run_script_from_command(
            "G90\nG1 Z%.3f F%.0f" % (nozzle_z, self.move_speed * 60.0)
        )
        toolhead.wait_moves()

    @staticmethod
    def _optional_float(gcmd, name):
        value = gcmd.get(name, None)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise gcmd.error("%s must be a number" % name) from exc

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

    def _raw_read_report(self, raw):
        """Format a stationary read without implying a probe or bed target.

        EDDY_RAW_READ is deliberately a sensor-only diagnostic.  In
        particular, do not route it through the target-pose or probe helpers:
        those helpers move the nozzle/coil and would make a supposedly
        stationary frequency check surprisingly dangerous.
        """
        position = raw["toolhead_position"]
        return (
            "EDDY_RAW_READ: no motion; toolhead=(%.3f, %.3f, %.3f) "
            "raw_frequency_hz=%.3f raw_frequency_span_hz=%.3f samples=%d "
            "built_in_sensor_height=%.6f stream_height=%.6f temperature=%s"
            % (
                position[0],
                position[1],
                position[2],
                raw["raw_frequency_hz"],
                raw["raw_frequency_span_hz"],
                raw["sample_count"],
                raw["built_in_sensor_height"],
                raw["stream_height"],
                (
                    "unknown"
                    if raw["temperature"] is None
                    else "%.3f" % raw["temperature"]
                ),
            )
        )

    def cmd_EDDY_RAW_READ(self, gcmd):
        """Read the current Eddy frequency without issuing any motion.

        This intentionally does not require homing, a selected tool, or a
        cleared mesh.  It observes wherever the machine already is.  Waiting
        for queued moves and dwelling only allow the sensor stream to settle;
        neither operation commands a move.
        """
        toolhead = self.printer.lookup_object("toolhead")
        duration = gcmd.get_float("DURATION", DEFAULT_RAW_DURATION, above=0.0)
        toolhead.wait_moves()
        raw = self._capture_raw_measurement(toolhead, duration)
        self.last_raw_read = {
            "duration": duration,
            **raw,
        }
        gcmd.respond_info(self._raw_read_report(raw))

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

    def _stationary_scan_measurement(
        self,
        gcmd,
        toolhead,
        bed_x,
        bed_y,
        nozzle_x,
        nozzle_y,
        nozzle_z,
        count,
        duration,
        xy_speed,
        label,
    ):
        approach_z = nozzle_z - ASCENT_APPROACH_CLEARANCE
        self._require_nozzle_z_in_limits(toolhead, nozzle_z, label)
        self._require_nozzle_z_in_limits(toolhead, approach_z, label)
        results = []
        try:
            self._move_to_coil_target(toolhead, nozzle_x, nozzle_y, xy_speed)
            self._move_z(toolhead, approach_z)
            self._move_z(toolhead, nozzle_z)
            for sample_index in range(count):
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
                    "%s sample %d/%d: scan_bed_z=%.6f raw_frequency_hz=%.3f "
                    "implied_bed_z=%.6f temperature=%s"
                    % (
                        label,
                        sample_index + 1,
                        count,
                        result["scan_bed_z"],
                        result["raw_frequency_hz"],
                        result["implied_bed_z"],
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
        raw_frequencies = [result["raw_frequency_hz"] for result in results]
        temperatures = [result["temperature"] for result in results]
        known_temperatures = [value for value in temperatures if value is not None]
        measurement = {
            "bed_x": bed_x,
            "bed_y": bed_y,
            "nozzle_x": nozzle_x,
            "nozzle_y": nozzle_y,
            "requested_nozzle_z": nozzle_z,
            "count": count,
            "duration": duration,
            "results": results,
            "scan_bed_z_median": statistics.median(scan_values),
            "scan_bed_z_span": max(scan_values) - min(scan_values),
            "raw_frequency_hz_median": statistics.median(raw_frequencies),
            "raw_frequency_hz_span": max(raw_frequencies) - min(raw_frequencies),
            "temperature_span": (
                None
                if not known_temperatures
                else max(known_temperatures) - min(known_temperatures)
            ),
        }
        gcmd.respond_info(
            "%s summary: bed=(%.3f, %.3f) nozzle=(%.3f, %.3f) "
            "scan_bed_z_median=%.6f scan_bed_z_span=%.6f "
            "raw_frequency_hz_median=%.3f raw_frequency_hz_span=%.3f"
            % (
                label,
                bed_x,
                bed_y,
                nozzle_x,
                nozzle_y,
                measurement["scan_bed_z_median"],
                measurement["scan_bed_z_span"],
                measurement["raw_frequency_hz_median"],
                measurement["raw_frequency_hz_span"],
            )
        )
        return measurement

    def cmd_EDDY_TAP_MEASURE(self, gcmd):
        command_name = "EDDY_TAP_MEASURE"
        toolhead = self._require_homed(command_name)
        x = gcmd.get_float("X", self.reference_x)
        y = gcmd.get_float("Y", self.reference_y)
        threshold = gcmd.get_float("THRESHOLD", self.tap_threshold, above=0.0)
        count = gcmd.get_int("COUNT", self.default_count, minval=1, maxval=100)
        eddy_mode = gcmd.get("EDDY_MODE", "probe").lower()
        if eddy_mode not in ("none", "probe", "scan"):
            raise gcmd.error("EDDY_MODE must be none, probe, or scan")
        xy_speed = gcmd.get_float("XY_SPEED", self.move_speed, above=0.0)
        scan_count = gcmd.get_int("SCAN_COUNT", 3, minval=1, maxval=20)
        scan_height = gcmd.get_float("SCAN_HEIGHT", 2.0, above=0.0)
        duration = gcmd.get_float("DURATION", DEFAULT_RAW_DURATION, above=0.0)
        trace = bool(gcmd.get_int("TRACE", 0, minval=0, maxval=1))
        # The staged reference search may deliberately inspect a trigger that
        # lands exactly on a band endpoint.  It needs the compact diagnostics
        # to decide whether that endpoint trigger is ambiguous and should be
        # retried in the next overlapping band.  This is an internal escape
        # hatch; the public EDDY_TAP_MEASURE command remains fail-fast.
        allow_rejected = bool(gcmd.get_int("ALLOW_REJECTED", 0, minval=0, maxval=1))
        start_z = gcmd.get_float("START_Z", self.move_z, above=0.0)
        target_z = gcmd.get_float(
            "TAP_TARGET_Z",
            self._axis_value(
                toolhead.get_status(self.printer.get_reactor().monotonic()).get(
                    "axis_minimum"
                ),
                2,
                "z",
            ),
        )
        retract = gcmd.get_float("SAMPLE_RETRACT_DIST", 4.0, above=0.0)
        if eddy_mode == "scan":
            self._require_t0_and_clear_mesh(command_name)

        self._move_to_reference(toolhead, x, y, xy_speed, start_z)
        mesh_transform_z = self._active_mesh_transform_z(toolhead)
        gcmd.respond_info(
            "EDDY_TAP_MEASURE: reference=(%.3f, %.3f), taps=%d, threshold=%.3f "
            "eddy_mode=%s start_z=%.3f target_z=%.3f retract=%.3f xy_speed=%.3f"
            % (x, y, count, threshold, eddy_mode, start_z, target_z, retract, xy_speed)
        )

        params = dict(gcmd.get_command_parameters())
        params.update(
            {
                "METHOD": "tap",
                "TAP_THRESHOLD": "%.3f" % threshold,
                "SAMPLES": "1",
                "TAP_TARGET_Z": "%.6f" % target_z,
                "SAMPLE_RETRACT_DIST": "%.6f" % retract,
                "TRACE": "1" if trace else "0",
            }
        )
        probe_gcmd = self.gcode.create_gcode_command(
            "_EDDY_TAP_MEASURE", "_EDDY_TAP_MEASURE", params
        )
        probe = self.printer.lookup_object("probe")
        probe_session = probe.start_probe_session(probe_gcmd)
        results = []
        tap_samples = []
        trace_records = []
        trace_metadata = None

        def trace_session():
            """Return the hardware tap session behind Klipper's wrapper.

            ``probe.start_probe_session()`` normally returns Klipper's
            ``ProbeSessionHelper``.  The trace API belongs to the underlying
            EddyTap session, not that generic wrapper.  Keep this lookup
            local to the diagnostic path so TRACE can never change normal
            probing behaviour.
            """
            hardware_session = getattr(probe_session, "hw_probe_session", None)
            if hardware_session is not None and any(
                callable(getattr(hardware_session, name, None))
                for name in ("flush_tap_trace", "get_last_tap_trace")
            ):
                return hardware_session
            hardware_session = getattr(probe, "eddy_tap", None)
            if hardware_session is not None and any(
                callable(getattr(hardware_session, name, None))
                for name in ("flush_tap_trace", "get_last_tap_trace")
            ):
                return hardware_session
            # Preserve compatibility with the lightweight test/dummy session
            # and with future Klipper versions that may expose the methods on
            # the wrapper itself.
            return probe_session

        def collect_trace(status=None, tap_index=None):
            if not trace:
                return
            session = trace_session()
            try:
                flush_trace = getattr(session, "flush_tap_trace", None)
                if flush_trace is not None:
                    flush_trace()
            except Exception as trace_exc:
                gcmd.respond_info(
                    "EDDY_TAP_MEASURE trace flush warning: %s" % trace_exc
                )
            try:
                get_trace = getattr(session, "get_last_tap_trace", None)
                record = get_trace() if get_trace is not None else None
            except Exception as trace_exc:
                gcmd.respond_info("EDDY_TAP_MEASURE trace read warning: %s" % trace_exc)
                record = None
            if record is None:
                record = {"status": status or "error", "rows": []}
            elif status and record.get("status") == "pending":
                record["status"] = status
            if tap_index is not None:
                record["tap_index"] = tap_index
            try:
                diagnostics = probe.get_last_tap_diagnostics() or {}
            except Exception:
                diagnostics = {}
            if diagnostics:
                record["diagnostics"] = diagnostics
            trace_records.append(record)

        try:
            for index in range(count):
                tap_start_position = [float(value) for value in toolhead.get_position()]
                try:
                    probe_session.run_probe(probe_gcmd)
                    sample = probe_session.pull_probed_results()
                except Exception as exc:
                    collect_trace(
                        (
                            "no_trigger"
                            if "No trigger on probe after full movement" in str(exc)
                            else "rejected"
                        ),
                        index + 1,
                    )
                    if "No trigger on probe after full movement" in str(exc):
                        gcmd.respond_info(
                            "EDDY_TAP_MEASURE no trigger: start_z=%.6f "
                            "target_z=%.6f; band completed safely"
                            % (tap_start_position[2], target_z)
                        )
                        self.last_tap_measurement = {
                            "eddy_mode": eddy_mode,
                            "bed_x": x,
                            "bed_y": y,
                            "tap": {
                                "status": "no_trigger",
                                "count": 0,
                                "samples": [],
                                "start_z": start_z,
                                "target_z": target_z,
                            },
                            "mesh": {"active_transform_z": mesh_transform_z},
                        }
                        return
                    if allow_rejected:
                        diagnostics = probe.get_last_tap_diagnostics() or {}
                        self.last_tap_measurement = {
                            "eddy_mode": eddy_mode,
                            "bed_x": x,
                            "bed_y": y,
                            "tap": {
                                "status": "rejected",
                                "count": 0,
                                "samples": [],
                                "start_z": start_z,
                                "target_z": target_z,
                                "error": str(exc),
                                "diagnostics": diagnostics,
                            },
                            "mesh": {"active_transform_z": mesh_transform_z},
                        }
                        self._report_tap_failure(
                            gcmd,
                            probe,
                            index + 1,
                            count,
                            tap_start_position,
                            target_z,
                        )
                        return
                    self._report_tap_failure(
                        gcmd,
                        probe,
                        index + 1,
                        count,
                        tap_start_position,
                        target_z,
                    )
                    raise
                if len(sample) != 1:
                    raise gcmd.error(
                        "EDDY_TAP_MEASURE expected one result, got %d" % len(sample)
                    )
                result = sample[0]
                collect_trace(tap_index=index + 1)
                results.append(float(result.bed_z))
                tap_x = float(result.bed_x)
                tap_y = float(result.bed_y)
                if (
                    abs(tap_x - x) > COMPARISON_XY_TOLERANCE
                    or abs(tap_y - y) > COMPARISON_XY_TOLERANCE
                ):
                    raise gcmd.error(
                        "EDDY_TAP_MEASURE Tap physical point mismatch: "
                        "expected=(%.3f, %.3f), got=(%.3f, %.3f)" % (x, y, tap_x, tap_y)
                    )
                tap_samples.append({"x": tap_x, "y": tap_y, "z": float(result.bed_z)})
                diagnostics = probe.get_last_tap_diagnostics() or {}
                if diagnostics:
                    release_fit = diagnostics.get("release_fit") or {}
                    gcmd.respond_info(
                        "EDDY_TAP_MEASURE fit accepted: intersection_z=%s "
                        "free_height_slope=%s"
                        % (
                            self._format_optional_fit_value(
                                release_fit.get("z_contact")
                            ),
                            self._format_optional_fit_value(
                                release_fit.get("free_height_slope")
                            ),
                        )
                    )
                gcmd.respond_info(
                    "EDDY_TAP_MEASURE tap %d/%d: contact=(%.3f, %.3f, %.6f) "
                    "post_retract_z=%.6f"
                    % (
                        index + 1,
                        count,
                        tap_x,
                        tap_y,
                        result.bed_z,
                        toolhead.get_position()[2],
                    )
                )
        finally:
            try:
                probe_session.end_probe_session()
            except Exception as end_exc:
                # TRACE is observational.  A cleanup mismatch after a
                # rejected probe must not mask the original tap error or
                # turn a diagnostic failure into a Klipper shutdown.
                if trace:
                    gcmd.respond_info(
                        "EDDY_TAP_MEASURE trace cleanup warning: %s" % end_exc
                    )
                else:
                    raise
            if trace:
                try:
                    trace_failed = len(trace_records) != count or any(
                        record.get("status") != "success" for record in trace_records
                    )
                    trace_metadata = self._publish_tap_trace(
                        trace_records,
                        x=x,
                        y=y,
                        count=count,
                        threshold=threshold,
                        error="tap batch aborted" if trace_failed else None,
                    )
                    gcmd.respond_info(
                        "EDDY_TAP_MEASURE trace: %s taps, CSV=%s plot=%s"
                        % (
                            trace_metadata["tap_count_recorded"],
                            trace_metadata["artifacts"]["csv"],
                            trace_metadata["artifacts"]["plot"] or "unavailable",
                        )
                    )
                    if self.last_tap_measurement is not None:
                        self.last_tap_measurement["trace"] = {
                            "run_id": trace_metadata["run_id"],
                            "status": trace_metadata["status"],
                            "artifacts": trace_metadata["artifacts"],
                        }
                except Exception as trace_exc:
                    # A filesystem or renderer problem is diagnostic-only;
                    # never let it shut down an otherwise healthy printer.
                    gcmd.respond_info(
                        "EDDY_TAP_MEASURE trace publication warning: %s" % trace_exc
                    )

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

        commanded_z_for_tap_median = None
        if mesh_transform_z is None:
            gcmd.respond_info(
                "EDDY_TAP_MEASURE mesh: inactive; "
                "commanded_z_for_tap_median=unavailable"
            )
        else:
            commanded_z_for_tap_median = self._commanded_z_for_tap(
                median, mesh_transform_z
            )
            gcmd.respond_info(
                "EDDY_TAP_MEASURE mesh: active_transform_z=%.6f "
                "tap_median_z=%.6f commanded_z_for_tap_median=%.6f"
                % (mesh_transform_z, median, commanded_z_for_tap_median)
            )

        measurement = {
            "eddy_mode": eddy_mode,
            "bed_x": x,
            "bed_y": y,
            "xy_speed": xy_speed,
            "tap": {
                "count": count,
                "samples": tap_samples,
                "mean": mean,
                "median": median,
                "span": span,
                "standard_deviation": standard_deviation,
            },
            "tap_coordinate_deltas": [
                {"x": sample["x"] - x, "y": sample["y"] - y} for sample in tap_samples
            ],
            "mesh": {
                "active_transform_z": mesh_transform_z,
                "commanded_z_for_tap_median": commanded_z_for_tap_median,
            },
        }
        if trace_metadata is not None:
            measurement["trace"] = {
                "run_id": trace_metadata["run_id"],
                "status": trace_metadata["status"],
                "artifacts": trace_metadata["artifacts"],
            }
        self.last_tap_measurement = measurement

        if eddy_mode == "none":
            return

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
            measurement["eddy"] = {
                "skipped": "coil target is unreachable",
                "requested_nozzle_x": requested_pose[0],
                "requested_nozzle_y": requested_pose[1],
                "limits": bounds,
            }
            return

        nozzle_x, nozzle_y = coil_pose
        measurement["coil_nozzle_x"] = nozzle_x
        measurement["coil_nozzle_y"] = nozzle_y
        if eddy_mode == "scan":
            nozzle_z = median + scan_height
            stationary = self._stationary_scan_measurement(
                gcmd,
                toolhead,
                x,
                y,
                nozzle_x,
                nozzle_y,
                nozzle_z,
                scan_count,
                duration,
                xy_speed,
                command_name,
            )
            measurement["stationary_scan"] = stationary
            measurement["scan_coordinate_deltas"] = [
                {
                    "x": float(sample["scan_bed_x"]) - x,
                    "y": float(sample["scan_bed_y"]) - y,
                }
                for sample in stationary["results"]
            ]
            measurement["delta_scan_minus_tap"] = (
                stationary["scan_bed_z_median"] - median
            )
            gcmd.respond_info(
                "EDDY_TAP_MEASURE comparison: tap_median=%.6f scan_median=%.6f "
                "delta_scan_minus_tap=%.6f target=(%.3f, %.3f) "
                "tap=(%.3f, %.3f) scan=(%.3f, %.3f) nozzle=(%.3f, %.3f)"
                % (
                    median,
                    stationary["scan_bed_z_median"],
                    measurement["delta_scan_minus_tap"],
                    x,
                    y,
                    tap_samples[-1]["x"],
                    tap_samples[-1]["y"],
                    stationary["results"][-1]["scan_bed_x"],
                    stationary["results"][-1]["scan_bed_y"],
                    nozzle_x,
                    nozzle_y,
                )
            )
            return

        self._move_to_coil_target(toolhead, nozzle_x, nozzle_y, xy_speed)
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
        self._lift_to_safe_z(toolhead)
        eddy_probe_z = float(result.bed_z)
        measurement["regular_probe"] = {
            "bed_x": float(result.bed_x),
            "bed_y": float(result.bed_y),
            "bed_z": eddy_probe_z,
        }
        measurement["delta_probe_minus_tap"] = eddy_probe_z - median
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
        safe_travel = gcmd.get_int("SAFE_TRAVEL", 1, minval=0, maxval=1)
        lift_after = gcmd.get_int("LIFT_AFTER", 1, minval=0, maxval=1)
        approach_z = self._optional_float(gcmd, "APPROACH_Z")
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
        completed = False
        try:
            self._require_nozzle_z_in_limits(toolhead, nozzle_z, command_name)
            if approach_z is not None:
                self._require_nozzle_z_in_limits(toolhead, approach_z, command_name)
                if approach_z >= nozzle_z:
                    raise gcmd.error(
                        "APPROACH_Z %.3f must be below requested nozzle Z %.3f"
                        % (approach_z, nozzle_z)
                    )
            if safe_travel:
                self._move_to_coil_target(toolhead, nozzle_x, nozzle_y)
            else:
                current_position = toolhead.get_position()
                if (
                    abs(current_position[0] - nozzle_x) > COMPARISON_XY_TOLERANCE
                    or abs(current_position[1] - nozzle_y) > COMPARISON_XY_TOLERANCE
                ):
                    raise gcmd.error(
                        "SAFE_TRAVEL=0 requires the coil already be over the target; "
                        "expected nozzle=(%.3f, %.3f), current=(%.3f, %.3f)"
                        % (
                            nozzle_x,
                            nozzle_y,
                            current_position[0],
                            current_position[1],
                        )
                    )
            if approach_z is not None:
                self._move_z(toolhead, approach_z)
            self._move_z(toolhead, nozzle_z)
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
            completed = True
        finally:
            if lift_after or not completed:
                self._lift_to_safe_z(toolhead)

    def cmd_EDDY_STATIONARY_SCAN_MEASURE(self, gcmd):
        command_name = "EDDY_STATIONARY_SCAN_MEASURE"
        toolhead = self._require_scan_ready(command_name)
        bed_x = gcmd.get_float("X", self.reference_x)
        bed_y = gcmd.get_float("Y", self.reference_y)
        nozzle_z = gcmd.get_float("Z", 2.0, above=0.0)
        count = gcmd.get_int("COUNT", 3, minval=1, maxval=20)
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
        xy_speed = gcmd.get_float("XY_SPEED", self.move_speed, above=0.0)
        measurement = self._stationary_scan_measurement(
            gcmd,
            toolhead,
            bed_x,
            bed_y,
            nozzle_x,
            nozzle_y,
            nozzle_z,
            count,
            duration,
            xy_speed,
            command_name,
        )
        self.last_stationary_scan_measurement = measurement

    def cmd_EDDY_SCAN_HEIGHT_TEST(self, gcmd):
        command_name = "EDDY_SCAN_HEIGHT_TEST"
        toolhead = self._require_scan_ready(command_name)
        bed_x = gcmd.get_float("X", self.reference_x)
        bed_y = gcmd.get_float("Y", self.reference_y)
        duration = gcmd.get_float("DURATION", DEFAULT_RAW_DURATION, above=0.0)
        nozzle_zs = self._parse_nozzle_zs(
            gcmd.get("NOZZLE_ZS", self.default_scan_nozzle_zs), gcmd
        )
        if any(high <= low for low, high in zip(nozzle_zs, nozzle_zs[1:])):
            raise gcmd.error(
                "NOZZLE_ZS must be strictly ascending so each measurement is approached from below"
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
            approach_z = nozzle_zs[0] - ASCENT_APPROACH_CLEARANCE
            self._require_nozzle_z_in_limits(toolhead, approach_z, command_name)
            self._move_to_coil_target(toolhead, nozzle_x, nozzle_y)
            self._move_z(toolhead, approach_z)
            for nozzle_z in nozzle_zs:
                self._move_z(toolhead, nozzle_z)
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
