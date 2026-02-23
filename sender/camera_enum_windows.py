import ctypes
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Iterable
from uuid import UUID

import pythoncom


VIDEO_INPUT_CATEGORY_CLSID = "{860BB310-5D01-11D0-BD3B-00A0C911CE86}"
MF_VERSION = 0x00020070
MFSTARTUP_FULL = 0x0
_HRESULT_OK = 0

_COM_RELEASE_METHOD_INDEX = 2
_IMFATTR_GET_ALLOCATED_STRING_METHOD_INDEX = 13
_IMFATTR_SET_GUID_METHOD_INDEX = 24

_GUID_PATTERN = re.compile(r"\{[0-9A-Fa-f-]{36}\}")


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", ctypes.c_ubyte * 8),
    ]

    @classmethod
    def from_string(cls, value: str) -> "GUID":
        raw = UUID(value).bytes_le
        return cls(
            int.from_bytes(raw[0:4], "little"),
            int.from_bytes(raw[4:6], "little"),
            int.from_bytes(raw[6:8], "little"),
            (ctypes.c_ubyte * 8).from_buffer_copy(raw[8:16]),
        )


_GUID_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE = GUID.from_string("c6e13360-30ac-11d0-a18c-00a0c9118956")
_GUID_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID = GUID.from_string("8ac3587a-4ae7-42d8-99e0-0a6013eef90f")
_GUID_MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME = GUID.from_string("60ddc264-4c3b-4fdc-ae17-15c5e6f3b6dd")
_GUID_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK = GUID.from_string("58f0aad8-22bf-4f8a-bb3d-d2c4978c6e2f")


@dataclass(frozen=True)
class OpenCandidate:
    backend: str
    index: int
    confidence: int


@dataclass
class CameraDescriptor:
    key: str
    name: str
    moniker_id: str
    candidates: list[OpenCandidate] = field(default_factory=list)
    source_flags: set[str] = field(default_factory=set)

    def add_candidate(self, backend: str, index: int, confidence: int) -> None:
        for candidate in self.candidates:
            if candidate.backend == backend and candidate.index == index:
                return
        self.candidates.append(OpenCandidate(backend=backend, index=index, confidence=confidence))


@dataclass(frozen=True)
class _MsmfDevice:
    name: str
    symbolic_link: str


def _normalize_name(name: str) -> str:
    return "".join(name.split()).casefold()


def _tokenize(value: str) -> str:
    token = re.sub(r"[^a-z0-9_-]", "-", value.casefold())
    token = re.sub(r"-{2,}", "-", token).strip("-")
    return token or "camera"


def _unique_key(base: str, existing_keys: set[str]) -> str:
    key = _tokenize(base)
    if key not in existing_keys:
        return key
    suffix = 2
    while True:
        candidate = f"{key}-{suffix}"
        if candidate not in existing_keys:
            return candidate
        suffix += 1


def _run_command(command: list[str], timeout_sec: int = 8) -> subprocess.CompletedProcess[str] | None:
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            creationflags=creationflags,
        )
    except Exception:
        return None


def _enumerate_dshow_names() -> list[str]:
    initialized = False
    try:
        pythoncom.CoInitialize()
        initialized = True
        from pygrabber.dshow_graph import FilterGraph

        graph = FilterGraph()
        names = graph.get_input_devices()
        if isinstance(names, list):
            return [str(name).strip() for name in names if str(name).strip()]
    except Exception:
        return []
    finally:
        if initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass
    return []


