import os

# OpenCVの不要なログを抑制 (cv2をインポートする前に設定する必要がある)
os.environ["OPENCV_LOG_LEVEL"] = "SILENT"
os.environ["OPENCV_VIDEOIO_PRIORITY_LIST"] = "DSHOW,MSMF"
os.environ["OPENCV_VIDEOIO_OBSENSOR_BACKEND_PRIORITY"] = "0"

import cv2
import threading
import time
from collections.abc import Iterable

from .camera_enum_windows import CameraDescriptor, OpenCandidate, enumerate_camera_descriptors

_BACKEND_TO_CV_FLAG = {
    "DSHOW": cv2.CAP_DSHOW,
    "MSMF": cv2.CAP_MSMF,
}

_ENUM_LOCK = threading.Lock()
_DESCRIPTORS_BY_KEY: dict[str, CameraDescriptor] = {}
_DESCRIPTOR_ORDER: list[str] = []


def _refresh_descriptor_cache(force: bool = False) -> list[CameraDescriptor]:
    with _ENUM_LOCK:
        if _DESCRIPTOR_ORDER and not force:
            return [_DESCRIPTORS_BY_KEY[key] for key in _DESCRIPTOR_ORDER]

        descriptors = enumerate_camera_descriptors()
        if not descriptors and _DESCRIPTOR_ORDER:
            print("Camera enumeration returned empty. Keeping previous cache.")
            return [_DESCRIPTORS_BY_KEY[key] for key in _DESCRIPTOR_ORDER]

        _DESCRIPTORS_BY_KEY.clear()
        _DESCRIPTOR_ORDER.clear()
        for descriptor in descriptors:
            _DESCRIPTORS_BY_KEY[descriptor.key] = descriptor
            _DESCRIPTOR_ORDER.append(descriptor.key)

        print(
            f"Camera enumeration: total={len(descriptors)} "
            f"(dshow={sum('dshow' in d.source_flags for d in descriptors)}, "
            f"msmf={sum('msmf' in d.source_flags for d in descriptors)})"
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
    """カメラ名の一覧を返す（UI表示向け）。"""
    return [entry["name"] for entry in get_available_cameras()]


def get_camera_debug_info() -> list[dict[str, object]]:
    """診断用: 統合済みカメラ情報（候補バックエンドを含む）を返す。"""
    descriptors = _refresh_descriptor_cache(force=True)
    return [
        {
            "key": descriptor.key,
            "name": descriptor.name,
            "moniker_id": descriptor.moniker_id,
            "sources": sorted(descriptor.source_flags),
            "candidates": [
                {"backend": candidate.backend, "index": candidate.index, "confidence": candidate.confidence}
                for candidate in descriptor.candidates
            ],
        }
        for descriptor in descriptors
    ]


def get_available_cameras():
    """利用可能なカメラの一覧を取得する（統合列挙版）。"""
    descriptors = _refresh_descriptor_cache(force=True)
    visible = [descriptor for descriptor in descriptors if descriptor.candidates]
    cameras = [{"id": descriptor.key, "name": descriptor.name} for descriptor in visible]
    return cameras


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

        # Zero-Copy設計: JPEG圧縮済みバッファ
        self._jpeg_buffer = None
        self._jpeg_lock = threading.Lock()
        self._encode_params = [cv2.IMWRITE_JPEG_QUALITY, 85]
        self._probe_timeout_sec = 2.0
        self._opened_backend = None
        self._opened_index = None

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

    def _candidate_priority(self, candidate: OpenCandidate) -> tuple[int, int, int]:
        backend_rank = {"DSHOW": 0, "MSMF": 1}
        return (-candidate.confidence, backend_rank.get(candidate.backend, 9), candidate.index)

    def _initial_candidates(self, descriptor: CameraDescriptor | None) -> list[OpenCandidate]:
        if descriptor and descriptor.candidates:
            return sorted(descriptor.candidates, key=self._candidate_priority)

        if isinstance(self.camera_id, int):
            return [
                OpenCandidate("DSHOW", self.camera_id, 80),
                OpenCandidate("MSMF", self.camera_id, 70),
            ]
        return []

    def _known_max_index(self, backend: str) -> int:
        descriptors = _refresh_descriptor_cache(force=False)
        known = [
            candidate.index
            for descriptor in descriptors
            for candidate in descriptor.candidates
            if candidate.backend == backend
        ]
        return max(known) if known else -1

    def _probe_candidates(self, descriptor: CameraDescriptor | None, tried: set[tuple[str, int]]) -> Iterable[OpenCandidate]:
        backend_order = ["DSHOW", "MSMF"]
        if descriptor:
            has_dshow = any(candidate.backend == "DSHOW" for candidate in descriptor.candidates)
            has_msmf = any(candidate.backend == "MSMF" for candidate in descriptor.candidates)
            if has_msmf and not has_dshow:
                backend_order = ["MSMF", "DSHOW"]

        max_indices = {
            "DSHOW": max(8, self._known_max_index("DSHOW") + 4),
            "MSMF": max(8, self._known_max_index("MSMF") + 4),
        }
        upper_bound = max(max_indices.values())
        for index in range(upper_bound):
            for backend in backend_order:
                if index >= max_indices[backend]:
                    continue
                key = (backend, index)
                if key in tried:
                    continue
                yield OpenCandidate(backend, index, 10)

    def _open_with_candidate(self, candidate: OpenCandidate) -> tuple[cv2.VideoCapture | None, str | None]:
        backend_flag = _BACKEND_TO_CV_FLAG.get(candidate.backend, cv2.CAP_ANY)
        cap = cv2.VideoCapture(candidate.index, backend_flag)
        if cap is None or not cap.isOpened():
            if cap is not None:
                cap.release()
            return None, f"{candidate.backend}:{candidate.index} open failed"

        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        if width > 0 and height > 0:
            self.width = width
            self.height = height
        self._opened_backend = candidate.backend
        self._opened_index = candidate.index
        return cap, None

    def start(self):
        if self.running:
            return

        descriptor = self._resolve_descriptor()
        tried: set[tuple[str, int]] = set()
        errors: list[str] = []

        initial_candidates = self._initial_candidates(descriptor)
        for candidate in initial_candidates:
            cap, error = self._open_with_candidate(candidate)
            tried.add((candidate.backend, candidate.index))
            if cap is not None:
                self.cap = cap
                break
            if error:
                errors.append(error)

        allow_cross_device_probe = descriptor is None or not descriptor.candidates
        if self.cap is None and allow_cross_device_probe:
            deadline = time.monotonic() + self._probe_timeout_sec
            for candidate in self._probe_candidates(descriptor, tried):
                if time.monotonic() >= deadline:
                    break
                cap, error = self._open_with_candidate(candidate)
                tried.add((candidate.backend, candidate.index))
                if cap is not None:
                    self.cap = cap
                    break
                if error:
                    errors.append(error)

        if self.cap is None or not self.cap.isOpened():
            target = descriptor.name if descriptor else str(self.descriptor_key or self.camera_id)
            summarized = "; ".join(errors[:6]) if errors else "no candidates found"
            raise RuntimeError(f"Could not open camera '{target}'. Tried={len(tried)} ({summarized})")

        print(f"Camera opened via {self._opened_backend}:{self._opened_index} at: {self.width}x{self.height}")

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
                # JPEG圧縮をカメラスレッドで事前実行（メインスレッドの負荷軽減）
                ret_enc, jpeg = cv2.imencode('.jpg', frame, self._encode_params)
                if ret_enc:
                    with self._jpeg_lock:
                        self._jpeg_buffer = jpeg.tobytes()
                with self.lock:
                    self.current_frame = frame
            else:
                time.sleep(0.1)

    def get_frame(self):
        """フレームのコピーを返す（外部で変更する場合用）"""
        with self.lock:
            if self.current_frame is not None:
                return self.current_frame.copy()
            return None

    def get_frame_view(self):
        """プレビュー用（コピーなし参照、読み取り専用）"""
        with self.lock:
            return self.current_frame

    def get_jpeg_frame(self):
        """互換性維持用（非推奨）"""
        return self.get_jpeg_frame_direct()

    def get_jpeg_frame_direct(self):
        """圧縮済みJPEGバッファを直接返す（Zero-Copy）"""
        with self._jpeg_lock:
            return self._jpeg_buffer
