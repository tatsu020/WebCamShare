@echo off
echo ========================================
echo WebCam Share - Nuitka Debug Build
echo ========================================
echo.

REM This build keeps the console window for debugging
set "ICON_OPT="
set "ICON_PATH="
if not exist "icon.ico" (
    if not exist "icon.png" (
        if exist "tools\\generate_icon.py" (
            echo Generating icon...
            uv run python tools\\generate_icon.py
        )
    )
)

if exist "icon.ico" (
    set "ICON_PATH=icon.ico"
) else if exist "icon.png" (
    set "ICON_PATH=icon.png"
)

if defined ICON_PATH (
    set "ICON_OPT=--windows-icon-from-ico=%ICON_PATH%"
) else (
    echo Note: icon.ico/icon.png not found. Building without custom icon.
)

uv run python -m nuitka ^
    --standalone ^
    --onefile ^
    %ICON_OPT% ^
    --enable-plugin=tk-inter ^
    --include-data-file=icon.ico=icon.ico ^
    --include-data-file=icon.png=icon.png ^
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
echo Copying license files...
if exist "dist\\icon.ico" del /F /Q "dist\\icon.ico" >nul
if exist "dist\\icon.png" del /F /Q "dist\\icon.png" >nul
if exist "LICENSE" copy /Y "LICENSE" "dist\\LICENSE" >nul
if exist "README.md" copy /Y "README.md" "dist\\README.md" >nul
if exist "THIRD_PARTY_NOTICES.txt" copy /Y "THIRD_PARTY_NOTICES.txt" "dist\\THIRD_PARTY_NOTICES.txt" >nul
if exist "LICENSES" xcopy /E /I /Y "LICENSES" "dist\\LICENSES" >nul

echo.
echo Build completed! Output: dist\WebCamShare_debug.exe
pause
