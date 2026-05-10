import psutil
import threading
import time

class SystemSentinel:
    def __init__(self, callback=None):
        self.callback = callback
        self.running = True
        self._thread = threading.Thread(target=self._monitor, daemon=True)
        self._thread.start()

    def _monitor(self):
        while self.running:
            try:
                cpu = psutil.cpu_percent(interval=1)
                ram = psutil.virtual_memory().percent
                disk = psutil.disk_usage('/').percent
                
                # Logic for "Critical" alerts
                status = "NOMINAL"
                if cpu > 90 or ram > 90:
                    status = "CRITICAL"
                elif cpu > 70 or ram > 70:
                    status = "HEAVY"
                
                if self.callback:
                    self.callback(cpu, ram, status)
            except Exception as e:
                print(f"Sentinel Error: {e}")
            
            time.sleep(5) # Check every 5 seconds to save resources

    def stop(self):
        self.running = False

    def get_current_stats(self):
        return {
            "cpu": psutil.cpu_percent(),
            "ram": psutil.virtual_memory().percent,
            "disk": psutil.disk_usage('/').percent
        }
