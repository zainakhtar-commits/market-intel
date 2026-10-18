"""Offline tests for SEC XBRL financial extraction."""
from app.financials import _annual_series, _extract

SAMPLE_FACTS = {
    "entityName": "Apple Inc.",
    "facts": {
        "us-gaap": {
            "Revenues": {
                "units": {
                    "USD": [
                        {"fy": 2022, "fp": "FY", "form": "10-K", "end": "2022-09-24", "val": 394328000000},
                        {"fy": 2023, "fp": "FY", "form": "10-K", "end": "2023-09-30", "val": 383285000000},
                        {"fy": 2023, "fp": "Q3", "form": "10-Q", "end": "2023-07-01", "val": 81797000000},
                    ]
                }
            },
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        {"fy": 2023, "fp": "FY", "form": "10-K", "end": "2023-09-30", "val": 96995000000},
                    ]
                }
            },
        }
    },
}


def test_annual_series_filters_to_full_year_10k():
    series = _annual_series(SAMPLE_FACTS["facts"]["us-gaap"]["Revenues"])
    # the 10-Q quarterly entry must be excluded
    assert [s["fy"] for s in series] == [2022, 2023]
    assert series[-1]["val"] == 383285000000


def test_extract_picks_first_available_concept():
    series = _extract(SAMPLE_FACTS, ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues"])
    assert series and series[-1]["fy"] == 2023


def test_extract_returns_empty_when_absent():
    assert _extract(SAMPLE_FACTS, ["NonexistentConcept"]) == []


def test_net_income_extracted():
    series = _extract(SAMPLE_FACTS, ["NetIncomeLoss"])
    assert series[-1]["val"] == 96995000000
