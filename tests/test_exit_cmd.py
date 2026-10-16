import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import subprocess, sys

p = subprocess.run(
    [sys.executable, "main.py"],
    input="/exit\n", capture_output=True, text=True,
    encoding="utf-8", timeout=30, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
)
assert p.returncode == 0, p.returncode
assert "[app]" in (p.stdout or "") or p.returncode == 0
print("EXIT CMD TEST OK, code =", p.returncode)
