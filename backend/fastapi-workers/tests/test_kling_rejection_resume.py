import json
from pathlib import Path
from unittest.mock import patch

from app.workers.longform_worker import _rejected_global_motion_indices


def test_previous_global_motion_rejection_is_loaded_for_resume(tmp_path: Path):
    audit = tmp_path / "520822" / "kling_audit.jsonl"
    audit.parent.mkdir(parents=True)
    audit.write_text(
        "\n".join([
            json.dumps({"scene_idx": 3, "status": "COMPLETED"}),
            json.dumps({"scene_idx": 5, "status": "REJECTED_GLOBAL_MOTION"}),
        ]),
        encoding="utf-8",
    )
    with patch("app.workers.longform_worker.Path") as path_cls:
        path_cls.return_value = audit
        assert _rejected_global_motion_indices(520822) == {5}


def test_multiple_previous_global_motion_rejections_are_all_loaded(tmp_path: Path):
    audit = tmp_path / "520822" / "kling_audit.jsonl"
    audit.parent.mkdir(parents=True)
    audit.write_text(
        "\n".join([
            json.dumps({"scene_idx": 5, "status": "REJECTED_GLOBAL_MOTION"}),
            json.dumps({"scene_idx": 6, "status": "REJECTED_GLOBAL_MOTION"}),
        ]),
        encoding="utf-8",
    )
    with patch("app.workers.longform_worker.Path") as path_cls:
        path_cls.return_value = audit
        assert _rejected_global_motion_indices(520822) == {5, 6}
