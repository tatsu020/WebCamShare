import ctypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
import pyvirtualcam

CUSTOM_CAMERA_CLSID = "{AEF3B972-5FA5-4647-9571-358EB472BC9E}"

# Load custom DLL if available
_dll = None
_dll_path = ""
_dll_load_error = ""


@dataclass(frozen=True)
class DriverStatus:
    dll_found: bool
    dll_path: str | None
    registered_path: str | None
    is_registered: bool
    path_matches: bool
    status_code: Literal["ok", "dll_not_found", "not_registered", "path_mismatch", "registry_error"]
    message: str


def _result(ok: bool, code: str, message: str) -> tuple[bool, str, str]:
    return ok, code, message


def _is_uac_cancel_error(error: Exception) -> bool:
    args = getattr(error, "args", ())
    for value in args:
        if isinstance(value, int) and value == 1223:
            return True
        if isinstance(value, str) and "cancel" in value.lower():
            return True

    text = str(error).lower()
    return "cancel" in text and "user" in text


def _run_regsvr32(parameters: str, action: str) -> tuple[bool, str, str]:
    try:
        import win32api
        import win32con
        import win32event
        import win32process
        import win32com.shell.shell as shell
        import win32com.shell.shellcon as shellcon

        process_info = shell.ShellExecuteEx(
            lpVerb="runas",
            lpFile="regsvr32.exe",
            lpParameters=parameters,
            fMask=shellcon.SEE_MASK_NOCLOSEPROCESS,
            nShow=win32con.SW_HIDE,
        )
        process_handle = process_info.get("hProcess")
        if process_handle:
            try:
                win32event.WaitForSingleObject(process_handle, win32event.INFINITE)
                exit_code = win32process.GetExitCodeProcess(process_handle)
            finally:
                win32api.CloseHandle(process_handle)

            if exit_code == 0:
                return _result(True, "success", f"Driver {action} completed successfully.")
            return _result(False, "regsvr32_failed", f"Driver {action} failed (regsvr32 exit code: {exit_code}).")

        return _result(True, "success", f"Driver {action} started.")
    except Exception as error:
        if _is_uac_cancel_error(error):
            return _result(False, "uac_cancelled", "User cancelled the UAC prompt.")

        try:
            result = ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                "regsvr32.exe",
                parameters,
                None,
                0,
            )
            if result <= 32:
                if result == 5:
                    return _result(False, "uac_cancelled", "UAC permission was denied.")
                return _result(False, "regsvr32_failed", f"Could not launch regsvr32 (ShellExecute code: {result}).")
            return _result(True, "success", f"Driver {action} started. Check UAC prompt.")
        except Exception as fallback_error:
            return _result(False, "regsvr32_failed", f"Failed to launch regsvr32: {fallback_error}")


def get_custom_dll_path() -> str | None:
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "webcamshare_camera.dll" if hasattr(sys, "_MEIPASS") else None,
        Path(__file__).resolve().parent / "webcamshare_camera.dll",
        Path.cwd() / "webcamshare_camera.dll",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            try:
                return str(candidate.resolve())
            except Exception:
                return str(candidate)
    return None


def get_registered_inproc_path(clsid: str = CUSTOM_CAMERA_CLSID) -> str | None:
    if sys.platform != "win32":
        return None

    import winreg

    key_suffix = f"CLSID\\{clsid}\\InprocServer32"
    lookup_keys = [
        (winreg.HKEY_CLASSES_ROOT, key_suffix),
        (winreg.HKEY_LOCAL_MACHINE, f"SOFTWARE\\Classes\\{key_suffix}"),
    ]

    for root, key_path in lookup_keys:
        try:
            with winreg.OpenKey(root, key_path) as key:
                value, _value_type = winreg.QueryValueEx(key, "")
                if isinstance(value, str) and value.strip():
                    return value.strip()
        except FileNotFoundError:
            continue
        except OSError:
            continue

    return None


def _strip_wrapping_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        text = text[1:-1]
    return text.strip()


