import inspect
import unittest
from unittest.mock import patch

from app import runtime_config
from app.utils.retry_policy import classify_image_error
from app.workers.images_worker import ImagesWorker


class _Provider:
    def __init__(self):
        self.kwargs = None

    def generate_image(self, **kwargs):
        self.kwargs = kwargs


class _Pressure:
    def __init__(self):
        self.outcomes = []

    def acquire(self):
        return None

    def outcome(self, error=None):
        self.outcomes.append(error)


class ImageWorkerStabilityTests(unittest.TestCase):
    def test_only_transient_provider_errors_are_retryable(self):
        self.assertFalse(classify_image_error(TypeError("bad config")).retryable)
        self.assertFalse(classify_image_error(ValueError("invalid setting")).retryable)
        self.assertFalse(classify_image_error(RuntimeError("invalid local output")).retryable)
        self.assertTrue(classify_image_error(RuntimeError("HTTP 503 unavailable")).retryable)
        self.assertTrue(classify_image_error(TimeoutError("timed out")).retryable)

    def test_prepaid_credit_exhaustion_is_not_retried_even_when_provider_uses_429(self):
        decision = classify_image_error(RuntimeError(
            "HTTP 429: Your prepayment credits are depleted; status=RESOURCE_EXHAUSTED"
        ))
        self.assertFalse(decision.retryable)
        self.assertEqual(decision.reason, "permanent provider billing/quota response")

    def test_background_layer_uses_registered_runtime_keys(self):
        provider = _Provider()
        pressure = _Pressure()
        with patch("app.workers.images_worker.gemini_pressure", pressure):
            ImagesWorker()._generate_background_layer(provider, "prompt", "/tmp/scene.png", "data", "neutral")
        self.assertEqual(provider.kwargs["gemini_service_tier"], runtime_config.value("gemini_service_tier"))
        self.assertEqual(provider.kwargs["gemini_retry_base_seconds"], runtime_config.value("gemini_pro_retry_base_seconds"))
        self.assertEqual(pressure.outcomes, [None])

    def test_parallel_renderer_accepts_preflight_from_generate_scope(self):
        params = inspect.signature(ImagesWorker._generate_parallel_scenes).parameters
        self.assertIn("budget_preflight", params)


if __name__ == "__main__":
    unittest.main()
