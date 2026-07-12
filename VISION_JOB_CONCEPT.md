# Klipper Vision Job Concept

This document describes a proposed next architecture for printer vision
measurements. It is meant as a discussion draft, consistent with the current
Mender IDEX vision stack:

- `vision-framebuffer` owns the camera devices and keeps fresh RAM-buffered
  preview/capture frames.
- `vision-capture` persists buffered frames today.
- Klipper exposes camera/light macros such as `NOZZLE_CAM_ANALYSIS_LIGHT`,
  `NOZZLE_CAM_CAPTURE`, and `IDEX_NOZZLE_VISION_SWEEP`.
- The current nozzle sweep works, but the high-level analyzer still drives
  printer motion one pose at a time through Moonraker.

The goal of the new design is to separate fast, deterministic acquisition from
slower orchestration and image analysis.

## Design Goal

A vision measurement should have two phases:

1. Acquisition: Klipper runs a generated G-code job from the virtual SD card.
   The job moves the printer through the exact required poses, sets lighting,
   waits for motion to settle, captures one frame, and immediately continues to
   the next pose.
2. Analysis: an orchestrator waits for the acquisition job to finish, verifies
   that every expected image exists, then analyzes those images and emits facts.

Acquisition should be boring and timeline-driven:

- no homing unless the specific measurement asks for it
- no parking unless the specific measurement asks for it
- no restore move by default
- no analysis during the G-code job
- no hidden fallback images or synthetic results
- one expected frame in the plan means exactly one persisted frame on disk

## Job State Machine

Vision jobs should have an explicit, persisted state machine. State changes are
written atomically into the job directory so a later process can distinguish a
completed job from an interrupted one.

States:

- `prepared`: manifest and acquisition G-code exist, but Klipper has not begun
  acquisition.
- `acquiring`: Klipper has accepted `VISION_JOB_BEGIN`; frames may be produced.
- `acquired`: Klipper has accepted `VISION_JOB_END`; every expected frame has
  been atomically committed and verified.
- `analysing`: acquisition is complete and host-side analysis is running.
- `completed`: analysis finished and produced accepted facts/report artifacts.
- `failed`: a live job hit a known hard error, such as capture timeout, profile
  mismatch, missing detection, or analysis rejection.
- `abandoned`: an incomplete job was interrupted, cancelled, or discovered after
  restart. Abandoned jobs are not resumable.

Normal transition:

```text
prepared -> acquiring -> acquired -> analysing -> completed
```

Failure transitions:

```text
prepared  -> failed | abandoned
acquiring -> failed | abandoned
acquired  -> analysing | failed | abandoned
analysing -> completed | failed | abandoned
```

`failed` means the system observed a specific error while the job was active.
`abandoned` means the job cannot be trusted because the process, Klipper print,
or host connection was interrupted. A later orchestrator must create a new job
instead of resuming partial state.

## Desired Runtime Flow

```text
Moonraker starts vision-calibration.gcode
              |
              v
Klipper virtual SD print
              |
              v
Klipper reaches VISION_JOB_BEGIN
              |
              v
Klipper queues motion ahead
              |
              v
Klipper reaches VISION_CAPTURE_SYNC
              |
              v
VISION_CAPTURE_SYNC flushes/waits for motion
              |
              v
VISION_CAPTURE_SYNC asks visiond to capture
              |
              v
visiond saves image and replies
              |
              v
Klipper reaches VISION_JOB_END
              |
              v
Klipper continues parsing G-code
```

The important property is that `VISION_CAPTURE_SYNC` is synchronous from Klipper's
point of view. When the next `G1` is parsed, the previous frame has already been
written or the job has failed.

## Example Generated Acquisition G-code

For a simple X sweep:

