@echo off
echo ========================================
echo WebCam Share - Nuitka Build Script
echo ========================================
echo.

REM Check if uv is available
uv --version >nul 2>&1
if errorlevel 1 (
    echo Error: uv is not installed or not in PATH
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Installing dependencies...
uv pip install nuitka ordered-set zstandard

echo.
echo Building with Nuitka...
echo This may take several minutes on first build.
echo.

uv run python -m nuitka ^
    --standalone ^
    --onefile ^
    --windows-console-mode=disable ^
    --enable-plugin=tk-inter ^
    --include-package=sender ^
    --include-package=receiver ^
    --include-package=utils ^
    --include-package=customtkinter ^
    --include-package=comtypes ^
    --include-package=pygrabber ^
    --include-module=cv2 ^
    --include-module=numpy ^
    --include-module=requests ^
    --include-module=PIL ^
    --include-module=pyvirtualcam ^
    --include-module=pythoncom ^
    --include-module=pywintypes ^
    --nofollow-import-to=numpy.tests ^
    --nofollow-import-to=numpy.testing ^
    --nofollow-import-to=numpy.distutils ^
    --nofollow-import-to=numpy.f2py ^
    --nofollow-import-to=numpy.conftest ^
    --nofollow-import-to=PIL.tests ^
    --nofollow-import-to=cv2.tests ^
    --nofollow-import-to=comtypes.test ^
    --output-filename=WebCamShare.exe ^
    --output-dir=dist ^
    --company-name="WebCamShare" ^
    --product-name="WebCam Share" ^
    --file-version=1.0.0.0 ^
    --product-version=1.0.0.0 ^
    --file-description="WebCam Streaming and Virtual Camera App" ^
    main.py

if errorlevel 1 (
    echo.
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo ========================================
echo Build completed successfully!
echo Output: dist\WebCamShare.exe
echo ========================================
pause
