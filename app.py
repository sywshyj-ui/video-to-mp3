# app.py
# 视频转MP3工具 - 在线视频(仅提取音频流，不下载视频)或本地视频文件提取音频
# 支持 YouTube / B站 / 抖音 / 微博 等上千平台，含视频网页，以及本地视频文件
# 功能：可选音质(128/192/320/V0)、多格式(mp3/m4a/opus/flac/wav)、批量任务、
#       本地文件、登录cookies、嵌入封面、全部清空/清除已完成、重试、打开目录
# 运行方式：
# 1. pip install yt-dlp
# 2. 确保 ffmpeg 在系统 PATH 中（https://ffmpeg.org/download.html）
# 3. python app.py

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import os
import re
import json
import subprocess
import sys
from pathlib import Path
from datetime import datetime

try:
    import yt_dlp
except ImportError:
    print("错误：未安装 yt-dlp")
    print("请运行：pip install yt-dlp")
    sys.exit(1)


def resource_dir():
    """返回资源根目录。
    打包成exe(PyInstaller)后，捆绑文件解压在 sys._MEIPASS；
    普通运行时返回脚本所在目录。"""
    if getattr(sys, 'frozen', False):
        return getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def find_ffmpeg_location():
    """查找ffmpeg目录，供yt-dlp使用。
    优先级：捆绑目录 > exe同级目录 > 系统PATH。
    返回ffmpeg所在目录(给yt-dlp的ffmpeg_location)，找不到返回None表示用PATH。"""
    exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    # 候选目录：资源目录、exe同级、以及它们的bin子目录
    candidates = [resource_dir(), os.path.dirname(sys.executable)]
    for base in candidates:
        for sub in ("", "bin"):
            d = os.path.join(base, sub) if sub else base
            if os.path.isfile(os.path.join(d, exe_name)):
                return d
    return None  # 交给PATH


