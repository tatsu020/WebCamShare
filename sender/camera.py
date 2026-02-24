import os

# Suppress noisy OpenCV logs. These must be set before importing cv2.
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_PRIORITY_LIST"] = "MSMF,DSHOW"
os.environ["OPENCV_VIDEOIO_OBSENSOR_BACKEND_PRIORITY"] = "0"

import cv2
import threading
import time

from .camera_enum_windows import CameraDescriptor, OpenCandidate, enumerate_camera_descriptors

_BACKEND_TO_CV_FLAG = {
    "DSHOW": cv2.CAP_DSHOW,
    "MSMF": cv2.CAP_MSMF,
}

_ENUM_LOCK = threading.Lock()
_DESCRIPTORS_BY_KEY: dict[str, CameraDescriptor] = {}
_DESCRIPTOR_ORDER: list[str] = []
_CACHE_INITIALIZED = False

_DEFAULT_OPEN_TIMEOUT_MSEC = 3000
_DEFAULT_READ_TIMEOUT_MSEC = 3000
_PROBE_READ_ATTEMPTS = 8
_PROBE_READ_INTERVAL_SEC = 0.05
_PROBE_MAX_INDEX = 8
_PROBE_BREAK_CONSECUTIVE_MISS = 3
_INITIAL_FRAME_READ_ATTEMPTS = 12
_INITIAL_FRAME_READ_INTERVAL_SEC = 0.03


def _candidate_priority(descriptor: CameraDescriptor, candidate: OpenCandidate) -> tuple[int, int, int]:
    preferred = descriptor.preferred_backend if descriptor.preferred_backend in ("MSMF", "DSHOW") else "MSMF"
    backend_rank = {preferred: 0, "MSMF": 1, "DSHOW": 2}
    return (backend_rank.get(candidate.backend, 9), -candidate.confidence, candidate.index)


def _open_capture(
    candidate: OpenCandidate,
    open_timeout_msec: int = _DEFAULT_OPEN_TIMEOUT_MSEC,
    read_timeout_msec: int = _DEFAULT_READ_TIMEOUT_MSEC,
) -> tuple[cv2.VideoCapture | None, str | None]:
    backend_flag = _BACKEND_TO_CV_FLAG.get(candidate.backend, cv2.CAP_ANY)
    open_params: list[int] = []
    if candidate.backend != "DSHOW":
        if hasattr(cv2, "CAP_PROP_OPEN_TIMEOUT_MSEC"):
            open_params.extend([cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, int(open_timeout_msec)])
        if hasattr(cv2, "CAP_PROP_READ_TIMEOUT_MSEC"):
            open_params.extend([cv2.CAP_PROP_READ_TIMEOUT_MSEC, int(read_timeout_msec)])

    try:
        cap = cv2.VideoCapture(candidate.index, backend_flag, open_params) if open_params else cv2.VideoCapture(candidate.index, backend_flag)
    except TypeError:
        cap = cv2.VideoCapture(candidate.index, backend_flag)
    except Exception as exc:
        return None, f"{candidate.backend}:{candidate.index} exception={exc}"

    if cap is None or not cap.isOpened():
        if cap is not None:
            cap.release()
        return None, f"{candidate.backend}:{candidate.index} open failed"

    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap, None


def _can_read_frame(cap: cv2.VideoCapture) -> bool:
    for _ in range(_PROBE_READ_ATTEMPTS):
        ret, _frame = cap.read()
        if ret:
            return True
        time.sleep(_PROBE_READ_INTERVAL_SEC)
    return False


def _classify_probe_failure(errors: list[str], had_open_no_frame: bool) -> tuple[str, str | None]:
    if had_open_no_frame:
        summary = "; ".join(errors[:6]) if errors else "camera opened but no frames"
        return "busy", summary

    if errors:
        summary = "; ".join(errors[:6])
        lowered = summary.lower()
        if "denied" in lowered or "access is denied" in lowered or "e_accessdenied" in lowered:
            return "permission_denied", summary
        return "open_failed", summary

    return "unknown", "no candidates"


