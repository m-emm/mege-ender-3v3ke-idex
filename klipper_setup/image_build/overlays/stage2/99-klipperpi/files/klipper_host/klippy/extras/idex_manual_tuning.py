# Persistent manual IDEX tuning across tool changes
#
# Copyright (C) 2026 Markus Emmenegger
#
# This file may be distributed under the terms of the GNU GPLv3 license.


class IDEXManualTuning:
    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.active_tool = 0
        self.active_tool_z_offset = 0.0
        self.manual_z_adjust = 0.0
        self.speed_factor = 100.0
        self.flow_factor = 100.0
        self.gcode.register_command(
            "IDEX_MANUAL_TUNING_CAPTURE",
            self.cmd_IDEX_MANUAL_TUNING_CAPTURE,
            desc="Capture manual Z, speed, and flow tuning before an IDEX tool change.",
        )
        self.gcode.register_command(
            "IDEX_MANUAL_TUNING_APPLY",
            self.cmd_IDEX_MANUAL_TUNING_APPLY,
            desc="Apply IDEX tool offsets with persistent manual tuning.",
        )
        self.gcode.register_command(
            "IDEX_MANUAL_TUNING_STATUS",
            self.cmd_IDEX_MANUAL_TUNING_STATUS,
            desc="Report persistent IDEX manual tuning.",
        )
        self.gcode.register_command(
            "IDEX_MANUAL_TUNING_RESET",
            self.cmd_IDEX_MANUAL_TUNING_RESET,
            desc="Reset persistent IDEX manual tuning for the current print.",
        )
        self.printer.register_event_handler(
            "virtual_sdcard:reset_file", self._handle_virtual_sdcard_reset
        )

    def _gcode_move_status(self):
        gcode_move = self.printer.lookup_object("gcode_move")
        reactor = self.printer.get_reactor()
        return gcode_move.get_status(reactor.monotonic())

    def _capture_current_state(self):
        status = self._gcode_move_status()
        homing_origin = status["homing_origin"]
        self.manual_z_adjust = float(homing_origin[2]) - self.active_tool_z_offset
        self.speed_factor = float(status["speed_factor"]) * 100.0
        self.flow_factor = float(status["extrude_factor"]) * 100.0

    def _run_script(self, script):
        self.gcode.run_script_from_command(script)

    def _apply(self, tool, tool_z, y_offset, move, move_speed):
        self.active_tool = tool
        self.active_tool_z_offset = tool_z
        effective_z = tool_z + self.manual_z_adjust
        self._run_script(
            "SET_GCODE_OFFSET X=0 Y=%.6f Z=%.6f MOVE=%d MOVE_SPEED=%.6f"
            % (y_offset, effective_z, move, move_speed)
        )
        self._run_script("M220 S%.6f" % (self.speed_factor,))
        self._run_script("M221 S%.6f" % (self.flow_factor,))

    def _reset(self):
        self.manual_z_adjust = 0.0
        self.speed_factor = 100.0
        self.flow_factor = 100.0
        self._run_script(
            "SET_GCODE_OFFSET Z=%.6f MOVE=0" % (self.active_tool_z_offset,)
        )
        self._run_script("M220 S100")
        self._run_script("M221 S100")

    def _handle_virtual_sdcard_reset(self):
        self._reset()

    def cmd_IDEX_MANUAL_TUNING_CAPTURE(self, gcmd):
        tool = gcmd.get_int("TOOL", self.active_tool, minval=0, maxval=1)
        self._capture_current_state()
        self.active_tool = tool

    def cmd_IDEX_MANUAL_TUNING_APPLY(self, gcmd):
        tool = gcmd.get_int("TOOL", minval=0, maxval=1)
        tool_z = gcmd.get_float("TOOL_Z")
        y_offset = gcmd.get_float("Y")
        move = gcmd.get_int("MOVE", 0, minval=0, maxval=1)
        move_speed = gcmd.get_float("MOVE_SPEED", 100.0, above=0.0)
        self._apply(tool, tool_z, y_offset, move, move_speed)

    def cmd_IDEX_MANUAL_TUNING_STATUS(self, gcmd):
        self._capture_current_state()
        gcmd.respond_info(
            "IDEX manual tuning: T%d static_z=%.4f manual_z=%.4f "
            "effective_z=%.4f speed=%.1f%% flow=%.1f%%"
            % (
                self.active_tool,
                self.active_tool_z_offset,
                self.manual_z_adjust,
                self.active_tool_z_offset + self.manual_z_adjust,
                self.speed_factor,
                self.flow_factor,
            )
        )

    def cmd_IDEX_MANUAL_TUNING_RESET(self, gcmd):
        self._reset()
        gcmd.respond_info("IDEX manual tuning reset: Z=0.0000, speed=100%, flow=100%")

    def get_status(self, eventtime):
        return {
            "active_tool": self.active_tool,
            "active_tool_z_offset": self.active_tool_z_offset,
            "manual_z_adjust": self.manual_z_adjust,
            "effective_z_offset": self.active_tool_z_offset + self.manual_z_adjust,
            "speed_factor": self.speed_factor,
            "flow_factor": self.flow_factor,
        }


def load_config(config):
    return IDEXManualTuning(config)
