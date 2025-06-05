import subprocess
import time
import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AppRestartHandler(FileSystemEventHandler):
    def __init__(self):
        self.process = None
        self.start_app()

    def start_app(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
        print("\nStarting application...")
        self.process = subprocess.Popen(['python', 'main.py'])

    def on_modified(self, event):
        if event.src_path.endswith('.py') or event.src_path.endswith('.html'):
            print(f"\nFile changed: {event.src_path}")
            self.start_app()

def main():
    handler = AppRestartHandler()
    observer = Observer()
    observer.schedule(handler, path='.', recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        if handler.process:
            handler.process.terminate()
    observer.join()

if __name__ == "__main__":
    main() 