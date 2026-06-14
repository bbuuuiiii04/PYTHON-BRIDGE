from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from rb_ss_bridge_v2.govee_owner_state import (  # noqa: E402
    GoveeOwnerStateMachine,
    OwnerState,
)


class GoveeOwnerStateMachineTests(unittest.TestCase):
    def test_acquire_release_and_force_release(self) -> None:
        owner = GoveeOwnerStateMachine()

        self.assertEqual(owner.current(), OwnerState.NONE)
        self.assertTrue(owner.acquire(OwnerState.REALTIME_RAZER))
        self.assertEqual(owner.current(), OwnerState.REALTIME_RAZER)
        self.assertTrue(owner.acquire(OwnerState.REALTIME_RAZER))
        self.assertFalse(owner.acquire(OwnerState.CLOUD_DIY))

        self.assertFalse(owner.release(OwnerState.CLOUD_DIY))
        self.assertTrue(owner.release(OwnerState.REALTIME_RAZER))
        self.assertEqual(owner.current(), OwnerState.NONE)

        self.assertTrue(owner.acquire(OwnerState.CLOUD_DIY))
        owner.force_release()
        self.assertEqual(owner.current(), OwnerState.NONE)


if __name__ == "__main__":
    unittest.main()
