"""Native worker-only resource enforcement with portable CPU/peak-memory reports."""

from __future__ import annotations

import os
import sys
import time


class ResourceGuard:
    """Install on a disposable worker, never on the long-lived Armory process."""

    def __init__(self, *, memory_bytes=512 * 1024 * 1024, cpu_seconds=128):
        if memory_bytes < 16 * 1024 * 1024 or cpu_seconds <= 0:
            raise ValueError("Resource budgets must allow at least 16 MiB and positive CPU time.")
        self.memory_bytes = memory_bytes
        self.cpu_limit = cpu_seconds
        self.enforcement = "unavailable"
        self._job = None

    def install(self):
        if os.name == "nt":
            self._windows()
        elif os.name == "posix":
            import resource

            for kind, requested in ((resource.RLIMIT_AS, self.memory_bytes), (resource.RLIMIT_CPU, self.cpu_limit)):
                soft, hard = resource.getrlimit(kind)
                ceiling = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
                if soft != resource.RLIM_INFINITY:
                    ceiling = min(ceiling, soft)
                resource.setrlimit(kind, (ceiling, ceiling))
                if kind == resource.RLIMIT_AS:
                    self.memory_bytes = ceiling
                else:
                    self.cpu_limit = ceiling
            self.enforcement = "posix_rlimit"
        else:
            raise OSError("Native math worker resource enforcement is unsupported on this platform.")

    def _windows(self):
        import ctypes as c
        from ctypes import wintypes as w

        class Basic(c.Structure):
            _fields_ = [("PerProcessUserTimeLimit", c.c_longlong), ("PerJobUserTimeLimit", c.c_longlong),
                        ("LimitFlags", w.DWORD), ("MinimumWorkingSetSize", c.c_size_t), ("MaximumWorkingSetSize", c.c_size_t),
                        ("ActiveProcessLimit", w.DWORD), ("Affinity", c.c_size_t), ("PriorityClass", w.DWORD), ("SchedulingClass", w.DWORD)]

        class IO(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                         "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class Extended(c.Structure):
            _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", IO), ("ProcessMemoryLimit", c.c_size_t),
                        ("JobMemoryLimit", c.c_size_t), ("PeakProcessMemoryUsed", c.c_size_t), ("PeakJobMemoryUsed", c.c_size_t)]

        kernel = c.WinDLL("kernel32", use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
        kernel.CreateJobObjectW.restype = w.HANDLE
        kernel.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
        kernel.SetInformationJobObject.restype = w.BOOL
        kernel.QueryInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD, c.c_void_p]
        kernel.QueryInformationJobObject.restype = w.BOOL
        kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
        kernel.AssignProcessToJobObject.restype = w.BOOL
        kernel.GetCurrentProcess.restype = w.HANDLE
        kernel.CloseHandle.argtypes = [w.HANDLE]
        job = kernel.CreateJobObjectW(None, None)
        if not job:
            raise c.WinError(c.get_last_error())
        limits = Extended()
        limits.BasicLimitInformation.LimitFlags = 0x100 | 0x2  # Process committed memory and user CPU lifetime.
        limits.BasicLimitInformation.PerProcessUserTimeLimit = int(self.cpu_limit * 10_000_000)
        limits.ProcessMemoryLimit = self.memory_bytes
        if not kernel.SetInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits)) or not kernel.AssignProcessToJobObject(job, kernel.GetCurrentProcess()):
            code = c.get_last_error()
            kernel.CloseHandle(job)
            raise c.WinError(code)
        # Keep the handle alive for this worker lifetime; the OS closes it on exit.
        self._job = job, kernel, Extended
        self.enforcement = "windows_job"

    def snapshot(self, cpu_delta=0.0):
        if self.enforcement == "windows_job":
            import ctypes as c

            job, kernel, structure = self._job
            limits = structure()
            if not kernel.QueryInformationJobObject(job, 9, c.byref(limits), c.sizeof(limits), None):
                raise c.WinError(c.get_last_error())
            peak = limits.PeakProcessMemoryUsed
        else:
            import resource

            peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak *= 1 if sys.platform == "darwin" else 1024
        return {"hard_limits": True, "enforcement": self.enforcement, "memory_limit_bytes": self.memory_bytes,
                "cpu_limit_seconds": self.cpu_limit, "peak_memory_bytes": int(peak),
                "cpu_seconds": max(0.0, cpu_delta), "cpu_total_seconds": time.process_time()}
