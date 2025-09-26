from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess, time, sys

class RestartOnChange(FileSystemEventHandler):
    def __init__(self, cmd):
        self.cmd = cmd
        self.process = None
        self.start_bot()

    def start_bot(self):
        if self.process:
            self.process.kill()
        self.process = subprocess.Popen(self.cmd)

    def on_modified(self, event):
        if event.src_path.endswith("main.py"):
            print("🔄 File changed, restarting bot...")
            self.start_bot()

if __name__ == "__main__":
    path = "."
    event_handler = RestartOnChange([sys.executable, "main.py"])
    observer = Observer()
    observer.schedule(event_handler, path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()