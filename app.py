from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from clipboard import copy_text
from transcript import ExportError, TranscriptResult, extract_video_id, fetch_transcript

BG = "#111318"
SURFACE = "#1b1e26"
CONTROL = "#2b3040"
CONTROL_HOVER = "#383f52"
BORDER = "#3c4354"
INK = "#edf0f7"
MUTED = "#a7b0c2"
DISABLED_INK = "#929db2"
ACCENT = "#6253ce"
ACCENT_HOVER = "#695bd5"
ACCENT_INK = "#b2a7ff"
SELECTION = "#51468c"
STATUS_COLORS = {
    "info": ("#202638", INK),
    "success": ("#17392e", "#9ce5bd"),
    "error": ("#3b222b", "#ffb2bd"),
}

class TranscriptApp:
    def __init__(self, root: tk.Tk, fetcher=fetch_transcript, copier=copy_text):
        self.root = root
        self.fetcher = fetcher
        self.copier = copier
        self.results = queue.Queue()
        self.result: TranscriptResult | None = None
        self.generation = 0
        self.active_video = None
        self.busy = False
        self.closed = False
        self.paste_job = None
        self.copy_job = None
        self.url = tk.StringVar()
        self.timestamps = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready when you are. Paste a video link to begin.")
        self.metadata = tk.StringVar(value="Your full transcript will appear here.")
        self.root.title("YouTube Transcript Exporter")
        self.root.geometry("920x720")
        self.root.minsize(740, 580)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self._build()
        self._set_dark_titlebar()
        self.url.trace_add("write", self._url_changed)
        self.poll_job = self.root.after(100, self._poll)

    def _build(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TCheckbutton", background=BG, foreground=MUTED,
                        font=("Segoe UI", 10), indicatorbackground=SURFACE,
                        indicatorforeground=INK, bordercolor=BORDER, focuscolor=ACCENT_INK)
        style.map("TCheckbutton", background=[("active", BG)],
                  foreground=[("disabled", DISABLED_INK), ("active", INK)],
                  indicatorbackground=[("disabled", CONTROL), ("selected", ACCENT),
                                       ("active", CONTROL_HOVER)],
                  bordercolor=[("focus", ACCENT_INK), ("active", ACCENT_INK)])
        style.configure("TButton", font=("Segoe UI", 10), padding=(14, 10),
                        background=CONTROL, foreground=INK, borderwidth=1,
                        bordercolor=CONTROL, lightcolor=CONTROL, darkcolor=CONTROL,
                        focuscolor=ACCENT_INK, relief="flat")
        style.map("TButton", background=[("disabled", CONTROL), ("pressed", SURFACE),
                                         ("active", CONTROL_HOVER)],
                  foreground=[("disabled", DISABLED_INK)],
                  bordercolor=[("focus", ACCENT_INK)])
        style.configure("Accent.TButton", background=ACCENT, foreground=INK,
                        bordercolor=ACCENT, lightcolor=ACCENT, darkcolor=ACCENT,
                        font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("disabled", CONTROL), ("pressed", "#5749bd"),
                                                ("active", ACCENT_HOVER)],
                  bordercolor=[("disabled", CONTROL), ("focus", ACCENT_INK),
                               ("active", ACCENT_HOVER)])
        style.configure("TEntry", padding=12, font=("Segoe UI", 12),
                        fieldbackground=SURFACE, foreground=INK, insertcolor=INK,
                        selectbackground=SELECTION, selectforeground=INK,
                        bordercolor=BORDER, lightcolor=SURFACE, darkcolor=SURFACE)
        style.map("TEntry", bordercolor=[("focus", ACCENT_INK)],
                  lightcolor=[("focus", ACCENT_INK)], darkcolor=[("focus", ACCENT_INK)])
        style.configure("Vertical.TScrollbar", background=CONTROL, troughcolor=SURFACE,
                        bordercolor=SURFACE, lightcolor=CONTROL, darkcolor=CONTROL,
                        arrowcolor=MUTED, gripcount=0)
        style.map("Vertical.TScrollbar", background=[("pressed", ACCENT), ("active", CONTROL_HOVER)],
                  arrowcolor=[("active", INK)])
        style.configure("Horizontal.TProgressbar", background=ACCENT, troughcolor=CONTROL,
                        lightcolor=ACCENT, darkcolor=ACCENT, bordercolor=BG, borderwidth=0)

        shell = ttk.Frame(self.root, padding=(30, 26, 30, 18))
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(6, weight=1)
        tk.Label(shell, text="YOUTUBE  /  CLIPBOARD", bg=BG, fg=ACCENT_INK,
                 font=("Segoe UI Semibold", 10)).grid(row=0, column=0, sticky="w")
        tk.Label(shell, text="Transcript Exporter", bg=BG, fg=INK,
                 font=("Segoe UI Semibold", 27)).grid(row=1, column=0, sticky="w", pady=(6, 4))
        tk.Label(shell, text="Paste a link. Get the full transcript, ready to paste anywhere.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 11)).grid(row=2, column=0, sticky="w", pady=(0, 23))

        input_panel = ttk.Frame(shell)
        input_panel.grid(row=3, column=0, sticky="ew")
        input_panel.columnconfigure(0, weight=1)
        self.entry = ttk.Entry(input_panel, textvariable=self.url, font=("Segoe UI", 12))
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 9))
        self.entry.bind("<Return>", lambda event: self.start_fetch())
        self.entry.bind("<Control-a>", self._select_url)
        ttk.Button(input_panel, text="Paste link", command=self.paste_link,
                   style="Accent.TButton").grid(row=0, column=1, padx=(0, 8))
        self.fetch_button = ttk.Button(input_panel, text="Fetch again", command=self.start_fetch)
        self.fetch_button.grid(row=0, column=2)
        self.entry.focus_set()

        options = ttk.Frame(shell)
        options.grid(row=4, column=0, sticky="ew", pady=(11, 14))
        ttk.Checkbutton(options, text="Include timestamps", variable=self.timestamps,
                        command=self._format_changed).pack(side="left")
        tk.Label(options, text="Pasted links fetch and copy automatically", bg=BG,
                 fg=MUTED, font=("Segoe UI", 9)).pack(side="right")

        self.status_label = tk.Label(shell, textvariable=self.status, bg=STATUS_COLORS["info"][0], fg=INK,
                                     anchor="w", justify="left", padx=14, pady=12,
                                     font=("Segoe UI", 10), wraplength=780)
        self.status_label.grid(row=5, column=0, sticky="ew", pady=(0, 14))
        shell.bind("<Configure>", lambda e: self.status_label.configure(wraplength=max(300, e.width - 90)))

        preview_card = tk.Frame(shell, bg=SURFACE, highlightbackground=BORDER,
                                highlightcolor=ACCENT_INK, highlightthickness=1)
        preview_card.grid(row=6, column=0, sticky="nsew")
        preview_card.columnconfigure(0, weight=1)
        preview_card.rowconfigure(1, weight=1)
        preview_header = tk.Frame(preview_card, bg=SURFACE)
        preview_header.grid(row=0, column=0, columnspan=2, sticky="ew", padx=18, pady=(15, 10))
        tk.Label(preview_header, text="TRANSCRIPT", bg=SURFACE, fg=INK,
                 font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Label(preview_header, textvariable=self.metadata, bg=SURFACE, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 0))
        self.preview = tk.Text(preview_card, wrap="word", font=("Segoe UI", 11),
                               bg=SURFACE, fg=INK, insertbackground=INK,
                               borderwidth=0, highlightthickness=0, padx=18, pady=10,
                               spacing1=2, spacing3=6, selectbackground=SELECTION,
                               selectforeground=INK, inactiveselectbackground=SELECTION, state="disabled")
        self.preview.grid(row=1, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(preview_card, command=self.preview.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 4), pady=(0, 8))
        self.preview.configure(yscrollcommand=scrollbar.set)

        self.progress = ttk.Progressbar(shell, mode="indeterminate")
        self.progress.grid(row=7, column=0, sticky="ew", pady=(12, 12))
        actions = ttk.Frame(shell)
        actions.grid(row=8, column=0, sticky="ew")
        self.copy_button = ttk.Button(actions, text="Copy transcript", command=self.copy_current,
                                      style="Accent.TButton", state="disabled")
        self.copy_button.pack(side="right")
        self.save_button = ttk.Button(actions, text="Save .txt", command=self.save_text, state="disabled")
        self.save_button.pack(side="right", padx=(0, 8))
        tk.Label(actions, text="No API key needed. Uses available video captions.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="left")
        self.root.bind("<Control-Return>", lambda event: self.start_fetch())

    def _set_dark_titlebar(self):
        if self.root.tk.call("tk", "windowingsystem") != "win32":
            return
        import ctypes
        from ctypes import wintypes

        try:
            self.root.update_idletasks()
            user32 = ctypes.WinDLL("user32")
            user32.GetParent.argtypes = [wintypes.HWND]
            user32.GetParent.restype = wintypes.HWND
            hwnd = user32.GetParent(self.root.winfo_id())
            dwm = ctypes.WinDLL("dwmapi")
            dwm.DwmSetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD,
                                                 ctypes.c_void_p, wintypes.DWORD]
            dwm.DwmSetWindowAttribute.restype = ctypes.c_long
            enabled = wintypes.BOOL(True)
            for attribute in (20, 19):
                if dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(enabled),
                                             ctypes.sizeof(enabled)) == 0:
                    break
        except (OSError, AttributeError):
            pass

    def _select_url(self, event):
        self.entry.selection_range(0, "end")
        return "break"

    def _set_status(self, message, kind="info"):
        bg, fg = STATUS_COLORS[kind]
        self.status.set(message)
        self.status_label.configure(bg=bg, fg=fg)

    def _cancel_copy(self):
        if self.copy_job is not None:
            self.root.after_cancel(self.copy_job)
            self.copy_job = None

    def _url_changed(self, *_):
        if self.paste_job is not None:
            self.root.after_cancel(self.paste_job)
        self.generation += 1
        self._cancel_copy()
        self.busy = False
        self.active_video = None
        self.result = None
        self.copy_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self._show_text("")
        self.metadata.set("Your full transcript will appear here.")
        self.progress.stop()
        self.paste_job = self.root.after(450, self._auto_fetch)

    def _auto_fetch(self):
        self.paste_job = None
        try:
            extract_video_id(self.url.get())
        except ExportError:
            if self.url.get().strip():
                self._set_status("Paste a complete YouTube video link, or press Enter to check it.")
            else:
                self._set_status("Ready when you are. Paste a video link to begin.")
            return
        self.start_fetch()

    def paste_link(self):
        try:
            value = self.root.clipboard_get().strip()
        except tk.TclError:
            self._set_status("The clipboard has no text. Copy a YouTube link first.", "error")
            return
        self.url.set(value)
        self.start_fetch()

    def start_fetch(self):
        if self.paste_job is not None:
            self.root.after_cancel(self.paste_job)
            self.paste_job = None
        try:
            video_id = extract_video_id(self.url.get())
        except ExportError as error:
            self._set_status(str(error), "error")
            return
        if self.busy and self.active_video == video_id:
            return
        self.generation += 1
        generation = self.generation
        self._cancel_copy()
        self.busy = True
        self.active_video = video_id
        self.result = None
        self.copy_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self._show_text("")
        self.metadata.set("Fetching all available caption segments...")
        self._set_status("Fetching the full transcript from YouTube...")
        self.progress.start(12)

        def work():
            try:
                self.results.put((generation, self.fetcher(video_id), None))
            except ExportError as error:
                self.results.put((generation, None, str(error)))
            except Exception:
                self.results.put((generation, None, "An unexpected error occurred. Close and reopen the app, then try again."))

        threading.Thread(target=work, daemon=True).start()

    def _poll(self):
        if self.closed:
            return
        while True:
            try:
                generation, result, error = self.results.get_nowait()
            except queue.Empty:
                break
            if generation != self.generation:
                continue
            self.busy = False
            self.progress.stop()
            if error:
                self.metadata.set("No transcript retrieved. Try another link or fetch again.")
                self._set_status(error, "error")
            else:
                self.result = result
                self._render_result()
                self.copy_current()
        self.poll_job = self.root.after(100, self._poll)

    def _show_text(self, text):
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _render_result(self):
        text = self.result.text(self.timestamps.get())
        self._show_text(text)
        kind = "Auto-generated captions" if self.result.is_generated else "Creator captions"
        self.metadata.set(f"{self.result.language}  /  {kind}  /  {len(self.result.text().split()):,} words")
        self.copy_button.configure(state="normal")
        self.save_button.configure(state="normal")

    def _format_changed(self):
        self._cancel_copy()
        if self.result is not None:
            self._render_result()
            self.copy_current()

    def copy_current(self, attempt=0):
        self._cancel_copy()
        if self.result is None:
            return
        try:
            self.copier(self.root, self.result.text(self.timestamps.get()))
            self._set_status("Copied! The full transcript is in your clipboard. Paste it anywhere with Ctrl+V.", "success")
        except (OSError, tk.TclError):
            if attempt < 4:
                self.copy_job = self.root.after(150, lambda: self.copy_current(attempt + 1))
            else:
                self._set_status("Transcript ready, but the clipboard is busy. Click Copy transcript to retry.", "error")

    def save_text(self):
        if self.result is None:
            return
        filename = filedialog.asksaveasfilename(
            parent=self.root, title="Save transcript", defaultextension=".txt",
            initialfile=f"transcript-{self.result.video_id}.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if filename:
            try:
                Path(filename).write_text(self.result.text(self.timestamps.get()), encoding="utf-8")
                self._set_status(f"Saved to {filename}", "success")
            except OSError:
                self._set_status("Couldn't save the file. Choose a writable folder and try again.", "error")

    def close(self):
        self.closed = True
        self.generation += 1
        self._cancel_copy()
        if self.paste_job is not None:
            self.root.after_cancel(self.paste_job)
        self.root.after_cancel(self.poll_job)
        self.root.destroy()

def main():
    root = tk.Tk()
    TranscriptApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()