```gcode
; generated vision job: nozzle_sweep_20260712T172140Z
; run dir: /home/pi/printer_data/vision/nozzle_cam/jobs/nozzle_sweep_20260712T172140Z

G90
VISION_JOB_BEGIN JOB=nozzle_sweep_20260712T172140Z MANIFEST_HASH=sha256:... GCODE_HASH=sha256:...
VISION_PROFILE CAMERA=nozzle_cam PROFILE=analysis
NOZZLE_CAM_ANALYSIS_LIGHT

G1 X100.000 Y100.000 Z5.000 F12000
M400
G4 P150
VISION_CAPTURE_SYNC JOB=nozzle_sweep_20260712T172140Z SEQ=0 FRAME=000 CAMERA=nozzle_cam PROFILE=analysis

G1 X102.500 Y100.000 Z5.000 F12000
M400
G4 P150
VISION_CAPTURE_SYNC JOB=nozzle_sweep_20260712T172140Z SEQ=1 FRAME=001 CAMERA=nozzle_cam PROFILE=analysis

G1 X105.000 Y100.000 Z5.000 F12000
M400
G4 P150
VISION_CAPTURE_SYNC JOB=nozzle_sweep_20260712T172140Z SEQ=2 FRAME=002 CAMERA=nozzle_cam PROFILE=analysis

VISION_JOB_END JOB=nozzle_sweep_20260712T172140Z EXPECTED_FRAMES=3
```

For the IDEX nozzle sweep, the generated file would include the necessary tool
selection commands and poses:

```gcode
; generated vision job: idex_nozzle_sweep_20260712T172140Z

G90
VISION_JOB_BEGIN JOB=idex_nozzle_sweep_20260712T172140Z MANIFEST_HASH=sha256:... GCODE_HASH=sha256:...
VISION_PROFILE CAMERA=nozzle_cam PROFILE=analysis
NOZZLE_CAM_ANALYSIS_LIGHT

T0
G1 X195.000 Y-14.800 Z20.000 F3600
M400
G4 P750
VISION_CAPTURE_SYNC JOB=idex_nozzle_sweep_20260712T172140Z SEQ=0 FRAME=t0_dx0p0 CAMERA=nozzle_cam PROFILE=analysis TOOL=T0

G1 X198.000 Y-14.800 Z20.000 F3600
M400
G4 P750
VISION_CAPTURE_SYNC JOB=idex_nozzle_sweep_20260712T172140Z SEQ=1 FRAME=t0_dx3p0 CAMERA=nozzle_cam PROFILE=analysis TOOL=T0

T1
G1 X195.000 Y-14.800 Z20.000 F3600
M400
G4 P750
VISION_CAPTURE_SYNC JOB=idex_nozzle_sweep_20260712T172140Z SEQ=2 FRAME=t1_dx0p0 CAMERA=nozzle_cam PROFILE=analysis TOOL=T1

G1 X198.000 Y-14.800 Z20.000 F3600
M400
G4 P750
VISION_CAPTURE_SYNC JOB=idex_nozzle_sweep_20260712T172140Z SEQ=3 FRAME=t1_dx3p0 CAMERA=nozzle_cam PROFILE=analysis TOOL=T1

VISION_JOB_END JOB=idex_nozzle_sweep_20260712T172140Z EXPECTED_FRAMES=4
```

The real generated file may add comments and metadata, but it should not add
unrequested homing, parking, recovery, or analysis.

## Components

### Orchestrator

The orchestrator is a host-side program. For the current nozzle sweep this would
be the future shape of `vision_nozzle_align.py`, or a sibling tool that it calls.

Responsibilities:

- check preconditions before starting:
  - Moonraker/Klipper ready
  - printer idle
  - required axes already homed
  - requested poses inside live Klipper limits
  - requested camera/profile available
- create a unique `job_id`
- create a job directory
- write a measurement manifest
- generate the virtual SD G-code file
- upload or write that G-code into `~/printer_data/gcodes/vision_jobs/`
- start it with Moonraker, for example `SDCARD_PRINT_FILE`
- monitor job state until completed or failed
- verify all expected frames were produced
- run analysis
- write report artifacts and machine-readable facts

The orchestrator does not capture frames directly and does not move the printer
pose-by-pose through Moonraker during acquisition.

### Acquisition G-code Job

The acquisition job is a generated G-code file. It is the source of truth for
the physical timeline of the measurement.

Responsibilities:

- switch tools when the measurement requires it
- set lighting/profile when the measurement requires it
- move to exactly the planned poses
- issue `M400` before each capture
- issue an explicit settling delay such as `G4 P150` or `G4 P750` before capture
  where the measurement requires mechanical or exposure settling
