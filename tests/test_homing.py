"""Checks of navigation geometry and calibration data flow, without Brian2 runs."""
import sys
import unittest
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from run_homing import decode, evaluate_return, fit_readout, home_command, integrate, observe_turns, wrap


class HomingTests(unittest.TestCase):
    def test_known_displacement_and_exact_return(self):
        headings = np.array([0.0, np.pi / 2])
        ds = np.array([3.0, 4.0])
        path = integrate(headings, ds)
        np.testing.assert_allclose(path[-1], [3, 4])
        metrics, _, _ = evaluate_return(path, headings[-1], headings, ds, 0.1)
        self.assertLess(metrics["endpoint_error"], 1e-12)
        self.assertAlmostEqual(metrics["return_distance"], 5)

    def test_wrong_yaw_changes_relative_return_command(self):
        path = np.array([[0., 0.], [3., 4.]])
        a, _ = home_command(path, 0)
        b, _ = home_command(path, np.pi / 2)
        self.assertAlmostEqual(float(wrap(a - b)), np.pi / 2)

    def test_noisy_turns_accumulate_and_share_random_draws(self):
        headings = np.array([0.0, 0.0, 0.5, 0.5])
        zero = observe_turns(headings, 0, 7)
        np.testing.assert_allclose(wrap(np.cumsum(zero)), headings)
        low = observe_turns(headings, 5, 7) - zero
        high = observe_turns(headings, 15, 7) - zero
        np.testing.assert_allclose(high, 3 * low)

    def test_readout_uses_features_on_unseen_directions(self):
        train = np.arange(16) * 2 * np.pi / 16
        features = np.column_stack([10 + 8 * np.cos(train), 10 + 8 * np.sin(train)])
        readout = fit_readout(features, train, alpha=1)
        test = train + np.pi / 16
        raw = np.column_stack([10 + 8 * np.cos(test), 10 + 8 * np.sin(test)])
        np.testing.assert_allclose(wrap(decode(raw, readout) - test), 0, atol=1e-12)
        self.assertGreater(float(np.std(wrap(decode(np.zeros_like(raw), readout) - test))), 1)


if __name__ == "__main__":
    unittest.main()
