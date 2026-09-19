"""
Namesniper - Checker Engine Module
Multi-threaded worker queue for checking usernames against Faceit,
with real-time stats, thread-safe persistence, callbacks, and rate limiting.
"""
import time
import queue
import threading
import csv
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable

from config import EXPORTS_DIR, load_config
from database import Database
from faceit_api import FaceitAPIClient

class CheckerEngine:
    def __init__(
        self,
        api_client: FaceitAPIClient,
        database: Database,
        threads: int = 3,
        delay_between_requests: float = 0.35,
        save_taken: bool = False,
        detect_idle: bool = True,
        on_result: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_finish: Optional[Callable[[], None]] = None
    ):
        self.api_client = api_client
        self.database = database
        self.num_threads = max(1, min(threads, 10))
        self.delay = delay_between_requests
        self.save_taken = save_taken
        self.detect_idle = detect_idle
        self.api_client.detect_idle = detect_idle

        # Callbacks
        self.on_result = on_result
        self.on_progress = on_progress
        self.on_finish = on_finish

        # State flags & queue
        self.queue = queue.Queue()
        self.workers: List[threading.Thread] = []
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False

        # Synchronization
        self.lock = threading.Lock()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Unpaused initially

        # Statistics
        self.total_queued = 0
        self.checked_count = 0
        self.available_count = 0
        self.claimable_count = 0
        self.taken_count = 0
        self.invalid_count = 0
        self.error_count = 0
        self.start_time: Optional[float] = None
        self.skip_checked = True
        self.skipped_db_count = 0

        # Files
        self.available_txt = EXPORTS_DIR / "available_names.txt"
        self.available_csv = EXPORTS_DIR / "available_names.csv"
        self._ensure_csv_headers()

    def _ensure_csv_headers(self) -> None:
        """Initialize CSV export file with headers if it does not exist."""
        if not self.available_csv.exists():
            with open(self.available_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Nickname", "Status", "Length", "Created Date", "Country", "ELO", "Games", "Details", "Faceit URL", "Checked At"])

    def _append_to_exports(self, result: Dict[str, Any]) -> None:
        """Thread-safe append of an available or claimable nickname to txt and csv files."""
        nick = result["nickname"]
        status = result["status"]
        
        # Write to TXT
        with open(self.available_txt, "a", encoding="utf-8") as f:
            created_str = f" [Created: {result.get('account_created_at')}]" if result.get("account_created_at") else ""
            if status == "CLAIMABLE_IDLE":
                f.write(f"{nick} [CLAIMABLE IDLE]{created_str}\n")
            else:
                f.write(f"{nick}\n")

        # Write to CSV
        with open(self.available_csv, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([
                nick,
                status,
                result.get("length", len(nick)),
                result.get("account_created_at") or "N/A",
                result.get("country") or "N/A",
                result.get("faceit_elo") or "N/A",
                result.get("games_count", 0),
                result.get("details", ""),
                result.get("faceit_url") or "",
                time.strftime("%Y-%m-%d %H:%M:%S")
            ])

    def load_names(self, names: List[str], skip_checked: bool = True, min_len: int = 3, max_len: int = 12) -> int:
        """
        Load a list of candidate names into the checking queue.
        Deduplicates, validates length and syntax, and optionally filters out names already in DB.
        """
        seen = set()
        clean_names = []
        skipped_db = 0
        
        already_checked = self.database.get_already_checked_set() if skip_checked else set()

        for raw_name in names:
            name = raw_name.strip()
            if not name:
                continue
            name_lower = name.lower()
            if name_lower in seen:
                continue
            if skip_checked and name_lower in already_checked:
                skipped_db += 1
                continue
            if not (min_len <= len(name) <= max_len):
                continue
            if not FaceitAPIClient.validate_nickname(name):
                continue
            seen.add(name_lower)
            clean_names.append(name)

        with self.lock:
            # Clear existing queue
            while not self.queue.empty():
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break

            for name in clean_names:
                self.queue.put(name)

            self.total_queued = len(clean_names)
            self.checked_count = 0
            self.available_count = 0
            self.claimable_count = 0
            self.taken_count = 0
            self.invalid_count = 0
            self.error_count = 0
            self.skip_checked = skip_checked
            self.skipped_db_count = skipped_db

        return len(clean_names)

    def start(self) -> None:
        """Start worker threads to process queue."""
        if self.is_running:
            return

        self.is_running = True
        self.stop_requested = False
        self.is_paused = False
        self.pause_event.set()
        self.start_time = time.time()
        self.workers = []

        for i in range(self.num_threads):
            t = threading.Thread(target=self._worker_loop, name=f"CheckerWorker-{i+1}", daemon=True)
            t.start()
            self.workers.append(t)

        # Monitor thread to check when all items are done
        monitor = threading.Thread(target=self._monitor_loop, name="CheckerMonitor", daemon=True)
        monitor.start()

    def pause(self) -> None:
        """Pause checking."""
        if self.is_running and not self.is_paused:
            self.is_paused = True
            self.pause_event.clear()

    def resume(self) -> None:
        """Resume checking."""
        if self.is_running and self.is_paused:
            self.is_paused = False
            self.pause_event.set()

    def stop(self) -> None:
        """Stop checking immediately."""
        self.stop_requested = True
        self.pause_event.set()  # Unblock any paused workers so they can exit
        self.is_running = False
        self.is_paused = False

    def _worker_loop(self) -> None:
        """Worker thread logic."""
        while not self.stop_requested:
            # Check for pause
            self.pause_event.wait()
            if self.stop_requested:
                break

            try:
                nickname = self.queue.get(timeout=0.5)
            except queue.Empty:
                # No more names in queue
                break

            if self.skip_checked and self.database.is_already_checked(nickname):
                with self.lock:
                    self.skipped_db_count += 1
                self.queue.task_done()
                continue

            try:
                result = self.api_client.check_nickname(nickname)
                status = result.get("status", "ERROR")

                with self.lock:
                    self.checked_count += 1
                    if status == "AVAILABLE":
                        self.available_count += 1
                        self._append_to_exports(result)
                    elif status == "CLAIMABLE_IDLE":
                        self.claimable_count += 1
                        self._append_to_exports(result)
                    elif status == "TAKEN":
                        self.taken_count += 1
                    elif status == "INVALID":
                        self.invalid_count += 1
                    else:
                        self.error_count += 1

                    # Persist to SQLite DB
                    self.database.record_result(
                        nickname=result["nickname"],
                        status=status,
                        length=result.get("length", len(result["nickname"])),
                        player_id=result.get("player_id"),
                        country=result.get("country"),
                        faceit_elo=result.get("faceit_elo"),
                        faceit_url=result.get("faceit_url"),
                        games_count=result.get("games_count", 0),
                        account_created_at=result.get("account_created_at"),
                        details=result.get("details")
                    )

                # Emit callback for result
                if self.on_result:
                    try:
                        self.on_result(result)
                    except Exception as e:
                        print(f"Error in on_result callback: {e}")

                # Emit progress callback
                if self.on_progress:
                    try:
                        stats = self.get_stats()
                        self.on_progress(stats)
                    except Exception as e:
                        print(f"Error in on_progress callback: {e}")

            except Exception as e:
                with self.lock:
                    self.checked_count += 1
                    self.error_count += 1
            finally:
                self.queue.task_done()

            # Respect rate limit delay per thread
            if self.delay > 0 and not self.stop_requested:
                time.sleep(self.delay)

    def _monitor_loop(self) -> None:
        """Monitors workers and fires on_finish when complete."""
        for t in self.workers:
            t.join()

        self.is_running = False
        self.is_paused = False

        if self.on_finish and not self.stop_requested:
            try:
                self.on_finish()
            except Exception as e:
                print(f"Error in on_finish callback: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Return snapshot of current checking session stats."""
        with self.lock:
            elapsed = time.time() - self.start_time if self.start_time else 0.0
            speed = (self.checked_count / elapsed) if elapsed > 0 else 0.0
            remaining = self.total_queued - self.checked_count
            eta_seconds = (remaining / speed) if speed > 0 else 0.0

            return {
                "total": self.total_queued,
                "checked": self.checked_count,
                "remaining": remaining,
                "available": self.available_count,
                "claimable": self.claimable_count,
                "taken": self.taken_count,
                "invalid": self.invalid_count,
                "errors": self.error_count,
                "skipped_db": self.skipped_db_count,
                "elapsed_seconds": round(elapsed, 1),
                "speed_per_sec": round(speed, 2),
                "eta_seconds": int(eta_seconds),
                "is_running": self.is_running,
                "is_paused": self.is_paused
            }
