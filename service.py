import bentoml
from proxy import create_app
import subprocess
import atexit
import sys
import aiohttp
import asyncio

# Global variable to hold the subprocess
subprocess_proc = None


def start_subprocess(cmd):
    """Starts a subprocess and registers a cleanup function."""
    global subprocess_proc
    try:
        # Start the subprocess
        subprocess_proc = subprocess.Popen(cmd, stdout=sys.stdout, stderr=sys.stderr)
        print(f"Subprocess started with PID: {subprocess_proc.pid}")
    except FileNotFoundError:
        print(f"Error: Command not found: {cmd[0]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error starting subprocess: {e}", file=sys.stderr)
        sys.exit(1)


def cleanup_subprocess():
    """Cleans up the subprocess on exit."""
    global subprocess_proc
    if subprocess_proc and subprocess_proc.poll() is None:
        print(f"Terminating subprocess with PID: {subprocess_proc.pid}")
        subprocess_proc.terminate()
        try:
            # Wait for a short period for the process to terminate
            subprocess_proc.wait(timeout=5)
            print("Subprocess terminated gracefully.")
        except subprocess.TimeoutExpired:
            print("Subprocess did not terminate in time, killing it.")
            subprocess_proc.kill()
            subprocess_proc.wait()
            print("Subprocess killed.")


# Register the cleanup function to be called on exit
atexit.register(cleanup_subprocess)


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

INTERNAL_PORT = 8080
MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"
CMD = [
    "max",
    "serve",
    "--model-path",
    MODEL_ID,
    "--port",
    str(INTERNAL_PORT),  # Ensure port is a string
]


app = create_app(f"http://localhost:{INTERNAL_PORT}")


@bentoml.service(
    name="llama-3.1-8b-instruct-modular",
    image=image,
    envs=[
        {"name": "HF_TOKEN"},
    ],
    resources={"gpu": 1, "gpu_type": "nvidia-l4"},
    traffic={"timeout": 300},
)
@bentoml.asgi_app(app)
class ModularLLMService:
    model = bentoml.models.HuggingFaceModel(MODEL_ID, exclude=["original/*"])

    def __init__(self):
        """
        Service constructor. Starts the background subprocess.
        """
        start_subprocess(CMD)

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
