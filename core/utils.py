import os
import json
import zipfile
import shutil
import time

CONFIG_FILE = "/storage/emulated/0/TelegramBotHost/config.json"

def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {
            "bot_token": "8868077003:AAHNmazPEVJpg9L_VnXffDW5ptBk3I-G_uI",
            "admin_ids": [7267577982],
            "storage_root": "/storage/emulated/0/TelegramBotHost",
            "max_bots_per_user": 3,
            "max_upload_size_mb": 25,
            "max_zip_extracted_mb": 60,
            "max_files_in_zip": 150,
            "max_log_bytes": 1048576,
            "max_restarts": 5,
            "restart_window_seconds": 60,
            "maintenance_mode": False
        }
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def ensure_directories():
    config = load_config()
    root = config.get("storage_root", "/storage/emulated/0/TelegramBotHost")
    dirs = [
        os.path.join(root, "database"),
        os.path.join(root, "bots"),
        os.path.join(root, "logs"),
        os.path.join(root, "backups"),
        os.path.join(root, "temp"),
        os.path.join(root, "data"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)

def safe_extract_zip(zip_path: str, extract_to: str, max_size_mb: int = 60, max_files: int = 150) -> tuple:
    """
    Validates against Zip-Slip vulnerabilities and resource exhaustion.
    """
    total_size = 0
    total_files = 0
    max_bytes = max_size_mb * 1024 * 1024
    extract_to = os.path.abspath(extract_to)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            infolist = zf.infolist()
            if len(infolist) > max_files:
                return False, f"ZIP contains too many files ({len(infolist)} > {max_files})."

            for member in infolist:
                total_files += 1
                total_size += member.file_size
                if total_size > max_bytes:
                    return False, f"Extracted contents exceed maximum quota of {max_size_mb}MB."

                target_path = os.path.abspath(os.path.join(extract_to, member.filename))
                if not target_path.startswith(extract_to + os.sep) and target_path != extract_to:
                    return False, "Security violation: Path traversal detected in archive!"

            zf.extractall(extract_to)
            return True, "Extraction successful"
    except zipfile.BadZipFile:
        return False, "Uploaded file is not a valid or corrupted ZIP file."
    except Exception as e:
        return False, f"Extraction failed: {str(e)}"

def format_bytes(size: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} TB"

def get_system_metrics() -> dict:
    """
    Pure-Python Android / Termux compatible system metrics
    without requiring external C libraries (psutil).
    """
    # 1. RAM Usage via /proc/meminfo
    mem_total_kb = 0
    mem_avail_kb = 0
    try:
        with open("/proc/meminfo", "r") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    mem_total_kb = int(line.split()[1])
                elif line.startswith("MemAvailable:"):
                    mem_avail_kb = int(line.split()[1])
        mem_used_kb = mem_total_kb - mem_avail_kb
        mem_pct = (mem_used_kb / mem_total_kb * 100) if mem_total_kb > 0 else 0
        mem_used_str = format_bytes(mem_used_kb * 1024)
        mem_total_str = format_bytes(mem_total_kb * 1024)
        mem_pct_str = f"{mem_pct:.1f}%"
    except Exception:
        mem_used_str = "N/A"
        mem_total_str = "N/A"
        mem_pct_str = "N/A"

    # 2. CPU Load via /proc/loadavg
    try:
        with open("/proc/loadavg", "r") as f:
            load = f.read().split()[:3]
            cpu_usage_str = f"Load: {load[0]}, {load[1]}, {load[2]}"
    except Exception:
        cpu_usage_str = "Running"

    # 3. Disk Usage via standard library shutil.disk_usage
    try:
        disk = shutil.disk_usage("/storage/emulated/0")
        disk_pct = (disk.used / disk.total * 100) if disk.total > 0 else 0
        disk_free_str = format_bytes(disk.free)
        disk_total_str = format_bytes(disk.total)
        disk_pct_str = f"{disk_pct:.1f}%"
    except Exception:
        disk_free_str = "N/A"
        disk_total_str = "N/A"
        disk_pct_str = "N/A"

    return {
        "cpu_usage": cpu_usage_str,
        "mem_used": mem_used_str,
        "mem_total": mem_total_str,
        "mem_pct": mem_pct_str,
        "disk_free": disk_free_str,
        "disk_total": disk_total_str,
        "disk_pct": disk_pct_str
    }

def sanitize_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in ("-", "_")).strip()