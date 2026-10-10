"""Local interactive input. Only masked progress reaches the terminal."""
import os
import sys


def masked_input(prompt):
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise ValueError('INTERACTIVE_SECURE_TERMINAL_REQUIRED')
    restore = None
    if os.name == 'nt':
        import msvcrt
        read = msvcrt.getwch
    else:
        import termios
        import tty
        fd = sys.stdin.fileno()
        prior = termios.tcgetattr(fd)
        tty.setraw(fd)
        read = lambda: sys.stdin.read(1)
        restore = lambda: termios.tcsetattr(fd, termios.TCSADRAIN, prior)
    chars = []
    width = 0
    try:
        while True:
            display = prompt + ('*' * min(len(chars), 24)) + f'  [{len(chars)} characters]'
            sys.stdout.write('\r' + display.ljust(width))
            sys.stdout.flush()
            width = max(width, len(display))
            c = read()
            if c in ('\r', '\n'):
                sys.stdout.write('\r\nInput received.\r\n')
                return ''.join(chars).strip()
            if c == '\x03':
                raise KeyboardInterrupt
            if c in ('', '\x04', '\x1a'):
                raise EOFError
            if c in ('\b', '\x7f'):
                chars = chars[:-1]
            elif c in ('\x00', '\xe0') and os.name == 'nt':
                read()  # Windows extended key, never part of a key.
            elif c.isprintable() and len(chars) < 8192:
                chars.append(c)
    finally:
        if restore:
            restore()


def main():
    import key_environment as keys
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', choices=keys.BASIC)
    parser.add_argument('--replace', action='store_true')
    args = parser.parse_args()
    print('EZIWORK API setup | Paste a key, then press Enter. Ctrl+C cancels.')
    try:
        result = keys.setup(args.name, replace=args.replace, reader=masked_input)
        print('Saved: ' + ', '.join(result.get('saved_names', [])))
        print('Missing: ' + ', '.join(result.get('missing', [])))
        print('Setup cancelled.' if result.get('input_cancelled') else 'Return to Codex to continue.')
    except (OSError, ValueError):
        print('Setup could not finish. Check storage permissions or input format; existing saved keys are retained.')
    try:
        input('Press Enter to close this window. ')
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == '__main__':
    main()