- issue one blocking `VISION_CAPTURE_SYNC` for each planned frame
- wrap the capture sequence in `VISION_JOB_BEGIN` and `VISION_JOB_END`

The G-code job should be fast. Klipper can queue motion normally between capture
points, and `M400` plus the optional settling delay plus `VISION_CAPTURE_SYNC` only
creates hard synchronization at the image timestamps.

### Klipper Capture Primitive

The current macro named `VISION_CAPTURE` uses `action_call_remote_method`, and
the current daemon queues work asynchronously. That name should stay available
for ad-hoc still captures, manual debugging, and compatibility with existing
macros.

For the job architecture, the new blocking primitive is `VISION_CAPTURE_SYNC`.
The preferred implementation is a small Klipper extra/module, for example
`[vision]`, that registers commands like:

```gcode
VISION_JOB_BEGIN JOB=<job_id> MANIFEST_HASH=<hash> GCODE_HASH=<hash>
VISION_PROFILE CAMERA=<camera> PROFILE=<profile>
VISION_CAPTURE_SYNC JOB=<job_id> SEQ=<n> FRAME=<frame_id> CAMERA=<camera> PROFILE=<profile>
VISION_JOB_END JOB=<job_id> EXPECTED_FRAMES=<n>
```

`VISION_JOB_BEGIN` behavior:

1. call Klipper's move wait defensively so the job begins at a clean motion
   boundary
2. ask `visiond` to acquire the active job lock
3. verify the manifest exists, is immutable, and matches `MANIFEST_HASH`
4. verify the manifest state is `prepared`
5. verify `GCODE_HASH` matches the immutable G-code hash recorded in the manifest
6. transition the job to `acquiring`
7. initialize the expected next capture sequence to `0`

`VISION_PROFILE` behavior:

1. request a profile change explicitly for a camera
2. block until `vision-framebuffer` reports that the requested profile is active
3. raise a G-code error on timeout or mismatch

Camera-specific commands such as `NOZZLE_CAM_PROFILE` may remain as wrappers
around `VISION_PROFILE`, but `VISION_PROFILE` is the core job command.

`VISION_CAPTURE_SYNC` behavior:

1. call Klipper's move wait defensively, even though generated G-code should
   already emit `M400`
2. verify the job is `acquiring`
3. verify `SEQ` is exactly the next expected monotonic sequence number
4. verify `FRAME` matches the manifest entry for that sequence
5. verify `PROFILE` is already active; capture must not silently switch profiles
6. collect the current Klipper status needed for metadata
7. send a synchronous request to `visiond`
8. wait for success or timeout without blocking Klipper's reactor or MCU
   servicing
9. return to Klipper only after the image and metadata are durable on disk
10. raise a G-code error on failure, causing the virtual SD job to fail

`VISION_JOB_END` behavior:

1. call Klipper's move wait defensively
2. verify the job is `acquiring`
3. ask `visiond` to verify that every manifest frame has a complete atomic
   commit
4. verify `EXPECTED_FRAMES` matches the manifest
5. transition the job to `acquired`
6. release the acquisition lock

This avoids the most dangerous ambiguity: Klipper should not continue to the
next pose while the previous image is still pending in a host queue.

Compatibility alternatives, such as keeping the current async `VISION_CAPTURE`
macro, are useful for manual capture, but the job path must use
`VISION_CAPTURE_SYNC`. The blocking behavior is the core contract.

The command may block the G-code stream, but it must not freeze Klipper's event
loop. The implementation should use Klipper reactor timers/file descriptors or a
small nonblocking state machine around the `visiond` socket rather than a plain
blocking socket read inside the reactor path.

### visiond

`visiond` is the acquisition daemon. It can evolve from the current
`vision_capture.py` service, but in the new architecture it should be job-aware
and synchronous for capture requests.

Responsibilities:

- own the job/frame output layout
- serialize capture requests per camera
- read the latest frame from the existing RAM framebuffer service
- wait for a fresh frame by monotonic framebuffer sequence, not by UTC timestamp
- verify JPEG validity and resolution
- verify the requested camera profile when one is specified
- write image and metadata atomically
- reply success only after files are durable
- reply failure with a specific reason on timeout, stale frame, profile mismatch,
  missing camera, or invalid frame

