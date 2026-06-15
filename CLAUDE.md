# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Video BA Pipe is a video stream analysis system that processes RTSP/video streams, applies AI detection algorithms (YOLO-based), and generates alerts with video recording capabilities. The system uses a **node-based workflow architecture** with multi-process execution and shared memory buffers for efficient video frame processing.

**Core Features:**
- Real-time video stream processing (RTSP, HTTP-FLV, HLS, local files)
- Node-based workflow system for flexible pipeline configuration
- Script-based algorithm plugins with hot-reload support
- Time-window based alert detection (prevents false alarms)
- ROI (Region of Interest) hot-zone configuration
- Video recording with pre/post alert buffering
- RabbitMQ integration for alert publishing
- Web UI for configuration and monitoring

## Development Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Initialize database
python app/setup_database.py

# Start the orchestrator (main entry point)
python app/main.py

# Start web interface (separate terminal)
python app/web/webapp.py

# Run all tests
pytest tests/

# Run a single test file
pytest tests/test_workflow_executor_confidence.py

# Run a specific test function
pytest tests/test_workflow_executor_confidence.py::test_function_name
```

### Docker Development

```bash
# CPU version
docker build -f Dockerfile.cpu -t video-ba-pipe:cpu .
docker-compose up

# CUDA/GPU version
docker build -f Dockerfile.cuda -t video-ba-pipe:cuda .
docker-compose -f docker-compose.yml.cuda up
```

## Architecture

### Process Model

The orchestrator (`app/core/orchestrator.py`) is the main entry point. For each active video source, it spawns one **source host process** (`app/source_workflow_host.py`). Each host process reads frames from the ring buffer once and fans them out to all workflows for that source via `WorkflowRunner` threads — avoiding per-workflow process overhead and duplicate buffer reads.

```
Orchestrator
  └── [source_workflow_host.py] (one process per source)
        ├── WorkflowRunner thread (workflow A)
        ├── WorkflowRunner thread (workflow B)
        └── ...each thread runs WorkflowExecutor
```

The legacy `app/workflow_worker.py` still exists but the orchestrator now uses the host-per-source model.

### Dual Ring Buffer Design

Two separate shared memory buffers serve different pipeline needs:

- **`VideoRingBuffer`** (`app/core/ringbuffer.py`): Analysis buffer — small, holds raw NV12 frames, used by workflow workers to get the latest frame. Capacity = `ANALYSIS_TARGET_FPS × ANALYSIS_BUFFER_SECONDS`.
- **`CompressedVideoRingBuffer`** (`app/core/compressed_ringbuffer.py`): Recording buffer — JPEG-compressed slots, larger duration, used by `VideoRecorderManager` to write pre-alert video. Capacity controlled by `RECORDING_BUFFER_DURATION`.

Buffer naming: `video_buffer.{source_code}` (analysis), `rec_buffer.{source_code}` (recording).

### Pixel Format Pipeline

The default runtime pixel format is **NV12** (YUV 4:2:0 planar), controlled by `VIDEO_FRAME_PIXEL_FORMAT`. Use `app/core/frame_utils.py` for all format conversions:

```python
from app.core.frame_utils import frame_to_bgr, frame_to_rgb, rgb_to_frame_format
bgr = frame_to_bgr(frame, pixel_format="nv12")
```

Script `process()` functions receive frames in the pipeline format. Convert to BGR/RGB as needed before passing to OpenCV or YOLO.

### Workflow Node System (`app/core/workflow_types.py`)

- **SourceNode**: Video source input (reads from ring buffer)
- **AlgorithmNode**: AI detection algorithms (script-based plugins)
- **FunctionNode**: Mathematical calculations (area ratios, distances, etc.)
- **RoiDrawNode**: ROI configuration (passes to downstream algorithms)
- **ConditionNode**: Conditional logic based on detection count
- **AlertNode/OutputNode**: Alert generation and video recording
- **ExternalApiNode**: Calls external HTTP APIs with detection results

### Script Algorithm System (`app/plugins/script_algorithm.py`)

Dynamic algorithm plugin loading. Scripts live in `app/user_scripts/`. Reusable helpers are in `app/user_scripts/common/`:
- `yolo_backends.py`: Unified inference for ultralytics YOLO, ONNX Runtime, RKNNLite
- `roi.py`: ROI filtering helpers
- `bbox.py`: Bounding box utilities
- `filter.py`: Detection filtering
- `result.py`: Result formatting
- `types.py`: Shared type definitions

### Database

- **Local development**: SQLite (auto-selected, stored at `app/data/db/ba.db`)
- **Docker**: PostgreSQL (auto-selected, connects to `postgres` host)
- Override with `DB_BACKEND=sqlite|postgres` env var
- ORM: Peewee (`app/core/database_models.py`)

**Core tables:** `Algorithm`, `VideoSource`, `Workflow`, `WorkflowNode`, `WorkflowConnection`, `Alert`, `MLModel`, `User`, `ExternalApi`, `SourceHealthLog`

## Key Configuration (`.env`)

**Decoders & Pipeline:**
- `VIDEO_DECODER_TYPE`: `ffmpeg_sw` (default) | `nvdec` | `rk_mpp`
- `VIDEO_FRAME_PIXEL_FORMAT`: `nv12` (default) | `rgb24` | `bgr24`
- `IS_EXTREME_DECODE_MODE`: Skip intermediate frames for performance
- `FFMPEG_SW_DECODER_THREADS`: Threads per ffmpeg decoder (default `1`)
- `DECODER_OUTPUT_QUEUE_SIZE`: Decoder output queue depth (default `5`)

**Analysis Buffer:**
- `ANALYSIS_TARGET_FPS`: Workflow sampling rate (default `3`)
- `ANALYSIS_BUFFER_SECONDS`: Analysis ring buffer duration (default `5`)

**Recording:**
- `RECORDING_ENABLED`: Toggle recording (default `true`)
- `RECORDING_BUFFER_DURATION`: Recording ring buffer duration in seconds (must be ≥ `PRE_ALERT_DURATION + POST_ALERT_DURATION`)
- `PRE_ALERT_DURATION` / `POST_ALERT_DURATION`: Recording window (default `5` each)
- `RECORDING_FPS`: Output FPS (default `5`)
- `RECORDING_JPEG_QUALITY`: JPEG quality for compressed buffer (default `85`)

**Alerts:**
- `ALERT_SUPPRESSION_DURATION`: Cooldown between same-type alerts (default `10`)
- `HEALTH_MONITOR_ENABLED`: Auto-restart unhealthy sources
- `NO_FRAME_CRITICAL_THRESHOLD`: Seconds without frames before restart

**RabbitMQ:**
- `RABBITMQ_ENABLED`: Enable message queue publishing
- `RABBITMQ_HOST/PORT/USER/PASSWORD/VHOST`: Connection settings

**Debugging:**
- `DETECTION_JSONL_LOG_ENABLED`: Log detection results to `logs/detection_results_YYYYMMDD.jsonl`

## Script Algorithm Plugin Structure

**Location:** `app/user_scripts/` (or `USER_SCRIPTS_ROOT` env path)

```python
SCRIPT_METADATA = {
    "name": "my_algorithm",
    "version": "1.0",
    "description": "My custom detection",
    "author": "Your Name",
    "options": []
}

