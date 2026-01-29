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

echo.
echo Building with Nuitka...
echo This may take several minutes on first build.
echo.

uv run python -m nuitka ^
    --standalone ^
    --onefile ^
    --windows-console-mode=disable ^
    %ICON_OPT% ^
    --enable-plugin=tk-inter ^
    --include-data-file=icon.ico=icon.ico ^
    --include-data-file=icon.png=icon.png ^
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
    --nofollow-import-to=setuptools ^
    --nofollow-import-to=pip ^
    --nofollow-import-to=pkg_resources ^
    --nofollow-import-to=unittest ^
    --nofollow-import-to=doctest ^
    --nofollow-import-to=pdb ^
    --nofollow-import-to=tkinter.test ^
    --nofollow-import-to=numpy.doc ^
    --lto=yes ^
    --python-flag=no_site ^
    --python-flag=no_asserts ^
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
echo Copying license files...
if exist "dist\\icon.ico" del /F /Q "dist\\icon.ico" >nul
if exist "dist\\icon.png" del /F /Q "dist\\icon.png" >nul
if exist "LICENSE" copy /Y "LICENSE" "dist\\LICENSE" >nul
if exist "README.md" copy /Y "README.md" "dist\\README.md" >nul
if exist "THIRD_PARTY_NOTICES.txt" copy /Y "THIRD_PARTY_NOTICES.txt" "dist\\THIRD_PARTY_NOTICES.txt" >nul
if exist "LICENSES" xcopy /E /I /Y "LICENSES" "dist\\LICENSES" >nul

echo.
echo ========================================
echo Build completed successfully!
echo Output: dist\WebCamShare.exe
echo ========================================
pause