def _get_long_path_name(path: str) -> str:
    if sys.platform != "win32" or not path:
        return path

    try:
        get_long_path_name = ctypes.windll.kernel32.GetLongPathNameW
        required = get_long_path_name(path, None, 0)
        if required <= 0:
            return path
        buffer = ctypes.create_unicode_buffer(required)
        written = get_long_path_name(path, buffer, required)
        if written <= 0:
            return path
        return buffer.value
    except Exception:
        return path


def _normalize_path(path: str | None) -> str:
    if not path:
        return ""

    cleaned = _strip_wrapping_quotes(path)
    if not cleaned:
        return ""

    try:
        normalized = str(Path(cleaned).resolve(strict=False))
    except Exception:
        normalized = os.path.abspath(cleaned)

    normalized = os.path.normpath(normalized)
    normalized = _get_long_path_name(normalized)
    return os.path.normcase(normalized)


def diagnose_custom_camera_registration(clsid: str = CUSTOM_CAMERA_CLSID) -> DriverStatus:
    dll_path = get_custom_dll_path()
    if not dll_path:
        return DriverStatus(
            dll_found=False,
            dll_path=None,
            registered_path=None,
            is_registered=False,
            path_matches=False,
            status_code="dll_not_found",
            message="webcamshare_camera.dll was not found.",
        )

    if sys.platform != "win32":
        return DriverStatus(
            dll_found=True,
            dll_path=dll_path,
            registered_path=None,
            is_registered=False,
            path_matches=False,
            status_code="registry_error",
            message="Driver registry diagnostics are available on Windows only.",
        )

    try:
        registered_path = get_registered_inproc_path(clsid)
    except Exception as error:
        return DriverStatus(
            dll_found=True,
            dll_path=dll_path,
            registered_path=None,
            is_registered=False,
            path_matches=False,
            status_code="registry_error",
            message=f"Could not read driver registry: {error}",
        )

    if not registered_path:
        return DriverStatus(
            dll_found=True,
            dll_path=dll_path,
            registered_path=None,
            is_registered=False,
            path_matches=False,
            status_code="not_registered",
            message="Driver is not registered. Click Install.",
        )

    path_matches = _normalize_path(dll_path) == _normalize_path(registered_path)
    if not path_matches:
        return DriverStatus(
            dll_found=True,
            dll_path=dll_path,
            registered_path=registered_path,
            is_registered=True,
            path_matches=False,
            status_code="path_mismatch",
            message="Registered DLL path differs from current app DLL. Click Install to repair.",
        )

    return DriverStatus(
        dll_found=True,
        dll_path=dll_path,
        registered_path=registered_path,
        is_registered=True,
        path_matches=True,
        status_code="ok",
        message="Custom driver is ready.",
    )


def init_custom_dll():
    global _dll, _dll_path, _dll_load_error
    if _dll is not None:
        return True

    _dll_load_error = ""
    _dll_path = get_custom_dll_path() or ""

    if not _dll_path:
        _dll_load_error = "webcamshare_camera.dll was not found."
        return False

    try:
        _dll = ctypes.CDLL(_dll_path)
        _dll.scCreateCamera.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_float]
        _dll.scCreateCamera.restype = ctypes.c_void_p
        _dll.scDeleteCamera.argtypes = [ctypes.c_void_p]
        _dll.scDeleteCamera.restype = None
        _dll.scSendFrame.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        _dll.scSendFrame.restype = None
        _dll.scWaitForConnection.argtypes = [ctypes.c_void_p, ctypes.c_float]
        _dll.scWaitForConnection.restype = ctypes.c_bool
        _dll.scIsConnected.argtypes = [ctypes.c_void_p]
        _dll.scIsConnected.restype = ctypes.c_bool
        return True
    except Exception as e:
        _dll = None
        _dll_load_error = str(e)
        print(f"Failed to load custom DLL: {e}")
        return False


def register_custom_camera():
    """Register the DLL to system (requires Admin). Returns (ok, code, message)."""
    if not init_custom_dll():
        if _dll_path:
            return _result(False, "dll_load_failed", f"Found DLL but could not load it: {_dll_load_error}")
        return _result(False, "dll_not_found", "webcamshare_camera.dll was not found.")

    return _run_regsvr32(f'/s "{_dll_path}"', "installation")


