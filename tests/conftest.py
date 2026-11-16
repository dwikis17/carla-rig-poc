"""Test setup: replace ``carla`` with a fake BEFORE any test imports project code.

# WHY at import time (not in a fixture): control/vehicle.py does `import carla` at module level,
# and pytest imports test modules during collection — the fake must already be in place.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import fake_carla  # noqa: E402

sys.modules["carla"] = fake_carla
