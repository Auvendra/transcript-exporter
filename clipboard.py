import ctypes
from ctypes import wintypes
import sys

def copy_text(root, text: str) -> None:
    if sys.platform != "win32":
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update_idletasks()
        return

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.CloseClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
    kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalLock.restype = wintypes.LPVOID
    kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
    kernel32.GlobalFree.argtypes = [wintypes.HGLOBAL]

    payload = (text.replace("\r\n", "\n").replace("\n", "\r\n") + "\0").encode("utf-16-le")

    handle = kernel32.GlobalAlloc(0x0002, len(payload))
    if not handle:
        raise OSError("Couldn't allocate clipboard memory.")
    try:
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            raise OSError("Couldn't access clipboard memory.")
        try:
            ctypes.memmove(pointer, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(root.winfo_id()):
            raise OSError("The clipboard is busy.")
        try:
            if not user32.EmptyClipboard() or not user32.SetClipboardData(13, handle):
                raise OSError("Couldn't write to the clipboard.")
            handle = None
        finally:
            user32.CloseClipboard()
    finally:
        if handle:
            kernel32.GlobalFree(handle)