"""Smallest possible app using ONLY the public engine API.  python examples/minimal_app.py"""

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from memoframe_engine.api import Engine, EngineError  # noqa: E402

root = tk.Tk()
root.title("Photo organizer (sample)")
events: "queue.Queue" = queue.Queue()
engine: Engine | None = None
status, bar = tk.StringVar(value="Pick a photo folder."), ttk.Progressbar(root, length=420)


def work(folder: str) -> None:
    global engine
    try:
        with Engine(Path.home() / "photo_ws", profile="gentle", on_event=events.put) as eng:
            engine = eng
            result = eng.run_all(folder)
            events.put(("done", result["stats"]))
    except EngineError as exc:
        events.put(("error", f"{exc.code.value}: {exc.message}"))
    finally:
        engine = None


def start() -> None:
    folder = filedialog.askdirectory()
    if folder and engine is None:
        threading.Thread(target=work, args=(folder,), daemon=True).start()


def poll() -> None:
    try:
        while True:
            ev = events.get_nowait()
            if isinstance(ev, tuple):
                kind, payload = ev
                if kind == "error":
                    messagebox.showerror("Error", payload)
                else:
                    status.set(
                        f"Done: {payload['processed']} photos, {payload['total_faces']} faces detected"
                    )
            else:
                status.set(f"{ev.stage}: {ev.done}/{ev.total} {ev.current or ev.message}")
                if ev.total:
                    bar["value"] = 100 * ev.done / ev.total
    except queue.Empty:
        pass
    root.after(150, poll)


tk.Button(root, text="Choose folder and run", command=start).pack(padx=10, pady=6)
tk.Button(root, text="Cancel", command=lambda: engine and engine.cancel()).pack()
bar.pack(padx=10, pady=6)
tk.Label(root, textvariable=status).pack(padx=10, pady=6)
poll()
root.mainloop()
