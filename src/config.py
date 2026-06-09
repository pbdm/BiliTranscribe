import json
import os
import shutil
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.absolute()

# 加载路径配置
PATHS_FILE = PROJECT_ROOT / "paths.json"
if PATHS_FILE.exists():
    with open(PATHS_FILE) as f:
        PATHS = json.load(f)
else:
    PATHS = {}

# 目录配置 - 从 paths.json 读取，默认为项目目录
TMP_REL = PATHS.get("TEMP_DIR", "temp")
OUTPUT_REL = PATHS.get("OUTPUT_DIR", "output")

BIN_DIR = PROJECT_ROOT / "bin"


def resolve_configured_path(path_value: str, project_root: Path) -> Path:
    configured_path = Path(path_value).expanduser()
    if configured_path.is_absolute():
        return configured_path
    return project_root / configured_path


TEMP_DIR = resolve_configured_path(TMP_REL, PROJECT_ROOT)
OUTPUT_DIR = resolve_configured_path(OUTPUT_REL, PROJECT_ROOT)
TRANSCRIPT_DIR = TEMP_DIR / "transcripts"  # 转录文稿存档（临时）


def get_platform_executable_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


# FFmpeg 路径 - 优先使用项目 bin/ 目录，其次使用系统路径
def find_ffmpeg(name):
    executable_name = get_platform_executable_name(name)

    if BIN_DIR.exists():
        path = BIN_DIR / executable_name
        if path.exists():
            return path

    system_path = shutil.which(executable_name) or shutil.which(name)
    if system_path:
        return Path(system_path)

    fallback_path = BIN_DIR / executable_name
    if BIN_DIR.exists():
        return fallback_path  # 返回 bin/ 路径，让后续检查失败有明确错误

    raise FileNotFoundError(f"{executable_name} not found in {BIN_DIR} or system PATH")


FFMPEG_PATH = find_ffmpeg("ffmpeg")
FFPROBE_PATH = find_ffmpeg("ffprobe")

# 确保目录存在
TEMP_DIR.mkdir(exist_ok=True)
TRANSCRIPT_DIR.mkdir(exist_ok=True)
try:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print(f"WARNING: Cannot create OUTPUT_DIR: {e}")


# ──────────────────────────────────────────────
# NVIDIA CUDA DLL 路径自动加载（Windows）
# 确保 ctranslate2 / faster-whisper 能找到 cublas/cudnn
# ──────────────────────────────────────────────
def _add_nvidia_dll_paths():
    """将 pip 安装的 nvidia-* package 中的 DLL 目录加入 PATH。"""
    added = []
    for site_pkg in sys.path:
        nv_root = Path(site_pkg) / "nvidia"
        if not nv_root.is_dir():
            continue
        for pkg_dir in nv_root.iterdir():
            bin_path = pkg_dir / "bin"
            if bin_path.is_dir():
                resolved = str(bin_path.resolve())
                if resolved not in os.environ.get("PATH", ""):
                    os.environ["PATH"] = resolved + os.pathsep + os.environ.get("PATH", "")
                added.append(resolved)
    return added


_added_nvidia_dlls = _add_nvidia_dll_paths()


# ──────────────────────────────────────────────
# 硬件检测
# ──────────────────────────────────────────────
def _has_cuda():
    """检测 CUDA 是否可用（不依赖 PyTorch）。"""
    if os.name != "nt":
        return False
    # 尝试加载 cublas（只要有这个，CUDA 就可用）
    try:
        import ctypes
        ctypes.CDLL("nvcuda.dll")  # 由 NVIDIA 驱动提供
        # 如果能找到 cublas DLL，说明运行时也已就位
        for dll_name in ("cublas64_12.dll", "cublasLt64_12.dll"):
            try:
                ctypes.CDLL(dll_name)
                return True
            except OSError:
                continue
        # 回退：在 nvidia package 目录里找
        for site_pkg in sys.path:
            candidate = Path(site_pkg) / "nvidia" / "cublas" / "bin" / "cublas64_12.dll"
            if candidate.exists():
                try:
                    ctypes.CDLL(str(candidate))
                    return True
                except OSError:
                    continue
        return False
    except Exception:
        return False


def get_default_device():
    # 优先用 PyTorch 检测
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        pass

    if _has_cuda():
        return "cuda"
    return "cpu"


DEFAULT_DEVICE = get_default_device()
DEFAULT_COMPUTE_TYPE = "float16" if DEFAULT_DEVICE == "cuda" else "int8"
DEFAULT_MODEL_SIZE = "large-v3" if DEFAULT_DEVICE == "cuda" else "base"
DEFAULT_NUM_WORKERS = 1 if DEFAULT_DEVICE == "cuda" else 4

print(
    f"DEBUG: Hardware detected: {DEFAULT_DEVICE} on {sys.platform}, using compute_type: {DEFAULT_COMPUTE_TYPE}"
)
