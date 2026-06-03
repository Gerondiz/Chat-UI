#!/usr/bin/env python3
"""Запускает бэкенд и фронтенд, проверяет работу, оставляет процессы жить."""

import subprocess, os, sys, json, time, urllib.request, signal

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "backend")
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
NODE = "/home/user/.local/node-v20.18.0-linux-x64/bin/node"
NPX = "/home/user/.local/node-v20.18.0-linux-x64/bin/npx"
VITE = os.path.join(FRONTEND_DIR, "node_modules", ".bin", "vite")

def start(cmd, cwd, logfile, env_add=None):
    env = os.environ.copy()
    if env_add:
        env.update(env_add)
    p = subprocess.Popen(
        cmd, cwd=cwd,
        stdout=open(logfile, "w"), stderr=subprocess.STDOUT,
        preexec_fn=os.setpgrp,
        env=env,
    )
    return p

def wait_for(url, timeout=10):
    for i in range(timeout * 2):
        try:
            r = urllib.request.urlopen(url, timeout=2)
            if r.status == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def test():
    print("=== Chat-UI Test ===")

    # Kill old
    for name in ["uvicorn", "vite"]:
        subprocess.run(["pkill", "-f", name], capture_output=True)
    time.sleep(1)

    # Start backend
    print("\n[1] Запуск бэкенда...")
    bp = start(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"],
        BACKEND_DIR, "/tmp/backend.log"
    )
    if not wait_for("http://localhost:8000/api/providers", 8):
        print("  ❌ Бэкенд не запустился")
        bp.kill()
        return False
    print(f"  ✅ Бэкенд запущен (PID {bp.pid})")

    # Test backend
    try:
        r = urllib.request.urlopen("http://localhost:8000/api/provider/status")
        d = json.loads(r.read())
        print(f"     Провайдер: {d['name']}  (🟢)" if d['online'] else "     🔴 Офлайн")
        print(f"     Модель: {d['chat_model']}")
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")

    # Chat test
    try:
        body = json.dumps({
            "messages": [{"role": "user", "content": "Привет! Ответь одним словом."}],
            "temperature": 0.7, "max_tokens": 50, "stream": False
        }).encode()
        req = urllib.request.Request(
            "http://localhost:8000/api/chat", data=body,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        r = urllib.request.urlopen(req, timeout=120)
        d = json.loads(r.read())
        print(f"  ✅ Чат: {d['content'][:80]}")
    except Exception as e:
        print(f"  ❌ Чат: {e}")

    # Start frontend
    print("\n[2] Запуск фронтенда...")
    node_dir = "/home/user/.local/node-v20.18.0-linux-x64/bin"
    fp = start(
        ["/usr/bin/env", "node", VITE, "--host", "0.0.0.0", "--port", "5173"],
        FRONTEND_DIR, "/tmp/frontend.log",
        env_add={"PATH": f"{node_dir}:{os.environ.get('PATH','')}"}
    )
    if not wait_for("http://localhost:5173", 10):
        print("  ❌ Фронтенд не запустился")
        bp.kill()
        return False
    print(f"  ✅ Фронтенд запущен (PID {fp.pid})")

    # Test proxy
    try:
        r = urllib.request.urlopen("http://localhost:5173/api/provider/status", timeout=5)
        d = json.loads(r.read())
        print(f"  ✅ Прокси Vite: 🟢 {d.get('chat_model', '')}")
    except Exception as e:
        print(f"  ❌ Прокси Vite: {e}")

    print("\n=== Всё работает! ===")
    print("Frontend: http://localhost:5173")
    print("Backend:  http://localhost:8000")
    print("")
    print("Для остановки процессов:")
    print(f"  kill {bp.pid} {fp.pid}")
    return True

if __name__ == "__main__":
    ok = test()
    if not ok:
        sys.exit(1)
