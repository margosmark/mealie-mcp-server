import os
import sys
from pathlib import Path

# The server reads its config lazily, but set both so tests never depend on
# ambient environment.
os.environ.setdefault("MEALIE_URL", "https://mealie.test")
os.environ.setdefault("MEALIE_API_KEY", "test-key")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
