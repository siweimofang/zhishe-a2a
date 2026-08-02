"""后台启动 uvicorn — 绕开 PowerShell GBK 中文路径问题"""
import subprocess
import os
import sys
import time

EXE = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a\.venv\Scripts\python.exe"
WORKDIR = r"D:\知设Agent生态\千问AI Agent\zhishe-a2a"
LOGDIR = os.path.join(WORKDIR, "logs")

os.makedirs(LOGDIR, exist_ok=True)

out_log = os.path.join(LOGDIR, "uvicorn.out.log")
err_log = os.path.join(LOGDIR, "uvicorn.err.log")

# 用 CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS 标志让子进程脱离父进程
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200

flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

proc = subprocess.Popen(
    [EXE, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765"],
    cwd=WORKDIR,
    stdout=open(out_log, "ab"),
    stderr=open(err_log, "ab"),
    creationflags=flags,
    close_fds=True,
)

print(f"Started uvicorn PID: {proc.pid}")
print(f"Logs: {out_log}")

# 等 4 秒确认启动
time.sleep(4)

# 验证进程是否还活着
if proc.poll() is None:
    print(f"✅ uvicorn running (PID {proc.pid})")
else:
    print(f"❌ uvicorn exited with code {proc.returncode}")
    sys.exit(1)

# 验证端口
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(('127.0.0.1', 8765))
sock.close()
if result == 0:
    print("✅ Port 8765 is OPEN")
else:
    print(f"❌ Port 8765 is CLOSED (error code {result})")