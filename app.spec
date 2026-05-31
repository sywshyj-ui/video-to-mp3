# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置
# 用法：pyinstaller app.spec
#
# 说明：
# - 把 app.py 打包成单文件 exe（onefile），无控制台窗口
# - 若 ffmpeg/ 目录下放了 ffmpeg.exe，会一并捆绑进 exe（用户无需自己装ffmpeg）
#   没有该目录则不捆绑，程序运行时回退到系统 PATH 里的 ffmpeg
# - yt-dlp 的隐藏依赖通过 collect_all 自动收集

import os
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# 收集 yt-dlp 的所有子模块/数据（其extractor是动态导入，必须显式收集）
ytdlp_datas, ytdlp_binaries, ytdlp_hiddenimports = collect_all('yt_dlp')

# 把图标作为数据捆绑，供运行时窗口 iconbitmap 使用
extra_datas = []
if os.path.isfile('app.ico'):
    extra_datas.append(('app.ico', '.'))

# 可选：捆绑 ffmpeg。把 ffmpeg.exe 放到项目下的 ffmpeg/ 目录即可被打包
extra_binaries = []
_ffmpeg_local = os.path.join('ffmpeg', 'ffmpeg.exe')
if os.path.isfile(_ffmpeg_local):
    # 放到exe解压根目录，find_ffmpeg_location() 会从 sys._MEIPASS 找到它
    extra_binaries.append((_ffmpeg_local, '.'))
_ffprobe_local = os.path.join('ffmpeg', 'ffprobe.exe')
if os.path.isfile(_ffprobe_local):
    extra_binaries.append((_ffprobe_local, '.'))

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=ytdlp_binaries + extra_binaries,
    datas=ytdlp_datas + extra_datas,
    hiddenimports=ytdlp_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='视频转MP3',           # 生成 dist/视频转MP3.exe
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # 若装了upx会压缩体积
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,               # 不弹控制台窗口（GUI程序）
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app.ico' if os.path.isfile('app.ico') else None,  # 有图标则使用
)
