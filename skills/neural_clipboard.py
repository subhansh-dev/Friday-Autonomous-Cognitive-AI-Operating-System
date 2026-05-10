import pyperclip
import threading
import time
from collections import deque

class NeuralClipboard:
    def __init__(self, callback=None):
        self.callback = callback
        self.last_content = pyperclip.paste()
        self.history = deque(maxlen=50)
        self.running = True
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def _watch(self):
        while self.running:
            try:
                current_content = pyperclip.paste()
                if current_content != self.last_content:
                    self.last_content = current_content
                    self.history.append(current_content)
                    if self.callback:
                        self.callback(current_content)
            except Exception as e:
                print(f"Clipboard Error: {e}")
            
            time.sleep(0.5) # Poll every 500ms

    def stop(self):
        self.running = False

    def get_history(self):
        return list(self.history)