The current `vision-framebuffer` service remains useful: it owns V4L2 and keeps
the dashboard stream/capture source warm. `visiond` should not re-open cameras
for every frame if the framebuffer can provide fresh images reliably.

### Monotonic Frame Sequencing

UTC timestamps are useful metadata, but they should not decide whether a frame
is fresh enough for a capture request. Clock adjustments, timezone handling, and
filesystem timestamp granularity can all create false freshness.

Instead, each `vision-framebuffer` instance should expose a monotonic
`frame_seq` counter:

- starts at `0` when the framebuffer service starts
- increments by one after each complete framebuffer image/metadata update
- is persisted in `latest.json`
- is returned by the framebuffer `/state` endpoint

Capture flow:

1. `VISION_CAPTURE_SYNC` asks `visiond` to capture `SEQ=n`.
2. `visiond` reads the current framebuffer `frame_seq` before waiting.
3. `visiond` waits until the framebuffer reports `frame_seq > previous_seq`.
4. `visiond` copies that exact frame and records both framebuffer sequence and
   job capture sequence in the sidecar.

The job capture `SEQ` and framebuffer `frame_seq` are different counters:

- job `SEQ` is the deterministic manifest order
- framebuffer `frame_seq` proves the image came from a new camera frame

## Atomic Frame Commit Rules

A frame counts as complete only when both the image and sidecar exist and
validate.

Rules:

- frame ids are immutable within a job
- an existing frame id must never be overwritten
- write image to a temporary filename in the same filesystem
- verify JPEG magic, dimensions, and expected profile metadata
- write sidecar JSON to a temporary filename
- fsync file contents where practical
- atomically rename the image into place
- atomically rename the sidecar into place
- record the committed frame in the job state only after both files validate
- if either final file is missing or invalid, the frame is incomplete

`VISION_JOB_END` must re-validate all expected frame commits from the manifest
before transitioning `acquiring -> acquired`.

## Job Directory Layout

Proposed layout for nozzle camera jobs:

```text
/home/pi/printer_data/vision/nozzle_cam/jobs/
  idex_nozzle_sweep_20260712T172140Z/
    index.html
    manifest.json
    acquisition.gcode
    state.json
    events.jsonl
    frames/
      t0_dx0p0.jpg
      t0_dx0p0.json
      t0_dx3p0.jpg
      t0_dx3p0.json
      t1_dx0p0.jpg
      t1_dx0p0.json
      t1_dx3p0.jpg
      t1_dx3p0.json
    analysis/
      raw_contact_sheet.jpg
      overlay_contact_sheet.jpg
      result.json
      facts.json
      overlays/
        t0_dx0p0_overlay.jpg
        t1_dx0p0_overlay.jpg
```

The web URLs would mirror the current convention:

```text
http://menderpi.local/vision/
http://menderpi.local/vision/nozzle_cam/jobs/<job_id>/
http://menderpi.local/vision/nozzle_cam/jobs/<job_id>/analysis/raw_contact_sheet.jpg
http://menderpi.local/vision/nozzle_cam/jobs/<job_id>/analysis/overlay_contact_sheet.jpg
http://menderpi.local/vision/nozzle_cam/jobs/<job_id>/analysis/result.json
```

We may keep compatibility symlinks:

```text
/home/pi/printer_data/vision/nozzle_cam/nozzle_sweep/latest_contact_sheet.jpg
/home/pi/printer_data/vision/nozzle_cam/nozzle_sweep/latest_result.json
```

## Manifest

The orchestrator writes `manifest.json` before starting the G-code job.
Manifests are immutable and versioned: once a job enters `prepared`, the
manifest must not be edited. Corrections create a new job id.

Example:

