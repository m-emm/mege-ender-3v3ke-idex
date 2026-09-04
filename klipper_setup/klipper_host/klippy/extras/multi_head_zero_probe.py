# Multi-head-zero contact measurement support.
#
# Copyright (C) 2026 Markus Emmenegger
# This file may be distributed under the terms of the GNU GPLv3 license.

from . import homing


class MultiHeadZeroProbe:
    """Perform guarded vertical contacts with the multi-head-zero switch."""

    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.pin = config.get("pin")
        self.clearance_z = config.getfloat("clearance_z", 2.5, above=0.0)
        self.approach_z = config.getfloat("approach_z", 2.0)
        self.target_z = config.getfloat("target_z", -1.0)
        self.travel_speed = config.getfloat("travel_speed", 20.0, above=0.0)
        self.probe_speed = config.getfloat("probe_speed", 1.0, above=0.0)
        self.mcu_endstop = self.printer.lookup_object("pins").setup_pin(
            "endstop", self.pin
        )
        self.last_measurement = None
        self.last_state = "UNKNOWN"
        self.printer.register_event_handler(
            "klippy:mcu_identify", self._handle_mcu_identify
        )
        self.gcode.register_command(
            "MULTI_HEAD_ZERO_CONTACT",
            self.cmd_MULTI_HEAD_ZERO_CONTACT,
            desc="Perform one guarded multi-head-zero vertical contact.",
        )
        self.gcode.register_command(
            "QUERY_MULTI_HEAD_ZERO",
            self.cmd_QUERY_MULTI_HEAD_ZERO,
            desc="Report the current multi-head-zero switch state.",
        )

    def _handle_mcu_identify(self):
        kin = self.printer.lookup_object("toolhead").get_kinematics()
        for stepper in kin.get_steppers():
            if stepper.is_active_axis("z"):
                self.mcu_endstop.add_stepper(stepper)

    def get_status(self, _eventtime):
        return {
            "pin": self.pin,
            "state": self.last_state,
            "clearance_z": self.clearance_z,
            "approach_z": self.approach_z,
            "target_z": self.target_z,
            "travel_speed": self.travel_speed,
            "probe_speed": self.probe_speed,
            "last_measurement": self.last_measurement,
        }

    @staticmethod
    def _axis_value(value, axis_index):
        return float(value[axis_index])

    def _switch_state(self, toolhead):
        print_time = toolhead.get_last_move_time()
        state = (
            "TRIGGERED" if self.mcu_endstop.query_endstop(print_time) else "RELEASED"
        )
        self.last_state = state
        return state

    def _require_homed_idle_unmeshed(self, command_name):
        eventtime = self.printer.get_reactor().monotonic()
        toolhead = self.printer.lookup_object("toolhead")
        homed_axes = toolhead.get_status(eventtime).get("homed_axes", "")
        if not all(axis in homed_axes for axis in "xyz"):
            raise self.gcode.error(
                "%s requires XYZ homing; homed_axes=%s" % (command_name, homed_axes)
            )
        print_state = (
            self.printer.lookup_object("print_stats").get_status(eventtime).get("state")
        )
        if print_state not in {"standby", "complete", "cancelled", "error"}:
            raise self.gcode.error(
                "%s requires an idle printer; print_stats.state=%s"
                % (command_name, print_state)
            )
        mesh_status = self.printer.lookup_object("bed_mesh").get_status(eventtime)
        if mesh_status.get("profile_name") or any(mesh_status.get("mesh_matrix", [])):
            raise self.gcode.error(
                "%s requires no active bed mesh; run BED_MESH_CLEAR first"
                % command_name
            )
        return toolhead

    def _require_active_tool(self, tool):
        active_tool = (
            self.printer.lookup_object("idex_manual_tuning")
            .get_status(self.printer.get_reactor().monotonic())
            .get("active_tool")
        )
        if active_tool != tool:
            raise self.gcode.error(
                "MULTI_HEAD_ZERO_CONTACT TOOL=%d requires active T%d; select T%d first"
                % (tool, tool, tool)
            )
        return active_tool

    def _require_limits(self, toolhead, x, y):
        status = toolhead.get_status(self.printer.get_reactor().monotonic())
        axis_minimum = status.get("axis_minimum")
        axis_maximum = status.get("axis_maximum")
        if axis_minimum is None or axis_maximum is None:
            raise self.gcode.error("MULTI_HEAD_ZERO_CONTACT cannot read axis limits")
        limits = [
            (
                "X",
                x,
                self._axis_value(axis_minimum, 0),
                self._axis_value(axis_maximum, 0),
            ),
            (
                "Y",
                y,
                self._axis_value(axis_minimum, 1),
                self._axis_value(axis_maximum, 1),
            ),
            (
                "clearance Z",
                self.clearance_z,
                self._axis_value(axis_minimum, 2),
                self._axis_value(axis_maximum, 2),
            ),
            (
                "approach Z",
                self.approach_z,
                self._axis_value(axis_minimum, 2),
                self._axis_value(axis_maximum, 2),
            ),
            (
                "target Z",
                self.target_z,
                self._axis_value(axis_minimum, 2),
                self._axis_value(axis_maximum, 2),
            ),
        ]
        for label, value, minimum, maximum in limits:
            if not minimum <= value <= maximum:
                raise self.gcode.error(
                    "MULTI_HEAD_ZERO_CONTACT %s %.3f is outside limits [%.3f, %.3f]"
                    % (label, value, minimum, maximum)
                )
        if not self.clearance_z > self.approach_z > self.target_z:
            raise self.gcode.error(
                "MULTI_HEAD_ZERO_CONTACT requires clearance_z > approach_z > target_z"
            )

    def _gcode_origin(self):
        origin = (
            self.printer.lookup_object("gcode_move")
            .get_status(self.printer.get_reactor().monotonic())
            .get("homing_origin", [0.0, 0.0, 0.0])
        )
        return [float(value) for value in origin]

    def _move_to_start(self, toolhead, x, y):
        origin = self._gcode_origin()
        gcode_x = x - origin[0]
        gcode_y = y - origin[1]
        gcode_clearance_z = self.clearance_z - origin[2]
        gcode_approach_z = self.approach_z - origin[2]
        self.gcode.run_script_from_command(
            "G90\nG1 Z%.3f F%.0f\nG1 X%.3f Y%.3f F%.0f\nG1 Z%.3f F%.0f"
            % (
                gcode_clearance_z,
                self.travel_speed * 60.0,
                gcode_x,
                gcode_y,
                self.travel_speed * 60.0,
                gcode_approach_z,
                self.travel_speed * 60.0,
            )
        )
        toolhead.wait_moves()
        return {
            "gcode_origin": origin,
            "gcode_x": gcode_x,
            "gcode_y": gcode_y,
            "gcode_clearance_z": gcode_clearance_z,
            "gcode_approach_z": gcode_approach_z,
        }

    def _retract_to_clearance(self, toolhead):
        current = toolhead.get_position()
        current[2] = self.clearance_z
        toolhead.manual_move(current, self.travel_speed)
        toolhead.wait_moves()

    def cmd_QUERY_MULTI_HEAD_ZERO(self, gcmd):
        toolhead = self.printer.lookup_object("toolhead")
        gcmd.respond_info("multi_head_zero: %s" % self._switch_state(toolhead))

    def cmd_MULTI_HEAD_ZERO_CONTACT(self, gcmd):
        x = gcmd.get_float("X")
        y = gcmd.get_float("Y")
        requested_tool = gcmd.get_int("TOOL", minval=0, maxval=1)
        allow_no_contact = gcmd.get_int("ALLOW_NO_CONTACT", 0, minval=0, maxval=1)
        measurement = {
            "commanded_x": x,
            "commanded_y": y,
            "requested_tool": requested_tool,
            "allow_no_contact": bool(allow_no_contact),
            "approach_z": self.approach_z,
            "target_z": self.target_z,
            "clearance_z": self.clearance_z,
            "probe_speed": self.probe_speed,
            "status": "failed",
        }
        self.last_measurement = measurement
        try:
            toolhead = self._require_homed_idle_unmeshed("MULTI_HEAD_ZERO_CONTACT")
            measurement["active_tool"] = self._require_active_tool(requested_tool)
            self._require_limits(toolhead, x, y)
            measurement["preflight_state"] = self._switch_state(toolhead)
            if measurement["preflight_state"] != "RELEASED":
                raise self.gcode.error(
                    "MULTI_HEAD_ZERO_CONTACT requires a released NC switch before motion"
                )
            measurement.update(self._move_to_start(toolhead, x, y))
            start_position = [float(value) for value in toolhead.get_position()]
            target_position = list(start_position)
            target_position[2] = self.target_z
            try:
                trigger_position = self.printer.lookup_object("homing").probing_move(
                    self.mcu_endstop, target_position, self.probe_speed
                )
            except self.printer.command_error as exc:
                if not (
                    allow_no_contact
                    and str(exc) == "No trigger on probe after full movement"
                ):
                    raise
                measurement.update(
                    {
                        "status": "no_contact",
                        "no_contact_reason": "target_reached",
                        "target_position": [float(value) for value in target_position],
                        "halt_position": [
                            float(value) for value in toolhead.get_position()
                        ],
                    }
                )
                self._retract_to_clearance(toolhead)
                measurement["post_retract_position"] = [
                    float(value) for value in toolhead.get_position()
                ]
                measurement["post_retract_state"] = self._switch_state(toolhead)
                if measurement["post_retract_state"] != "RELEASED":
                    raise self.gcode.error(
                        "MULTI_HEAD_ZERO_CONTACT no-contact retract left the "
                        "switch %s" % measurement["post_retract_state"]
                    )
                gcmd.respond_info(
                    "Multi-head-zero no contact: T%d commanded=(%.3f, %.3f) "
                    "reached target Z=%.6f"
                    % (
                        measurement["active_tool"],
                        x,
                        y,
                        self.target_z,
                    )
                )
                return
            halt_position = [float(value) for value in toolhead.get_position()]
            measurement.update(
                {
                    "status": "completed",
                    "start_position": start_position,
                    "target_position": [float(value) for value in target_position],
                    "trigger_position": [float(value) for value in trigger_position],
                    "halt_position": halt_position,
                    "trigger_x": float(trigger_position[0]),
                    "trigger_y": float(trigger_position[1]),
                    "trigger_z": float(trigger_position[2]),
                }
            )
            self._retract_to_clearance(toolhead)
            measurement["post_retract_position"] = [
                float(value) for value in toolhead.get_position()
            ]
            measurement["post_retract_state"] = self._switch_state(toolhead)
            gcmd.respond_info(
                "Multi-head-zero contact: T%d commanded=(%.3f, %.3f) trigger=(%.6f, %.6f, %.6f)"
                % (
                    measurement["active_tool"],
                    x,
                    y,
                    measurement["trigger_x"],
                    measurement["trigger_y"],
                    measurement["trigger_z"],
                )
            )
        except Exception as exc:
            measurement["error"] = str(exc)
            raise


def load_config(config):
    return MultiHeadZeroProbe(config)