def _enumerate_dshow_registry_clsid_buckets() -> dict[str, list[str]]:
    registry_path = rf"HKLM\SOFTWARE\Classes\CLSID\{VIDEO_INPUT_CATEGORY_CLSID}\Instance"
    result = _run_command(["reg", "query", registry_path, "/s"], timeout_sec=8)
    if result is None or result.returncode != 0:
        return {}

    current_clsid = ""
    buckets: dict[str, list[str]] = {}
    for raw in (result.stdout or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("HKEY_"):
            matches = _GUID_PATTERN.findall(line)
            current_clsid = matches[-1].upper() if matches else ""
            continue

        if "FriendlyName" in line and "REG_SZ" in line:
            name = line.split("REG_SZ", 1)[1].strip()
            if not name:
                continue
            normalized = _normalize_name(name)
            buckets.setdefault(normalized, [])
            if current_clsid:
                buckets[normalized].append(current_clsid)

    return buckets


def _com_method(instance: ctypes.c_void_p, method_index: int, restype, *argtypes):
    if not instance or not instance.value:
        raise ValueError("COM instance pointer is null")
    vtable = ctypes.cast(instance, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
    function_ptr = vtable[method_index]
    prototype = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return prototype(function_ptr)


def _com_release(instance: ctypes.c_void_p) -> None:
    if not instance or not instance.value:
        return
    release = _com_method(instance, _COM_RELEASE_METHOD_INDEX, ctypes.c_ulong)
    release(instance)


def _read_mf_allocated_string(
    instance: ctypes.c_void_p,
    key: GUID,
    co_task_mem_free,
) -> str:
    get_allocated_string = _com_method(
        instance,
        _IMFATTR_GET_ALLOCATED_STRING_METHOD_INDEX,
        ctypes.c_long,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_uint32),
    )
    raw_value = ctypes.c_void_p()
    value_len = ctypes.c_uint32(0)
    hr = get_allocated_string(
        instance,
        ctypes.byref(key),
        ctypes.byref(raw_value),
        ctypes.byref(value_len),
    )
    if hr != _HRESULT_OK or not raw_value.value:
        return ""

    try:
        return ctypes.wstring_at(raw_value.value, value_len.value).strip()
    finally:
        co_task_mem_free(raw_value.value)


def _enumerate_msmf_devices() -> list[_MsmfDevice]:
    if os.name != "nt":
        return []

    attrs = ctypes.c_void_p()
    devices = ctypes.POINTER(ctypes.c_void_p)()
    device_count = ctypes.c_uint32(0)
    startup_called = False
    initialized = False
    msmf_devices: list[_MsmfDevice] = []

    try:
        pythoncom.CoInitialize()
        initialized = True
        mfplat = ctypes.WinDLL("mfplat")
        mf = ctypes.WinDLL("mf")
        ole32 = ctypes.OleDLL("ole32")
        co_task_mem_free = ole32.CoTaskMemFree
        co_task_mem_free.argtypes = [ctypes.c_void_p]
        co_task_mem_free.restype = None

        mf_startup = mfplat.MFStartup
        mf_startup.argtypes = [ctypes.c_ulong, ctypes.c_uint32]
        mf_startup.restype = ctypes.c_long

        mf_create_attributes = mfplat.MFCreateAttributes
        mf_create_attributes.argtypes = [ctypes.POINTER(ctypes.c_void_p), ctypes.c_uint32]
        mf_create_attributes.restype = ctypes.c_long

        mf_enum_device_sources = mf.MFEnumDeviceSources
        mf_enum_device_sources.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)),
            ctypes.POINTER(ctypes.c_uint32),
        ]
        mf_enum_device_sources.restype = ctypes.c_long

        if mf_startup(MF_VERSION, MFSTARTUP_FULL) != _HRESULT_OK:
            return []
        startup_called = True

        if mf_create_attributes(ctypes.byref(attrs), 1) != _HRESULT_OK or not attrs.value:
            return []

        set_guid = _com_method(
            attrs,
            _IMFATTR_SET_GUID_METHOD_INDEX,
            ctypes.c_long,
            ctypes.POINTER(GUID),
            ctypes.POINTER(GUID),
        )
        if set_guid(
            attrs,
            ctypes.byref(_GUID_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE),
            ctypes.byref(_GUID_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_GUID),
        ) != _HRESULT_OK:
            return []

        if mf_enum_device_sources(attrs, ctypes.byref(devices), ctypes.byref(device_count)) != _HRESULT_OK:
            return []

        for index in range(device_count.value):
            ptr_value = devices[index]
            if not ptr_value:
                continue
            device = ctypes.c_void_p(ptr_value)
            name = _read_mf_allocated_string(
                device,
                _GUID_MF_DEVSOURCE_ATTRIBUTE_FRIENDLY_NAME,
                co_task_mem_free,
            )
            if name:
                symbolic_link = _read_mf_allocated_string(
                    device,
                    _GUID_MF_DEVSOURCE_ATTRIBUTE_SOURCE_TYPE_VIDCAP_SYMBOLIC_LINK,
                    co_task_mem_free,
                )
                msmf_devices.append(_MsmfDevice(name=name, symbolic_link=symbolic_link))
            _com_release(device)

        if devices:
            co_task_mem_free(ctypes.cast(devices, ctypes.c_void_p).value)
    except Exception:
        return []
    finally:
        if attrs.value:
            _com_release(attrs)
        if startup_called:
            try:
                ctypes.WinDLL("mfplat").MFShutdown()
            except Exception:
                pass
        if initialized:
            try:
                pythoncom.CoUninitialize()
            except Exception:
                pass

    return msmf_devices


