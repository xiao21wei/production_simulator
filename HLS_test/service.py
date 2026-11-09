import json
from pathlib import Path
from threading import Lock
from typing import Any

import bentoml


image = (
    bentoml.images.Image(
        base_image="tgagent/bentoml-base",
        lock_python_packages=False,
    )
    .requirements_file("requirements.txt")
)

BASE_DIR = Path(__file__).parent
MODEL_DIR = BASE_DIR / "model"


def asset_root() -> Path:
    for candidate in (BASE_DIR, MODEL_DIR):
        if (candidate / "hls_engine.py").is_file():
            return candidate
    raise FileNotFoundError("HLS runtime assets were not found")


with bentoml.importing():
    import sys

    RUNTIME_ROOT = asset_root()
    sys.path.insert(0, str(RUNTIME_ROOT))
    from hls_engine import HLSDeploymentEngine


@bentoml.service(image=image)
class HLSDeploymentService:
    def __init__(self) -> None:
        config_path = next(
            (
                candidate / "config.json"
                for candidate in (BASE_DIR, MODEL_DIR)
                if (candidate / "config.json").is_file()
            ),
            None,
        )
        if config_path is None:
            raise FileNotFoundError("HLS deployment config.json was not found")
        with config_path.open(encoding="utf-8") as stream:
            config = json.load(stream)
        runtime = config["runtime"]
        executable = next(
            (
                candidate / runtime["binary"]
                for candidate in (BASE_DIR, MODEL_DIR)
                if (candidate / runtime["binary"]).is_file()
            ),
            None,
        )
        if executable is None:
            executable = next(
                (
                    candidate / "production_scheduling"
                    for candidate in (BASE_DIR, MODEL_DIR)
                    if (candidate / "production_scheduling").is_file()
                ),
                None,
            )
        if executable is None:
            raise FileNotFoundError("HLS native executable was not found")
        self.engine = HLSDeploymentEngine(config, executable)
        self.inference_lock = Lock()

    @bentoml.api
    def schedule(self, request: dict[str, Any]) -> dict[str, Any]:
        with self.inference_lock:
            return self.engine.predict(request)