```json
{
  "schema_version": 1,
  "job_id": "idex_nozzle_sweep_20260712T172140Z",
  "kind": "idex_nozzle_sweep",
  "camera": "nozzle_cam",
  "profile": "analysis",
  "created_at_utc": "2026-07-12T17:21:40Z",
  "manifest_hash": "sha256:...",
  "gcode_file": "acquisition.gcode",
  "gcode_hash": "sha256:...",
  "frame_count": 10,
  "software_versions": {
    "orchestrator": "vision_nozzle_align.py:...",
    "visiond": "vision_capture.py:...",
    "klipper": "v0.13.0-650-gca8230d50-dirty"
  },
  "klipper_config_hash": "sha256:...",
  "camera_settings": {
    "profile": "analysis",
    "resolved_profile": "nozzle_cam_analysis",
    "device": "/dev/v4l/by-id/usb-Vimicro_corp._PC-LM1E_Camera_PC-LM1E_Audio-video-index0",
    "width": 1920,
    "height": 1080
  },
  "preconditions": {
    "required_homed_axes": "xyz",
    "require_idle": true
  },
  "frames": [
    {
      "frame": "t0_dx0p0",
      "tool": "T0",
      "pose": {"x": 195.0, "y": -14.8, "z": 20.0},
      "lighting": "nozzle_cam_analysis_light",
      "profile": "analysis"
    },
    {
      "frame": "t1_dx0p0",
      "tool": "T1",
      "pose": {"x": 195.0, "y": -14.8, "z": 20.0},
      "lighting": "nozzle_cam_analysis_light",
      "profile": "analysis"
    }
  ]
}
```

The manifest hash should be computed over a canonical JSON representation with
the `manifest_hash` field omitted or set to a fixed placeholder. The same hash
is passed to `VISION_JOB_BEGIN`.

The G-code hash should be computed over a canonical byte representation of the
generated acquisition file with every `MANIFEST_HASH=...` token replaced by
`MANIFEST_HASH=sha256:PLACEHOLDER` and every `GCODE_HASH=...` token replaced by
`GCODE_HASH=sha256:PLACEHOLDER`. The final file may then embed the real
`MANIFEST_HASH` and `GCODE_HASH` values in `VISION_JOB_BEGIN`. `VISION_JOB_BEGIN`
verifies the supplied `GCODE_HASH` against the immutable value in the manifest.
In v1, this does not depend on Klipper exposing the currently running virtual SD
filename or file hash; the orchestrator records the uploaded filename and hash
externally when starting the job.

## Per-frame Metadata

Every captured frame should have a sidecar JSON file. The sidecar is part of the
data contract between acquisition and analysis.

Suggested fields:

```json
{
  "job_id": "idex_nozzle_sweep_20260712T172140Z",
  "frame": "t0_dx0p0",
  "job_seq": 0,
  "captured_at_utc": "2026-07-12T17:21:45.123456Z",
  "image_path": "frames/t0_dx0p0.jpg",
  "camera": "nozzle_cam",
  "profile": {
    "requested": "analysis",
    "active": "nozzle_cam_analysis"
  },
  "klipper": {
    "tool": "T0",
    "homed_axes": "xyz",
    "gcode_position": [195.0, -14.8, 20.0, 0.0],
    "toolhead_position": [195.0, -14.8, 20.0, 0.0]
  },
  "framebuffer": {
    "frame_seq": 12345,
    "source_timestamp_utc": "2026-07-12T17:21:45.090000Z",
    "age_s": 0.033
  },
  "image": {
    "width": 1920,
    "height": 1080,
    "sha256": "..."
  }
}
```

The analyzer should consume these sidecars instead of inferring pose, tool, or
profile from filenames.

## Analysis Output

The analyzer writes facts after acquisition completes. For the current IDEX
nozzle sweep, facts might include:

```json
{
  "ok": true,
  "measurement": "idex_nozzle_sweep",
  "job_id": "idex_nozzle_sweep_20260712T172140Z",
  "frame_count": 10,
  "global_nozzle_roi": [942, 445, 280, 172],
  "cross_match": {
    "accepted": true,
    "rms_px": 0.5695,
    "usable_pairs": 66
  },
  "nozzle_delta_t1_minus_t0": {
    "dx_px": -7.684,
    "dy_px": -2.829,
    "along_x_mm_approx": -0.98645,
    "perpendicular_mm_approx": -0.36562
  }
}
```

Applying calibration remains a separate explicit step. The analyzer can produce
a recommended offset, but it should not silently mutate `calib.yaml` or Klipper
state.

## User Interface

The vision system should have a small browser UI served from the printer, so a
user can start jobs, watch acquisition, inspect images, and review analysis
without SSH.

