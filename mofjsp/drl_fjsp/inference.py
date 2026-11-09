import json
import re
import tempfile
from pathlib import Path
from typing import Any

import torch

from . import ppo_model
from .env import FJSPEnv
from .load_data import nums_detec


class FJSPScheduler:
    """Load the trained FJSP policy and schedule one instance with DRL-S sampling."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir).resolve()
        artifact_dirs = (self.base_dir, self.base_dir / "model")
        config_path = next(
            (path for path in artifact_dirs if (path / "config.json").is_file()),
            None,
        )
        if config_path is None:
            raise FileNotFoundError(
                "config.json was not found in: "
                + ", ".join(str(path) for path in artifact_dirs)
            )
        with (config_path / "config.json").open("r", encoding="utf-8") as stream:
            config = json.load(stream)

        inference_paras = config["inference_paras"]
        checkpoint_name = Path(inference_paras["checkpoint"]).name
        checkpoint_path = next(
            (
                path / checkpoint_name
                for path in artifact_dirs
                if (path / checkpoint_name).is_file()
            ),
            None,
        )
        if checkpoint_path is None:
            raise FileNotFoundError(
                f"Checkpoint {checkpoint_name} was not found in: "
                + ", ".join(str(path) for path in artifact_dirs)
            )
        self.checkpoint_path = checkpoint_path
        self.default_num_samples = int(inference_paras["default_num_samples"])
        self.max_num_samples = int(inference_paras["max_num_samples"])
        self.max_input_chars = int(inference_paras["max_input_chars"])

        # The runtime tensors are created on the default device, matching the
        # CPU-only dependency set in requirements.txt.
        self.device = torch.device("cpu")
        self.env_paras = dict(config["env_paras"])
        self.env_paras["device"] = self.device
        self.env_paras["show_mode"] = "print"

        self.model_paras = dict(config["model_paras"])
        self.model_paras["device"] = self.device
        self.model_paras["actor_in_dim"] = (
            self.model_paras["out_size_ma"] * 2
            + self.model_paras["out_size_ope"] * 2
        )
        self.model_paras["critic_in_dim"] = (
            self.model_paras["out_size_ma"] + self.model_paras["out_size_ope"]
        )
        self.train_paras = dict(config["train_paras"])

        self.model = ppo_model.PPO(self.model_paras, self.train_paras)
        try:
            state_dict = torch.load(
                self.checkpoint_path, map_location=self.device, weights_only=True
            )
        except TypeError:
            # Compatibility with PyTorch versions before weights_only was introduced.
            state_dict = torch.load(self.checkpoint_path, map_location=self.device)
        self.model.policy.load_state_dict(state_dict, strict=True)
        self.model.policy_old.load_state_dict(state_dict, strict=True)
        self.model.policy.eval()
        self.model.policy_old.eval()

    def predict(self, request: dict[str, Any] | None) -> dict[str, Any]:
        request = request or {}
        raw_lines = self._require_text(request, "raw_lines")
        additional_lines = self._require_text(request, "additional_lines")
        num_samples = int(request.get("num_samples") or self.default_num_samples)
        seed = int(request.get("seed") if request.get("seed") is not None else 0)
        instance_name = self._safe_instance_name(request.get("instance_name"))

        if not 1 <= num_samples <= self.max_num_samples:
            raise ValueError(
                f"num_samples must be between 1 and {self.max_num_samples}"
            )
        if len(raw_lines) + len(additional_lines) > self.max_input_chars:
            raise ValueError(
                f"input text exceeds the {self.max_input_chars}-character limit"
            )

        normalized_raw = self._normalize_file_text(raw_lines)
        normalized_additional = self._normalize_file_text(additional_lines)
        raw_file_lines = normalized_raw.splitlines()
        if not raw_file_lines:
            raise ValueError("raw_lines is empty")

        header = raw_file_lines[0].split()
        if len(header) < 2:
            raise ValueError(
                "raw_lines header must contain at least: num_jobs num_machines"
            )
        try:
            num_jobs = int(header[0])
            num_machines = int(header[1])
        except ValueError as exc:
            raise ValueError(
                "raw_lines header fields 1 and 2 must be integers"
            ) from exc
        if num_jobs <= 0 or num_machines <= 0:
            raise ValueError("num_jobs and num_machines must be positive")
        if len(raw_file_lines) - 1 != num_jobs:
            raise ValueError(
                f"raw_lines declares {num_jobs} jobs but contains "
                f"{len(raw_file_lines) - 1} job rows"
            )

        _, detected_machines, num_operations = nums_detec(
            [line + "\n" for line in raw_file_lines]
        )
        if detected_machines != num_machines:
            raise ValueError("raw_lines machine count is inconsistent")
        if num_operations <= 0:
            raise ValueError("raw_lines contains no operations")
        additional_token_count = len(normalized_additional.split())
        if additional_token_count < 2 * num_machines * num_machines:
            raise ValueError(
                "additional_lines does not contain enough values for the "
                "transport-time and transport-energy matrices"
            )

        with tempfile.TemporaryDirectory(prefix="drl_fjsp_") as temp_dir:
            root = Path(temp_dir)
            raw_dir = root / "raw"
            add_dir = root / "add"
            raw_dir.mkdir()
            add_dir.mkdir()
            raw_path = raw_dir / f"{instance_name}.fjs"
            add_path = add_dir / f"{instance_name}.fjs"
            raw_path.write_text(normalized_raw, encoding="utf-8")
            add_path.write_text(normalized_additional, encoding="utf-8")

            env_paras = dict(self.env_paras)
            env_paras["batch_size"] = num_samples
            env_paras["num_jobs"] = num_jobs
            env_paras["num_mas"] = num_machines
            env = FJSPEnv(
                [str(raw_path)] * num_samples, env_paras, data_source="file"
            )

            rng_devices = (
                []
                if self.device.type == "cpu"
                else [self.device.index if self.device.index is not None else 0]
            )
            with torch.random.fork_rng(devices=rng_devices):
                torch.manual_seed(seed)
                if self.device.type == "cuda":
                    torch.cuda.manual_seed_all(seed)
                self._run_policy(env, num_operations)

            feasible, _ = env.validate_gantt()
            if not feasible:
                raise RuntimeError("The generated schedule failed feasibility checks")

            makespans = env.makespan_batch.detach().cpu().double()
            energies = env.energy_batch.detach().cpu().double()
            penalties = env.penalty_batch.detach().cpu().double()
            best_index = self._select_candidate(makespans, energies, penalties)
            schedules = env.schedules_batch.detach().cpu()
            num_opes = int(env.nums_opes[best_index].item())

            schedule_rows = []
            for operation_id in range(num_opes):
                machine_id = int(schedules[best_index, operation_id, 1].item())
                start_time = float(schedules[best_index, operation_id, 2].item())
                end_time = float(schedules[best_index, operation_id, 3].item())
                job_id, operation_index = env.get_idx(operation_id, best_index)
                schedule_rows.append(
                    {
                        "job_id": int(job_id),
                        "operation_index": int(operation_index),
                        "operation_id": operation_id,
                        "machine_id": machine_id,
                        "start_time": start_time,
                        "end_time": end_time,
                        "processing_time": end_time - start_time,
                    }
                )
            schedule_rows.sort(
                key=lambda row: (
                    row["start_time"],
                    row["machine_id"],
                    row["job_id"],
                    row["operation_index"],
                )
            )

            return {
                "success": True,
                "instance_name": instance_name,
                "model": self.checkpoint_path.name,
                "device": str(self.device),
                "num_samples": num_samples,
                "best_sample": best_index,
                "n_jobs": num_jobs,
                "n_machines": num_machines,
                "n_operations": num_operations,
                "objectives": {
                    "makespan": float(makespans[best_index].item()),
                    "energy": float(energies[best_index].item()),
                    "penalty": float(penalties[best_index].item()),
                },
                "feasible": True,
                "schedule": schedule_rows,
            }

    def _run_policy(self, env: FJSPEnv, num_operations: int) -> None:
        max_steps = num_operations + 1
        for _ in range(max_steps):
            if bool(env.done_batch.all().item()):
                return
            with torch.no_grad():
                actions = self.model.policy_old.act(
                    env.state,
                    memories=None,
                    dones=env.done_batch,
                    flag_sample=True,
                    flag_train=False,
                )
            env.step(actions)
        raise RuntimeError("scheduling did not finish within the expected step count")

    @staticmethod
    def _select_candidate(
        makespans: torch.Tensor,
        energies: torch.Tensor,
        penalties: torch.Tensor,
    ) -> int:
        eps = 1e-9
        normalized = torch.stack(
            (
                makespans / torch.clamp(makespans.min(), min=eps),
                energies / torch.clamp(energies.min(), min=eps),
                penalties / torch.clamp(penalties.min(), min=eps),
            ),
            dim=1,
        )
        distance = torch.sqrt(torch.mean(normalized * normalized, dim=1))
        return int(torch.argmin(distance).item())

    @staticmethod
    def _require_text(request: dict[str, Any], field: str) -> str:
        value = request.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} must be a non-empty string")
        return value

    @staticmethod
    def _normalize_file_text(text: str) -> str:
        if "\x00" in text:
            raise ValueError("input text must not contain NUL characters")
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")
        return normalized.rstrip() + "\n"

    @staticmethod
    def _safe_instance_name(value: Any) -> str:
        candidate = str(value or "instance").strip()
        candidate = Path(candidate).name
        if candidate.lower().endswith(".fjs"):
            candidate = candidate[:-4]
        candidate = re.sub(r"[^A-Za-z0-9_.-]+", "_", candidate)
        if candidate in {"", ".", ".."}:
            return "instance"
        return candidate[:80]
