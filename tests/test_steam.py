"""
Unit Tests for Steam Vanity / ID Checker Module
"""
import unittest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

from database import Database
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

class TestSteamDatabase(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_steam.db"
        self.db = Database(db_path=self.db_path)

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

        self.db.clear_steam_records()
        self.assertEqual(len(self.db.get_all_steam_records()), 0)

class TestSteamCheckerEngine(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_steam_engine.db"
        self.db = Database(db_path=self.db_path)
        self.client = SteamAPIClient()
        self.engine = SteamCheckerEngine(api_client=self.client, database=self.db, threads=2)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_load_names(self):
        names = ["abc", "longervalidname", "ab", "toolong" * 10, "abc"]
        queued = self.engine.load_names(names, skip_checked=True, min_len=3, max_len=32)
        # 'ab' is <3, 'toolong'*10 is >32, 'abc' duplicate -> only 'abc' and 'longervalidname' remain
        self.assertEqual(queued, 2)
