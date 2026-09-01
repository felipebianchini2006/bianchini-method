from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/_shared/scripts"


class WindowsPortabilityScenarios(unittest.TestCase):
    def test_packaged_python_entrypoint_loads_without_fcntl(self) -> None:
        simulation = textwrap.dedent(
            f"""
            import builtins
            import subprocess
            import sys
            import types

            original_import = builtins.__import__

            def windows_import(name, *args, **kwargs):
                if name == "fcntl":
                    raise ModuleNotFoundError("No module named 'fcntl'")
                return original_import(name, *args, **kwargs)

            builtins.__import__ = windows_import
            sys.modules["msvcrt"] = types.SimpleNamespace(
                LK_NBLCK=1,
                LK_UNLCK=0,
                locking=lambda descriptor, mode, size: None,
            )
            sys.path.insert(0, {str(SCRIPTS)!r})
            import bm
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", simulation],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr or completed.stdout,
        )

    def test_native_backend_rejects_a_concurrent_process(self) -> None:
        sys.path.insert(0, str(SCRIPTS))
        from bm_file_lock import lock_exclusive_nonblocking, unlock

        child = textwrap.dedent(
            f"""
            import os
            import sys

            sys.path.insert(0, {str(SCRIPTS)!r})
            from bm_file_lock import lock_exclusive_nonblocking, unlock

            descriptor = os.open(sys.argv[1], os.O_RDWR | os.O_CREAT, 0o600)
            try:
                try:
                    lock_exclusive_nonblocking(descriptor)
                except BlockingIOError:
                    raise SystemExit(0)
                else:
                    unlock(descriptor)
                    raise SystemExit(1)
            finally:
                os.close(descriptor)
            """
        )
        with tempfile.TemporaryDirectory() as temporary:
            lock_path = Path(temporary) / "native.lock"
            descriptor = os.open(
                lock_path,
                os.O_RDWR | os.O_CREAT,
                0o600,
            )
            try:
                lock_exclusive_nonblocking(descriptor)
                completed = subprocess.run(
                    [sys.executable, "-c", child, str(lock_path)],
                    cwd=ROOT,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    completed.stderr or completed.stdout,
                )
            finally:
                unlock(descriptor)
                os.close(descriptor)

    def test_windows_backend_locks_and_unlocks_the_same_byte(self) -> None:
        simulation = textwrap.dedent(
            f"""
            import builtins
            import os
            import sys
            import tempfile
            import types

            calls = []
            original_import = builtins.__import__

            def windows_import(name, *args, **kwargs):
                if name == "fcntl":
                    raise ModuleNotFoundError("No module named 'fcntl'")
                return original_import(name, *args, **kwargs)

            builtins.__import__ = windows_import
            sys.modules["msvcrt"] = types.SimpleNamespace(
                LK_NBLCK=1,
                LK_UNLCK=0,
                locking=lambda descriptor, mode, size: calls.append((mode, size)),
            )
            sys.path.insert(0, {str(SCRIPTS)!r})

            import bm_file_lock

            with tempfile.TemporaryDirectory() as temporary:
                path = os.path.join(temporary, "transition.lock")
                descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
                try:
                    bm_file_lock.lock_exclusive_nonblocking(descriptor)
                    bm_file_lock.unlock(descriptor)
                    assert os.fstat(descriptor).st_size == 1
                finally:
                    os.close(descriptor)

            assert calls == [(1, 1), (0, 1)], calls
            """
        )
        completed = subprocess.run(
            [sys.executable, "-c", simulation],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            completed.stderr or completed.stdout,
        )


if __name__ == "__main__":
    unittest.main()
