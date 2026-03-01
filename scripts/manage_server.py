#!/usr/bin/env python3
"""
Simple Python start/stop/status utility for the Django development server.
Run from the project root (or the script will locate the project root).

Usage:
  python scripts/manage_server.py start [--collectstatic]
  python scripts/manage_server.py stop
  python scripts/manage_server.py status

This starts the server with the same Python interpreter that runs this script
(so activate your virtualenv first if needed).

It writes .runserver.pid and logs to logs/server.log.
"""

import argparse
import os
import subprocess
import sys
import time
import signal

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PIDFILE = os.path.join(PROJECT_ROOT, '.runserver.pid')
LOGFILE = os.path.join(PROJECT_ROOT, 'logs', 'server.log')
MANAGE_PY = os.path.join(PROJECT_ROOT, 'manage.py')


def is_pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True


def _load_env():
    """Return environment dict with values from .env (if present) merged over os.environ."""
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


def _ensure_debug_or_whitenoise(env: dict):
    """If whitenoise is not importable in this interpreter and DJANGO_DEBUG is not set,
    set DJANGO_DEBUG='1' so the runserver will serve static files for local dev.
    """
    if env.get('DJANGO_DEBUG'):
        return env
    try:
        import whitenoise  # type: ignore
    except Exception:
        env['DJANGO_DEBUG'] = '1'
    return env


def start(collectstatic: bool = False) -> None:
    if os.path.exists(PIDFILE):
        try:
            with open(PIDFILE, 'r') as f:
                pid = int(f.read().strip())
        except Exception:
            pid = None
        else:
            if pid and is_pid_running(pid):
                print(f"Server already running with pid {pid}")
                return
            else:
                # stale pidfile
                try:
                    os.remove(PIDFILE)
                except Exception:
                    pass

    os.makedirs(os.path.dirname(LOGFILE), exist_ok=True)

    env = _load_env()
    env = _ensure_debug_or_whitenoise(env)

    if collectstatic:
        print('Running collectstatic...')
        ret = subprocess.run([sys.executable, MANAGE_PY, 'collectstatic', '--noinput'], cwd=PROJECT_ROOT, env=env)
        if ret.returncode != 0:
            print('collectstatic failed, aborting start')
            return

    # Start the dev server using the same Python interpreter
    cmd = [sys.executable, MANAGE_PY, 'runserver', '0.0.0.0:8000']
    print('Starting server:', ' '.join(cmd))

    logfile = open(LOGFILE, 'ab')
    proc = subprocess.Popen(cmd, cwd=PROJECT_ROOT, stdout=logfile, stderr=subprocess.STDOUT, env=env)

    with open(PIDFILE, 'w') as f:
        f.write(str(proc.pid))

    print(f'Server started (pid {proc.pid}). Logs: {LOGFILE}')


def stop() -> None:
    if not os.path.exists(PIDFILE):
        print('PID file not found; server may not be running')
        return

    try:
        with open(PIDFILE, 'r') as f:
            pid = int(f.read().strip())
    except Exception:
        print('Failed to read pidfile; removing it')
        try:
            os.remove(PIDFILE)
        except Exception:
            pass
        return

    if not is_pid_running(pid):
        print(f'No process with pid {pid} running; removing pidfile')
        try:
            os.remove(PIDFILE)
        except Exception:
            pass
        return

    print(f'Stopping server pid {pid}...')
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception as e:
        print('Error sending SIGTERM:', e)

    # wait up to 5 seconds
    for _ in range(10):
        if not is_pid_running(pid):
            break
        time.sleep(0.5)

    if is_pid_running(pid):
        print('Process did not exit after SIGTERM, sending SIGKILL')
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception as e:
            print('Error sending SIGKILL:', e)

    if os.path.exists(PIDFILE):
        try:
            os.remove(PIDFILE)
        except Exception:
            pass

    print('Server stopped')


def status() -> None:
    if not os.path.exists(PIDFILE):
        print('Not running (no pidfile)')
        return
    try:
        with open(PIDFILE, 'r') as f:
            pid = int(f.read().strip())
    except Exception:
        print('Invalid pidfile')
        return
    if is_pid_running(pid):
        print(f'Running (pid {pid})')
    else:
        print('Stale pidfile found; process not running')


def main(argv=None):
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='cmd')
    p_start = sub.add_parser('start')
    p_start.add_argument('--collectstatic', action='store_true', help='Run collectstatic before starting')
    sub.add_parser('stop')
    sub.add_parser('status')

    args = parser.parse_args(argv)

    if args.cmd == 'start':
        start(getattr(args, 'collectstatic', False))
    elif args.cmd == 'stop':
        stop()
    elif args.cmd == 'status':
        status()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
