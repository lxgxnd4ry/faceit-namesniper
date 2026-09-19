"""
Unit Tests for Namesniper Faceit Checker
"""
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from database import Database
from faceit_api import FaceitAPIClient
from generator import NameGenerator
from checker import CheckerEngine

class TestFaceitValidation(unittest.TestCase):
    def test_validate_nickname(self):
        # Valid Faceit usernames (3-12 characters, alphanumeric, hyphen, underscore)
        self.assertTrue(FaceitAPIClient.validate_nickname("vex"))
        self.assertTrue(FaceitAPIClient.validate_nickname("s1mple"))
        self.assertTrue(FaceitAPIClient.validate_nickname("pro_gamer"))
        self.assertTrue(FaceitAPIClient.validate_nickname("cool-name"))
        self.assertTrue(FaceitAPIClient.validate_nickname("123456789012"))

        # Invalid usernames
        self.assertFalse(FaceitAPIClient.validate_nickname("ab"))  # Too short (<3)
        self.assertFalse(FaceitAPIClient.validate_nickname("toolongusername123"))  # Too long (>12)
        self.assertFalse(FaceitAPIClient.validate_nickname("name with space"))
        self.assertFalse(FaceitAPIClient.validate_nickname("cool!name"))
        self.assertFalse(FaceitAPIClient.validate_nickname("user@name"))
        self.assertFalse(FaceitAPIClient.validate_nickname(""))

    def test_parse_creation_date(self):
        # Account created in 2013 should be older than 1 year
        dt_str, years, older = FaceitAPIClient.parse_creation_date("2013-05-30T21:34:13Z")
        self.assertEqual(dt_str, "2013-05-30")
        self.assertTrue(years > 10.0)
        self.assertTrue(older)

        # Account created very recently (e.g. within current year) should be <= 1 year
        # Using a date from 2026-08-01 (1.5 months ago in 2026-09-16)
        dt_str, years, older = FaceitAPIClient.parse_creation_date("2026-08-01T00:00:00Z")
        self.assertEqual(dt_str, "2026-08-01")
        self.assertFalse(older)

        # None / empty handling
        dt_str, years, older = FaceitAPIClient.parse_creation_date(None)
        self.assertIsNone(dt_str)
        self.assertFalse(older)

class TestGenerator(unittest.TestCase):
    def test_3l_pronounceable(self):
        words = NameGenerator.generate_3l_pronounceable(limit=50)
        self.assertTrue(len(words) > 0)
        for w in words:
            self.assertEqual(len(w), 3)
            self.assertTrue(FaceitAPIClient.validate_nickname(w))

    def test_4l_pronounceable(self):
        words = NameGenerator.generate_4l_pronounceable(limit=50)
        self.assertTrue(len(words) > 0)
        for w in words:
            self.assertEqual(len(w), 4)
            self.assertTrue(FaceitAPIClient.validate_nickname(w))

    def test_pattern_generator(self):
        words = NameGenerator.generate_by_pattern("CVCV", count=20)
        for w in words:
            self.assertEqual(len(w), 4)
            self.assertTrue(FaceitAPIClient.validate_nickname(w))

    def test_compound_generator(self):
        words = NameGenerator.generate_compound_words(count=20)
        for w in words:
            self.assertTrue(3 <= len(w) <= 12)
            self.assertTrue(FaceitAPIClient.validate_nickname(w))

    def test_3_alnum(self):
        words = NameGenerator.generate_3_alnum(limit=50)
        self.assertEqual(len(words), 50)
        for w in words:
            self.assertEqual(len(w), 3)
            self.assertTrue(FaceitAPIClient.validate_nickname(w))

    def test_4_alnum(self):
        words = NameGenerator.generate_4_alnum(limit=50)
        self.assertEqual(len(words), 50)
        for w in words:
            self.assertEqual(len(w), 4)
            self.assertTrue(FaceitAPIClient.validate_nickname(w))

    def test_3_mixed(self):
        words = NameGenerator.generate_3_mixed(limit=50)
        self.assertEqual(len(words), 50)
        for w in words:
            self.assertEqual(len(w), 3)
            self.assertTrue(any(c.isalpha() for c in w))
            self.assertTrue(any(c.isdigit() for c in w))
            self.assertTrue(FaceitAPIClient.validate_nickname(w))

    def test_4_mixed(self):
        words = NameGenerator.generate_4_mixed(limit=50)
        self.assertEqual(len(words), 50)
        for w in words:
            self.assertEqual(len(w), 4)
            self.assertTrue(any(c.isalpha() for c in w))
            self.assertTrue(any(c.isdigit() for c in w))
            self.assertTrue(FaceitAPIClient.validate_nickname(w))

    def test_apply_leet(self):
        word = "beast"
        for amt in range(1, 6):
            leeted = NameGenerator.apply_leet(word, amount=amt)
            self.assertEqual(len(leeted), len(word))
            self.assertTrue(FaceitAPIClient.validate_nickname(leeted))
            digits_count = sum(1 for c in leeted if c.isdigit())
            self.assertTrue(1 <= digits_count <= amt)

    def test_apply_leet_to_list(self):
        input_list = ["legend", "sniper", "shadow", "frost", "beast"]
        leeted_list = NameGenerator.apply_leet_to_list(input_list, amount=2)
        self.assertEqual(len(leeted_list), len(input_list))
        for item in leeted_list:
            self.assertTrue(FaceitAPIClient.validate_nickname(item))
            self.assertTrue(any(c.isdigit() for c in item))

