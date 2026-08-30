"""部署脚本：把项目打包上传到 Ubuntu 服务器并启动。

用法：python tests/deploy.py
依赖：paramiko（仅本机使用，不部署到服务器）
"""
import os
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")
import paramiko  # noqa: E402

HOST = "152.136.60.146"
USER = "root"
PASSWORD = "112230loVE#"
REMOTE_DIR = "/opt/vc_hero"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run_local(cmd):
    print("+", cmd, flush=True)
    subprocess.run(cmd, cwd=ROOT, shell=True, check=True)


def main():
    # 1. 打包（git 跟踪的文件，排除 key 与 data）
    tar = os.path.join(ROOT, "vc_hero_deploy.tar.gz")
    if os.path.exists(tar):
        os.remove(tar)
    run_local("git archive HEAD -o vc_hero_deploy.tar.gz")

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PASSWORD, timeout=20,
              look_for_keys=False, allow_agent=False)
    print("SSH 连接成功", flush=True)

    def sh(cmd):
        print("+", cmd, flush=True)
        stdin, stdout, stderr = c.exec_command(cmd, timeout=300)
        out = stdout.read().decode()
        err = stderr.read().decode()
        if out.strip():
            print(out, flush=True)
        if err.strip():
            print("STDERR:", err, flush=True)
        code = stdout.channel.recv_exit_status()
        if code != 0:
            raise RuntimeError(f"命令失败({code}): {cmd}")

    # 2. 上传并解压
    sftp = c.open_sftp()
    sh(f"mkdir -p {REMOTE_DIR}")
    print("上传中…", flush=True)
    sftp.put(tar, f"{REMOTE_DIR}/vc_hero_deploy.tar.gz")
    sftp.close()
    sh(f"cd {REMOTE_DIR} && tar xzf vc_hero_deploy.tar.gz && rm vc_hero_deploy.tar.gz")

    # 3. 上传 API key（不进 git）
    sftp = c.open_sftp()
    sftp.put(os.path.join(ROOT, "kimi_api_key.txt"),
             f"{REMOTE_DIR}/kimi_api_key.txt")
    sftp.close()

    # 4. 依赖与启动
    sh("python3 --version")
    sh("pip3 install -q flask pypdf 2>/dev/null || pip install -q flask pypdf")
    sh(f"pkill -f 'python3 app.py' 2>/dev/null; sleep 1; true")
    sh(f"cd {REMOTE_DIR} && nohup python3 app.py > server.log 2>&1 &")
    sh("sleep 3 && curl -s http://127.0.0.1:5000/api/health")

    c.close()
    os.remove(tar)
    print("\n部署完成：http://%s:5000" % HOST, flush=True)


if __name__ == "__main__":
    main()
