"""Describe the machine and build a benchmark ran on, so every number has its context."""

import os
import platform
import subprocess

import mcpricer


def _sysctl(name):
    try:
        out = subprocess.run(["sysctl", "-n", name], capture_output=True, text=True, check=True)
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def _cpu_name():
    if platform.system() == "Darwin":
        return _sysctl("machdep.cpu.brand_string")
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or None


def _git_commit():
    """Short hash of HEAD, with "+dirty" if tracked files have uncommitted changes."""
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return head + ("+dirty" if dirty else "")


def environment():
    info = mcpricer.build_info()
    env = {
        "git_commit": _git_commit(),
        "cpu": _cpu_name(),
        "logical_cpus": os.cpu_count(),
        "os": platform.platform(),
        "python": platform.python_version(),
        "compiler": info["compiler"],
        "build_type": info["build_type"],
        "cxx_flags": info["cxx_flags"],
    }
    if platform.system() == "Darwin":
        # Apple Silicon: perflevel0 = performance cores, perflevel1 = efficiency cores.
        env["performance_cores"] = _sysctl("hw.perflevel0.physicalcpu")
        env["efficiency_cores"] = _sysctl("hw.perflevel1.physicalcpu")
    return env


def print_environment():
    for key, value in environment().items():
        print(f"{key:>18}: {value}")
