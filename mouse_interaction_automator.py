#!/usr/bin/env python3
"""Cross-platform random scroll-then-click desktop automation.

Dependencies: pip install -r requirements.txt
Run: python mouse_interaction_automator.py

Global shortcuts:
  Ctrl+Shift+S: Start / pause / resume
  Ctrl+Shift+Q: Stop

Emergency fallback: move the pointer to a screen corner to trigger
PyAutoGUI's built-in fail-safe.
"""

import sys
import os

# Use logical, consistent coordinates for Tkinter and PyAutoGUI on Windows.
# Do this before importing either GUI/mouse library.
if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass

import queue
import random
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import pyautogui
    from pynput import keyboard
    import pystray
    from PIL import Image, ImageDraw
except ImportError as exc:
    raise SystemExit(
        "Missing dependency. Install with:\n"
        "    python -m pip install -r requirements.txt\n"
        f"Details: {exc}"
    ) from exc

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.04


class RegionSelector:
    """A temporary overlay for dragging out a rectangle on the main display."""

    def __init__(self, parent, screen_size, on_select, on_cancel):
        self.on_select = on_select
        self.on_cancel = on_cancel
        self.screen_width, self.screen_height = screen_size
        self.start = None
        self.rectangle_id = None

        self.window = tk.Toplevel(parent)
        self.window.title("Select click and scroll region")
        self.window.attributes("-topmost", True)
        self.window.attributes("-fullscreen", True)
        self.window.attributes("-alpha", 0.42)
        self.window.configure(bg="#0f172a")
        self.window.protocol("WM_DELETE_WINDOW", self.cancel)
        self.window.bind("<Escape>", lambda _event: self.cancel())

        self.canvas = tk.Canvas(
            self.window,
            bg="#0f172a",
            highlightthickness=0,
            cursor="crosshair",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(
            self.screen_width // 3,
            max(65, self.screen_height // 15),
            text="Drag to select a screen region  |  Esc to cancel",
            fill="white",
            font=("Arial", 18, "bold"),
        )
        self.canvas.bind("<ButtonPress-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)
        self.window.after(100, self.window.focus_force)

    def mouse_down(self, event):
        self.start = (event.x_root, event.y_root)
        if self.rectangle_id is not None:
            self.canvas.delete(self.rectangle_id)
        self.rectangle_id = self.canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#7dd3fc", width=3, fill="#38bdf8", stipple="gray25",
        )

    def mouse_drag(self, event):
        if self.start is None:
            return
        local_x = self.start[0] - self.window.winfo_rootx()
        local_y = self.start[1] - self.window.winfo_rooty()
        self.canvas.coords(self.rectangle_id, local_x, local_y, event.x, event.y)

    def mouse_up(self, event):
        if self.start is None:
            return
        x1, x2 = sorted((self.start[0], event.x_root))
        y1, y2 = sorted((self.start[1], event.y_root))
        x1, x2 = max(0, x1), min(self.screen_width - 1, x2)
        y1, y2 = max(0, y1), min(self.screen_height - 1, y2)
        if x2 - x1 < 20 or y2 - y1 < 20:
            messagebox.showwarning(
                "Region too small", "Please select a rectangle at least 20 x 20 pixels.",
                parent=self.window,
            )
            self.start = None
            return
        self.window.destroy()
        self.on_select((x1, y1, x2, y2))

    def cancel(self):
        self.window.destroy()
        self.on_cancel()


class MouseAutomationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Mouse Interaction Automator")
        self.root.geometry("700x900")
        self.root.minsize(700, 750)

        self.region = None
        self.selecting = False
        self.state = "idle"  # idle, running, paused, stopping
        self.worker = None
        self.stop_event = threading.Event()
        self.run_event = threading.Event()
        self.messages = queue.Queue()
        self.tray_icon = None

        self.scroll_min_var = tk.StringVar(value="200")
        self.scroll_max_var = tk.StringVar(value="400")
        self.scroll_wait_min_var = tk.StringVar(value="0.8")
        self.scroll_wait_max_var = tk.StringVar(value="1.8")
        self.click_wait_min_var = tk.StringVar(value="1.0")
        self.click_wait_max_var = tk.StringVar(value="3.0")
        self.region_var = tk.StringVar(value="No region selected")
        self.status_var = tk.StringVar(value="Idle. Select a region and start.")

        self.make_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        try:
            self.hotkeys = keyboard.GlobalHotKeys({
                "<ctrl>+<shift>+s": self.request_toggle,
                "<ctrl>+<shift>+q": self.request_stop,
            })
            self.hotkeys.start()
        except Exception as exc:
            self.hotkeys = None
            self.status_var.set(f"Hotkeys unavailable: {exc}. Use the buttons.")
        self.root.after(80, self.process_messages)

    def make_ui(self):
        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="Mouse Interaction Automator", font=("Arial", 17, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text="Every cycle: random scroll → wait → one random click → wait.",
            wraplength=440,
        ).pack(anchor="w", pady=(4, 14))

        region_frame = ttk.LabelFrame(main, text="1. Screen region", padding=12)
        region_frame.pack(fill="x", pady=(0, 10))
        self.select_button = ttk.Button(region_frame, text="Select region on screen", command=self.select_region)
        self.select_button.pack(anchor="w")
        ttk.Label(region_frame, textvariable=self.region_var, wraplength=400).pack(anchor="w", pady=(7, 0))

        options = ttk.LabelFrame(main, text="2. Random ranges", padding=12)
        options.pack(fill="x", pady=(0, 10))
        options.columnconfigure(1, weight=1)
        options.columnconfigure(2, weight=1)
        ttk.Label(options, text="", width=21).grid(row=0, column=0)
        ttk.Label(options, text="Minimum").grid(row=0, column=1, sticky="w")
        ttk.Label(options, text="Maximum").grid(row=0, column=2, sticky="w")

        self.add_range(options, 1, "Scroll amount (steps)", self.scroll_min_var, self.scroll_max_var)
        self.add_range(options, 2, "Wait after scroll (sec)", self.scroll_wait_min_var, self.scroll_wait_max_var)
        self.add_range(options, 3, "Wait after click (sec)", self.click_wait_min_var, self.click_wait_max_var)

        ttk.Label(
            options,
            text="Scroll direction is randomly up or down each cycle.",
            wraplength=400,
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(10, 0))

        shortcuts = ttk.LabelFrame(main, text="3. Controls", padding=12)
        shortcuts.pack(fill="x", pady=(0, 10))
        ttk.Label(shortcuts, text="Ctrl + Shift + S: Start / Pause / Resume").pack(anchor="w")
        ttk.Label(shortcuts, text="Ctrl + Shift + Q: Stop").pack(anchor="w", pady=(3, 0))

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=(4, 8))
        self.toggle_button = ttk.Button(buttons, text="Start", command=self.toggle)
        self.toggle_button.pack(side="left", expand=True, fill="x", padx=(0, 5))
        self.stop_button = ttk.Button(buttons, text="Stop", command=self.stop)
        self.stop_button.pack(side="left", expand=True, fill="x", padx=(5, 0))
        ttk.Button(main, text="Run in Background (System Tray)", command=self.minimize_to_tray).pack(fill="x", pady=(4, 6))

        ttk.Label(main, textvariable=self.status_var, wraplength=440, foreground="#226e85").pack(anchor="w")
        ttk.Label(
            main,
            text="Emergency stop: move the mouse to a screen corner. "
                 "The selected area must be visible on your primary screen.",
            wraplength=440,
            foreground="#777777",
        ).pack(anchor="w", pady=(10, 0))

    @staticmethod
    def add_range(parent, row, caption, min_var, max_var):
        ttk.Label(parent, text=caption).grid(row=row, column=0, sticky="w", pady=5)
        ttk.Entry(parent, textvariable=min_var, width=10).grid(row=row, column=1, sticky="ew", padx=(0, 12), pady=5)
        ttk.Entry(parent, textvariable=max_var, width=10).grid(row=row, column=2, sticky="ew", pady=5)

    def select_region(self):
        if self.state != "idle" or self.selecting:
            self.status_var.set("Stop the automation before selecting another region.")
            return
        self.selecting = True
        self.select_button.configure(state="disabled")
        self.root.withdraw()
        # Wait for the main window to disappear before displaying the overlay.
        self.root.after(180, self.show_selector)

    def show_selector(self):
        try:
            RegionSelector(
                self.root,
                pyautogui.size(),
                on_select=self.region_selected,
                on_cancel=self.region_cancelled,
            )
        except Exception as exc:
            self.region_cancelled()
            messagebox.showerror("Region selection failed", str(exc), parent=self.root)

    def region_selected(self, region):
        self.region = region
        x1, y1, x2, y2 = region
        self.region_var.set(f"Left {x1}, Top {y1}, Right {x2}, Bottom {y2}")
        self.region_cancelled()
        self.status_var.set("Region saved. Ready to start.")

    def region_cancelled(self):
        self.root.deiconify()
        self.root.lift()
        self.selecting = False
        self.select_button.configure(state="normal")

    def settings(self):
        if self.region is None:
            raise ValueError("Select a screen region first.")

        def range_pair(a, b, label, integer=False):
            convert = int if integer else float
            try:
                low, high = convert(a.get()), convert(b.get())
            except ValueError as exc:
                raise ValueError(f"{label}: enter valid numbers.") from exc
            minimum = 1 if integer else 0.1
            if not (minimum <= low <= high <= 3600):
                raise ValueError(f"{label}: use {minimum} ≤ minimum ≤ maximum ≤ 3600.")
            return low, high

        amount = range_pair(self.scroll_min_var, self.scroll_max_var, "Scroll steps", True)
        after_scroll = range_pair(self.scroll_wait_min_var, self.scroll_wait_max_var, "Wait after scroll")
        after_click = range_pair(self.click_wait_min_var, self.click_wait_max_var, "Wait after click")
        return self.region, amount, after_scroll, after_click

    def request_toggle(self):
        self.messages.put(("toggle", None))

    def request_stop(self):
        # Set the stop flag immediately, even before Tk processes the message.
        self.stop_event.set()
        self.run_event.set()
        self.messages.put(("stop", None))

    def toggle(self):
        if self.selecting or self.state == "stopping":
            return
        if self.state == "running":
            self.run_event.clear()
            self.state = "paused"
            self.toggle_button.configure(text="Resume")
            self.status_var.set("Paused. Ctrl + Shift + S to resume.")
            return
        if self.state == "paused":
            self.run_event.set()
            self.state = "running"
            self.toggle_button.configure(text="Pause")
            self.status_var.set("Running: random scroll → click.")
            return

        try:
            configuration = self.settings()
        except ValueError as exc:
            messagebox.showerror("Invalid settings", str(exc), parent=self.root)
            return
        self.stop_event.clear()
        self.run_event.set()
        self.state = "running"
        self.toggle_button.configure(text="Pause")
        self.select_button.configure(state="disabled")
        self.status_var.set("Running: random scroll → click.")
        self.worker = threading.Thread(
            target=self.automation_loop, args=(configuration,), daemon=True
        )
        self.worker.start()

    def stop(self):
        if self.state in ("idle", "stopping"):
            return
        self.stop_event.set()
        self.run_event.set()
        self.state = "stopping"
        self.toggle_button.configure(text="Stopping…")
        self.status_var.set("Stopping automation…")

    def point_in_region(self, region):
        x1, y1, x2, y2 = region
        width, height = pyautogui.size()
        # Avoid the outermost screen pixels, which can trigger a fail-safe.
        x1, x2 = max(1, x1), min(width - 2, x2)
        y1, y2 = max(1, y1), min(height - 2, y2)
        return random.randint(x1, x2), random.randint(y1, y2)

    def check_ready(self):
        while not self.stop_event.is_set():
            if self.run_event.wait(timeout=0.05):
                return not self.stop_event.is_set()
        return False

    def interruptible_wait(self, seconds):
        # Pausing stops the timer; stopping ends the wait immediately.
        remaining = seconds
        while remaining > 0:
            if not self.check_ready():
                return False
            chunk = min(remaining, 0.05)
            start = time.monotonic()
            if self.stop_event.wait(chunk):
                return False
            remaining -= time.monotonic() - start
        return self.check_ready()

    def automation_loop(self, config):
        region, amount, after_scroll, after_click = config
        try:
            while self.check_ready():
                pyautogui.moveTo(*self.point_in_region(region), duration=0.10)
                if not self.check_ready():
                    break
                scroll_steps = random.randint(*amount) * random.choice((-1, 1))
                pyautogui.scroll(scroll_steps)
                if not self.interruptible_wait(random.uniform(*after_scroll)):
                    break

                pyautogui.moveTo(*self.point_in_region(region), duration=0.10)
                if not self.check_ready():
                    break
                pyautogui.click(button="left")  # Exactly one click per cycle.
                if not self.interruptible_wait(random.uniform(*after_click)):
                    break
        except pyautogui.FailSafeException:
            self.messages.put(("error", "Emergency fail-safe triggered at a screen corner."))
        except Exception as exc:
            self.messages.put(("error", f"Automation error: {exc}"))
        finally:
            self.messages.put(("finished", None))

    def _tray_image(self):
        """Draw a distinct MIA monogram for the system tray only."""
        image = Image.new("RGBA", (64, 64), (28, 50, 72, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((2, 2, 61, 61), radius=15,
                               outline=(108, 191, 210, 255), width=3)
        draw.polygon([(16, 44), (16, 21), (24, 35), (32, 21), (32, 44)],
                     fill=(255, 255, 255, 255))
        draw.rectangle((38, 21, 43, 44), fill=(255, 255, 255, 255))
        draw.polygon([(47, 44), (51, 21), (55, 44)],
                     fill=(255, 255, 255, 255))
        return image

    def minimize_to_tray(self):
        """Hide the settings window while keeping a visible tray icon."""
        if self.selecting:
            return
        if self.tray_icon is None:
            menu = pystray.Menu(
                pystray.MenuItem("Open Mouse Interaction Automator", lambda icon, item: self.messages.put(("show_window", None)), default=True),
                pystray.MenuItem("Stop automation", lambda icon, item: self.request_stop()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Quit Mouse Interaction Automator", lambda icon, item: self.messages.put(("quit_app", None))),
            )
            self.tray_icon = pystray.Icon("mouse_interaction_automator", self._tray_image(), "MIA", menu)
            try:
                self.tray_icon.run_detached()
            except Exception as exc:
                self.tray_icon = None
                messagebox.showerror("System tray unavailable", str(exc), parent=self.root)
                return
        self.root.withdraw()

    def show_from_tray(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def process_messages(self):
        try:
            while True:
                kind, data = self.messages.get_nowait()
                if kind == "show_window":
                    self.show_from_tray()
                elif kind == "quit_app":
                    self.close()
                    return
                elif kind == "toggle":
                    self.toggle()
                elif kind == "stop":
                    self.stop()
                elif kind == "error":
                    self.status_var.set(data)
                elif kind == "finished":
                    self.state = "idle"
                    self.stop_event.set()
                    self.run_event.clear()
                    self.toggle_button.configure(text="Start")
                    self.select_button.configure(state="normal")
                    if not self.status_var.get().startswith(("Automation error", "Emergency")):
                        self.status_var.set("Stopped. Ready to start again.")
        except queue.Empty:
            pass
        self.root.after(80, self.process_messages)

    def close(self):
        self.stop_event.set()
        self.run_event.set()
        if self.hotkeys is not None:
            self.hotkeys.stop()
        if self.tray_icon is not None:
            self.tray_icon.stop()
            self.tray_icon = None
        self.root.destroy()


def main():
    root = tk.Tk()
    if sys.platform == "win32":
        icon_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
        if os.path.isfile(icon_file):
            try:
                root.iconbitmap(icon_file)
            except tk.TclError:
                pass
    try:
        MouseAutomationApp(root)
    except Exception as exc:
        messagebox.showerror("Startup error", str(exc), parent=root)
        root.destroy()
        return
    root.mainloop()


if __name__ == "__main__":
    main()