def unregister_custom_camera():
    """Unregister the DLL from system (requires Admin). Returns (ok, code, message)."""
    if not init_custom_dll():
        if _dll_path:
            return _result(False, "dll_load_failed", f"Found DLL but could not load it: {_dll_load_error}")
        return _result(False, "dll_not_found", "webcamshare_camera.dll was not found.")

    return _run_regsvr32(f'/u /s "{_dll_path}"', "uninstallation")


class VirtualCamera:
    def __init__(self, width=1280, height=720, fps=30, prefer_custom=True, allow_custom_when_mismatch=False):
        self.width = width
        self.height = height
        self.fps = fps
        self.prefer_custom = prefer_custom
        self.allow_custom_when_mismatch = allow_custom_when_mismatch
        self.cam = None
        self.is_custom = False

    def start(self) -> tuple[bool, str, str]:
        if self.cam:
            message = "Virtual camera is already running."
            return self.is_custom, "already_started", message

        custom_reason = ""
        can_try_custom = False

        diagnostic = diagnose_custom_camera_registration()
        if self.prefer_custom:
            if diagnostic.status_code == "ok":
                can_try_custom = True
            elif self.allow_custom_when_mismatch and diagnostic.status_code == "path_mismatch":
                can_try_custom = True
            else:
                custom_reason = diagnostic.message
        else:
            custom_reason = "Custom driver disabled by configuration."

        if can_try_custom:
            if init_custom_dll():
                try:
                    self.cam = _dll.scCreateCamera(self.width, self.height, float(self.fps))
                    if self.cam:
                        self.is_custom = True
                        message = "Virtual camera started (Custom DLL: WebCamShare Camera)"
                        print(message)
                        return True, "custom_started", message
                    custom_reason = "Custom camera creation returned null handle."
                except Exception as error:
                    custom_reason = f"Custom camera start failed: {error}"
                    print(custom_reason)
            else:
                custom_reason = _dll_load_error or "Failed to load custom camera DLL."
                print(custom_reason)

        # Fallback to pyvirtualcam
        try:
            self.cam = pyvirtualcam.Camera(width=self.width, height=self.height, fps=self.fps)
            self.is_custom = False
            if custom_reason:
                message = f"Virtual camera fallback started: {self.cam.device}"
            else:
                message = f"Virtual camera started: {self.cam.device}"
            print(message)
            return False, "fallback_started", message
        except Exception as error:
            details = f"Could not start virtual camera. Error: {error}"
            if custom_reason:
                details = f"{details} (Custom unavailable: {custom_reason})"
            raise RuntimeError(details)

    def reconfigure(self, width, height):
        width = int(width)
        height = int(height)
        if width <= 0 or height <= 0:
            raise ValueError(f"Invalid virtual camera size: {width}x{height}")

        if self.cam is not None and width == self.width and height == self.height:
            return False

        self.stop()
        self.width = width
        self.height = height
        self.start()
        return True

    def send_frame(self, frame):
        if not self.cam or frame is None:
            return False

        if frame.shape[1] != self.width or frame.shape[0] != self.height:
            return False

        if self.is_custom:
            # The custom softcam expects BGR internally because it copies bits directly to DirectShow (which usually uses RGB/BGR depending on subtype).
            # Actually softcam_vs2019 DShowSoftcam.cpp sets MEDIASUBTYPE_RGB24.
            # In PyVirtualCam RGB is expected, but let's check softcam simple_usage.py!
            # Ah! simple_usage.py says: "Note that the color component order should be BGR, not RGB."
            # So we can pass the BGR frame directly!
            if not frame.flags['C_CONTIGUOUS']:
                frame = np.ascontiguousarray(frame)
            _dll.scSendFrame(self.cam, frame.ctypes.data_as(ctypes.c_void_p))
        else:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.cam.send(frame_rgb)
            self.cam.sleep_until_next_frame()
        return True

    def stop(self):
        if self.cam:
            if self.is_custom:
                _dll.scDeleteCamera(self.cam)
            else:
                self.cam.close()
            self.cam = None
