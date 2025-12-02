@echo off
echo ========================================
echo WebCam Share - Nuitka Debug Build
echo ========================================
echo.

REM This build keeps the console window for debugging

uv run python -m nuitka ^
    --standalone ^
    --onefile ^
    --enable-plugin=tk-inter ^
    --include-package=sender ^
    --include-package=receiver ^
    --include-package=utils ^
    --include-package=customtkinter ^
    --include-package=cv2 ^
    --include-package=numpy ^
    --include-package=requests ^
    --include-package=PIL ^
    --include-package=pyvirtualcam ^
    --include-package=pygrabber ^
    --output-filename=WebCamShare_debug.exe ^
    --output-dir=dist ^
    main.py

if errorlevel 1 (
    echo.
    echo Build failed!
    pause
    exit /b 1
)

echo.
echo Build completed! Output: dist\WebCamShare_debug.exe
pause
