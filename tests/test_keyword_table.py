"""keyword_table must map eRank's {value, order_value} cells to every UI column."""

from erank_mcp.summarize import keyword_table, top_tags


def test_keyword_ideas_columns():
    payload = {
        "related_searches": {
            "data": [
                {
                    "keyword": "bridal shower",
                    "character_count": 13,
                    "occurrences": 1,
                    "avg_searches": {"value": "10,227", "order_value": 10227},
                    "avg_clicks": {"value": "11,016", "order_value": 11016},
                    "ctr": {"value": "108", "order_value": 108, "suffix": "%"},
                    "competition": {"value": "Unknown", "order_value": 0},
                    "keyword_difficulty": {"value": "", "order_value": 0},
                    "search_trend": [{"value": 5770, "date": "Aug 2025"}, {"value": 12810, "date": "Sep 2025"}],
                    "google": {"avg_searches": "N/A", "order_value": -1},
                }
            ]
        },
        "competition": {"bridal shower": {"value": "1,688,833", "order_value": 1688833}},
        "keyword_difficulty": {"bridal shower": {"value": "100", "order_value": 100}},
        "google_data": {"bridal shower": {"term": "bridal shower", "avg_searches": 33100}},
        "etsy_tags": [{"keyword": "bridal shower", "occurrences": 1}, {"keyword": "shower game", "occurrences": 3}],
    }
    rows = keyword_table(payload)
    assert rows[0] == {
        "keyword": "bridal shower",
        "search_trend": [5770, 12810],
        "avg_searches": "10,227",
        "avg_clicks": "11,016",
        "avg_ctr": "108",
        "kd": "100",
        "etsy_competition": "1,688,833",
        "tag_occurrences": 1,
        "chars": 13,
        "google_searches": 33100,
        "is_top_tag": True,
    }
    assert len(rows) == 1
    assert top_tags(payload)[0] == {"keyword": "shower game", "occurrences": 3}
