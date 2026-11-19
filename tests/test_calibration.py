import unittest

from src.calibration import calibrate_threshold


class TestCalibration(unittest.TestCase):
    def test_uses_configured_threshold_until_both_classes_have_enough_labels(self):
        threshold, result = calibrate_threshold(
            [
                {"fit_score": "70", "label": "apply"},
                {"fit_score": "35", "label": "reject"},
                {"fit_score": "90", "label": "review"},
            ],
            default_threshold=55,
            minimum_per_class=2,
        )

        self.assertEqual(threshold, 55)
        self.assertFalse(result["active"])

    def test_balances_user_apply_and_reject_labels_without_using_review_labels(self):
        rows = [
            {"fit_score": 82, "label": "apply"},
            {"fit_score": 74, "label": "apply"},
            {"fit_score": 69, "label": "apply"},
            {"fit_score": 48, "label": "reject"},
            {"fit_score": 39, "label": "reject"},
            {"fit_score": 28, "label": "reject"},
            {"fit_score": 100, "label": "review"},
        ]

        threshold, result = calibrate_threshold(
            rows, default_threshold=55, minimum_per_class=3
        )

        self.assertTrue(result["active"])
        self.assertEqual(result["positive"], 3)
        self.assertEqual(result["negative"], 3)
        self.assertGreaterEqual(threshold, 49)
        self.assertLessEqual(threshold, 69)


if __name__ == "__main__":
    unittest.main()
