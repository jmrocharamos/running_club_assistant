from datetime import date
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from app.services import ai_service


class AIServiceTests(TestCase):
    def test_routes_every_workflow_to_both_providers(self):
        cases = {
            "get_chat_reply": {"reply": "Hello runner"},
            "summarize_conversation": {"current_goal": "Finish a 5K"},
            "get_training_safety_assessment": {"plan_mode": "blocked", "message": "No clearance"},
            "get_feedback_safety_assessment": {
                "decision": "continue_revision", "plan_mode": "normal_running",
                "message": "Continue", "requested_start_date": "2026-10-12",
            },
            "get_recommendation": {
                "content": {"summary": "Plan", "training_days": [], "weekly_distance": [], "safety_notes": []},
                "explanation": {"why_this_plan_fits": []},
            },
        }
        for provider in ("openai", "ollama"):
            for name, output in cases.items():
                with self.subTest(provider=provider, workflow=name):
                    method = Mock(return_value=output)
                    with patch.object(ai_service, "AI_PROVIDER", provider):
                        with patch.object(ai_service, "import_module", return_value=SimpleNamespace(**{name: method})) as loader:
                            kwargs = {"plan_mode": "normal_running"} if name == "get_recommendation" else {}
                            result = getattr(ai_service, name)("input", "prompt", "version", **kwargs)
                    loader.assert_called_once_with(f"app.client_{provider}")
                    method.assert_called_once_with("input", "prompt", "version", **kwargs)
                    if name == "get_feedback_safety_assessment":
                        self.assertEqual(result["requested_start_date"], date(2026, 10, 12))

    def test_unknown_provider_does_not_import_a_client(self):
        with patch.object(ai_service, "AI_PROVIDER", "unknown"):
            with patch.object(ai_service, "import_module") as loader:
                with self.assertRaisesRegex(ValueError, "Unsupported AI provider"):
                    ai_service.get_chat_reply("input", "prompt", "version")
                loader.assert_not_called()

    def test_rejects_contradictory_feedback_safety(self):
        method = Mock(return_value={
            "decision": "requires_coach_review", "plan_mode": "normal_running", "message": "Review",
        })
        with patch.object(ai_service, "import_module", return_value=SimpleNamespace(get_feedback_safety_assessment=method)):
            with self.assertRaises(ValueError):
                ai_service.get_feedback_safety_assessment("input", "prompt", "version")
