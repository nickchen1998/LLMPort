"""主機狀態：記憶體、CPU、記憶體壓力、Metal 上限、GPU（有裝 macmon 才有）與 Cloudflare Tunnel。"""
import json
import logging
import shutil
import subprocess
import sys
import threading

import httpx
import psutil

logger = logging.getLogger(__name__)
MB = 2 ** 20


def total_memory_gb() -> float:
    return psutil.virtual_memory().total / 2 ** 30


def _sysctl(name: str) -> str | None:
    if sys.platform != "darwin":
        return None
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, timeout=2)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def memory_pressure(available_ratio: float) -> str:
    """macOS 的 kern.memorystatus_vm_pressure_level：1 正常、2 警告、4 嚴重；其他系統依可用比例估計。"""
    level = _sysctl("kern.memorystatus_vm_pressure_level")
    if level in ("1", "2", "4"):
        return {"1": "normal", "2": "warn", "4": "critical"}[level]
    return "critical" if available_ratio < .08 else "warn" if available_ratio < .18 else "normal"


def wired_limit_mb() -> int | None:
    """iogpu.wired_limit_mb；0 表示 macOS 預設值。"""
    value = _sysctl("iogpu.wired_limit_mb")
    return int(value) if value and value.isdigit() else None


def host_snapshot() -> dict:
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "total_mb": vm.total / MB,
        "available_mb": vm.available / MB,
        "swap_used_mb": swap.used / MB,
        "pressure": memory_pressure(vm.available / vm.total),
        "cpu_percent": psutil.cpu_percent(interval=None),
        "gpu_percent": gpu.value,
        "wired_limit_mb": wired_limit_mb(),
    }


class GpuSampler:
    """macmon（brew install macmon）不需要 sudo 就能讀 GPU 使用率；沒安裝時 value 一直是 None。"""

    def __init__(self):
        self.value: float | None = None
        self._started = False

    def start(self) -> None:
        if self._started or not shutil.which("macmon"):
            return
        self._started = True
        threading.Thread(target=self._run, name="macmon", daemon=True).start()

    def _run(self) -> None:
        try:
            proc = subprocess.Popen(["macmon", "pipe", "-i", "2000"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                    text=True)
        except OSError:
            return
        for line in proc.stdout:
            try:
                usage = json.loads(line).get("gpu_usage")
                # macmon 回傳 [頻率 MHz, 使用率 0–1]
                self.value = round(float(usage[1]) * 100, 1) if isinstance(usage, list) else None
            except (ValueError, TypeError, IndexError, AttributeError):
                self.value = None


gpu = GpuSampler()


async def cloudflared_status(metrics_url: str | None) -> str:
    """cloudflared --metrics 提供的 /ready：200 表示至少一條連線到 Cloudflare。"""
    if not metrics_url:
        return "unknown"
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get(metrics_url.rstrip("/") + "/ready")
        return "connected" if r.status_code == 200 else "down"
    except httpx.HTTPError:
        return "down"
