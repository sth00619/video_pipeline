from scripts.run_wo_img02a_before_after_canary import _git_head


def test_runner_commit_can_be_injected_in_gitless_execution_environment(monkeypatch):
    monkeypatch.setenv("VIDEO_PIPELINE_RUNNER_COMMIT", "95b930f")

    assert _git_head() == "95b930f"
