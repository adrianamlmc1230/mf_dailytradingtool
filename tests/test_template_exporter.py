import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from template_exporter import resolve_template_path


class ResolveTemplatePathTests(unittest.TestCase):
    def test_handicap_and_totals_share_the_same_template_file(self) -> None:
        expected = PROJECT_ROOT / "新版Daily Trading_Demo.xlsx"

        self.assertEqual(resolve_template_path("handicap"), expected)
        self.assertEqual(resolve_template_path("totals"), expected)


if __name__ == "__main__":
    unittest.main()
