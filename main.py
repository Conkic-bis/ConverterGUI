import os
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import threading
import json


def is_ffmpeg_present(user_ffmpeg_path, ignore_environment=False, ignore_empty=False):
    """
    检查 FFmpeg 是否存在，返回检测到的 FFmpeg 可执行文件的绝对路径（如果存在），否则返回 None。
    先检查用户指定路径，再依次检查程序目录、公共目录及 PATH 环境变量中的位置。
    """

    def adjust_path(path):
        if not os.path.isabs(path):
            return os.path.join(os.getcwd(), path)
        return path

    if user_ffmpeg_path and user_ffmpeg_path.strip():
        real_path = adjust_path(user_ffmpeg_path.strip())
        if os.path.isfile(real_path):
            return real_path

    if not ignore_empty and (not user_ffmpeg_path or user_ffmpeg_path.strip() == ""):
        # 检查当前目录下的 ffmpeg.exe
        relative_ffmpeg = adjust_path("ffmpeg.exe")
        if os.path.isfile(relative_ffmpeg):
            return relative_ffmpeg

        # 检查 ProgramData 文件夹
        progdata_ffmpeg = os.path.expandvars(r"%ProgramData%\ScreenToGif\ffmpeg.exe")
        if os.path.isfile(progdata_ffmpeg):
            return progdata_ffmpeg

    if ignore_environment:
        return None

    # 检查环境变量 PATH 中的所有路径
    path_env = os.environ.get("PATH", "")
    for path in path_env.split(os.pathsep):
        candidate = os.path.join(path, "ffmpeg.exe")
        if os.path.isfile(candidate):
            return candidate

    return None


def get_ffprobe_path(ffmpeg_executable):
    """
    尝试根据 ffmpeg 可执行文件路径定位 ffprobe。
    如果 ffmpeg_executable 为 ".../ffmpeg.exe"，则替换为 ffprobe.exe，
    否则直接返回 "ffprobe"（假定已在 PATH 中）。
    """
    if ffmpeg_executable.lower().endswith("ffmpeg.exe"):
        ffprobe_candidate = ffmpeg_executable[:-len("ffmpeg.exe")] + "ffprobe.exe"
        if os.path.isfile(ffprobe_candidate):
            return ffprobe_candidate
    return "ffprobe"


def get_audio_stream_count(input_file, ffprobe_path):
    """
    使用 ffprobe 获取输入文件中音频流的数量。
    """
    try:
        cmd = f'"{ffprobe_path}" -v error -select_streams a -show_entries stream=index -of json "{input_file}"'
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                universal_newlines=True)
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        return len(streams)
    except Exception as e:
        return 0


def get_map_options(input_file, ffprobe_path):
    """
    根据输入文件的流情况返回合适的 -map 参数字符串：
      始终映射 0 号视频流，
      若检测到至少 2 个音频流，则映射 0:a:0 与 0:a:1，
      否则映射存在的音频流（如果有）。
    """
    map_str = "-map 0:v:0"
    audio_count = get_audio_stream_count(input_file, ffprobe_path)
    if audio_count >= 2:
        map_str += " -map 0:a:0 -map 0:a:1"
    elif audio_count == 1:
        map_str += " -map 0:a:0"
    # 若没有音频流，则只输出视频流
    return map_str


