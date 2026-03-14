"""File dialog API router - open native file/folder selection dialogs."""

from __future__ import annotations

import logging
import platform
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()


class FolderDialogRequest(BaseModel):
    """Request for folder selection dialog."""
    title: str = "选择文件夹"
    initial_dir: Optional[str] = None


class FolderDialogResponse(BaseModel):
    """Response with selected folder path."""
    path: Optional[str] = None
    cancelled: bool = False


@router.post("/select-folder")
async def select_folder(req: FolderDialogRequest):
    """Open native folder selection dialog.
    
    Args:
        req: Dialog configuration
        
    Returns:
        Selected folder path or cancelled status
    """
    try:
        # Windows: use tkinter (built-in, no extra deps)
        if platform.system() == "Windows":
            import tkinter as tk
            from tkinter import filedialog
            
            # Create hidden root window
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            
            # Open folder dialog
            result = filedialog.askdirectory(
                title=req.title,
                initialdir=req.initial_dir or None,
            )
            
            root.destroy()
            
            if result:
                return {"ok": True, "data": {"path": result, "cancelled": False}}
            else:
                return {"ok": True, "data": {"path": None, "cancelled": True}}
        
        # macOS: use osascript
        elif platform.system() == "Darwin":
            import subprocess
            
            script = f'''
            tell application "Finder"
                set selectedFolder to choose folder with prompt "{req.title}"
                return POSIX path of selectedFolder
            end tell
            '''
            
            try:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                
                if result.returncode == 0:
                    path = result.stdout.strip()
                    return {"ok": True, "data": {"path": path, "cancelled": False}}
                else:
                    return {"ok": True, "data": {"path": None, "cancelled": True}}
            except subprocess.TimeoutExpired:
                return {"ok": True, "data": {"path": None, "cancelled": True}}
        
        # Linux: try zenity or kdialog
        else:
            import subprocess
            import shutil
            
            if shutil.which("zenity"):
                try:
                    result = subprocess.run(
                        ["zenity", "--file-selection", "--directory", f"--title={req.title}"],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    
                    if result.returncode == 0:
                        path = result.stdout.strip()
                        return {"ok": True, "data": {"path": path, "cancelled": False}}
                    else:
                        return {"ok": True, "data": {"path": None, "cancelled": True}}
                except subprocess.TimeoutExpired:
                    return {"ok": True, "data": {"path": None, "cancelled": True}}
            
            elif shutil.which("kdialog"):
                try:
                    result = subprocess.run(
                        ["kdialog", "--getexistingdirectory", req.initial_dir or "."],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    
                    if result.returncode == 0:
                        path = result.stdout.strip()
                        return {"ok": True, "data": {"path": path, "cancelled": False}}
                    else:
                        return {"ok": True, "data": {"path": None, "cancelled": True}}
                except subprocess.TimeoutExpired:
                    return {"ok": True, "data": {"path": None, "cancelled": True}}
            
            else:
                return {
                    "ok": False,
                    "message": "No file dialog available. Please install zenity or kdialog.",
                }
                
    except Exception as e:
        logger.exception(f"Failed to open folder dialog: {e}")
        return {"ok": False, "message": str(e)}


@router.post("/select-file")
async def select_file(title: str = "选择文件", initial_dir: Optional[str] = None, file_types: Optional[str] = None):
    """Open native file selection dialog.
    
    Args:
        title: Dialog title
        initial_dir: Initial directory
        file_types: File type filter (e.g., "*.pdf;*.docx")
        
    Returns:
        Selected file path or cancelled status
    """
    try:
        if platform.system() == "Windows":
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            
            # Build filetypes
            filetypes = []
            if file_types:
                types = file_types.split(";")
                filetypes = [("Supported Files", types)]
            filetypes.append(("All Files", "*.*"))
            
            result = filedialog.askopenfilename(
                title=title,
                initialdir=initial_dir or None,
                filetypes=filetypes,
            )
            
            root.destroy()
            
            if result:
                return {"ok": True, "data": {"path": result, "cancelled": False}}
            else:
                return {"ok": True, "data": {"path": None, "cancelled": True}}
        
        elif platform.system() == "Darwin":
            import subprocess
            
            script = f'''
            tell application "Finder"
                set selectedFile to choose file with prompt "{title}"
                return POSIX path of selectedFile
            end tell
            '''
            
            try:
                result = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                
                if result.returncode == 0:
                    path = result.stdout.strip()
                    return {"ok": True, "data": {"path": path, "cancelled": False}}
                else:
                    return {"ok": True, "data": {"path": None, "cancelled": True}}
            except subprocess.TimeoutExpired:
                return {"ok": True, "data": {"path": None, "cancelled": True}}
        
        else:
            # Linux with zenity
            import subprocess
            import shutil
            
            if shutil.which("zenity"):
                cmd = ["zenity", "--file-selection", f"--title={title}"]
                if file_types:
                    cmd.extend(["--file-filter", f"Supported Files | {file_types}"])
                
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )
                    
                    if result.returncode == 0:
                        path = result.stdout.strip()
                        return {"ok": True, "data": {"path": path, "cancelled": False}}
                    else:
                        return {"ok": True, "data": {"path": None, "cancelled": True}}
                except subprocess.TimeoutExpired:
                    return {"ok": True, "data": {"path": None, "cancelled": True}}
            
            return {"ok": False, "message": "No file dialog available"}
            
    except Exception as e:
        logger.exception(f"Failed to open file dialog: {e}")
        return {"ok": False, "message": str(e)}