def _build_dshow_open_probe_descriptors(max_index: int = _PROBE_MAX_INDEX) -> list[CameraDescriptor]:
    """
    Build descriptors by actively opening DSHOW index candidates.
    Only devices that can be opened and read are included.
    """
    descriptors: list[CameraDescriptor] = []
    consecutive_miss = 0
    found_any = False

    for index in range(max(1, max_index)):
        candidate = OpenCandidate("DSHOW", index, 140)
        cap, error = _open_capture(candidate)
        if cap is None:
            consecutive_miss += 1
            if found_any and consecutive_miss >= _PROBE_BREAK_CONSECUTIVE_MISS:
                break
            continue

        try:
            if not _can_read_frame(cap):
                consecutive_miss += 1
                if found_any and consecutive_miss >= _PROBE_BREAK_CONSECUTIVE_MISS:
                    break
                continue
        finally:
            try:
                cap.release()
            except Exception:
                pass

        descriptor = CameraDescriptor(
            key=f"probe-dshow-{index}",
            name=f"Camera {index}",
            moniker_id=f"probe-dshow-index:{index}",
        )
        descriptor.source_flags.add("open-probe")
        descriptor.preferred_backend = "DSHOW"
        descriptor.add_candidate("DSHOW", index, confidence=140)
        descriptor.availability = "available"
        descriptor.last_error = None
        descriptor.candidates = [candidate]
        descriptors.append(descriptor)

        found_any = True
        consecutive_miss = 0

    return descriptors


def _probe_descriptor_availability(descriptor: CameraDescriptor) -> None:
    if not descriptor.candidates:
        descriptor.availability = "unknown"
        descriptor.last_error = "no open candidates from OS enumeration"
        return

    ordered = sorted(descriptor.candidates, key=lambda c: _candidate_priority(descriptor, c))
    errors: list[str] = []
    had_open_no_frame = False

    for candidate in ordered:
        cap, error = _open_capture(candidate)
        if cap is None:
            if error:
                errors.append(error)
            continue

        try:
            if _can_read_frame(cap):
                descriptor.availability = "available"
                descriptor.last_error = None
                descriptor.preferred_backend = candidate.backend
                return

            had_open_no_frame = True
            errors.append(f"{candidate.backend}:{candidate.index} opened but frame read failed")
        finally:
            try:
                cap.release()
            except Exception:
                pass

    descriptor.availability, descriptor.last_error = _classify_probe_failure(errors, had_open_no_frame)


def _refresh_descriptor_cache(force: bool = False) -> list[CameraDescriptor]:
    global _CACHE_INITIALIZED
    with _ENUM_LOCK:
        if _CACHE_INITIALIZED and not force:
            return [_DESCRIPTORS_BY_KEY[key] for key in _DESCRIPTOR_ORDER]

        descriptors = enumerate_camera_descriptors()
        if not descriptors:
            for attempt in range(2):
                descriptors = _build_dshow_open_probe_descriptors()
                if descriptors:
                    print("Camera enumeration: OS APIs returned 0 devices. Using open-verified DSHOW probe.")
                    break
                if attempt == 0:
                    time.sleep(0.6)

        for descriptor in descriptors:
            if descriptor.availability == "available" and "open-probe" in descriptor.source_flags:
                continue
            _probe_descriptor_availability(descriptor)

        _DESCRIPTORS_BY_KEY.clear()
        _DESCRIPTOR_ORDER.clear()
        for descriptor in descriptors:
            _DESCRIPTORS_BY_KEY[descriptor.key] = descriptor
            _DESCRIPTOR_ORDER.append(descriptor.key)
        _CACHE_INITIALIZED = True

        available_count = sum(descriptor.availability == "available" for descriptor in descriptors)
        reasons: dict[str, int] = {}
        for descriptor in descriptors:
            if descriptor.availability == "available":
                continue
            reasons[descriptor.availability] = reasons.get(descriptor.availability, 0) + 1
        print(
            f"Camera enumeration: total={len(descriptors)} "
            f"available={available_count} unavailable={len(descriptors) - available_count} reasons={reasons}"
        )
        return descriptors