The primary entrypoint should be:

```text
http://menderpi.local/vision/
```

This page should show:

- current printer/vision readiness: Klipper ready, printer idle, homed axes,
  camera online, active profile, active light scene
- the active vision job, if any
- queued/prepared jobs waiting to run
- recent jobs grouped by terminal state: `completed`, `failed`, `abandoned`
- available job types, such as IDEX nozzle sweep, LED index contact sheet, and
  camera exposure/focus checks

### Starting a Job

Starting a job should be an orchestrator action, not a hand-written G-code
upload by the user. The UI sends a request to the local vision orchestrator,
which then:

1. checks preconditions
2. creates the job directory
3. writes `manifest.json`
4. writes `acquisition.gcode`
5. computes manifest and G-code hashes
6. uploads or writes the G-code into the virtual SD path
7. starts the job through Moonraker

The UI should not send pose-by-pose motion commands. Its job is to choose a
measurement type and parameters, then ask the orchestrator to create and start a
normal vision job.

For the first version, job parameters can be intentionally small and explicit:

- job type
- camera
- camera profile
- optional pose range or preset
- settle time preset
- dry-run/preview mode that generates the manifest and G-code but does not
  start the virtual SD print

If a precondition fails, the UI should show the exact failed check and not start
the job. It should not offer hidden recovery moves. Homing, parking, and setup
moves remain explicit user actions outside the vision job unless a specific job
type deliberately includes them in generated G-code.

The minimal mutating API can be:

```text
POST /vision/api/jobs/prepare
POST /vision/api/jobs/<job_id>/start
POST /vision/api/jobs/<job_id>/abandon
```

`prepare` creates immutable artifacts but does not move the printer. `start`
starts the already prepared virtual SD job. `abandon` is only for jobs that have
not completed successfully; it records intent and leaves existing artifacts in
place for diagnosis.

### Job Queue

Only one acquisition job may run at a time, but the UI can present a simple
queue model:

- `draft`: parameters selected in the browser, not yet materialized
- `prepared`: manifest and G-code generated, not yet started
- `active`: currently acquiring or analysing
- terminal history: completed, failed, abandoned

The queue page should be backed by JSON files under the vision directory, not a
separate database. A top-level `jobs.json` can list job ids, state, kind,
created time, started time, completed time, frame count, and links to each job
detail page.

Prepared jobs are immutable once generated. Editing parameters creates a new
prepared job with a new job id.

### Job Detail Page

Each job directory should contain a generated `index.html`:

```text
http://menderpi.local/vision/nozzle_cam/jobs/<job_id>/
```

The detail page should be useful while the job is running and after it finishes.
It should show:

- current state from the strict job state machine
- acquisition progress: committed frames over expected frames
- analysis progress and terminal result
- failure reason, if any
- manifest hash and G-code hash
- links to `manifest.json`, `acquisition.gcode`, `state.json`, and logs
- a frame table with sequence number, frame id, tool, pose, profile, capture
  time, framebuffer sequence, and image validity
- raw image thumbnails as soon as atomic frame commits complete
- sidecar metadata links for every frame
- overlays as soon as analysis produces them
- contact sheets for raw acquisition and analyzed overlays
- `facts.json` and `result.json` rendered as readable tables

The page should poll lightweight JSON files such as `state.json`, `jobs.json`,
and per-frame sidecars. WebSockets are optional later; periodic polling is
enough for v1 and keeps the UI robust if the browser reloads.

### Images and Overlays

Raw captures should be visible during acquisition. Analysis artifacts appear
later:

- `frames/<frame>.jpg`: raw committed image
- `frames/<frame>.json`: capture sidecar
- `analysis/raw_contact_sheet.jpg`: contact sheet of raw frames
- `analysis/overlays/<frame>_overlay.jpg`: detection overlay for one frame
- `analysis/overlay_contact_sheet.jpg`: contact sheet of analyzed overlays
- `analysis/result.json`: analysis status and diagnostic measurements
- `analysis/facts.json`: accepted machine-readable facts

The UI should never hide failed detections behind fallback graphics. If an
expected detection fails, the overlay area should show the raw frame, the failed
detection name, and the specific error. Partial frames and partial overlays stay
available for diagnosis.

