import multiprocessing
import sys
import os
import time

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

class SmartHeater:
    def __init__(self):
        self.running = True
        self.processes = []
        self.target_cpu_usage = 80
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
                for name, entries in temps.items():
                    for entry in entries:
                        if entry.current:
                            return entry.current

        return None
    
    def get_system_stats(self):
        cpu_percent = psutil.cpu_percent(interval=self.check_interval)
        cpu_temp = self.get_cpu_temperature()
        memory = psutil.virtual_memory()

        return {
            'cpu_percent': cpu_percent,
            'cpu_temp': cpu_temp,
            'memory_percent': memory.percent,
            'worker_count': len(self.processes),
        }

    def display_status(self, stats):
        os.system('cls' if sys.platform == 'win32' else 'clear')
        
        print("=" * 10)
        print("SMART ROOM HEATER")
        print("=" * 10)
        print(f"CPU usage: {stats['cpu_percent']:.1f}%")
        
        if stats['cpu_temp']:
            print(f"CPU temperature: {stats['cpu_temp']:.1f}°C")
        else:
            print("CPU temperature: not available")
        
        print(f"Memory usage: {stats['memory_percent']:.1f}%")
        print(f"Active worker count: {stats['worker_count']}/{multiprocessing.cpu_count()}")
        print("-" * 10)
        print("If other programs are running, they will be automatically yielded.")
        print("To exit, press Ctrl+C")
        print("=" * 10)

    def adjust_workers(self, current_cpu_usage):
        max_workers = multiprocessing.cpu_count()
        current_workers = len([p for p in self.processes if p.is_alive()])
        
        # clean up dead processes
        self.processes = [p for p in self.processes if p.is_alive()]
        
        # if CPU usage is low, add a worker
        if current_cpu_usage < self.min_idle_threshold and current_workers < max_workers:
            new_worker = multiprocessing.Process(target=heat_worker)
            new_worker.daemon = True
            new_worker.start()
            self.processes.append(new_worker)
        
        # if CPU usage is too high, remove a worker (yield to other programs)
        elif current_cpu_usage > self.max_usage_threshold and current_workers > 0:
            worker_to_remove = self.processes.pop()
            worker_to_remove.terminate()

    def run(self):
        print("Starting Smart Room Heater...")
        print("Initializing workers...")

        initial_workers = max(1, multiprocessing.cpu_count() // 2)
        for _ in range(initial_workers):
            worker = multiprocessing.Process(target=heat_worker)
            worker.daemon = True
            worker.start()
            self.processes.append(worker)
        
        try:
            while self.running:
                stats = self.get_system_stats()
                self.display_status(stats)
                self.adjust_workers(stats['cpu_percent'])
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n\nShutting down...")
            self.shutdown()

    def shutdown(self):
        self.running = False
        for p in self.processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=1)
        print("Smart Room Heater shutdown complete.")