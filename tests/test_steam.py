"""
Unit Tests for Steam Vanity / ID Checker Module
"""
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from database import Database, SteamDatabase
from steam_api import SteamAPIClient
from steam_checker import SteamCheckerEngine

class TestSteamValidation(unittest.TestCase):
    def test_validate_vanity(self):
        # Valid: 3-32 characters, alphanumeric, hyphen, underscore
        self.assertTrue(SteamAPIClient.validate_vanity("vex"))
        self.assertTrue(SteamAPIClient.validate_vanity("s1mple"))
        self.assertTrue(SteamAPIClient.validate_vanity("pro_gamer"))
        self.assertTrue(SteamAPIClient.validate_vanity("cool-name"))
        self.assertTrue(SteamAPIClient.validate_vanity("12345678901234567890123456789012"))  # 32 chars

        # Invalid
        self.assertFalse(SteamAPIClient.validate_vanity("ab"))  # Too short (<3)
        self.assertFalse(SteamAPIClient.validate_vanity("a" * 33))  # Too long (>32)
        self.assertFalse(SteamAPIClient.validate_vanity("name with space"))
        self.assertFalse(SteamAPIClient.validate_vanity("cool!name"))
        self.assertFalse(SteamAPIClient.validate_vanity("user@name"))
        self.assertFalse(SteamAPIClient.validate_vanity(""))

