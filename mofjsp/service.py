import sys
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

for runtime_root in (BASE_DIR, MODEL_DIR):
    if (runtime_root / "drl_fjsp").is_dir():
        sys.path.insert(0, str(runtime_root))
        break


with bentoml.importing():
    from drl_fjsp.inference import FJSPScheduler


@bentoml.service(image=image)
class FJSPDeploymentService:
    def __init__(self) -> None:
        self.engine = FJSPScheduler(BASE_DIR)
        self.inference_lock = Lock()

    @bentoml.api
    def schedule(self, request: dict[str, Any]) -> dict[str, Any]:
        with self.inference_lock:
            return self.engine.predict(request)
