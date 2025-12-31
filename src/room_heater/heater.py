import multiprocessing
import sys
import os
import threading
import time
import numpy as np

try:
    import psutil
except ImportError:
    print("psutil is not installed. Please install it using `pip install psutil`")
    sys.exit(1)

# Windows Management Instrumentation
try:
    import WinTmp
    WIN_TMP_AVAILABLE = True
except ImportError:
    WIN_TMP_AVAILABLE = False

# GPUtil
try:
    import GPUtil
    GPU_TEMP_AVAILABLE = True
except ImportError:
    GPU_TEMP_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = torch.cuda.is_available()
except ImportError:
    TORCH_AVAILABLE = False

try:
    import pynvml
    pynvml.nvmlInit()
    NVIDIA_SMI_AVAILABLE = pynvml.nvmlDeviceGetCount() > 0
except ImportError:
    NVIDIA_SMI_AVAILABLE = False

def heat_worker():
    try:
        p = psutil.Process(os.getpid())
        if sys.platform == 'win32':
            p.nice(psutil.IDLE_PRIORITY_CLASS)
        else:
            p.nice(19)
    except Exception:
        pass

    while(True):
        number = 0
        if(number >= sys.maxsize):
            number = 0
        else:
            number = number + 1

def gpu_heat_worker(matrix_size: int, stop_event: threading.Event):
    if not TORCH_AVAILABLE:
        return

    device = torch.device('cuda')

    a = torch.randn(matrix_size, matrix_size, device=device)
    b = torch.randn(matrix_size, matrix_size, device=device)
    
    while not stop_event.is_set():
        _ = torch.mm(a, b)
        torch.cuda.synchronize()
        time.sleep(0.01)

