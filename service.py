import bentoml
from proxy import create_app
import subprocess
import sys
import aiohttp
import asyncio
import os
import signal
import time
import threading

# Global variable to hold the subprocess
subprocess_proc = None


def start_subprocess(cmd):
    """Starts a subprocess."""
    global subprocess_proc
    try:
        subprocess_proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
        print(f"Subprocess started with PID: {subprocess_proc.pid}")
    except FileNotFoundError:
        print(f"Error: Command not found: {cmd[0]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error starting subprocess: {e}", file=sys.stderr)
        sys.exit(1)


image = (
    bentoml.images.Image(
        base_image="ubuntu:22.04",
        python_version="3.11.13",
        lock_python_packages=False,
    )
    .system_packages("curl", "git", "python3-pip")
    .requirements_file("requirements.txt")
    .run(
        "uv pip install modular --index-url https://dl.modular.com/public/nightly/python/simple/ --prerelease allow"
    )
    .run("chmod 777 -R /app/.venv")  # bug
)

INTERNAL_PORT = 38080
MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"

app = create_app(f"http://localhost:{INTERNAL_PORT}")


@bentoml.service(
    name="llama-3.1-8b-instruct-modular",
    image=image,
    envs=[{"name": "HF_TOKEN"}],
    resources={"gpu": 1, "gpu_type": "nvidia-l4"},
    traffic={"timeout": 300},
    logging={"access": {"enabled": False}},
)
@bentoml.asgi_app(app)
class ModularLLMService:
    model = bentoml.models.HuggingFaceModel(MODEL_ID, exclude=["original/*"])

    def __init__(self):
        """
        Service constructor. Starts the background subprocess and a thread to monitor it.
        """
        CMD = [
            "max",
            "serve",
            "--model-path",
            self.model,
            "--port",
            str(INTERNAL_PORT),
        ]
        start_subprocess(CMD)
        monitor_thread = threading.Thread(target=self._monitor_subprocess, daemon=True)
        monitor_thread.start()

    def _monitor_subprocess(self):
        """
        Monitors the subprocess. If it exits, waits 1 minute,
        then sends SIGTERM to the current (parent) process.
        """
        global subprocess_proc
        if not subprocess_proc:
            return

        # Wait for the subprocess to exit
        subprocess_proc.wait()

        print(
            f"Subprocess with PID {subprocess_proc.pid} has exited with code {subprocess_proc.returncode}."
        )

        try:
            print("Waiting for 1 minute before sending SIGTERM to self...")
            time.sleep(60)

            parent_pid = os.getpid()  # Get current process PID
            print(f"Sending SIGTERM to self (PID: {parent_pid}) to initiate shutdown.")
            os.kill(parent_pid, signal.SIGTERM)
        except Exception as e:
            print(
                f"An error occurred while signaling parent process: {e}",
                file=sys.stderr,
            )

    async def __is_ready__(self) -> bool:
        """
        Readiness probe for the service. Checks the upstream server's health endpoint.
        """
        url = f"http://localhost:{INTERNAL_PORT}/v1/health"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=1) as response:
                    return response.status == 200
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False
