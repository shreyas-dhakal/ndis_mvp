import unittest
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent.parent / "src" / "agent" / "task_triggers.py"
SPEC = spec_from_file_location("task_triggers", MODULE_PATH)
TASK_TRIGGERS = module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(TASK_TRIGGERS)

detect_rule_based_trigger = TASK_TRIGGERS.detect_rule_based_trigger


class DetectRuleBasedDecisionTests(unittest.TestCase):
    def test_triggers_for_headache_during_supported_activity(self):
        decision = detect_rule_based_trigger(
            {
                "subjective": "Participant reported a headache during community access.",
                "objective": "Support worker paused the outing and offered water.",
                "assessment": "Acute symptom emerged during support.",
                "plan": "Monitor and escalate if symptoms worsen.",
                "linked_goals": [],
                "support_type": "Community access",
                "participant_voice": "I have a headache.",
                "risks_incidents": "Headache during supported activity.",
            }
        )

        self.assertIsNotNone(decision)
        self.assertEqual(decision[0], "reportable_incident_injury")

    def test_does_not_trigger_for_historical_migraine_before_support(self):
        decision = detect_rule_based_trigger(
            {
                "subjective": "Participant said they had a migraine before support started.",
                "objective": "Symptoms had settled by the time the worker arrived.",
                "assessment": "Historical symptom only.",
                "plan": "No action required.",
                "linked_goals": [],
                "support_type": "Home support",
                "participant_voice": "I felt sick earlier today.",
                "risks_incidents": "Not documented",
            }
        )

        self.assertIsNone(decision)


if __name__ == "__main__":
    unittest.main()