class SmartHeater:
    def __init__(self):
        self.running = True

        # CPU
        self.cpu_processes = []
        self.cpu_max_temp = 90
        self.cpu_target_temp = 85
        self.cpu_min_temp = 50

        # GPU
        self.gpu_thread = None
        self.gpu_stop_event = threading.Event()
        self.gpu_max_temp = 90
        self.gpu_target_temp = 85
        self.gpu_min_temp = 45
        self.gpu_running = False

        # For usage based adjustment
        self.min_idle_threshold = 30
        self.max_usage_threshold = 90

        self.check_interval = 2

    def get_cpu_temperature(self):
        if WIN_TMP_AVAILABLE:
            try:
                temps = WinTmp.CPU_Temp()
                if temps:
                    # Kelvin to Celsius conversion
                    return temps
            except Exception:
                pass

        # try psutil(for linux)
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                for _, entries in temps.items():
                    for entry in entries:
                        if entry.current:
                            return entry.current

        return None
    
    def get_gpu_temperature(self):
        if WIN_TMP_AVAILABLE:
            try:
                temps = WinTmp.GPU_Temp()
                if temps:
                    return temps
            except Exception:
                pass

        # try GPUtil(for linus)
        if GPU_TEMP_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    return gpus[0].temperature
            except Exception:
                pass

        return None

    def get_gpu_percent(self):
        if not TORCH_AVAILABLE:
            return None

        if not NVIDIA_SMI_AVAILABLE:
            return None

        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)

        return utilization.gpu
    
    def get_system_stats(self):
        cpu_percent = psutil.cpu_percent(interval=self.check_interval)
        cpu_temp = self.get_cpu_temperature()
        gpu_temp = self.get_gpu_temperature()
        gpu_percent = self.get_gpu_percent()
        memory = psutil.virtual_memory()

        return {
            'cpu_percent': cpu_percent,
            'cpu_temp': cpu_temp,
            'gpu_percent': gpu_percent,
            'gpu_temp': gpu_temp,
            'memory_percent': memory.percent,
            'cpu_worker_count': len([p for p in self.cpu_processes if p.is_alive()]),
            'gpu_active': self.gpu_running,
        }

    def display_status(self, stats):
        os.system('cls' if sys.platform == 'win32' else 'clear')
        
        print("=" * 10)
        print("SMART ROOM HEATER")
        print("=" * 10)
        
        # CPU Status
        print(f"CPU usage: {stats['cpu_percent']:.1f}%")
        if stats['cpu_temp']:
            print(f"CPU temperature: {stats['cpu_temp']:.1f}°C")
        else:
            print("CPU temperature: not available")

        # GPU Status
        print(f"GPU active: {'Yes' if stats['gpu_active'] else 'No'}")
        if stats['gpu_percent']:
            print(f"GPU usage: {stats['gpu_percent']:.1f}%")
        else:
            print("GPU usage: not available")
        if stats['gpu_temp']:
            print(f"GPU temperature: {stats['gpu_temp']:.1f}°C")
        else:
            print("GPU temperature: not available")
        
        print(f"Memory usage: {stats['memory_percent']:.1f}%")
        print(f"Active worker count: {stats['cpu_worker_count']}/{multiprocessing.cpu_count()}")
        print("-" * 10)
        print("If other programs are running, they will be automatically yielded.")
        print("To exit, press Ctrl+C")
        print("=" * 10)

    def adjust_cpu_workers(self, cpu_temp, cpu_usage):
        max_workers = multiprocessing.cpu_count()
        
        # clean up dead processes
        self.cpu_processes = [p for p in self.cpu_processes if p.is_alive()]
        current_workers = len([p for p in self.cpu_processes if p.is_alive()])

        # based on temperature
        if cpu_temp is not None:
            if cpu_temp >= self.cpu_max_temp and current_workers > 0:
                worker = self.cpu_processes.pop()
                worker.terminate()
                return
            elif cpu_temp <= self.cpu_min_temp and current_workers < max_workers:
                self._add_cpu_worker()
                return
            elif cpu_temp > self.cpu_target_temp and current_workers > 1:
                worker = self.cpu_processes.pop()
                worker.terminate()
                return

        # based on usage
        if cpu_usage > self.max_usage_threshold and current_workers > 0:
            worker = self.cpu_processes.pop()
            worker.terminate()
        elif cpu_usage < self.min_idle_threshold and current_workers < max_workers:
            self._add_cpu_worker()

    def _add_cpu_worker(self):
        worker = multiprocessing.Process(target=heat_worker)
        worker.daemon = True
        worker.start()
        self.cpu_processes.append(worker)

    def adjust_gpu_workers(self, gpu_temp, gpu_usage):
        if not TORCH_AVAILABLE:
            return

        if not self.gpu_running:
            return

        # based on temperature
        if gpu_temp is not None:
            if gpu_temp >= self.gpu_max_temp and self.gpu_running:
                self._stop_gpu_heater()
            elif gpu_temp <= self.gpu_min_temp and not self.gpu_running:
                self._start_gpu_heater()
            elif gpu_temp > self.gpu_target_temp and self.gpu_running:
                self._stop_gpu_heater()

        # base on usage
        if gpu_usage is not None:
            if gpu_usage > self.max_usage_threshold and self.gpu_running:
                self._stop_gpu_heater()
            elif gpu_usage < self.min_idle_threshold and not self.gpu_running:
                self._start_gpu_heater()

    def _start_gpu_heater(self):
        if self.gpu_running:
            self._stop_gpu_heater()
            return

        self.gpu_stop_event.clear()
        self.gpu_thread = threading.Thread(
            target=gpu_heat_worker,
            args=(4096, self.gpu_stop_event),
            daemon=True,
        )
        self.gpu_thread.start()
        self.gpu_running = True

    def _stop_gpu_heater(self):
        if not self.gpu_running:
            return

        self.gpu_stop_event.set()
        if self.gpu_thread:
            self.gpu_thread.join(timeout=2)
        self.gpu_running = False

    def run(self):
        print("Starting Smart Room Heater...")
        print("Initializing workers...")

        initial_workers = max(1, multiprocessing.cpu_count() // 2)
        for _ in range(initial_workers):
            self._add_cpu_worker()

        if TORCH_AVAILABLE:
            self._start_gpu_heater()
        
        try:
            while self.running:
                stats = self.get_system_stats()
                self.display_status(stats)
                
                self.adjust_cpu_workers(stats['cpu_temp'], stats['cpu_percent'])
                self.adjust_gpu_workers(stats['gpu_temp'], stats['gpu_percent'])
                
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n\nShutting down...")
            self.shutdown()

    def shutdown(self):
        self.running = False

        if TORCH_AVAILABLE:
            self._stop_gpu_heater()

        if NVIDIA_SMI_AVAILABLE:
            pynvml.nvmlShutdown()

        for p in self.cpu_processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=1)
        print("Smart Room Heater shutdown complete.")