class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test.db"
        self.db = Database(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_record_and_get(self):
        self.assertFalse(self.db.is_already_checked("phantom"))
        
        self.db.record_result(
            nickname="phantom",
            status="AVAILABLE",
            length=7,
            details="Available for registration"
        )
        self.assertTrue(self.db.is_already_checked("phantom"))
        self.assertTrue(self.db.is_already_checked("PHANTOM"))  # Case insensitive

        results = self.db.get_results("AVAILABLE")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["nickname"], "phantom")

        stats = self.db.get_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["available"], 1)

    def test_search_results(self):
        self.db.record_result(nickname="alpha", status="AVAILABLE", length=5)
        self.db.record_result(nickname="beta", status="AVAILABLE", length=4)
        self.db.record_result(nickname="alphabet", status="TAKEN", length=8)

        res = self.db.get_results(search_query="alph")
        self.assertEqual(len(res), 2)
        nicknames = {r["nickname"] for r in res}
        self.assertIn("alpha", nicknames)
        self.assertIn("alphabet", nicknames)

        res_filtered = self.db.get_results(status_filter="AVAILABLE", search_query="alph")
        self.assertEqual(len(res_filtered), 1)
        self.assertEqual(res_filtered[0]["nickname"], "alpha")

class TestCheckerEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test.db"
        self.db = Database(self.db_path)
        self.api_client = FaceitAPIClient(api_keys=["dummy-test-key"])

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("faceit_api.requests.Session.get")
    def test_engine_available_and_taken(self, mock_get):
        # Setup mock behavior for search/players and players/{id} endpoints
        def mock_side_effect(url, **kwargs):
            mock_resp = MagicMock()
            if "/players/mock-uuid-123" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "activated_at": "2013-05-30T21:34:13Z",
                    "games": {"cs2": {"faceit_elo": 2500}}
                }
            elif "/players/mock-uuid-456" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "activated_at": "2016-01-01T00:00:00Z",  # > 1 year ago -> Claimable
                    "games": {}
                }
            elif "/players/mock-uuid-789" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "activated_at": "2026-08-01T00:00:00Z",  # < 1 year ago -> Fresh, not claimable
                    "games": {}
                }
            elif "search/players" in url and "vex" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": []}  # No exact match -> Available
            elif "search/players" in url and "ferocity" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "items": [
                        {
                            "player_id": "mock-uuid-123",
                            "nickname": "Ferocity",  # Capital F
                            "country": "gb",
                            "games": [{"name": "cs2", "skill_level": "10"}]
                        }
                    ]
                }
            elif "search/players" in url and "idleuser" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "items": [
                        {
                            "player_id": "mock-uuid-456",
                            "nickname": "IdleUser",
                            "country": "se",
                            "games": []  # 0 games -> Claimable idle because > 1 yr
                        }
                    ]
                }
            elif "search/players" in url and "freshuser" in url:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "items": [
                        {
                            "player_id": "mock-uuid-789",
                            "nickname": "FreshUser",
                            "country": "de",
                            "games": []  # 0 games but < 1 yr -> TAKEN
                        }
                    ]
                }
            else:
                mock_resp.status_code = 200
                mock_resp.json.return_value = {"items": []}
            return mock_resp

        mock_get.side_effect = mock_side_effect

        results_collected = []
        def on_res(r):
            results_collected.append(r)

        engine = CheckerEngine(
            api_client=self.api_client,
            database=self.db,
            threads=1,
            delay_between_requests=0.0,
            detect_idle=True,
            on_result=on_res
        )

        test_names = ["vex", "ferocity", "idleuser", "freshuser"]
        queued = engine.load_names(test_names, skip_checked=False)
        self.assertEqual(queued, 4)

        engine.start()
        # Wait for workers
        for w in engine.workers:
            w.join(timeout=3.0)

        statuses = {r["nickname"]: r["status"] for r in results_collected}
        self.assertEqual(statuses.get("vex"), "AVAILABLE")
        self.assertEqual(statuses.get("Ferocity"), "TAKEN")  # Preserves real capitalization
        self.assertEqual(statuses.get("IdleUser"), "CLAIMABLE_IDLE")  # Created > 1 yr ago
        self.assertEqual(statuses.get("FreshUser"), "TAKEN")  # Fresh (< 1 yr) -> Not claimable

if __name__ == "__main__":
    unittest.main()
