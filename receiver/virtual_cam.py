import pyvirtualcam
import cv2
import numpy as np
import ctypes
import sys
from pathlib import Path

# Load custom DLL if available
_dll = None
_dll_path = ""
_dll_load_error = ""


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

def init_custom_dll():
    global _dll, _dll_path, _dll_load_error
    if _dll is not None:
        return True

    _dll_load_error = ""
    _dll_path = ""
    candidates = [
        Path(getattr(sys, "_MEIPASS", "")) / "webcamshare_camera.dll" if hasattr(sys, "_MEIPASS") else None,
        Path(__file__).resolve().parent / "webcamshare_camera.dll",
        Path.cwd() / "webcamshare_camera.dll",
    ]
    for c in candidates:
        if c and c.exists():
            _dll_path = str(c)
            break

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
    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        self.cam = None
        self.is_custom = False

    def start(self):
        # 1. Try Custom DLL First
        if init_custom_dll():
            try:
                # To actually make it appear in apps, it must be registered.
                # If the user hasn't registered it, wait... it might not show up.
                # We'll just create the instance and push frames. 
                self.cam = _dll.scCreateCamera(self.width, self.height, float(self.fps))
                if self.cam:
                    self.is_custom = True
                    print('Virtual camera started (Custom DLL: WebCamShare Camera)')
                    return
            except Exception as e:
                print(f"Custom camera start failed: {e}")

        # 2. Fallback to pyvirtualcam
        try:
            self.cam = pyvirtualcam.Camera(width=self.width, height=self.height, fps=self.fps)
            self.is_custom = False
            print(f'Virtual camera started: {self.cam.device}')
        except Exception as e:
            # Let's suggest registering custom as fallback
            raise RuntimeError(f"Could not start virtual camera. Error: {e}")

    def send_frame(self, frame):
        if self.cam:
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))

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

    def stop(self):
        if self.cam:
            if self.is_custom:
                _dll.scDeleteCamera(self.cam)
            else:
                self.cam.close()
            self.cam = None
