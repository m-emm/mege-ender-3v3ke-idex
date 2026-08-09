# Generic persistent data-acquisition store for Klipper jobs.
#
# Copyright (C) 2026 Markus Emmenegger
# This file may be distributed under the terms of the GNU GPLv3 license.

import datetime
import json
import logging
import os
import re

try:
    from sqlitedict import SqliteDict
except ImportError:
    SqliteDict = None


_logger = logging.getLogger(__name__)
DEFAULT_DATABASE_PATH = "/home/pi/printer_data/database/daq.sqlite"
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")


def _utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _require_job_id(value):
    if not JOB_ID_RE.fullmatch(value or ""):
        raise ValueError(
            "JOB_ID must contain 1..96 letters, digits, '.', '_' or '-' and "
            "must start with a letter or digit"
        )
    return value


class DaqStore:
    """Generic flat-record job store shared by printer DAQ extras."""

    def __init__(self, database_path):
        if SqliteDict is None:
            raise RuntimeError(
                "sqlitedict is unavailable in Klipper's Python environment; "
                "deploy the managed DAQ extra package first"
            )
        self.database_path = os.path.abspath(database_path)
        os.makedirs(os.path.dirname(self.database_path), exist_ok=True)
        self.db = SqliteDict(self.database_path, autocommit=True)

    @staticmethod
    def record_key(job_id, record_index):
        _require_job_id(job_id)
        if record_index < 0:
            raise ValueError("record_index must be non-negative")
        return "%s_%06d" % (job_id, record_index)

    def _job(self, job_id):
        _require_job_id(job_id)
        try:
            job = self.db[job_id]
        except KeyError as exc:
            raise ValueError("unknown DAQ JOB_ID %s" % job_id) from exc
        if not isinstance(job, dict) or job.get("record_kind") != "job":
            raise ValueError("DAQ key %s is not a job record" % job_id)
        return dict(job)

    def start_job(self, job_id, job_type="generic", metadata=None):
        _require_job_id(job_id)
        if job_id in self.db:
            raise ValueError("DAQ JOB_ID %s already exists" % job_id)
        job = {
            "record_kind": "job",
            "schema_version": 1,
            "job_id": job_id,
            "job_type": str(job_type),
            "status": "running",
            "created_at": _utc_now(),
            "finished_at": None,
            "record_count": 0,
            "error_count": 0,
        }
        if metadata:
            job.update(dict(metadata))
        json.dumps(job, allow_nan=False, sort_keys=True)
        self.db[job_id] = job
        _logger.info("DAQ job started: job_id=%s type=%s", job_id, job_type)
        return job

    def update_job_metadata(self, job_id, metadata):
        job = self._job(job_id)
        if job.get("status") not in {"running", "completed_with_errors"}:
            raise ValueError("DAQ job %s is already finished" % job_id)
        job.update(dict(metadata))
        json.dumps(job, allow_nan=False, sort_keys=True)
        self.db[job_id] = job
        return job

    def write_record(self, job_id, record_index, record):
        job = self._job(job_id)
        if job.get("status") != "running":
            raise ValueError("DAQ job %s is not running" % job_id)
        key = self.record_key(job_id, record_index)
        if key in self.db:
            raise ValueError("DAQ record already exists: %s" % key)
        payload = dict(record)
        payload.update(
            {
                "record_kind": "measurement",
                "schema_version": 1,
                "job_id": job_id,
                "record_index": int(record_index),
                "recorded_at": _utc_now(),
            }
        )
        json.dumps(payload, allow_nan=False, sort_keys=True)
        self.db[key] = payload
        job["record_count"] = int(job.get("record_count", 0)) + 1
        if payload.get("error"):
            job["error_count"] = int(job.get("error_count", 0)) + 1
        self.db[job_id] = job
        return payload

    def finish_job(self, job_id):
        job = self._job(job_id)
        if job.get("status") != "running":
            raise ValueError("DAQ job %s is not running" % job_id)
        job["status"] = (
            "completed_with_errors" if job.get("error_count") else "completed"
        )
        job["finished_at"] = _utc_now()
        self.db[job_id] = job
        _logger.info(
            "DAQ job finished: job_id=%s status=%s records=%d errors=%d",
            job_id,
            job["status"],
            job["record_count"],
            job["error_count"],
        )
        return job

    def close(self):
        self.db.close()


class PrinterDaq:
    """Klipper command adapter for the generic DAQ store."""

    def __init__(self, config):
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")
        self.store = DaqStore(config.get("database_path", DEFAULT_DATABASE_PATH))
        self.gcode.register_command(
            "DAQ_JOB_START", self.cmd_DAQ_JOB_START, desc="Start a persistent DAQ job."
        )
        self.gcode.register_command(
            "DAQ_JOB_FINISH",
            self.cmd_DAQ_JOB_FINISH,
            desc="Finish a persistent DAQ job.",
        )
        self.printer.register_event_handler(
            "klippy:disconnect", self._handle_disconnect
        )

    def _handle_disconnect(self):
        self.store.close()

    def get_status(self, _eventtime):
        return {"database_path": self.store.database_path}

    def cmd_DAQ_JOB_START(self, gcmd):
        job_id = gcmd.get("JOB_ID")
        try:
            job = self.store.start_job(
                job_id,
                gcmd.get("JOB_TYPE", "generic"),
                {
                    "expected_records": gcmd.get_int("EXPECTED_RECORDS", 0, minval=0),
                    "gcode_parameters": dict(gcmd.get_command_parameters()),
                },
            )
        except ValueError as exc:
            raise gcmd.error(str(exc)) from exc
        gcmd.respond_info(
            "DAQ job started: job_id=%s type=%s expected_records=%d"
            % (job["job_id"], job["job_type"], job["expected_records"])
        )

    def cmd_DAQ_JOB_FINISH(self, gcmd):
        try:
            job = self.store.finish_job(gcmd.get("JOB_ID"))
        except ValueError as exc:
            raise gcmd.error(str(exc)) from exc
        gcmd.respond_info(
            "DAQ job finished: job_id=%s status=%s records=%d errors=%d"
            % (job["job_id"], job["status"], job["record_count"], job["error_count"])
        )


def load_config(config):
    return PrinterDaq(config)
