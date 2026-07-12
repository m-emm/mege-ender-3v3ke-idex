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


def load_config(config):
    return Vision(config)