### Result Review

For calibration jobs, the result page should separate observation from action:

- show the measured offsets and quality metrics
- show whether the analyzer accepted or rejected the measurement
- link to the exact frames and overlays that support the result
- offer a downloadable/appliable recommendation only when the result is
  accepted
- never mutate `calib.yaml`, printer config, or live Klipper state silently

Applying a calibration remains an explicit follow-up command or UI action with a
separate confirmation step.

### Generated Static Pages First

The first implementation should prefer generated static HTML plus JSON artifacts
over a large web application. The orchestrator can write or refresh:

```text
/home/pi/printer_data/vision/index.html
/home/pi/printer_data/vision/jobs.json
/home/pi/printer_data/vision/nozzle_cam/jobs/<job_id>/index.html
/home/pi/printer_data/vision/nozzle_cam/jobs/<job_id>/state.json
```

A tiny local HTTP/API service is still needed for mutating actions such as
starting or abandoning a job. Everything else should be readable as static
files, so the UI remains useful even after a daemon restart.

The generated pages should contain enough links that a user can copy a job URL
into notes or chat and get the same artifacts later.

## Failure Semantics

Acquisition failures should fail hard.

Examples:

- `VISION_JOB_BEGIN` sees a manifest hash mismatch
- `VISION_CAPTURE_SYNC` times out waiting for a fresh frame
- requested camera profile is not active
- output frame is not a valid JPEG
- capture `SEQ` skips or repeats a manifest sequence number
- frame id already exists for this job
- job id is unknown or not active
- printer loses ready state during acquisition
- any expected frame from the manifest is missing

If any of these happen, the virtual SD job should fail and the orchestrator
should not produce calibration facts. It may still produce a diagnostic report
showing partial frames and the failure reason.

Failed acquisition leaves the printer exactly at the failure pose by default.
There is no implicit home, park, restore, or cleanup move. If a future job type
needs cleanup, that cleanup must be explicit generated G-code in the acquisition
file, not hidden behavior in the capture command or orchestrator.

Analysis failures should also be explicit:

- missing expected detection
- red marker fit failed
- no nozzle candidates
- cross-match rejected

The current "no fallback" rule should stay: if an expected detection fails, the
result is failed, not estimated.

## Cancellation and Restart Semantics

Vision jobs are non-resumable.

If the printer, Klipper, Moonraker, `visiond`, or the orchestrator restarts while
a job is `acquiring` or `analysing`, the next process to inspect that job must
mark it `abandoned`. It must not continue from the last frame, because the
physical printer state, lighting state, camera profile, and frame freshness
contract may no longer match the manifest.

Cancellation behavior:

- a user cancel of the virtual SD print marks an active acquisition job
  `abandoned`
- a Klipper shutdown during acquisition marks the job `abandoned`
- a host daemon restart with an active job lock marks the job `abandoned`
- a timeout waiting for `VISION_JOB_END` may mark the job `failed` if the
  orchestrator observed the exact timeout, or `abandoned` if discovered later
- abandoned jobs keep all partial frames for diagnostics
- rerun always means generate a new `job_id`

`failed` and `abandoned` are both terminal. Neither may transition back to
`prepared` or `acquiring`.

## Locking and Concurrency

Only one vision acquisition job should run at a time per printer.

Suggested rules:

- `visiond` holds an active-job lock.
- `VISION_JOB_BEGIN` is the only command that can acquire the active-job lock.
- `VISION_JOB_END` releases the lock only after complete frame verification.
- starting a second job fails unless the first is terminal: `completed`,
  `failed`, or `abandoned`.
- frame writes are atomic.
- frame ids are unique within a job.
- reruns create new job ids instead of overwriting old images.
- daemon startup scans for stale `prepared`, `acquiring`, or `analysing` jobs
  and marks interrupted ones `abandoned` according to the restart rules.

This keeps artifact paths stable and makes debugging much easier.

## Relationship to Current Nozzle Sweep

Current behavior:

- `IDEX_NOZZLE_VISION_SWEEP` calls a remote method.
- `vision_capture.py` starts `vision_nozzle_align.py`.
- `vision_nozzle_align.py` drives motion pose-by-pose through Moonraker, captures
  each image, then analyzes.

