import bentoml

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

MODEL_ID = "meta-llama/Llama-3.1-8B-Instruct"


@bentoml.service(
    name="llama-3.1-8b-instruct-modular",
    image=image,
    cmd=[
        "max",
        "serve",
        "--model-path",
        MODEL_ID,
        "--port",
        "${PORT}",
    ],
    envs=[
        {"name": "HF_TOKEN"},
    ],
    endpoints={"livez": "/v1/health", "readyz": "/v1/health"},
    resources={"gpu": 1, "gpu_type": "nvidia-l4"},
    traffic={"timeout": 300},
)
class ModularLLMService:
    model = bentoml.models.HuggingFaceModel(MODEL_ID, exclude=["original/*"])
