@echo off
REM ============================================================
REM  一键打包脚本 - 把 app.py 打包成单文件 exe
REM  双击运行即可。需要已安装 Python。
REM ============================================================
chcp 65001 >nul
setlocal

echo [1/4] 检查并安装打包依赖...
python -m pip install --upgrade pip
python -m pip install yt-dlp pyinstaller
if errorlevel 1 (
    echo 安装依赖失败，请检查 Python 和网络。
    pause
    exit /b 1
)

echo.
echo [2/4] 可选：捆绑 ffmpeg
if exist "ffmpeg\ffmpeg.exe" (
    echo   已检测到 ffmpeg\ffmpeg.exe，将一并打包进 exe。
) else (
    echo   未检测到 ffmpeg\ffmpeg.exe。
    echo   如需让用户免装ffmpeg，请把 ffmpeg.exe 放到本目录的 ffmpeg\ 文件夹后重跑。
    echo   否则生成的exe运行时需要系统已安装ffmpeg。
)

echo.
echo [3/4] 清理旧的构建产物...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo.
echo [4/4] 开始打包（PyInstaller）...
pyinstaller app.spec --clean --noconfirm
if errorlevel 1 (
    echo.
    echo 打包失败！请查看上方错误信息。
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  打包完成！exe 位于： dist\视频转MP3.exe
echo ============================================================
echo  提示：首次启动稍慢（onefile需解压），属正常现象。
pause
endlocal
