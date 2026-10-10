"""Open an interactive terminal for the user; never put key values in argv."""
import json
from pathlib import Path
import platform
import shlex
import subprocess
import sys


def open_window(name=None, replace=False):
    import key_environment as keys
    if name is not None and name not in keys.BASIC:
        raise ValueError('UNSUPPORTED_KEY_NAME')
    if replace and not name:
        raise ValueError('REPLACE_REQUIRES_NAME')
    if not replace and not keys.check()['missing']:
        return {**keys.check(), 'window_opened': False}
    command = [sys.executable, '-X', 'utf8', '-B', str(Path(__file__).with_name('key_input.py').resolve())]
    if name:
        command += ['--name', name]
    if replace:
        command += ['--replace']
    try:
        if platform.system() == 'Windows':
            child = subprocess.Popen(command, creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0x10))
            pid = child.pid
        elif platform.system() == 'Darwin':
            line = shlex.join(command)
            script = 'tell application "Terminal"\nactivate\ndo script ' + json.dumps(line) + '\nend tell'
            subprocess.run(['osascript', '-e', script], check=True, capture_output=True)
            pid = None
        else:
            raise ValueError('AUTOMATIC_TERMINAL_UNSUPPORTED')
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError('INPUT_WINDOW_OPEN_FAILED') from exc
    return {'status': 'INPUT_WINDOW_OPENED', 'window_opened': True, 'pid': pid,
            'next_action': 'After user input, run key-env check, then resume the report job.',
            'live_call': False}
