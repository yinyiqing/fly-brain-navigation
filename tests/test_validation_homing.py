"""Control conditions and environment perturbations, without neural simulation."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_search_homing import execute_return, return_actions
from run_validation_suite import execution_errors, shuffled_labels


class ValidationTests(unittest.TestCase):
    def test_repeated_direction_labels_share_one_permutation(self):
        original = np.tile(np.arange(16) * 2 * np.pi / 16, 3)
        untouched = original.copy()
        labels, unique, mapped = shuffled_labels(original, 801)
        np.testing.assert_array_equal(original, untouched)
        np.testing.assert_array_equal(labels[:16], labels[16:32])
        np.testing.assert_array_equal(labels[:16], labels[32:])
        np.testing.assert_array_equal(np.sort(mapped), unique)
        self.assertFalse(np.array_equal(labels, original))

    def test_zero_execution_errors_preserve_original_results(self):
        first, points = execute_return([3, 0], 0, return_actions(np.pi, 1, 1.5, 72), 1)
        second, other = execute_return([3, 0], 0, return_actions(np.pi, 1, 1.5, 72), 1,
                                       turn_errors=np.zeros(30))
        self.assertEqual(first, second)
        self.assertEqual(points, other)

    def test_environment_turn_error_changes_actual_movement(self):
        exact, _ = execute_return([3, 0], 0, return_actions(np.pi, 3, 1.5, 0), 1)
        noisy, _ = execute_return([3, 0], 0, return_actions(np.pi, 3, 1.5, 0), 1,
                                  turn_errors=[np.pi / 2])
        self.assertTrue(exact["success"])
        self.assertFalse(noisy["success"])
        np.testing.assert_allclose([noisy["endpoint_x"], noisy["endpoint_y"]], [3, -3], atol=1e-12)
        self.assertAlmostEqual(noisy["return_distance"], 3)

    def test_paired_execution_noise_uses_common_prefix_and_scale(self):
        small = execution_errors(123, 1, 701, 2, 8)
        longer = execution_errors(123, 1, 701, 4, 20)
        np.testing.assert_array_equal(longer[:8], small * 2)
        different_trial = execution_errors(123, 1, 702, 2, 8)
        self.assertFalse(np.array_equal(small, different_trial))

    def test_noisy_search_preserves_distance_budget(self):
        result, _ = execute_return([100, 100], 0, return_actions(.5, 3, 1.5, 18), 1,
                                   turn_errors=execution_errors(123, 0, 701, 2, 20))
        self.assertFalse(result["success"])
        self.assertAlmostEqual(result["search_distance"], 18)
        self.assertAlmostEqual(result["return_distance"], 21)

    def test_missing_or_nonfinite_execution_errors_fail_explicitly(self):
        for errors in [[], [np.nan]]:
            with self.assertRaises(ValueError):
                execute_return([3, 0], 0, return_actions(np.pi, 1, 1.5, 0), 1, turn_errors=errors)


if __name__ == "__main__":
    unittest.main()
