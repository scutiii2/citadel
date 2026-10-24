"""Resolve complete local Laya snapshots without fetching any model artifacts."""
from pathlib import Path



def _snapshot(checkpoint: str) -> Path:
    from huggingface_hub import snapshot_download
    from laya.router import resolve_model_spec
    from laya.revisions import resolve_revision

    repo, subfolder = resolve_model_spec(checkpoint) or (checkpoint, None)
    # Explicit local_files_only prevents network access, including HEAD requests.
    # token=False also avoids consulting stored Hub credentials for this local probe.
    root = Path(snapshot_download(repo_id=repo, revision=resolve_revision(repo, None),
                                  local_files_only=True, token=False))
    return root / subfolder if subfolder else root


def cached_checkpoint(checkpoint: str) -> str:
    """An absolute complete checkpoint directory, or a safe unavailable error."""
    try:
        root = _snapshot(checkpoint).resolve()
        required = ("rl_agent_config.json", "model.safetensors", "encoder/config.json", "tokenizer/tokenizer.json")
        if not all((root / name).is_file() for name in required):
            raise RuntimeError("incomplete snapshot")
        return str(root)
    except (ImportError, OSError, ValueError, RuntimeError):
        raise RuntimeError("Router checkpoint is not cached; prepare local Laya models before using local routing") from None
