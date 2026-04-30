import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from template_exporter import resolve_template_path


class ResolveTemplatePathTests(unittest.TestCase):
    def test_handicap_resolves_to_hdp_template(self) -> None:
        expected = PROJECT_ROOT / "Daily Trading_HDP_Demo.xlsx"
        self.assertEqual(resolve_template_path("handicap"), expected)

    def test_totals_resolves_to_ou_template(self) -> None:
        expected = PROJECT_ROOT / "Daily Trading_OU_Demo.xlsx"
        self.assertEqual(resolve_template_path("totals"), expected)


if __name__ == "__main__":
    unittest.main()