class TestSteamCommunityCheck(unittest.TestCase):
    @patch("requests.Session.get")
    def test_available_community(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<?xml version="1.0" encoding="UTF-8"?><response><error><![CDATA[The specified profile could not be found.]]></error></response>'
        mock_get.return_value = mock_resp

        client = SteamAPIClient()
        res = client.check_vanity("freevanityname")
        self.assertEqual(res["status"], "AVAILABLE")
        self.assertEqual(res["vanity"], "freevanityname")
        self.assertIsNone(res["steamid64"])

    @patch("requests.Session.get")
    def test_taken_community(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '<?xml version="1.0" encoding="UTF-8"?><profile><steamID64>76561197978186923</steamID64><steamID><![CDATA[plastic]]></steamID></profile>'
        mock_get.return_value = mock_resp

        client = SteamAPIClient()
        res = client.check_vanity("s1mple")
        self.assertEqual(res["status"], "TAKEN")
        self.assertEqual(res["vanity"], "s1mple")
        self.assertEqual(res["steamid64"], "76561197978186923")

    @patch("requests.Session.get")
    def test_available_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        client = SteamAPIClient()
        res = client.check_vanity("unregisteredid")
        self.assertEqual(res["status"], "AVAILABLE")

    @patch("requests.Session.get")
    def test_rate_limited_429(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_get.return_value = mock_resp

        client = SteamAPIClient()
        res = client.check_vanity("ratelimitedname")
        self.assertEqual(res["status"], "RATE_LIMITED")
        self.assertEqual(res["vanity"], "ratelimitedname")

class TestSteamDatabase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_steam_names.db"
        self.db = SteamDatabase(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_steam_records(self):
        self.assertFalse(self.db.is_steam_already_checked("phantom"))

        self.db.record_steam_result(
            vanity="phantom",
            status="AVAILABLE",
            length=7,
            details="Free to claim"
        )
        self.assertTrue(self.db.is_steam_already_checked("phantom"))
        self.assertIn("phantom", self.db.get_already_checked_steam_set())

        stats = self.db.get_steam_stats()
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["available"], 1)
        self.assertEqual(stats["taken"], 0)

        records = self.db.get_all_steam_records(filter_status="AVAILABLE")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["vanity"], "phantom")

        # Test search query
        self.db.record_steam_result(vanity="phantasm", status="TAKEN", length=8)
        search_res = self.db.get_all_steam_records(search_query="phant")
        self.assertEqual(len(search_res), 2)

        search_avail = self.db.get_all_steam_records(filter_status="AVAILABLE", search_query="phant")
        self.assertEqual(len(search_avail), 1)
        self.assertEqual(search_avail[0]["vanity"], "phantom")

        self.db.clear_steam_records()
        self.assertEqual(len(self.db.get_all_steam_records()), 0)

    def test_steam_database_over_500_records(self):
        for i in range(600):
            self.db.record_steam_result(vanity=f"v_{i:04d}", status="AVAILABLE", length=6)
        records = self.db.get_all_steam_records()
        self.assertEqual(len(records), 600)

class TestSteamCheckerEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_steam_engine.db"
        self.db = SteamDatabase(db_path=self.db_path)
        self.client = SteamAPIClient()
        self.engine = SteamCheckerEngine(api_client=self.client, database=self.db, threads=2)

    def tearDown(self):
        self.engine.stop()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_names(self):
        names = ["abc", "longervalidname", "ab", "toolong" * 10, "abc"]
        queued = self.engine.load_names(names, skip_checked=True, min_len=3, max_len=32)
        # 'ab' is <3, 'toolong'*10 is >32, 'abc' duplicate -> only 'abc' and 'longervalidname' remain
        self.assertEqual(queued, 2)

    def test_rate_limit_requeues_and_pauses(self):
        results_received = []
        def on_result(res):
            results_received.append(res)

        self.engine.on_result = on_result
        self.engine.cooldown_duration = 1  # 1 second for fast testing

        # Mock check_vanity to return RATE_LIMITED first time, then AVAILABLE
        call_count = 0
        def mock_check(vanity):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "status": "RATE_LIMITED",
                    "vanity": vanity,
                    "length": len(vanity),
                    "steamid64": None,
                    "profile_url": "",
                    "details": "Rate limit"
                }
            return {
                "status": "AVAILABLE",
                "vanity": vanity,
                "length": len(vanity),
                "steamid64": None,
                "profile_url": "",
                "details": "Free to claim"
            }

        self.client.check_vanity = mock_check
        self.engine.load_names(["testvanity"], skip_checked=False)
        self.engine.start()

        import time
        # Wait for cooldown to complete and item to be processed
        time.sleep(2.2)
        self.engine.stop()

        # Check that testvanity was not lost, cooldown events fired, and result eventually became AVAILABLE
        cooldown_starts = [r for r in results_received if r.get("status") == "COOLDOWN_START"]
        cooldown_ends = [r for r in results_received if r.get("status") == "COOLDOWN_END"]
        available_res = [r for r in results_received if r.get("status") == "AVAILABLE"]

        self.assertTrue(len(cooldown_starts) >= 1)
        self.assertTrue(len(cooldown_ends) >= 1)
        self.assertTrue(len(available_res) >= 1)
        self.assertEqual(available_res[0]["vanity"], "testvanity")

    def test_database_duplicate_skip(self):
        def mock_check(vanity):
            if vanity == "takename":
                return {
                    "status": "TAKEN",
                    "vanity": vanity,
                    "length": len(vanity),
                    "steamid64": "76561198000000001",
                    "profile_url": f"https://steamcommunity.com/id/{vanity}/",
                    "details": "Profile active"
                }
            elif vanity == "availname":
                return {
                    "status": "AVAILABLE",
                    "vanity": vanity,
                    "length": len(vanity),
                    "steamid64": None,
                    "profile_url": f"https://steamcommunity.com/id/{vanity}/",
                    "details": "Free to claim"
                }
            return {
                "status": "AVAILABLE",
                "vanity": vanity,
                "length": len(vanity),
                "steamid64": None,
                "profile_url": f"https://steamcommunity.com/id/{vanity}/",
                "details": "Free to claim"
            }

        self.client.check_vanity = mock_check
        self.engine.delay = 0.01

        # Run 1: Check both names
        queued = self.engine.load_names(["takename", "availname"], skip_checked=True)
        self.assertEqual(queued, 2)
        self.assertEqual(self.engine.skipped_db_count, 0)
        self.engine.start()

        import time
        max_wait = 3.0
        start = time.time()
        while (self.engine.checked_count < 2) and (time.time() - start < max_wait):
            time.sleep(0.05)
        self.engine.stop()

        self.assertEqual(self.engine.checked_count, 2)
        self.assertEqual(self.engine.available_count, 1)
        self.assertEqual(self.engine.taken_count, 1)

        # Verify DB recorded both TAKEN and AVAILABLE
        checked_set = self.db.get_already_checked_steam_set()
        self.assertIn("takename", checked_set)
        self.assertIn("availname", checked_set)
        self.assertTrue(self.db.is_steam_already_checked("takename"))
        self.assertTrue(self.db.is_steam_already_checked("availname"))

        # Run 2: Load same names plus a fresh one with skip_checked=True
        queued2 = self.engine.load_names(["takename", "availname", "freshname"], skip_checked=True)
        self.assertEqual(queued2, 1)
        self.assertEqual(self.engine.skipped_db_count, 2)

        # Run 3: Load same names with bypass cache (skip_checked=False)
        queued3 = self.engine.load_names(["takename", "availname", "freshname"], skip_checked=False)
        self.assertEqual(queued3, 3)
        self.assertEqual(self.engine.skipped_db_count, 0)