def _sort_candidates(candidates: Iterable[OpenCandidate]) -> list[OpenCandidate]:
    backend_rank = {"DSHOW": 0, "MSMF": 1}
    return sorted(candidates, key=lambda c: (-c.confidence, backend_rank.get(c.backend, 99), c.index))


def enumerate_camera_descriptors() -> list[CameraDescriptor]:
    descriptors: list[CameraDescriptor] = []
    existing_keys: set[str] = set()
    by_name_ordinal: dict[tuple[str, int], CameraDescriptor] = {}
    dshow_names = _enumerate_dshow_names()
    if dshow_names:
        registry_buckets = _enumerate_dshow_registry_clsid_buckets()
        name_counts: dict[str, int] = {}

        for index, name in enumerate(dshow_names):
            normalized = _normalize_name(name)
            name_counts[normalized] = name_counts.get(normalized, 0) + 1
            ordinal = name_counts[normalized]

            clsid = ""
            bucket = registry_buckets.get(normalized)
            if bucket:
                clsid = bucket.pop(0)

            moniker_id = f"dshow:{clsid}" if clsid else f"dshow-name:{normalized}:{ordinal}"
            key = _unique_key(moniker_id, existing_keys)
            existing_keys.add(key)

            descriptor = CameraDescriptor(key=key, name=name, moniker_id=moniker_id)
            descriptor.source_flags.add("dshow")
            descriptor.add_candidate("DSHOW", index, confidence=120)
            descriptors.append(descriptor)
            by_name_ordinal[(normalized, ordinal)] = descriptor

    msmf_devices = _enumerate_msmf_devices()
    if msmf_devices:
        name_counts: dict[str, int] = {}
        for index, msmf_device in enumerate(msmf_devices):
            normalized = _normalize_name(msmf_device.name)
            name_counts[normalized] = name_counts.get(normalized, 0) + 1
            ordinal = name_counts[normalized]

            descriptor = by_name_ordinal.get((normalized, ordinal))
            if descriptor is None:
                if msmf_device.symbolic_link:
                    moniker_id = f"msmf-link:{msmf_device.symbolic_link.casefold()}"
                else:
                    moniker_id = f"msmf-name:{normalized}:{ordinal}"
                key = _unique_key(moniker_id, existing_keys)
                existing_keys.add(key)

                descriptor = CameraDescriptor(key=key, name=msmf_device.name, moniker_id=moniker_id)
                descriptors.append(descriptor)
                by_name_ordinal[(normalized, ordinal)] = descriptor

            has_dshow = "dshow" in descriptor.source_flags
            descriptor.source_flags.add("msmf")
            descriptor.add_candidate("MSMF", index, confidence=105 if has_dshow else 100)

    for descriptor in descriptors:
        descriptor.candidates = _sort_candidates(descriptor.candidates)

    return descriptors