class Config:
    """配置管理类 - 保存用户设置"""
    CONFIG_FILE = Path.home() / ".video_to_mp3_config.json"

    @staticmethod
    def load():
        """加载配置，缺失字段用默认值补齐"""
        defaults = {
            "output_dir": str(Path.home() / "Music"),
            "audio_format": "mp3",       # 输出格式：mp3/m4a/opus/flac/wav/best
            "quality": "192",            # 音质 kbps（mp3/opus有效）：128/192/256/320/V0(最佳VBR)
            "embed_metadata": True,      # 是否嵌入标题/封面等元数据
            "browser_cookies": "none",   # 从哪个浏览器读取cookies以访问登录内容
            "download_playlist": False,  # URL含播放列表时是否转换整个列表
        }
        if Config.CONFIG_FILE.exists():
            try:
                with open(Config.CONFIG_FILE, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                    defaults.update(saved)  # 用户保存值覆盖默认值
            except:
                pass
        return defaults

    @staticmethod
    def save(config):
        """保存配置"""
        try:
            with open(Config.CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except:
            pass


class TaskItem:
    """单个提取任务的UI组件"""

    def __init__(self, parent, url, task_id, app=None):
        self.parent = parent
        self.app = app  # 主App引用，用于重试/移除等回调
        self.url = url
        self.task_id = task_id
        self.status = "等待中"
        self.title = "获取信息中..."
        self.progress = 0
        self.done = False  # 是否已结束（完成/失败/取消）

        # 创建任务框架
        self.frame = ttk.Frame(parent, relief="solid", borderwidth=1)
        self.frame.pack(fill="x", padx=5, pady=3)

        # 标题标签
        self.title_label = ttk.Label(self.frame, text=self.title, font=("Arial", 9, "bold"))
        self.title_label.pack(anchor="w", padx=5, pady=(5, 0))

        # URL标签（截断显示）
        url_display = url if len(url) <= 60 else url[:57] + "..."
        self.url_label = ttk.Label(self.frame, text=url_display, font=("Arial", 8), foreground="gray")
        self.url_label.pack(anchor="w", padx=5)

        # 进度条
        self.progress_bar = ttk.Progressbar(self.frame, mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", padx=5, pady=3)

        # 状态标签
        self.status_label = ttk.Label(self.frame, text=self.status, font=("Arial", 8))
        self.status_label.pack(anchor="w", padx=5, pady=(0, 5))

        # 右键菜单
        self.context_menu = tk.Menu(self.frame, tearoff=0)
        self.context_menu.add_command(label="取消任务", command=self.cancel_task)
        self.context_menu.add_command(label="重试", command=self.retry_task)
        self.context_menu.add_command(label="打开所在文件夹", command=self.open_folder)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="从列表移除", command=self.remove_self)
        # 任务框架及其所有子控件都绑定右键，避免点到标签时菜单不弹出
        for widget in (self.frame, self.title_label, self.url_label, self.status_label):
            widget.bind("<Button-3>", self.show_context_menu)

        self.output_path = None
        self.cancelled = False

    def update_title(self, title):
        """更新任务标题"""
        self.title = title
        self.title_label.config(text=title)

    def update_progress(self, progress):
        """更新进度条"""
        self.progress = progress
        self.progress_bar["value"] = progress

    def update_status(self, status, color="black"):
        """更新状态文本"""
        self.status = status
        self.status_label.config(text=status, foreground=color)

    def set_completed(self, output_path):
        """标记任务完成"""
        self.output_path = output_path
        self.done = True
        self.update_status("✓ 已完成", "green")
        self.update_progress(100)

    def set_failed(self, error_msg):
        """标记任务失败"""
        self.done = True
        self.update_status(f"✗ 失败: {error_msg}", "red")

    def cancel_task(self):
        """取消任务"""
        if self.done:
            return
        self.cancelled = True
        self.done = True
        self.update_status("已取消", "orange")

    def retry_task(self):
        """重试任务（仅在已结束时有效）"""
        if self.app and self.done:
            self.app.retry_task(self.task_id)

    def remove_self(self):
        """从任务列表移除本任务"""
        if self.app:
            self.app.remove_task(self.task_id)

    def show_context_menu(self, event):
        """显示右键菜单"""
        try:
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def open_folder(self):
        """打开输出文件所在文件夹"""
        if self.output_path and os.path.exists(self.output_path):
            folder = os.path.dirname(self.output_path)
            if sys.platform == "win32":
                os.startfile(folder)
            elif sys.platform == "darwin":
                subprocess.run(["open", folder])
            else:
                subprocess.run(["xdg-open", folder])
        else:
            messagebox.showinfo("提示", "文件尚未生成")


class ExtractWorker(threading.Thread):
    """后台音频提取工作线程"""

    def __init__(self, task_item, output_dir, result_queue, options):
        super().__init__(daemon=True)
        self.task_item = task_item
        self.output_dir = output_dir
        self.result_queue = result_queue
        self.options = options  # dict: audio_format / quality / embed_metadata / browser_cookies
        self.final_path = None  # 由postprocessor_hook回填的最终文件路径

    def run(self):
        """执行音频提取：本地文件走ffmpeg直转，在线URL走yt-dlp"""
        try:
            # 本地文件：直接用ffmpeg转码，无需yt-dlp，更快且离线可用
            if self.is_local_file(self.task_item.url):
                self.extract_local()
                return
            self.extract_online()
        except Exception as e:
            self.result_queue.put(('failed', self.task_item.task_id, self.friendly_error(str(e))))

    @staticmethod
    def is_local_file(path):
        """判断是否为本地文件路径（非http/https且文件存在）"""
        if path.startswith(('http://', 'https://')):
            return False
        return os.path.isfile(path)

    def extract_online(self):
        """从在线URL提取音频（yt-dlp）"""
        try:
            audio_format = self.options.get("audio_format", "mp3")
            quality = self.options.get("quality", "192")
            embed = self.options.get("embed_metadata", True)
            browser = self.options.get("browser_cookies", "none")
            download_playlist = self.options.get("download_playlist", False)

            # 后处理器：提取音频并按所选格式转码，可选嵌入封面与元数据
            postprocessors = []
            if audio_format == "best":
                # 保留源音频格式（webm/m4a等），不转码，速度最快、零质量损失
                pass
            else:
                extract_pp = {
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': audio_format,
                }
                # 仅有损格式(mp3/opus/m4a)需要指定码率；无损(flac/wav)忽略
                if audio_format in ("mp3", "opus", "m4a"):
                    # quality 可为数字码率，或 "0"~"9" 的 VBR 等级(0最佳)
                    extract_pp['preferredquality'] = quality
                postprocessors.append(extract_pp)

            if embed:
                # 写入标题/艺术家等标签，并尝试嵌入封面缩略图
                postprocessors.append({'key': 'FFmpegMetadata'})
                postprocessors.append({'key': 'EmbedThumbnail'})

            # 配置yt-dlp选项
            ydl_opts = {
                'format': 'bestaudio/best',  # 只下载音频流，不碰视频画面流
                'postprocessors': postprocessors,
                'outtmpl': os.path.join(self.output_dir, '%(title)s.%(ext)s'),
                'progress_hooks': [self.progress_hook],
                'postprocessor_hooks': [self.postprocessor_hook],
                'writethumbnail': embed,     # 下载封面以便嵌入
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': False,
                'noplaylist': not download_playlist,  # 勾选则转换整个播放列表，否则只取单条
            }

            # 从浏览器读取cookies，以访问需登录的内容（如会员/私享视频）
            if browser and browser != "none":
                ydl_opts['cookiesfrombrowser'] = (browser,)

            # 指定ffmpeg位置（打包exe时用捆绑的ffmpeg，否则用PATH）
            ffmpeg_loc = self.options.get("ffmpeg_location")
            if ffmpeg_loc:
                ydl_opts['ffmpeg_location'] = ffmpeg_loc

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # 获取视频信息
                info = ydl.extract_info(self.task_item.url, download=False)
                title = self.sanitize_filename(info.get('title', 'Unknown'))

                # 更新标题
                self.result_queue.put(('title', self.task_item.task_id, title))
                self.result_queue.put(('status', self.task_item.task_id, '提取中...', 'blue'))

                # 检查是否被取消
                if self.task_item.cancelled:
                    return

                # 开始下载音频
                ydl.download([self.task_item.url])

                # 优先用postprocessor_hook回填的精确路径，否则回退到推断查找
                output_path = self.final_path
                if not (output_path and os.path.exists(output_path)):
                    output_path = self.find_output_file(title, audio_format)

                if output_path and os.path.exists(output_path):
                    self.result_queue.put(('completed', self.task_item.task_id, output_path))
                else:
                    self.result_queue.put(('failed', self.task_item.task_id, '文件未找到'))

        except Exception as e:
            self.result_queue.put(('failed', self.task_item.task_id, self.friendly_error(str(e))))

    def extract_local(self):
        """从本地视频文件提取音频，直接调用ffmpeg转码"""
        src = self.task_item.url
        audio_format = self.options.get("audio_format", "mp3")
        quality = self.options.get("quality", "192")
        embed = self.options.get("embed_metadata", True)

        # 显示文件名作为标题
        title = self.sanitize_filename(os.path.splitext(os.path.basename(src))[0])
        self.result_queue.put(('title', self.task_item.task_id, title))
        self.result_queue.put(('status', self.task_item.task_id, '转码中...', 'blue'))

        # best模式保留源音频编码(copy)，否则按所选格式
        out_ext = audio_format if audio_format != "best" else "m4a"
        out_path = self.unique_path(os.path.join(self.output_dir, f"{title}.{out_ext}"))

        ffmpeg_exe = self.ffmpeg_exe_path()

        # 组装ffmpeg命令：-vn去掉视频流，只保留音频
        cmd = [ffmpeg_exe, '-y', '-i', src, '-vn']
        cmd += self.audio_codec_args(audio_format, quality)
        if embed:
            cmd += ['-map_metadata', '0']  # 保留源文件的元数据标签
        cmd += ['-progress', 'pipe:1', '-nostats', out_path]

        # 先探测总时长，用于计算百分比进度
        total_dur = self.probe_duration(src)

        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            universal_newlines=True, encoding='utf-8', errors='replace',
            startupinfo=startupinfo
        )

        # 读取ffmpeg的-progress输出，解析out_time_ms换算进度
        for line in proc.stdout:
            if self.task_item.cancelled:
                proc.terminate()
                return
            line = line.strip()
            if line.startswith('out_time_ms=') and total_dur > 0:
                try:
                    cur = int(line.split('=', 1)[1]) / 1_000_000  # 微秒->秒
                    pct = min(cur / total_dur * 100, 99)
                    self.result_queue.put(('progress', self.task_item.task_id, pct))
                except (ValueError, ZeroDivisionError):
                    pass
        proc.wait()

        if proc.returncode == 0 and os.path.exists(out_path):
            self.result_queue.put(('completed', self.task_item.task_id, out_path))
        else:
            self.result_queue.put(('failed', self.task_item.task_id, 'ffmpeg转码失败'))

    def audio_codec_args(self, audio_format, quality):
        """根据格式返回ffmpeg音频编码参数"""
        if audio_format == "best":
            return ['-acodec', 'copy']        # 直接拷贝音频流，零损失零转码
        if audio_format == "mp3":
            if quality == "0":                # V0 最佳VBR
                return ['-acodec', 'libmp3lame', '-q:a', '0']
            return ['-acodec', 'libmp3lame', '-b:a', f'{quality}k']
        if audio_format == "m4a":
            return ['-acodec', 'aac', '-b:a', f'{quality}k']
        if audio_format == "opus":
            return ['-acodec', 'libopus', '-b:a', f'{quality}k']
        if audio_format == "flac":
            return ['-acodec', 'flac']        # 无损
        if audio_format == "wav":
            return ['-acodec', 'pcm_s16le']   # 无损PCM
        return ['-acodec', 'libmp3lame', '-b:a', '192k']

    def probe_duration(self, src):
        """用ffprobe探测媒体总时长(秒)，失败返回0"""
        ffmpeg_exe = self.ffmpeg_exe_path()
        ffprobe = os.path.join(os.path.dirname(ffmpeg_exe), 'ffprobe.exe' if sys.platform == "win32" else 'ffprobe')
        if not os.path.isfile(ffprobe):
            ffprobe = 'ffprobe'  # 回退PATH
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        try:
            out = subprocess.run(
                [ffprobe, '-v', 'quiet', '-show_entries', 'format=duration',
                 '-of', 'default=noprint_wrappers=1:nokey=1', src],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                universal_newlines=True, encoding='utf-8', errors='replace',
                startupinfo=startupinfo
            )
            return float(out.stdout.strip())
        except (ValueError, subprocess.SubprocessError):
            return 0

    def ffmpeg_exe_path(self):
        """返回ffmpeg可执行文件完整路径（捆绑目录或PATH）"""
        loc = self.options.get("ffmpeg_location")
        exe = 'ffmpeg.exe' if sys.platform == "win32" else 'ffmpeg'
        return os.path.join(loc, exe) if loc else exe

    def unique_path(self, path):
        """目标文件已存在时自动加序号：song.mp3 -> song (1).mp3"""
        if not os.path.exists(path):
            return path
        base, ext = os.path.splitext(path)
        i = 1
        while os.path.exists(f"{base} ({i}){ext}"):
            i += 1
        return f"{base} ({i}){ext}"

    def friendly_error(self, raw):
        """把yt-dlp的常见英文报错转成可操作的中文提示"""
        low = raw.lower()
        if "unsupported url" in low:
            return "不支持的链接（请用单个视频页地址，非搜索/主页）"
        if "fresh cookies" in low or "cookies" in low and "needed" in low:
            return "需要cookies：请在下方选择浏览器并关闭它后重试"
        if "sign in" in low or "login" in low or "private" in low:
            return "需要登录：请在下方选择浏览器cookies后重试"
        if "ffmpeg" in low:
            return "ffmpeg错误：请确认ffmpeg可用"
        if "http error 404" in low or "not found" in low:
            return "视频不存在或已删除(404)"
        if "geo" in low and "restrict" in low:
            return "该视频有地区限制"
        if "timed out" in low or "timeout" in low or "connection" in low:
            return "网络超时，请检查网络或重试"
        # 其余错误截断显示
        return raw[:47] + "..." if len(raw) > 50 else raw

    def progress_hook(self, d):
        """yt-dlp进度回调"""
        if self.task_item.cancelled:
            raise Exception("任务已取消")

        if d['status'] == 'downloading':
            # 计算下载进度
            if 'total_bytes' in d:
                progress = (d['downloaded_bytes'] / d['total_bytes']) * 100
            elif 'total_bytes_estimate' in d:
                progress = (d['downloaded_bytes'] / d['total_bytes_estimate']) * 100
            else:
                progress = 0

            self.result_queue.put(('progress', self.task_item.task_id, min(progress, 99)))

        elif d['status'] == 'finished':
            # 音频流下载完毕，进入转码阶段
            self.result_queue.put(('status', self.task_item.task_id, '转码中...', 'blue'))

    def postprocessor_hook(self, d):
        """后处理回调：记录转码后的最终文件路径"""
        # 转码完成时 d['info_dict']['filepath'] 指向最终输出文件
        if d.get('status') == 'finished':
            info = d.get('info_dict', {})
            path = info.get('filepath') or info.get('_filename')
            if path and (path.endswith(('.mp3', '.m4a', '.opus', '.flac', '.wav'))
                         or self.options.get("audio_format") == "best"):
                self.final_path = path

    def sanitize_filename(self, filename):
        """清理文件名中的非法字符"""
        # 移除Windows/Linux不允许的字符
        filename = re.sub(r'[<>:"/\\|?*]', '', filename)
        # 移除前后空格
        filename = filename.strip()
        # 限制长度
        if len(filename) > 200:
            filename = filename[:200]
        return filename or "untitled"

    def find_output_file(self, title, audio_format="mp3"):
        """查找输出文件（postprocessor_hook失败时的回退方案）"""
        base_name = self.sanitize_filename(title)
        # best模式输出格式未知，匹配所有常见音频后缀
        exts = [audio_format] if audio_format != "best" else \
            ["mp3", "m4a", "opus", "flac", "wav", "webm", "ogg", "aac"]

        for ext in exts:
            # 尝试直接匹配
            direct_path = os.path.join(self.output_dir, f"{base_name}.{ext}")
            if os.path.exists(direct_path):
                return direct_path
            # 尝试查找带序号的文件
            for i in range(1, 10):
                numbered_path = os.path.join(self.output_dir, f"{base_name} ({i}).{ext}")
                if os.path.exists(numbered_path):
                    return numbered_path

        # 模糊搜索（处理yt-dlp自动重命名的情况）
        try:
            for file in os.listdir(self.output_dir):
                if any(file.endswith(f".{e}") for e in exts) and base_name[:20] in file:
                    return os.path.join(self.output_dir, file)
        except:
            pass

        return None


class App:
    """主应用窗口"""

    def __init__(self, root):
        self.root = root
        self.root.title("在线视频转MP3工具")
        self.root.geometry("700x600")
        self.root.minsize(600, 400)

        # 设置窗口图标（标题栏/任务栏），找不到则忽略
        try:
            ico = os.path.join(resource_dir(), "app.ico")
            if os.path.isfile(ico):
                self.root.iconbitmap(ico)
        except Exception:
            pass

        # 加载配置
        self.config = Config.load()
        self.output_dir = self.config.get("output_dir", str(Path.home() / "Music"))

        # 任务管理
        self.tasks = {}
        self.task_counter = 0
        self.result_queue = queue.Queue()

        # 查找ffmpeg位置（捆绑 > 同级 > PATH）
        self.ffmpeg_location = find_ffmpeg_location()

        # 检查依赖
        if not self.check_ffmpeg():
            messagebox.showerror(
                "缺少依赖",
                "未检测到 ffmpeg！\n\n"
                "请从 https://ffmpeg.org/download.html 下载，\n"
                "并添加到系统 PATH，或放在本程序同级目录。\n"
                "Windows用户可以使用：winget install ffmpeg"
            )
            self.root.quit()
            return

        self.setup_ui()
        self.start_queue_processor()

    def check_ffmpeg(self):
        """检查ffmpeg是否可用（捆绑目录或PATH）"""
        exe_name = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        ffmpeg_cmd = os.path.join(self.ffmpeg_location, exe_name) if self.ffmpeg_location else "ffmpeg"
        try:
            # Windows下隐藏ffmpeg控制台窗口
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            subprocess.run(
                [ffmpeg_cmd, "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                startupinfo=startupinfo
            )
            return True
        except:
            return False

    def setup_ui(self):
        """构建用户界面"""
        # 顶部输入区域
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill="x")

        ttk.Label(top_frame, text="视频URL:", font=("Arial", 10)).pack(anchor="w")

        input_frame = ttk.Frame(top_frame)
        input_frame.pack(fill="x", pady=(5, 0))

        self.url_entry = ttk.Entry(input_frame, font=("Arial", 10))
        self.url_entry.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.url_entry.bind("<Return>", lambda e: self.add_task())

        # 支持拖拽URL（需 tkinterdnd2，没有则自动跳过，不影响其他功能）
        try:
            self.url_entry.drop_target_register('DND_Text')
            self.url_entry.bind("<<Drop>>", self.on_drop)
        except (AttributeError, tk.TclError):
            pass  # 标准 tkinter 不支持拖拽，静默降级

        self.extract_btn = ttk.Button(input_frame, text="开始提取", command=self.add_task)
        self.extract_btn.pack(side="left")

        # 选择本地视频文件按钮
        self.local_btn = ttk.Button(input_frame, text="本地视频...", command=self.add_local_files)
        self.local_btn.pack(side="left", padx=(5, 0))

        # 提示文本
        hint_text = "支持 YouTube、B站、抖音、微博等上千平台及含视频的网页 | 在线URL或本地文件均可"
        ttk.Label(top_frame, text=hint_text, font=("Arial", 8), foreground="gray").pack(anchor="w", pady=(3, 0))

        # 工具栏：批量操作按钮
        toolbar = ttk.Frame(top_frame)
        toolbar.pack(fill="x", pady=(6, 0))
        ttk.Button(toolbar, text="全部清空", command=self.clear_all).pack(side="left")
        ttk.Button(toolbar, text="清除已完成", command=self.clear_completed).pack(side="left", padx=(5, 0))
        ttk.Button(toolbar, text="重试失败项", command=self.retry_failed).pack(side="left", padx=(5, 0))
        ttk.Button(toolbar, text="打开输出目录", command=self.open_output_dir).pack(side="left", padx=(5, 0))

        # 分隔线
        ttk.Separator(self.root, orient="horizontal").pack(fill="x", pady=5)

        # 中部任务列表区域
        middle_frame = ttk.Frame(self.root)
        middle_frame.pack(fill="both", expand=True, padx=10)

        ttk.Label(middle_frame, text="任务列表:", font=("Arial", 10, "bold")).pack(anchor="w")

        # 滚动区域
        canvas_frame = ttk.Frame(middle_frame)
        canvas_frame.pack(fill="both", expand=True, pady=(5, 0))

        self.canvas = tk.Canvas(canvas_frame, bg="white")
        scrollbar = ttk.Scrollbar(canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 鼠标滚轮支持
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        # 底部输出目录选择
        bottom_frame = ttk.Frame(self.root, padding=10)
        bottom_frame.pack(fill="x", side="bottom")

        dir_frame = ttk.Frame(bottom_frame)
        dir_frame.pack(fill="x")

        ttk.Label(dir_frame, text="输出目录:", font=("Arial", 9)).pack(side="left", padx=(0, 5))

        self.dir_label = ttk.Label(dir_frame, text=self.output_dir, font=("Arial", 9), foreground="blue")
        self.dir_label.pack(side="left", fill="x", expand=True)

        ttk.Button(dir_frame, text="浏览...", command=self.choose_directory).pack(side="left", padx=(5, 0))

        # 选项栏：格式 / 音质 / 元数据 / 登录cookies
        opt_frame = ttk.Frame(bottom_frame)
        opt_frame.pack(fill="x", pady=(6, 0))

        # 输出格式选择
        ttk.Label(opt_frame, text="格式:", font=("Arial", 9)).pack(side="left")
        self.format_var = tk.StringVar(value=self.config.get("audio_format", "mp3"))
        format_box = ttk.Combobox(
            opt_frame, textvariable=self.format_var, width=7, state="readonly",
            values=["mp3", "m4a", "opus", "flac", "wav", "best"]
        )
        format_box.pack(side="left", padx=(3, 10))
        format_box.bind("<<ComboboxSelected>>", self.on_format_change)

        # 音质选择（含VBR最佳质量V0；无损/best格式时禁用）
        ttk.Label(opt_frame, text="音质:", font=("Arial", 9)).pack(side="left")
        self.quality_var = tk.StringVar(value=self.config.get("quality", "192"))
        # V0=最佳VBR(~245kbps平均), 数字为固定CBR码率
        self.quality_box = ttk.Combobox(
            opt_frame, textvariable=self.quality_var, width=14, state="readonly",
            values=["V0 (最佳VBR)", "320", "256", "192", "128", "96"]
        )
        self.quality_box.pack(side="left", padx=(3, 12))
        self.quality_box.bind("<<ComboboxSelected>>", lambda e: self.save_options())

        # 嵌入元数据（标题/封面）开关
        self.embed_var = tk.BooleanVar(value=self.config.get("embed_metadata", True))
        ttk.Checkbutton(
            opt_frame, text="嵌入封面/标签", variable=self.embed_var,
            command=self.save_options
        ).pack(side="left", padx=(0, 12))

        # 整个播放列表开关：勾选则URL含列表时转换全部，否则只取单条
        self.playlist_var = tk.BooleanVar(value=self.config.get("download_playlist", False))
        ttk.Checkbutton(
            opt_frame, text="转换整个播放列表", variable=self.playlist_var,
            command=self.save_options
        ).pack(side="left", padx=(0, 12))

        # 浏览器cookies来源（访问需登录的内容）
        ttk.Label(opt_frame, text="登录cookies:", font=("Arial", 9)).pack(side="left")
        self.cookies_var = tk.StringVar(value=self.config.get("browser_cookies", "none"))
        cookies_box = ttk.Combobox(
            opt_frame, textvariable=self.cookies_var, width=9, state="readonly",
            values=["none", "chrome", "edge", "firefox", "safari", "brave", "opera", "chromium"]
        )
        cookies_box.pack(side="left", padx=(3, 0))
        cookies_box.bind("<<ComboboxSelected>>", lambda e: self.save_options())

        # 根据初始格式设置音质框可用状态
        self.update_quality_state()

        # 状态栏
        self.status_bar = ttk.Label(bottom_frame, text="就绪", relief="sunken", anchor="w")
        self.status_bar.pack(fill="x", pady=(6, 0))

    def on_mousewheel(self, event):
        """鼠标滚轮滚动"""
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def on_drop(self, event):
        """处理拖拽URL"""
        self.url_entry.insert(0, event.data)

    def choose_directory(self):
        """选择输出目录"""
        directory = filedialog.askdirectory(initialdir=self.output_dir)
        if directory:
            self.output_dir = directory
            self.dir_label.config(text=directory)
            self.config["output_dir"] = directory
            Config.save(self.config)

    def update_quality_state(self):
        """无损(flac/wav)和best格式不需要码率，禁用音质下拉框"""
        fmt = self.format_var.get()
        if fmt in ("flac", "wav", "best"):
            self.quality_box.config(state="disabled")
        else:
            self.quality_box.config(state="readonly")

    def on_format_change(self, event=None):
        """格式切换时更新音质框状态并保存"""
        self.update_quality_state()
        self.save_options()

    def _quality_value(self):
        """把音质下拉的显示值转成yt-dlp的preferredquality参数
        'V0 (最佳VBR)' -> '0'（VBR等级，0为最佳）；其余为CBR码率数字"""
        raw = self.quality_var.get()
        if raw.startswith("V0"):
            return "0"
        return raw

    def current_options(self):
        """收集当前提取选项"""
        return {
            "audio_format": self.format_var.get(),
            "quality": self._quality_value(),
            "embed_metadata": self.embed_var.get(),
            "browser_cookies": self.cookies_var.get(),
            "download_playlist": self.playlist_var.get(),
            "ffmpeg_location": self.ffmpeg_location,
        }

    def save_options(self):
        """选项变化时写入配置"""
        self.config["audio_format"] = self.format_var.get()
        self.config["quality"] = self.quality_var.get()  # 存显示值，保留V0标签
        self.config["embed_metadata"] = self.embed_var.get()
        self.config["browser_cookies"] = self.cookies_var.get()
        self.config["download_playlist"] = self.playlist_var.get()
        Config.save(self.config)
        self.update_status("设置已保存")

    def spawn_task(self, source):
        """创建任务并启动后台工作线程（在线URL或本地文件路径通用）"""
        task_id = self.task_counter
        self.task_counter += 1
        task_item = TaskItem(self.scrollable_frame, source, task_id, app=self)
        self.tasks[task_id] = task_item
        # 快照当前选项，确保任务期间设置变化不影响已派发任务
        worker = ExtractWorker(task_item, self.output_dir, self.result_queue, self.current_options())
        worker.start()

    def add_local_files(self):
        """选择本地视频文件并加入提取队列"""
        files = filedialog.askopenfilenames(
            title="选择本地视频文件",
            initialdir=self.output_dir,
            filetypes=[
                ("视频文件", "*.mp4 *.mkv *.avi *.mov *.flv *.wmv *.webm *.m4v *.ts *.mpg *.mpeg *.3gp"),
                ("音频文件", "*.m4a *.aac *.wav *.flac *.ogg *.opus *.wma"),
                ("所有文件", "*.*"),
            ]
        )
        if not files:
            return
        for path in files:
            self.spawn_task(path)
            self.update_status(f"已添加本地文件: {os.path.basename(path)}")
        self.root.after(100, lambda: self.canvas.yview_moveto(1.0))

    def check_unsupported_page(self, url):
        """检测明显不是单个视频页的URL（搜索/用户主页等），返回提示文字或None"""
        low = url.lower()
        # 各平台的非视频页特征：搜索页、发现页、用户主页等
        bad_patterns = [
            ("douyin.com/search", "抖音搜索结果页"),
            ("douyin.com/jingxuan", "抖音精选/推荐页"),
            ("douyin.com/discover", "抖音发现页"),
            ("douyin.com/user/", "抖音用户主页"),
            ("bilibili.com/v/", "B站分区页"),
            ("search.bilibili.com", "B站搜索页"),
            ("youtube.com/results", "YouTube搜索结果页"),
            ("youtube.com/feed", "YouTube订阅/首页"),
            ("/search?", "搜索结果页"),
            ("/search/", "搜索结果页"),
        ]
        for pat, desc in bad_patterns:
            if pat in low:
                return desc
        return None

    def check_needs_cookies(self, url):
        """检测是否为通常需要cookies的平台(抖音/微博等)，返回平台名或None"""
        low = url.lower()
        cookie_platforms = [
            ("douyin.com", "抖音"),
            ("v.douyin.com", "抖音"),
            ("weibo.com", "微博"),
            ("weibo.cn", "微博"),
            ("xiaohongshu.com", "小红书"),
            ("kuaishou.com", "快手"),
        ]
        for domain, name in cookie_platforms:
            if domain in low:
                return name
        return None

    def add_task(self):
        """添加提取任务"""
        urls_text = self.url_entry.get().strip()
        if not urls_text:
            messagebox.showwarning("提示", "请输入视频URL")
            return

        # 支持多行URL
        urls = [url.strip() for url in urls_text.split('\n') if url.strip()]

        cookie_warned = False  # 同一批只提醒一次cookies
        for url in urls:
            # 本地文件路径：直接加入队列（ffmpeg直转）
            if not url.startswith(('http://', 'https://')):
                # 去掉可能的 file:// 前缀和引号
                local = url.replace('file:///', '').replace('file://', '').strip('"')
                if os.path.isfile(local):
                    self.spawn_task(local)
                    self.update_status(f"已添加本地文件: {os.path.basename(local)}")
                    continue
                messagebox.showwarning("提示", f"无效的URL或文件不存在: {url}")
                continue

            # 改进1：粘贴时检测非视频页（搜索/主页等），提前拦截
            bad = self.check_unsupported_page(url)
            if bad:
                if not messagebox.askyesno(
                    "可能不是视频链接",
                    f"这看起来是「{bad}」，不是单个视频页面。\n\n"
                    "请点进某个具体视频，复制地址栏里 .../video/数字 形式的链接。\n\n"
                    "仍要尝试提取吗？"
                ):
                    continue

            # 改进2：抖音/微博等平台未选cookies时提醒
            need = self.check_needs_cookies(url)
            if need and self.cookies_var.get() == "none" and not cookie_warned:
                cookie_warned = True
                messagebox.showinfo(
                    "提示",
                    f"{need} 通常需要浏览器 cookies 才能提取。\n\n"
                    "请在下方「登录cookies」选择你常用的浏览器"
                    "（如 chrome/edge），并先关闭该浏览器再提取。"
                )

            # 在线URL：创建任务并启动
            self.spawn_task(url)
            self.update_status(f"已添加任务: {url[:50]}...")

        # 清空输入框
        self.url_entry.delete(0, tk.END)

        # 滚动到底部
        self.root.after(100, lambda: self.canvas.yview_moveto(1.0))

    def retry_task(self, task_id):
        """重试单个已结束的任务"""
        task_item = self.tasks.get(task_id)
        if not task_item:
            return
        # 重置任务状态并重新派发线程
        task_item.cancelled = False
        task_item.done = False
        task_item.update_progress(0)
        task_item.update_status("等待中...", "black")
        worker = ExtractWorker(task_item, self.output_dir, self.result_queue, self.current_options())
        worker.start()
        self.update_status(f"重试任务: {task_item.url[:50]}...")

    def retry_failed(self):
        """重试所有失败的任务"""
        retried = 0
        for task_id, task_item in list(self.tasks.items()):
            if task_item.done and task_item.status.startswith("✗"):
                self.retry_task(task_id)
                retried += 1
        self.update_status(f"已重试 {retried} 个失败任务" if retried else "没有失败的任务")

    def remove_task(self, task_id):
        """从列表移除单个任务"""
        task_item = self.tasks.get(task_id)
        if task_item:
            task_item.frame.destroy()
            del self.tasks[task_id]
            self.update_status("已移除任务")

    def clear_all(self):
        """全部清空：移除所有任务（运行中的任务先标记取消）"""
        if not self.tasks:
            return
        if not messagebox.askyesno("确认", "确定要清空所有任务吗？\n正在进行的任务会被取消。"):
            return
        for task_item in self.tasks.values():
            if not task_item.done:
                task_item.cancelled = True  # 通知后台线程停止
            task_item.frame.destroy()
        self.tasks.clear()
        self.update_status("已清空全部任务")

    def clear_completed(self):
        """清除已完成的任务，保留进行中和失败的"""
        removed = 0
        for task_id, task_item in list(self.tasks.items()):
            if task_item.done and task_item.status.startswith("✓"):
                task_item.frame.destroy()
                del self.tasks[task_id]
                removed += 1
        self.update_status(f"已清除 {removed} 个完成任务" if removed else "没有已完成的任务")

    def open_output_dir(self):
        """打开当前输出目录"""
        if not os.path.isdir(self.output_dir):
            try:
                os.makedirs(self.output_dir, exist_ok=True)
            except Exception:
                messagebox.showerror("错误", "输出目录不存在且无法创建")
                return
        if sys.platform == "win32":
            os.startfile(self.output_dir)
        elif sys.platform == "darwin":
            subprocess.run(["open", self.output_dir])
        else:
            subprocess.run(["xdg-open", self.output_dir])

    def start_queue_processor(self):
        """启动队列处理器（定期检查结果队列）"""
        self.process_queue()

    def process_queue(self):
        """处理结果队列中的消息"""
        try:
            while True:
                msg = self.result_queue.get_nowait()
                msg_type = msg[0]
                task_id = msg[1]

                if task_id not in self.tasks:
                    continue

                task_item = self.tasks[task_id]

                if msg_type == 'title':
                    task_item.update_title(msg[2])

                elif msg_type == 'progress':
                    task_item.update_progress(msg[2])

                elif msg_type == 'status':
                    task_item.update_status(msg[2], msg[3] if len(msg) > 3 else 'black')

                elif msg_type == 'completed':
                    output_path = msg[2]
                    task_item.set_completed(output_path)
                    self.update_status(f"✓ 完成: {os.path.basename(output_path)}")
                    self.show_notification("提取完成", f"已保存: {os.path.basename(output_path)}")

                elif msg_type == 'failed':
                    error_msg = msg[2]
                    task_item.set_failed(error_msg)
                    self.update_status(f"✗ 失败: {error_msg}")

        except queue.Empty:
            pass

        # 每100ms检查一次队列
        self.root.after(100, self.process_queue)

    def update_status(self, text):
        """更新状态栏"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.status_bar.config(text=f"[{timestamp}] {text}")

    def show_notification(self, title, message):
        """显示系统通知（可选功能）"""
        try:
            if sys.platform == "win32":
                # Windows 10/11 Toast通知
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=3, threaded=True)
        except:
            pass  # 通知失败不影响主功能


def main():
    """主函数"""
    root = tk.Tk()
    app = App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