def init(config):
    """Initialize algorithm, load models. config has: models, script_config, ext_config"""
    return state  # Optional state object

def process(frame, roi_regions, state, upstream_results=None):
    """
    Args:
        frame: numpy array in pipeline pixel format (default NV12)
        roi_regions: list of ROI configs
        state: object returned from init()
        upstream_results: dict from connected nodes
    Returns:
        {"detections": [{"box": [x1,y1,x2,y2], "label": str, "confidence": float}]}
    """
```

Use `app/user_scripts/templates/` as starting points. The `simple_yolo_detector.py` and `adaptive_yolo_detector.py` templates use `common/yolo_backends.py` for backend-agnostic YOLO inference.

## Workflow Node Configuration Reference

**Algorithm Node:**
```json
{
  "id": "algo_1", "type": "algorithm",
  "data": {"dataId": 5, "interval_seconds": 0.5, "config": {"roi_regions": []}}
}
```

**ROI Draw Node:**
```json
{
  "id": "roi_1", "type": "roi_draw",
  "data": {"roi_regions": [{"name": "入口", "polygon": [[x,y],...], "mode": "post_filter"}]}
}
```
ROI modes: `post_filter` (detect full frame, filter results — more accurate) or `pre_mask` (mask frame before detection — faster).

**Function Node** (multi-input math):
```json
{
  "id": "func_1", "type": "function",
  "data": {"dataId": 10, "config": {"function_name": "area_ratio", "threshold": 0.7, "operator": "less_than"}}
}
```
Single-input functions: `height_ratio_frame`, `width_ratio_frame`, `area_ratio_frame`, `size_absolute`
Multi-input (A/B): `area_ratio`, `height_ratio`, `iou_check`, `distance_check`

**Alert Node:**
```json
{
  "id": "alert_1", "type": "alert",
  "data": {
    "alert_level": "warning", "alert_message": "检测到人员",
    "trigger_condition": {"enable": true, "window_size": 30, "mode": "ratio", "threshold": 0.3},
    "suppression": {"enable": true, "seconds": 60}
  }
}
```
Window modes: `ratio` (detections/total frames), `consecutive` (consecutive detections), `count` (absolute count).

**Connection conditions:** `"detected"`, `"always"`, `"not_detected"`

## ROI Priority

1. Context from upstream `roi_draw` node (highest)
2. Algorithm node `config.roi_regions`
3. Algorithm database default `roi_regions`

## Important Constraints

1. **Pixel format**: Ring buffer outputs NV12 by default; convert with `frame_utils.py` before OpenCV/YOLO ops
2. **Process isolation**: Each source host runs in a separate process — use shared memory for cross-process data
3. **Thread safety**: Ring buffer uses atomic ops; avoid concurrent `read()` calls
4. **Memory management**: Always call `buffer.close()` and `buffer.unlink()` when done
5. **Script resources**: Scripts have configurable timeout and memory limits (`ext_config` per algorithm)
6. **Recording buffer**: `RECORDING_BUFFER_DURATION` must be ≥ `PRE_ALERT_DURATION + POST_ALERT_DURATION`

## File Structure Notes

- `app/core/decoder/`: FFmpeg/NVDEC/RK-MPP/VideoToolbox decoder implementations
- `app/core/frame_utils.py`: Pixel format detection and conversion utilities
- `app/core/workflow_executor.py`: Node scheduling and execution engine (shared by live and test modes)
- `app/core/workflow_runtime.py`: Workflow metadata helpers
- `app/user_scripts/templates/`: Script templates for algorithm and function nodes
- `app/user_scripts/common/`: Shared helpers for user scripts (yolo_backends, roi, bbox, etc.)
- `docs/`: RabbitMQ integration, RK3588 usage, Docker build workflows
- `scripts/`: SQLite→PostgreSQL migration, RabbitMQ consumer examples
