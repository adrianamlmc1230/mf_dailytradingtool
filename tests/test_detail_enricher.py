import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from detail_enricher import parse_listing_page_score, select_score_compact


class ParseListingPageScoreTests(unittest.TestCase):
    def test_returns_compact_score_from_listing_header(self) -> None:
        html = """
        <div class="row" id="headVs">
            <div class="end">
                <div class="score">1</div>
                <div>
                    <span class="row red b">完</span>
                    <span class="row">(0-1)</span>
                </div>
                <div class="score gt">1</div>
            </div>
        </div>
        """

        self.assertEqual(parse_listing_page_score(html), "11")

    def test_returns_empty_when_listing_header_has_no_score(self) -> None:
        html = """
        <div class="row" id="headVs">
            <div class="end">
                <div class="score">&nbsp;</div>
                <div class='vs'>取消</div>
                <div class="score gt">&nbsp;</div>
            </div>
        </div>
        """

        self.assertEqual(parse_listing_page_score(html), "")


class SelectScoreCompactTests(unittest.TestCase):
    def test_prefers_listing_score_over_detail_rows(self) -> None:
        detail_rows = [
            {"score": "0-1"},
            {"score": "0-0"},
        ]

        self.assertEqual(select_score_compact(detail_rows, "11", ""), "11")

    def test_falls_back_to_detail_rows_then_homepage_score(self) -> None:
        self.assertEqual(select_score_compact([{"score": "0-0"}], "", ""), "00")
        self.assertEqual(select_score_compact([], "", "1-2"), "12")


if __name__ == "__main__":
    unittest.main()