def _get_descriptor_by_key(camera_key: str) -> CameraDescriptor | None:
    descriptors = _refresh_descriptor_cache(force=False)
    if camera_key in _DESCRIPTORS_BY_KEY:
        return _DESCRIPTORS_BY_KEY[camera_key]
    for descriptor in descriptors:
        if descriptor.name == camera_key:
            return descriptor
    return None


def _descriptor_from_legacy_index(index: int) -> CameraDescriptor | None:
    descriptors = _refresh_descriptor_cache(force=False)
    if 0 <= index < len(descriptors):
        return descriptors[index]
    return None


def get_camera_names() -> list[str]:
    return [entry["name"] for entry in get_available_cameras()]


def get_camera_diagnostics(force_refresh: bool = True) -> list[dict[str, object]]:
    descriptors = _refresh_descriptor_cache(force=force_refresh)
    return [
        {
            "key": descriptor.key,
            "name": descriptor.name,
            "moniker_id": descriptor.moniker_id,
            "sources": sorted(descriptor.source_flags),
            "availability": descriptor.availability,
            "last_error": descriptor.last_error,
            "preferred_backend": descriptor.preferred_backend,
            "candidates": [
                {"backend": candidate.backend, "index": candidate.index, "confidence": candidate.confidence}
                for candidate in descriptor.candidates
            ],
        }
        for descriptor in descriptors
    ]


def get_camera_debug_info() -> list[dict[str, object]]:
    # Backward compatibility with existing debug calls.
    return get_camera_diagnostics(force_refresh=True)


def get_available_cameras(force_refresh: bool = True) -> list[dict[str, str]]:
    descriptors = _refresh_descriptor_cache(force=force_refresh)
    visible = [descriptor for descriptor in descriptors if descriptor.availability == "available" and descriptor.candidates]
    return [{"id": descriptor.key, "name": descriptor.name} for descriptor in visible]


