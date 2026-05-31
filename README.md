# 视频转MP3工具

从在线视频 URL 或本地视频文件提取音频，保存为 MP3 等格式。在线模式全程不下载完整视频文件。

支持 YouTube、B站、抖音、微博、Twitter/X 等 1800+ 平台和含视频的网页，也支持本地视频文件（mp4/mkv/avi/mov/flv 等）。

## 下载使用（开箱即用）

到 [Releases](https://github.com/sywshyj-ui/video-to-mp3/releases) 下载 `video-to-mp3-with-ffmpeg.exe`，
双击即可运行——**已内置 ffmpeg，无需另外安装任何东西**（也不需要 Python）。

> 体积约 100MB，因为捆绑了 ffmpeg/ffprobe。首次启动稍慢（onefile 需解压）属正常。
> 若想要不含 ffmpeg 的精简版（约 30MB，需系统自备 ffmpeg），见旧版 Release。

## 从源码运行（开发模式）

```bash
pip install yt-dlp
# 还需要系统已安装 ffmpeg（见下）
python app.py
```

## 自行打包成 EXE

### 方式一：一键脚本（推荐）

双击 `build_exe.bat`，自动安装依赖并打包。完成后 exe 在 `dist\视频转MP3.exe`。

### 方式二：手动

```bash
pip install yt-dlp pyinstaller
pyinstaller app.spec --clean --noconfirm
```

### 让 EXE 免装 ffmpeg（强烈建议）

默认情况下 exe 运行时仍需用户系统装有 ffmpeg。若想让 exe 开箱即用：

1. 从 https://www.gyan.dev/ffmpeg/builds/ 下载 ffmpeg（essentials 版即可）
2. 解压后把 `ffmpeg.exe`（可选 `ffprobe.exe`）放到项目下的 `ffmpeg\` 目录：
   ```
   video-to-mp3\
   ├── app.py
   ├── app.spec
   └── ffmpeg\
       ├── ffmpeg.exe
       └── ffprobe.exe   (可选)
   ```
3. 重新打包。`app.spec` 会自动把它们捆绑进 exe，程序启动时通过
   `find_ffmpeg_location()` 从解压目录找到，无需用户再装。

### 自定义图标

把一个 `app.ico` 放到项目根目录，重新打包即可生效。

## ffmpeg 安装（开发模式或未捆绑时）

- Windows: `winget install ffmpeg`
- macOS: `brew install ffmpeg`
- Linux: `sudo apt install ffmpeg`

## 功能

- 在线：仅提取音频流（`bestaudio/best`），不下载视频画面
- 本地：选择本地视频文件，用 ffmpeg 直接提取音频（离线可用，更快）
- 输出格式：mp3 / m4a / opus / flac / wav / best(源格式不转码)
- 音质：V0 最佳VBR、320/256/192/128/96 kbps CBR（无损格式自动忽略码率）
- 批量任务、进度条、后台线程不卡UI
- 嵌入封面与标题/艺术家标签
- 登录 cookies（从浏览器读取，访问需登录内容）
- 全部清空 / 清除已完成 / 重试失败 / 打开目录
- 右键单任务：取消 / 重试 / 打开文件夹 / 移除
- 记住输出目录与所有选项（`~/.video_to_mp3_config.json`）

## 配置文件

设置保存在用户主目录的 `.video_to_mp3_config.json`，删除该文件可恢复默认。
