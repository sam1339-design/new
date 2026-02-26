import unittest
from unittest.mock import patch

import finance_news_monitor as fnm


class FetchNewsTests(unittest.TestCase):
    def test_source_failure_does_not_block_other_sources(self):
        seen_ids = set()
        urls = ["bad-source", "good-source"]

        def fake_parse(url):
            if url == "bad-source":
                raise TimeoutError("timeout")
            return [
                {
                    "id": "item-1",
                    "title": "ok",
                    "link": "https://example.com",
                    "published": "today",
                    "source": url,
                }
            ]

        with patch("finance_news_monitor.parse_rss", side_effect=fake_parse):
            items = fnm.fetch_news(urls, seen_ids)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "item-1")
        self.assertIn("item-1", seen_ids)


if __name__ == "__main__":
    unittest.main()