class Camera:
    def __init__(self, camera_id=0, width=1280, height=720, descriptor_key: str | None = None):
        self.camera_id = camera_id
        self.descriptor_key = descriptor_key if descriptor_key is not None else (camera_id if isinstance(camera_id, str) else None)
        self.width = width
        self.height = height
        self.cap = None
        self.running = False
        self.thread = None
        self.current_frame = None
        self.lock = threading.Lock()

        self._jpeg_buffer = None
        self._jpeg_lock = threading.Lock()
        self._encode_params = [cv2.IMWRITE_JPEG_QUALITY, 100]
        self._open_timeout_msec = _DEFAULT_OPEN_TIMEOUT_MSEC
        self._read_timeout_msec = _DEFAULT_READ_TIMEOUT_MSEC
        self._opened_backend = None
        self._opened_index = None
        self._reported_width = width
        self._reported_height = height

    def _store_frame(self, frame) -> None:
        # Keep sender output in the camera's native frame size; do not resize here.
        ret_enc, jpeg = cv2.imencode(".jpg", frame, self._encode_params)
        if ret_enc:
            with self._jpeg_lock:
                self._jpeg_buffer = jpeg.tobytes()
        with self.lock:
            self.current_frame = frame

    def _read_initial_frame(self, cap: cv2.VideoCapture) -> tuple[int, int, object | None]:
        for _ in range(_INITIAL_FRAME_READ_ATTEMPTS):
            ret, frame = cap.read()
            if ret and frame is not None and frame.size > 0:
                h, w = frame.shape[:2]
                if w > 0 and h > 0:
                    return w, h, frame
            time.sleep(_INITIAL_FRAME_READ_INTERVAL_SEC)
        return 0, 0, None

    def _resolve_descriptor(self) -> CameraDescriptor | None:
        if isinstance(self.descriptor_key, str) and self.descriptor_key:
            descriptor = _get_descriptor_by_key(self.descriptor_key)
            if descriptor:
                return descriptor

        if isinstance(self.camera_id, int):
            descriptor = _descriptor_from_legacy_index(self.camera_id)
            if descriptor:
                return descriptor

        return None

    def _initial_candidates(self, descriptor: CameraDescriptor | None) -> list[OpenCandidate]:
        if descriptor and descriptor.candidates:
            return sorted(descriptor.candidates, key=lambda c: _candidate_priority(descriptor, c))

        if isinstance(self.camera_id, int):
            return [
                OpenCandidate("MSMF", self.camera_id, 100),
                OpenCandidate("DSHOW", self.camera_id, 90),
            ]
        return []

    def _open_with_candidate(self, candidate: OpenCandidate) -> tuple[cv2.VideoCapture | None, str | None]:
        cap, error = _open_capture(candidate, self._open_timeout_msec, self._read_timeout_msec)
        if cap is None:
            return None, error

        reported_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        reported_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self._reported_width = reported_width
        self._reported_height = reported_height

        actual_width, actual_height, initial_frame = self._read_initial_frame(cap)
        if actual_width > 0 and actual_height > 0:
            self.width = actual_width
            self.height = actual_height
            if initial_frame is not None:
                self._store_frame(initial_frame)
        elif reported_width > 0 and reported_height > 0:
            # Fallback when driver reports size but no frame was obtained during warmup.
            self.width = reported_width
            self.height = reported_height

        self._opened_backend = candidate.backend
        self._opened_index = candidate.index
        return cap, None

    def start(self):
        if self.running:
            return

        descriptor = self._resolve_descriptor()
        if descriptor is None:
            raise RuntimeError("Selected camera is no longer available. Refresh the camera list.")

        tried: set[tuple[str, int]] = set()
        errors: list[str] = []

        for candidate in self._initial_candidates(descriptor):
            cap, error = self._open_with_candidate(candidate)
            tried.add((candidate.backend, candidate.index))
            if cap is not None:
                self.cap = cap
                break
            if error:
                errors.append(error)

        if self.cap is None or not self.cap.isOpened():
            target = descriptor.name if descriptor else str(self.descriptor_key or self.camera_id)
            summarized = "; ".join(errors[:6]) if errors else (descriptor.last_error or "no candidates found")
            raise RuntimeError(
                f"Could not open camera '{target}'. "
                f"availability={descriptor.availability} tried={len(tried)} ({summarized})"
            )

        print(
            "Camera opened via "
            f"{self._opened_backend}:{self._opened_index} "
            f"reported={self._reported_width}x{self._reported_height} "
            f"actual={self.width}x{self.height}"
        )

        self.running = True
        self.thread = threading.Thread(target=self._update, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
        if self.cap:
            self.cap.release()

    def _update(self):
        while self.running:
            ret, frame = self.cap.read()
            if ret:
                h, w = frame.shape[:2]
                if w > 0 and h > 0 and (w != self.width or h != self.height):
                    old_w, old_h = self.width, self.height
                    self.width = w
                    self.height = h
                    print(f"Camera frame size changed: {old_w}x{old_h} -> {w}x{h}")
                self._store_frame(frame)
            else:
                time.sleep(0.1)

    def get_frame(self):
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None

    def get_frame_view(self):
        with self.lock:
            return self.current_frame

    def get_current_resolution(self) -> tuple[int, int]:
        return self.width, self.height

    def get_jpeg_frame(self):
        return self.get_jpeg_frame_direct()

    def get_jpeg_frame_direct(self):
        with self._jpeg_lock:
            return self._jpeg_buffer