class ConverterGUI:
    def __init__(self, master):
        self.master = master
        master.title("MOV to MP4 Converter with Extra Tracks")

        # FFmpeg 可执行文件
        self.ffmpeg_path_label = tk.Label(master, text="FFmpeg Executable Path:")
        self.ffmpeg_path_label.grid(row=0, column=0, sticky="e", padx=5, pady=5)
        self.ffmpeg_path_entry = tk.Entry(master, width=50)
        self.ffmpeg_path_entry.grid(row=0, column=1, padx=5, pady=5)
        self.ffmpeg_browse_button = tk.Button(master, text="Browse", command=self.browse_ffmpeg)
        self.ffmpeg_browse_button.grid(row=0, column=2, padx=5, pady=5)

        # 新增：视频比特率输入框
        self.bitrate_label = tk.Label(master, text="Video Bitrate (e.g., 2000k):")
        self.bitrate_label.grid(row=1, column=0, sticky="e", padx=5, pady=5)
        self.bitrate_entry = tk.Entry(master, width=20)
        self.bitrate_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # 输入文件夹
        self.input_folder_label = tk.Label(master, text="Input Folder (MOV files):")
        self.input_folder_label.grid(row=2, column=0, sticky="e", padx=5, pady=5)
        self.input_folder_entry = tk.Entry(master, width=50)
        self.input_folder_entry.grid(row=2, column=1, padx=5, pady=5)
        self.input_folder_browse_button = tk.Button(master, text="Browse", command=self.browse_input_folder)
        self.input_folder_browse_button.grid(row=2, column=2, padx=5, pady=5)

        # 输出文件夹
        self.output_folder_label = tk.Label(master, text="Output Folder (MP4 files):")
        self.output_folder_label.grid(row=3, column=0, sticky="e", padx=5, pady=5)
        self.output_folder_entry = tk.Entry(master, width=50)
        self.output_folder_entry.grid(row=3, column=1, padx=5, pady=5)
        self.output_folder_browse_button = tk.Button(master, text="Browse", command=self.browse_output_folder)
        self.output_folder_browse_button.grid(row=3, column=2, padx=5, pady=5)

        # FFmpeg 参数模板
        self.parameters_label = tk.Label(master, text="FFmpeg Parameters:")
        self.parameters_label.grid(row=4, column=0, sticky="ne", padx=5, pady=5)
        self.parameters_text = tk.Text(master, width=60, height=6)
        self.parameters_text.grid(row=4, column=1, padx=5, pady=5, columnspan=2)
        # 默认参数模板：
        # {I}：输入文件，{O}：输出文件，{MAP}：自动检测并生成流映射参数，
        # {BITRATE}：由用户输入的比特率（若有）
        default_parameters = "-i {I} {MAP} -c:v libx264 {BITRATE} -c:a copy -timecode 00:00:00:00 {O}"
        self.parameters_text.insert(tk.END, default_parameters)

        # 开始转换按钮
        self.convert_button = tk.Button(master, text="Convert", command=self.start_conversion_thread)
        self.convert_button.grid(row=5, column=1, pady=10)

        # 日志输出框
        self.log_text = scrolledtext.ScrolledText(master, width=80, height=15, state="disabled")
        self.log_text.grid(row=6, column=0, columnspan=3, padx=5, pady=5)

    def log(self, message):
        self.log_text.config(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")

    def browse_ffmpeg(self):
        file_path = filedialog.askopenfilename(
            title="Select FFmpeg Executable",
            filetypes=[("Executable", "*.exe"), ("All Files", "*.*")]
        )
        if file_path:
            self.ffmpeg_path_entry.delete(0, tk.END)
            self.ffmpeg_path_entry.insert(0, file_path)

    def browse_input_folder(self):
        folder = filedialog.askdirectory(title="Select Input Folder")
        if folder:
            self.input_folder_entry.delete(0, tk.END)
            self.input_folder_entry.insert(0, folder)

    def browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder_entry.delete(0, tk.END)
            self.output_folder_entry.insert(0, folder)

    def start_conversion_thread(self):
        # 使用线程启动转换任务，避免 GUI 卡顿
        thread = threading.Thread(target=self.start_conversion)
        thread.start()

    def start_conversion(self):
        # 检查 FFmpeg 可执行文件
        ffmpeg_path_input = self.ffmpeg_path_entry.get().strip()
        ffmpeg_executable = is_ffmpeg_present(ffmpeg_path_input)
        if not ffmpeg_executable:
            messagebox.showerror("Error", "FFmpeg executable not found. Please specify a valid path.")
            return
        self.log(f"Using FFmpeg: {ffmpeg_executable}")

        # 尝试定位 ffprobe
        ffprobe_executable = get_ffprobe_path(ffmpeg_executable)
        self.log(f"Using FFprobe: {ffprobe_executable}")

        # 检查输入、输出文件夹
        input_folder = self.input_folder_entry.get().strip()
        output_folder = self.output_folder_entry.get().strip()
        if not os.path.isdir(input_folder):
            messagebox.showerror("Error", "Invalid input folder.")
            return
        if not os.path.isdir(output_folder):
            messagebox.showerror("Error", "Invalid output folder.")
            return

        # 获取用户提供的比特率（若有）
        bitrate_input = self.bitrate_entry.get().strip()
        bitrate_param = f"-b:v {bitrate_input}" if bitrate_input else ""

        # 获取用户提供的参数模板
        parameters_template = self.parameters_text.get("1.0", tk.END).strip()
        # 模板必须包含 {I}、{O}、{MAP} 占位符
        for ph in ["{I}", "{O}", "{MAP}"]:
            if ph not in parameters_template:
                messagebox.showerror("Error", f"Parameters must include {ph} placeholder.")
                return

        # 获取输入文件夹中所有 .mov 文件（不区分大小写）
        mov_files = [f for f in os.listdir(input_folder) if f.lower().endswith(".mov")]
        if not mov_files:
            messagebox.showinfo("Info", "No MOV files found in the selected input folder.")
            return

        self.log(f"Found {len(mov_files)} MOV file(s) in input folder.")

        # 依次转换每个文件
        for mov_file in mov_files:
            input_file = os.path.join(input_folder, mov_file)
            base_name = os.path.splitext(mov_file)[0]
            # 输出文件扩展名默认为 .mp4
            output_file = os.path.join(output_folder, base_name + ".mp4")

            # 根据输入文件自动生成 -map 参数
            map_options = get_map_options(input_file, ffprobe_executable)

            # 用输入/输出文件路径、比特率、映射参数替换模板中的占位符
            parameters = parameters_template.replace("{I}", f'"{input_file}"') \
                .replace("{O}", f'"{output_file}"') \
                .replace("{BITRATE}", bitrate_param) \
                .replace("{MAP}", map_options)
            # 构建完整的命令行（注意：ffmpeg_executable 路径可能含空格，用引号包围）
            command = f'"{ffmpeg_executable}" {parameters}'
            self.log(f"Converting: {mov_file}")
            self.log(f"Command: {command}")

            try:
                result = subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        universal_newlines=True)
                if result.returncode == 0:
                    self.log(f"Successfully converted: {mov_file}")
                else:
                    self.log(f"Error converting {mov_file}:\n{result.stderr}")
            except Exception as e:
                self.log(f"Exception occurred while converting {mov_file}: {str(e)}")

        self.log("Conversion process completed.")
        messagebox.showinfo("Done", "Conversion process completed.")


if __name__ == "__main__":
    root = tk.Tk()
    gui = ConverterGUI(root)
    root.mainloop()
