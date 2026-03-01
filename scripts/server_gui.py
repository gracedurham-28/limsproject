#!/usr/bin/env python3
"""
Simple Tkinter GUI to start/stop the Django dev server without typing terminal commands.
Run with the project venv Python:

  limsenv/bin/python3 scripts/server_gui.py

Or make executable and double-click (macOS) if Python files are associated with the interpreter.

The GUI calls the existing manage_server.py script (which writes .runserver.pid and logs to logs/server.log).
"""
import os
import sys
import threading
import subprocess
import time
import tkinter as tk
from tkinter import scrolledtext, messagebox

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MANAGE_SCRIPT = os.path.join(PROJECT_ROOT, 'scripts', 'manage_server.py')
LOGFILE = os.path.join(PROJECT_ROOT, 'logs', 'server.log')
PIDFILE = os.path.join(PROJECT_ROOT, '.runserver.pid')
# Prefer project virtualenv python if present, otherwise use the interpreter running this script
_venv_py = os.path.join(PROJECT_ROOT, 'limsenv', 'bin', 'python3')
if os.path.exists(_venv_py) and os.access(_venv_py, os.X_OK):
    # If this process was launched with a different Python, re-exec with the venv python
    if os.path.abspath(sys.executable) != os.path.abspath(_venv_py):
        try:
            # execv requires the first argv element to be the program name (the python binary)
            # and the script path must be passed as the first argument to the interpreter.
            os.execv(_venv_py, [_venv_py, os.path.abspath(__file__)] + sys.argv[1:])
        except Exception:
            # Fall back to using sys.executable if re-exec fails
            PY = sys.executable
        else:
            # os.execv replaces the process; code below won't run in the parent
            PY = _venv_py
    else:
        PY = _venv_py
else:
    PY = sys.executable


def _load_env():
    """Return an environment dict loaded from the current process env plus .env file if present."""
    env = os.environ.copy()
    envfile = os.path.join(PROJECT_ROOT, '.env')
    if os.path.exists(envfile):
        try:
            with open(envfile, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
        except Exception:
            pass
    return env


def run_manage(cmd_args, show_output=False):
    cmd = [PY, MANAGE_SCRIPT] + cmd_args
    try:
        # run with environment that includes .env values so Django settings are available
        env = _load_env()
        subprocess.run(cmd, cwd=PROJECT_ROOT, env=env)
    except Exception as e:
        messagebox.showerror('Error', f'Failed to run: {cmd}\n{e}')


class ServerGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('LIMS: Server Control')
        self.geometry('700x500')

        frm = tk.Frame(self)
        frm.pack(fill='x', padx=8, pady=8)

        self.start_btn = tk.Button(frm, text='Start Server', command=self.start_server)
        self.start_btn.pack(side='left', padx=4)

        self.stop_btn = tk.Button(frm, text='Stop Server', command=self.stop_server)
        self.stop_btn.pack(side='left', padx=4)

        self.status_btn = tk.Button(frm, text='Status', command=self.show_status)
        self.status_btn.pack(side='left', padx=4)

        self.collect_var = tk.BooleanVar(value=True)
        self.collect_cb = tk.Checkbutton(frm, text='Run collectstatic', variable=self.collect_var)
        self.collect_cb.pack(side='left', padx=8)

        self.log_area = scrolledtext.ScrolledText(self, wrap='none', state='disabled')
        self.log_area.pack(fill='both', expand=True, padx=8, pady=(0,8))

        self._stop_tail = threading.Event()
        self._tail_thread = threading.Thread(target=self._tail_logs, daemon=True)
        self._tail_thread.start()

    def start_server(self):
        self._append_log('Starting server...')
        args = ['start']
        if self.collect_var.get():
            args.append('--collectstatic')
        threading.Thread(target=run_manage, args=(args,), daemon=True).start()
        # wait a second then refresh status
        self.after(1000, self.show_status)

    def stop_server(self):
        if not os.path.exists(PIDFILE):
            messagebox.showinfo('Info', 'No PID file found — server may not be running')
            return
        if not messagebox.askyesno('Confirm', 'Stop the server?'):
            return
        self._append_log('Stopping server...')
        threading.Thread(target=run_manage, args=(['stop'],), daemon=True).start()
        self.after(1000, self.show_status)

    def show_status(self):
        try:
            result = subprocess.run([PY, MANAGE_SCRIPT, 'status'], cwd=PROJECT_ROOT, capture_output=True, text=True)
            out = result.stdout.strip() or result.stderr.strip()
            self._append_log(f'Status: {out}')
            messagebox.showinfo('Status', out)
        except Exception as e:
            messagebox.showerror('Error', str(e))

    def _append_log(self, text):
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        self.log_area.configure(state='normal')
        self.log_area.insert('end', f'[{ts}] {text}\n')
        self.log_area.configure(state='disabled')
        self.log_area.yview_moveto(1.0)

    def _tail_logs(self):
        # Simple file tailing
        last_size = 0
        while not self._stop_tail.is_set():
            try:
                if os.path.exists(LOGFILE):
                    size = os.path.getsize(LOGFILE)
                    if size < last_size:
                        last_size = 0
                    if size > last_size:
                        with open(LOGFILE, 'r', encoding='utf-8', errors='replace') as f:
                            f.seek(last_size)
                            data = f.read()
                            if data:
                                self._append_log(data.rstrip())
                        last_size = size
                time.sleep(1.0)
            except Exception:
                time.sleep(1.0)

    def on_close(self):
        self._stop_tail.set()
        self.destroy()


def main():
    app = ServerGUI()
    app.protocol('WM_DELETE_WINDOW', app.on_close)
    app.mainloop()


if __name__ == '__main__':
    main()
