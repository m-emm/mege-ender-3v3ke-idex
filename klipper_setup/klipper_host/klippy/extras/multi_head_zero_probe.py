# Multi-head-zero contact measurement support.
#
# Copyright (C) 2026 Markus Emmenegger
# This file may be distributed under the terms of the GNU GPLv3 license.


class MultiHeadZeroProbe:
    """Perform guarded vertical contacts with the multi-head-zero switch."""

    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.pin = config.get("pin")
        self.start_z = config.getfloat("start_z", 4.0)
        self.recovery_z = config.getfloat("recovery_z", 10.0, above=0.0)
        self.target_z = config.getfloat("target_z", -1.0)
        self.travel_speed = config.getfloat("travel_speed", 20.0, above=0.0)
        self.probe_speed = config.getfloat("probe_speed", 1.0, above=0.0)
        self.priors = {
            "ball_radius_mm": config.getfloat("ball_radius_mm", 5.0, above=0.0),
            "ball_front_gap_mm": config.getfloat("ball_front_gap_mm", 1.0),
            "y_zero_behind_front_edge_mm": config.getfloat(
                "y_zero_behind_front_edge_mm", 3.0
            ),
            "target_x": config.getfloat("target_x", 75.0),
            "target_y": config.getfloat("target_y", -9.0),
            "seed_x_min": config.getfloat("seed_x_min", 72.0),
            "seed_x_max": config.getfloat("seed_x_max", 78.0),
            "seed_y_min": config.getfloat("seed_y_min", -12.0),
            "seed_y_max": config.getfloat("seed_y_max", -6.0),
            "ring_radius_mm": config.getfloat("ring_radius_mm", 2.8, above=0.0),
        }
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
            desc=(
                "Measure the configured ball with TOOL=0|1, optional COUNT, "
                "START_Z, X, and Y."
            ),
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
            "start_z": self.start_z,
            "recovery_z": self.recovery_z,
            "target_z": self.target_z,
            "travel_speed": self.travel_speed,
            "probe_speed": self.probe_speed,
            "priors": self.priors,
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

    def _require_homed_idle(self, command_name):
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
        return toolhead

    def _clear_active_mesh(self, toolhead):
        eventtime = self.printer.get_reactor().monotonic()
        mesh_status = self.printer.lookup_object("bed_mesh").get_status(eventtime)
        active = bool(mesh_status.get("profile_name")) or any(
            mesh_status.get("mesh_matrix", [])
        )
        if active:
            self.gcode.run_script_from_command("BED_MESH_CLEAR\nM400")
            toolhead.wait_moves()
        mesh_status = self.printer.lookup_object("bed_mesh").get_status(
            self.printer.get_reactor().monotonic()
        )
        if mesh_status.get("profile_name") or any(mesh_status.get("mesh_matrix", [])):
            raise self.gcode.error(
                "MULTI_HEAD_ZERO_CONTACT could not clear the active bed mesh"
            )
        return active

    def _active_tool_status(self):
        eventtime = self.printer.get_reactor().monotonic()
        toolhead = self.printer.lookup_object("toolhead")
        carriage_status = self.printer.lookup_object("dual_carriage").get_status(
            eventtime
        )
        return {
            "active_tool": self.printer.lookup_object("idex_manual_tuning")
            .get_status(eventtime)
            .get("active_tool"),
            "macro_active_tool": self.printer.lookup_object(
                "gcode_macro _IDEX_TOOL_STATE"
            )
            .get_status(eventtime)
            .get("active_tool"),
            "active_extruder": toolhead.get_status(eventtime).get("extruder"),
            "carriage_0": carriage_status.get("carriage_0"),
            "carriage_1": carriage_status.get("carriage_1"),
        }

    def _require_active_tool(self, tool):
        observed = self._active_tool_status()
        expected_extruder = "extruder" if tool == 0 else "extruder1"
        expected_carriages = (
            ("PRIMARY", "INACTIVE") if tool == 0 else ("INACTIVE", "PRIMARY")
        )
        if (
            observed["active_tool"] != tool
            or observed["macro_active_tool"] != tool
            or observed["active_extruder"] != expected_extruder
            or (observed["carriage_0"], observed["carriage_1"]) != expected_carriages
        ):
            raise self.gcode.error(
                "MULTI_HEAD_ZERO_CONTACT TOOL=%d physical selection mismatch: "
                "manual=%s macro=%s extruder=%s carriage_0=%s carriage_1=%s"
                % (
                    tool,
                    observed["active_tool"],
                    observed["macro_active_tool"],
                    observed["active_extruder"],
                    observed["carriage_0"],
                    observed["carriage_1"],
                )
            )
        return observed

    def _select_tool(self, tool, toolhead):
        observed = self._active_tool_status()
        if observed["active_tool"] != tool:
            self.gcode.run_script_from_command("T%d\nM400" % tool)
            toolhead.wait_moves()
            return True, self._require_active_tool(tool)
        return False, self._require_active_tool(tool)

    def _gcode_origin(self):
        origin = (
            self.printer.lookup_object("gcode_move")
            .get_status(self.printer.get_reactor().monotonic())
            .get("homing_origin", [0.0, 0.0, 0.0])
        )
        return [float(value) for value in origin]

    @staticmethod
    def _logical_to_machine(logical, origin):
        return [float(value) + float(offset) for value, offset in zip(logical, origin)]

    @staticmethod
    def _machine_to_logical(machine, origin):
        return [float(value) - float(offset) for value, offset in zip(machine, origin)]

    def _machine_limits(self, toolhead):
        status = toolhead.get_status(self.printer.get_reactor().monotonic())
        minimum = status.get("axis_minimum")
        maximum = status.get("axis_maximum")
        if minimum is None or maximum is None:
            raise self.gcode.error("MULTI_HEAD_ZERO_CONTACT cannot read axis limits")
        return minimum, maximum

    def _require_machine_value(self, toolhead, label, value, axis):
        minimum, maximum = self._machine_limits(toolhead)
        lower = self._axis_value(minimum, axis)
        upper = self._axis_value(maximum, axis)
        if not lower <= value <= upper:
            raise self.gcode.error(
                "MULTI_HEAD_ZERO_CONTACT %s %.3f is outside limits [%.3f, %.3f]"
                % (label, value, lower, upper)
            )

    def _lift_to_recovery(self, toolhead):
        self._require_machine_value(toolhead, "recovery Z", self.recovery_z, 2)
        current = [float(value) for value in toolhead.get_position()]
        if current[2] >= self.recovery_z:
            return False, current
        current[2] = self.recovery_z
        toolhead.manual_move(current, self.travel_speed)
        toolhead.wait_moves()
        return True, [float(value) for value in toolhead.get_position()]

    def _move_to_logical_target(self, toolhead, x, y, start_z):
        self.gcode.run_script_from_command(
            "G90\nG1 X%.3f Y%.3f F%.0f\nG1 Z%.3f F%.0f"
            % (x, y, self.travel_speed * 60.0, start_z, self.travel_speed * 60.0)
        )
        toolhead.wait_moves()
        return [float(value) for value in toolhead.get_position()]

    def _retract_to_start(self, toolhead, machine_start_z):
        current = [float(value) for value in toolhead.get_position()]
        current[2] = machine_start_z
        toolhead.manual_move(current, self.travel_speed)
        toolhead.wait_moves()

    def _prepare_batch(self, x, y, requested_tool, start_z):
        toolhead = self._require_homed_idle("MULTI_HEAD_ZERO_CONTACT")
        mesh_cleared = self._clear_active_mesh(toolhead)
        preflight_state = self._switch_state(toolhead)
        recovery_lifted, recovery_position = self._lift_to_recovery(toolhead)
        post_recovery_state = self._switch_state(toolhead)
        if post_recovery_state != "RELEASED":
            raise self.gcode.error(
                "MULTI_HEAD_ZERO_CONTACT switch remains %s after upward recovery "
                "to machine Z=%.3f; inspect the ball contact or NC wiring"
                % (post_recovery_state, recovery_position[2])
            )
        tool_switched, tool_selection = self._select_tool(requested_tool, toolhead)
        origin = self._gcode_origin()
        machine_target = self._logical_to_machine((x, y, self.target_z), origin)
        machine_start = self._logical_to_machine((x, y, start_z), origin)
        self._require_machine_value(toolhead, "X", machine_target[0], 0)
        self._require_machine_value(toolhead, "Y", machine_target[1], 1)
        self._require_machine_value(toolhead, "START_Z", machine_start[2], 2)
        self._require_machine_value(toolhead, "target Z", machine_target[2], 2)
        pre_descent_state = self._switch_state(toolhead)
        if pre_descent_state != "RELEASED":
            raise self.gcode.error(
                "MULTI_HEAD_ZERO_CONTACT switch became %s before XY/descent; "
                "inspect the ball contact or NC wiring" % pre_descent_state
            )
        start_position = self._move_to_logical_target(toolhead, x, y, start_z)
        return {
            "commanded_x": x,
            "commanded_y": y,
            "requested_tool": requested_tool,
            "start_z": start_z,
            "target_z": self.target_z,
            "recovery_z": self.recovery_z,
            "gcode_origin": origin,
            "machine_commanded_x": machine_target[0],
            "machine_commanded_y": machine_target[1],
            "machine_start_z": machine_start[2],
            "machine_target_z": machine_target[2],
            "mesh_cleared": mesh_cleared,
            "preflight_state": preflight_state,
            "recovery_lifted": recovery_lifted,
            "recovery_position": recovery_position,
            "post_recovery_state": post_recovery_state,
            "tool_switched": tool_switched,
            "tool_selection": tool_selection,
            "pre_descent_state": pre_descent_state,
            "start_position": start_position,
        }

    def cmd_QUERY_MULTI_HEAD_ZERO(self, gcmd):
        toolhead = self.printer.lookup_object("toolhead")
        gcmd.respond_info("multi_head_zero: %s" % self._switch_state(toolhead))

    def _contact_once(self, preparation, allow_no_contact):
        measurement = dict(preparation)
        measurement.update(
            {"allow_no_contact": bool(allow_no_contact), "status": "failed"}
        )
        self.last_measurement = measurement
        toolhead = self.printer.lookup_object("toolhead")
        start_position = [float(value) for value in toolhead.get_position()]
        target_position = list(start_position)
        target_position[2] = preparation["machine_target_z"]
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
                    "tap_start_position": start_position,
                    "target_position": [float(value) for value in target_position],
                    "halt_position": [
                        float(value) for value in toolhead.get_position()
                    ],
                }
            )
            self._retract_to_start(toolhead, preparation["machine_start_z"])
        else:
            trigger_position = [float(value) for value in trigger_position]
            logical_trigger = self._machine_to_logical(
                trigger_position, preparation["gcode_origin"]
            )
            measurement.update(
                {
                    "status": "completed",
                    "tap_start_position": start_position,
                    "target_position": [float(value) for value in target_position],
                    "trigger_position": trigger_position,
                    "halt_position": [
                        float(value) for value in toolhead.get_position()
                    ],
                    "trigger_x": trigger_position[0],
                    "trigger_y": trigger_position[1],
                    "trigger_z": trigger_position[2],
                    "logical_trigger_x": logical_trigger[0],
                    "logical_trigger_y": logical_trigger[1],
                    "logical_trigger_z": logical_trigger[2],
                }
            )
            self._retract_to_start(toolhead, preparation["machine_start_z"])
        measurement["post_retract_position"] = [
            float(value) for value in toolhead.get_position()
        ]
        measurement["post_retract_state"] = self._switch_state(toolhead)
        if measurement["post_retract_state"] != "RELEASED":
            raise self.gcode.error(
                "MULTI_HEAD_ZERO_CONTACT retract left the switch %s"
                % measurement["post_retract_state"]
            )
        return measurement

    @staticmethod
    def _tap_statistics(samples):
        values = [float(sample["z"]) for sample in samples]
        if not values:
            return {
                "count": 0,
                "mean": None,
                "median": None,
                "minimum": None,
                "maximum": None,
                "span": None,
                "standard_deviation": None,
            }
        import statistics

        return {
            "count": len(values),
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "minimum": min(values),
            "maximum": max(values),
            "span": max(values) - min(values),
            "standard_deviation": statistics.pstdev(values),
        }

    def cmd_MULTI_HEAD_ZERO_CONTACT(self, gcmd):
        requested_tool = gcmd.get_int("TOOL", minval=0, maxval=1)
        x = gcmd.get_float("X", self.priors["target_x"])
        y = gcmd.get_float("Y", self.priors["target_y"])
        start_z = gcmd.get_float("START_Z", self.start_z)
        if start_z < self.start_z:
            raise self.gcode.error(
                "MULTI_HEAD_ZERO_CONTACT START_Z %.3f is below the configured "
                "safe minimum %.3f" % (start_z, self.start_z)
            )
        count = gcmd.get_int("COUNT", 1, minval=1, maxval=100)
        # Calibration seeds may opt into no-contact records. Normal console use
        # deliberately remains strict and does not need this parameter.
        allow_no_contact = gcmd.get_int("ALLOW_NO_CONTACT", 0, minval=0, maxval=1)
        result = {
            "requested_tool": requested_tool,
            "commanded_x": x,
            "commanded_y": y,
            "start_z": start_z,
            "count": count,
            "status": "failed",
        }
        self.last_measurement = result
        try:
            gcmd.respond_info(
                "Multi-head-zero: preparing T%d at logical X=%.3f Y=%.3f "
                "START_Z=%.3f (%d tap%s)"
                % (requested_tool, x, y, start_z, count, "" if count == 1 else "s")
            )
            preparation = self._prepare_batch(x, y, requested_tool, start_z)
            if preparation["mesh_cleared"]:
                gcmd.respond_info("Multi-head-zero: active bed mesh cleared")
            if preparation["recovery_lifted"]:
                gcmd.respond_info(
                    "Multi-head-zero: upward recovery to machine Z=%.3f"
                    % preparation["recovery_position"][2]
                )
            if preparation["tool_switched"]:
                gcmd.respond_info("Multi-head-zero: selected T%d" % requested_tool)
            measurements = []
            samples = []
            for index in range(count):
                measurement = self._contact_once(preparation, allow_no_contact)
                measurements.append(measurement)
                if measurement["status"] == "completed":
                    samples.append(
                        {
                            "x": measurement["logical_trigger_x"],
                            "y": measurement["logical_trigger_y"],
                            "z": measurement["logical_trigger_z"],
                        }
                    )
                    gcmd.respond_info(
                        "Multi-head-zero contact: T%d tap %d/%d logical "
                        "trigger=(%.6f, %.6f, %.6f)"
                        % (
                            requested_tool,
                            index + 1,
                            count,
                            measurement["logical_trigger_x"],
                            measurement["logical_trigger_y"],
                            measurement["logical_trigger_z"],
                        )
                    )
                else:
                    gcmd.respond_info(
                        "Multi-head-zero contact: T%d tap %d/%d status=%s"
                        % (requested_tool, index + 1, count, measurement["status"])
                    )
            statistics = self._tap_statistics(samples)
            result = dict(measurements[-1])
            result.update(
                {
                    "count": count,
                    "completed_count": len(samples),
                    "no_contact_count": sum(
                        measurement["status"] == "no_contact"
                        for measurement in measurements
                    ),
                    "measurements": measurements,
                    "tap": {"count": count, "samples": samples, **statistics},
                    "statistics": statistics,
                }
            )
            if result["no_contact_count"]:
                result["status"] = "no_contact"
            self.last_measurement = result
            gcmd.respond_info(
                "Multi-head-zero statistics: T%d count=%d mean=%s median=%s "
                "min=%s max=%s span=%s stddev=%s"
                % (
                    requested_tool,
                    count,
                    (
                        "%.6f" % statistics["mean"]
                        if statistics["mean"] is not None
                        else "n/a"
                    ),
                    (
                        "%.6f" % statistics["median"]
                        if statistics["median"] is not None
                        else "n/a"
                    ),
                    (
                        "%.6f" % statistics["minimum"]
                        if statistics["minimum"] is not None
                        else "n/a"
                    ),
                    (
                        "%.6f" % statistics["maximum"]
                        if statistics["maximum"] is not None
                        else "n/a"
                    ),
                    (
                        "%.6f" % statistics["span"]
                        if statistics["span"] is not None
                        else "n/a"
                    ),
                    (
                        "%.6f" % statistics["standard_deviation"]
                        if statistics["standard_deviation"] is not None
                        else "n/a"
                    ),
                )
            )
        except Exception as exc:
            result["error"] = str(exc)
            self.last_measurement = result
            raise


def load_config(config):
    return MultiHeadZeroProbe(config)
