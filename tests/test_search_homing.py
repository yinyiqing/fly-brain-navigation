"""Physical checks for goal contact and bounded external search."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_search_homing import contact_distance, execute_return, return_actions


class SearchHomingTests(unittest.TestCase):
    def test_contact_finds_entry_even_when_endpoint_overshoots(self):
        self.assertAlmostEqual(contact_distance([3, 0], np.pi, 6, 1), 2)
        self.assertIsNone(contact_distance([3, 2], np.pi, 6, 1))
        self.assertIsNone(contact_distance([3, 0], 0, 6, 1))
        self.assertAlmostEqual(contact_distance([3, 1], np.pi, 6, 1), 3)
        self.assertEqual(contact_distance([.5, 0], 0, 6, 1), 0)

    def test_direct_and_search_stop_at_same_contact_on_initial_leg(self):
        results = []
        for budget in [0, 72]:
            metrics, _ = execute_return([3, 0], 0, return_actions(np.pi, 6, 1.5, budget), 1)
            results.append(metrics)
        self.assertEqual(results[0], results[1])
        self.assertTrue(results[0]["success"])
        self.assertAlmostEqual(results[0]["return_distance"], 2)
        self.assertEqual(results[0]["search_distance"], 0)

    def test_search_reaches_nearby_missed_home(self):
        direct, _ = execute_return([3, 0], 0, return_actions(np.pi, 1, 1.5, 0), 1)
        search, _ = execute_return([3, 0], 0, return_actions(np.pi, 1, 1.5, 72), 1)
        self.assertFalse(direct["success"])
        self.assertTrue(search["success"])
        self.assertEqual(search["termination_stage"], "search")
        self.assertGreater(search["search_distance"], 0)
        self.assertLessEqual(search["endpoint_error"], 1 + 1e-10)

    def test_distant_home_exhausts_budget_and_stays_a_failure(self):
        result, _ = execute_return([100, 100], 0, return_actions(0, 3, 1.5, 7.25), 1)
        self.assertFalse(result["success"])
        self.assertEqual(result["termination_stage"], "budget_exhausted")
        self.assertAlmostEqual(result["search_distance"], 7.25)
        self.assertAlmostEqual(result["return_distance"], 10.25)

    def test_rotating_world_preserves_plan_success_and_cost(self):
        angle = .73
        rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        a, _ = execute_return([3, 0], 0, return_actions(np.pi, 1, 1.5, 72), 1)
        b, _ = execute_return(rotation @ [3, 0], angle, return_actions(np.pi, 1, 1.5, 72), 1)
        self.assertEqual(a["success"], b["success"])
        self.assertAlmostEqual(a["return_distance"], b["return_distance"])
        np.testing.assert_allclose(rotation @ [a["endpoint_x"], a["endpoint_y"]],
                                   [b["endpoint_x"], b["endpoint_y"]], atol=1e-10)

    def test_invalid_parameters_do_not_create_unbounded_plans(self):
        for spacing, budget in [(0, 72), (1.5, -1), (1.5, np.inf)]:
            with self.assertRaises(ValueError):
                list(return_actions(0, 3, spacing, budget))


if __name__ == "__main__":
    unittest.main()