Proposed behavior:

- `vision_nozzle_align.py` becomes an orchestrator/analyzer.
- It generates `acquisition.gcode` and `manifest.json`.
- Moonraker starts the generated G-code file as a virtual SD print.
- Klipper performs the motion/capture timeline.
- `visiond` persists frames synchronously when Klipper reaches each
  `VISION_CAPTURE_SYNC`.
- The orchestrator analyzes only after the virtual SD job completes.

This moves physical timing authority from a Python loop into Klipper, which is
where it belongs.

## Implementation Sketch

### Stage 1: job model and generated G-code

- Add a host-side `VisionJob` data model.
- Generate `manifest.json` and `acquisition.gcode` for the existing nozzle
  sweep.
- Include `VISION_JOB_BEGIN`, monotonic `SEQ`, explicit settle delays, and
  `VISION_JOB_END` in generated G-code.
- Compute immutable manifest and G-code hashes.
- Keep current analysis code, but point it at a job frame directory.

### Stage 2: blocking capture command

- Add a Klipper extra/module that registers `VISION_JOB_BEGIN`,
  `VISION_PROFILE`, `VISION_CAPTURE_SYNC`, and `VISION_JOB_END`.
- Add a small synchronous API in `visiond`, probably over a Unix socket.
- Have the command block until `visiond` returns success/failure.
- Use nonblocking Klipper socket/reactor integration so MCU servicing continues
  while the G-code stream waits.
- Keep the existing async `VISION_CAPTURE` macro under its current name for
  manual capture and compatibility.

### Stage 3: monotonic framebuffer and atomic frame commits

- Add `frame_seq` to the framebuffer metadata and state endpoint.
- Make `visiond` wait for `frame_seq` advancement instead of UTC freshness.
- Implement image-plus-sidecar atomic commit validation.
- Enforce no overwrite of existing frame ids.

### Stage 4: orchestrator-driven virtual SD execution

- Have the nozzle sweep orchestrator write the job G-code into
  `~/printer_data/gcodes/vision_jobs/`.
- Start it through Moonraker.
- Monitor virtual SD/job state.
- Verify all frames against the manifest.
- Mark interrupted jobs `abandoned`, not resumable.

### Stage 5: migrate analysis and reports

- Make the analyzer consume manifest + frame sidecars.
- Produce `facts.json`, `result.json`, overlays, raw contact sheet, and overlay
  contact sheet.
- Keep compatibility symlinks for latest nozzle sweep reports.

### Stage 6: generated web UI

- Generate `/vision/index.html` and `/vision/jobs.json` for queue/history.
- Generate one job detail page per job with status, raw frames, sidecars,
  overlays, contact sheets, result JSON, facts JSON, and failure diagnostics.
- Add a small local API for mutating actions: create prepared job, start job,
  abandon prepared/active job where safe.
- Keep observation mostly static-file based so pages remain useful after daemon
  restarts.

### Stage 7: generalize measurements

Once the nozzle sweep works with this architecture, other vision tasks can use
the same acquisition layer:

- LED index contact sheet
- bed/nozzle feature scans
- camera focus/exposure sweeps
- toolhead-to-camera geometry checks
- part inspection poses

## Closed Design Decisions

- The blocking job capture command is `VISION_CAPTURE_SYNC`. The existing async
  `VISION_CAPTURE` macro keeps its current name for compatibility, manual
  captures, and debugging.
- Failed acquisition leaves the printer exactly at the failure pose. There is no
  implicit home, park, restore, or cleanup move. Cleanup is allowed only when it
  is explicit generated G-code for a specific job type.
- `VISION_PROFILE` is the generic blocking profile command. Camera-specific
  commands such as `NOZZLE_CAM_PROFILE` may remain as wrappers around it.
- `VISION_JOB_BEGIN` verifies immutable job identity through explicit
  `MANIFEST_HASH` and `GCODE_HASH` arguments. v1 does not require Klipper to
  expose the running virtual SD filename or hash to this command; the
  orchestrator records the uploaded filename and hash externally.

The design favors predictable motion and clear artifacts over convenience: no
implicit home, no implicit park, no implicit calibration update, no hidden frame
fallback, and no resume from partial acquisition.
