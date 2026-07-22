import threading
from types import SimpleNamespace

import numpy as np

from app.core.video_recorder import VideoRecorder
from app.plugins.script_algorithm import ScriptAlgorithm
import app.core.workflow_executor as workflow_executor_module
from app.core.workflow_executor import WorkflowExecutor


class _FakeHookManager:
    def has_hooks_for_algorithm(self, algorithm_id, hook_point):
        return False

    def execute_pre_detect_hooks(self, algorithm_id, frame, source_id):
        return frame, False

    def execute_post_detect_hooks(self, algorithm_id, detections, frame_rgb, source_id):
        return detections, False


class _FakeExecutor:
    def execute(self, func, **kwargs):
        return func(**kwargs), 0.5, True, None


def test_video_recorder_treats_decoded_compressed_frames_as_rgb():
    buffer = SimpleNamespace(pixel_format="nv12")
    recorder = VideoRecorder(buffer=buffer, save_dir="/tmp")
    frame_rgb = np.zeros((12, 16, 3), dtype=np.uint8)

    assert recorder._get_frame_pixel_format(frame_rgb) == "rgb24"


def test_script_algorithm_accepts_direct_rgb_frames():
    algo = ScriptAlgorithm.__new__(ScriptAlgorithm)
    algo.config = {"source_id": 0}
    algo.process_func = lambda frame, pixel_format=None, frame_width=None, frame_height=None, **kwargs: {
        "detections": [],
        "metadata": {
            "pixel_format": pixel_format,
            "shape": tuple(frame.shape),
            "frame_width": frame_width,
            "frame_height": frame_height,
        },
    }
    algo.executor = _FakeExecutor()
    algo.hook_manager = _FakeHookManager()
    algo.algorithm_id = None
    algo.script_state = None
    algo.script_path = "inline.py"
    algo._empty_detection_count = 0
    algo._last_empty_detection_log_at = 0.0
    algo.resolved_config = algo.config

    frame_rgb = np.zeros((8, 10, 3), dtype=np.uint8)
    result = algo.process(frame_rgb)

    assert result["detections"] == []
    assert result["metadata"]["pixel_format"] == "rgb24"
    assert result["metadata"]["shape"] == (8, 10, 3)
    assert result["metadata"]["frame_width"] == 10
    assert result["metadata"]["frame_height"] == 8


def test_workflow_executor_run_once_uses_configured_pixel_format(monkeypatch):
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    executor.workflow_id = 1
    executor.running = True
    executor.execution_results = {}
    executor.executed_nodes = []
    executor._state_lock = threading.Lock()
    captured = {}

    def fake_execute_by_topology_levels(executor=None, context=None):
        captured["frame_width"] = context["frame_width"]
        captured["frame_height"] = context["frame_height"]
        captured["frame"] = context.get("frame")
        captured["frame_pixel_format"] = context.get("frame_pixel_format")

    executor._execute_by_topology_levels = fake_execute_by_topology_levels
    executor._record_to_window_detector_for_all_alerts = lambda context: None

    monkeypatch.setattr(workflow_executor_module, "VIDEO_FRAME_PIXEL_FORMAT", "rgb24")

    frame_rgb = np.zeros((9, 11, 3), dtype=np.uint8)
    executor.run_once(frame_rgb, 123.456)

    assert captured["frame_width"] == 11
    assert captured["frame_height"] == 9
    assert captured["frame_pixel_format"] == "rgb24"
    assert captured["frame"].shape == (9, 11, 3)


def test_browser_video_writer_uses_h264_yuv420p_faststart(monkeypatch):
    from app.core.video_recorder import FfmpegBrowserVideoWriter
    import app.core.video_recorder as video_recorder_module

    captured = {}

    class _FakeStream:
        def __init__(self):
            self.closed = False
            self.payload = b""

        def write(self, payload):
            self.payload += payload

        def close(self):
            self.closed = True

        def read(self):
            return b""

    class _FakeProcess:
        def __init__(self, cmd, stdin=None, stdout=None, stderr=None):
            captured["cmd"] = cmd
            captured["stdin_arg"] = stdin
            captured["stdout_arg"] = stdout
            captured["stderr_arg"] = stderr
            self.stdin = _FakeStream()
            self.stderr = _FakeStream()

        def poll(self):
            return None

        def wait(self, timeout=None):
            captured["wait_timeout"] = timeout
            return 0

    monkeypatch.setattr(video_recorder_module.subprocess, "Popen", _FakeProcess)

    writer = FfmpegBrowserVideoWriter("/tmp/alert.mp4", fps=10, width=17, height=15)
    writer.write(np.zeros((15, 17, 3), dtype=np.uint8))
    writer.release()

    cmd = captured["cmd"]
    assert cmd[0] == "ffmpeg"
    assert "libx264" in cmd
    assert "yuv420p" in cmd
    assert "+faststart" in cmd
    assert "pad=ceil(iw/2)*2:ceil(ih/2)*2" in cmd
    assert cmd[-1] == "/tmp/alert.mp4"
    assert captured["wait_timeout"] == 30


def test_video_recorder_does_not_fallback_to_opencv_writer(monkeypatch):
    import app.core.video_recorder as video_recorder_module

    recorder = VideoRecorder(buffer=SimpleNamespace(pixel_format="rgb24"), save_dir="/tmp")

    def fail_ffmpeg(*args, **kwargs):
        raise FileNotFoundError("ffmpeg")

    def fail_if_opencv_writer_is_used(*args, **kwargs):
        raise AssertionError("OpenCV VideoWriter should not be used for alert recording")

    monkeypatch.setattr(video_recorder_module, "FfmpegBrowserVideoWriter", fail_ffmpeg)
    monkeypatch.setattr(video_recorder_module, "require_cv2", lambda: None)
    monkeypatch.setattr(
        video_recorder_module,
        "cv2",
        SimpleNamespace(VideoWriter=fail_if_opencv_writer_is_used),
    )

    frame_rgb = np.zeros((12, 16, 3), dtype=np.uint8)
    assert recorder._open_video_writer(frame_rgb, "/tmp/alert.mp4") is None
