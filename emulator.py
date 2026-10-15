import argparse
import base64
import csv
import getpass
import os
from datetime import datetime


class VirtualFileSystem:
    def __init__(self, csv_path):
        self.fs = {}  # Абсолютный путь -> {'is_dir': bool, 'content': bytes}
        self.current_dir = "/"
        self.vfs_name = os.path.basename(csv_path)
        self._load_from_csv(csv_path)

    def _load_from_csv(self, csv_path):
        # Корневой каталог по умолчанию должен быть всегда
        self.fs["/"] = {'is_dir': True, 'content': b""}
        if not os.path.exists(csv_path):
            return

        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if not row.get('path'):
                    continue
                # Принудительно делаем слеши прямыми (UNIX)
                path = row['path'].strip().replace('\\', '/')
                if path != '/':
                    path = path.rstrip('/')

                is_dir = row['is_dir'].strip().lower() in ('true', '1')
                content_b64 = row.get('content_b64', '').strip()
                if content_b64:
                    content = base64.b64decode(content_b64)
                else:
                    content = b""
                self.fs[path] = {'is_dir': is_dir, 'content': content}

    def _get_absolute_path(self, target_path):
        if not target_path:
            return self.current_dir

        target_path = target_path.strip().replace('\\', '/')

        # Защита от багов Windows
        if target_path.startswith('/'):
            res_path = target_path
        else:
            if self.current_dir == '/':
                res_path = '/' + target_path
            else:
                res_path = self.current_dir + '/' + target_path

        # Нормализуем путь (удаляем дубли слешей и обрабатываем точки)
        parts = res_path.split('/')
        actual_parts = []
        for p in parts:
            if p == '.' or p == '':
                continue
            elif p == '..':
                if actual_parts:
                    actual_parts.pop()
            else:
                actual_parts.append(p)

        final_path = '/' + '/'.join(actual_parts)
        return final_path

    def cd(self, target_path):
        abs_path = self._get_absolute_path(target_path)
        if abs_path in self.fs and self.fs[abs_path]['is_dir']:
            self.current_dir = abs_path
            return None
        return f"cd: no such file or directory: {target_path}"

    def ls(self, target_path=""):
        if target_path:
            abs_path = self._get_absolute_path(target_path)
        else:
            abs_path = self.current_dir

        if abs_path not in self.fs:
            return f"ls: {target_path}: No such file or directory"

        if not self.fs[abs_path]['is_dir']:
            return os.path.basename(abs_path)

        children = set()
        for path in self.fs:
            if path == abs_path:
                continue

            if abs_path == '/':
                if path.startswith('/') and path.count('/') == 1:
                    children.add(path.lstrip('/'))
            else:
                prefix = abs_path + '/'
                if path.startswith(prefix):
                    relative = path[len(prefix):]
                    if '/' not in relative:
                        children.add(relative)

        return "  ".join(sorted(list(children)))

    def mkdir(self, target_path):
        if not target_path:
            return "mkdir: missing operand"

        abs_path = self._get_absolute_path(target_path)
        if abs_path in self.fs:
            return (
                f"mkdir: cannot create directory "
                f"‘{target_path}’: File exists"
            )

        if '/' not in abs_path[1:]:
            parent = '/'
        else:
            parent = abs_path[:abs_path.rfind('/')]
            if not parent:
                parent = '/'

        if parent not in self.fs or not self.fs[parent]['is_dir']:
            return (
                f"mkdir: cannot create directory "
                f"‘{target_path}’: No such file or directory"
            )

        self.fs[abs_path] = {'is_dir': True, 'content': b""}
        return None

    def get_file_content(self, target_path):
        abs_path = self._get_absolute_path(target_path)
        if abs_path in self.fs and not self.fs[abs_path]['is_dir']:
            return self.fs[abs_path]['content']
        return None


class ShellEmulator:
    def __init__(self, vfs_path, log_path, script_path):
        self.vfs = VirtualFileSystem(vfs_path)
        self.log_path = log_path
        self.script_path = script_path
        self.username = getpass.getuser()

        print("=== Shell Emulator Debug Configuration ===")
        print(f"VFS Path:    {os.path.abspath(vfs_path)}")
        print(f"Log Path:    {os.path.abspath(log_path)}")
        scr_p = (
            os.path.abspath(script_path) if script_path else 'None'
        )
        print(f"Script Path: {scr_p}")
        print("==========================================\n")

    def log_event(self, command_line):
        file_exists = os.path.exists(self.log_path)
        with open(
            self.log_path, mode='a', newline='', encoding='utf-8'
        ) as f:
            writer = csv.writer(f)
            if not file_exists or os.path.getsize(self.log_path) == 0:
                writer.writerow(['timestamp', 'username', 'command'])
            writer.writerow([
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                self.username,
                command_line
            ])

    def execute_command(self, cmd_line):
        self.log_event(cmd_line)
        parts = cmd_line.strip().split()
        if not parts:
            return True

        # Исправлено разделение команды и аргумента
        cmd = parts[0]
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "exit":
            return False
        elif cmd == "ls":
            res = self.vfs.ls(arg)
            if res:
                print(res)
        elif cmd == "cd":
            err = self.vfs.cd(arg)
            if err:
                print(err)
        elif cmd == "pwd":
            print(self.vfs.current_dir)
        elif cmd == "who":
            print(self.username)
        elif cmd == "rev":
            if not arg:
                print("rev: missing file operand")
                return True
            content = self.vfs.get_file_content(arg)
            if content is not None:
                text = content.decode('utf-8')
                print(text[::-1])
            else:
                print(f"rev: {arg}: No such file")
        elif cmd == "mkdir":
            if not arg:
                print("mkdir: missing operand")
                return True
            err = self.vfs.mkdir(arg)
            if err:
                print(err)
        else:
            print(f"{cmd}: command not found")
        return True

    def run_script(self):
        if not self.script_path or not os.path.exists(self.script_path):
            return
        with open(self.script_path, 'r', encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                prompt = f"[{self.vfs.vfs_name} {self.vfs.current_dir}]$ "
                print(f"{prompt}{stripped}")
                if not self.execute_command(stripped):
                    return

    def run_repl(self):
        while True:
            try:
                prompt = f"[{self.vfs.vfs_name} {self.vfs.current_dir}]$ "
                cmd_line = input(prompt)
                if not self.execute_command(cmd_line):
                    break
            except (KeyboardInterrupt, EOFError):
                print("\nexit")
                break


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UNIX-like Shell Emulator")
    parser.add_argument("--vfs", required=True, help="Path to VFS CSV file")
    parser.add_argument("--log", required=True, help="Path to log CSV file")
    parser.add_argument(
        "--script", help="Path to startup script", default=None
    )
    args = parser.parse_args()

    emulator = ShellEmulator(
        vfs_path=args.vfs, log_path=args.log, script_path=args.script
    )
    if args.script:
        emulator.run_script()
    emulator.run_repl()