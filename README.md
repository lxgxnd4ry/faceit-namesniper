# Namesniper

Fully vibecoded multi-threaded Faceit username availability checker and account scanner.
![GUI IMAGE](https://github.com/lxgxnd4ry/faceit-namesniper/blob/main/gui.png)
Provides a frameless desktop GUI and an interactive terminal CLI for discovering available usernames and claimable idle accounts on Faceit.

---

## Capabilities

- **Status Detection**:
  - `AVAILABLE`: Name is unregistered and available for immediate registration (HTTP 404).
  - `CLAIMABLE (IDLE)`: Registered account with 0 matches or inactive history eligible for release under Faceit idle policy.
  - `TAKEN`: Active account with game statistics, ELO, and registration date.
- **Wordlists**:
  - Handpicked single-word gaming terms (`og_cool_words.txt`).
  - Short 3-letter combinations (`short_3l.txt`).
  - Short 4-letter words (`short_4l.txt`).
  - English vocabulary subset (`dictionary_words.txt`).
- **Algorithmic Generator**:
  - Pronounceable 3-letter (CVC) and 4-letter (CVCV) generation.
  - Compound handle generation.
  - Custom pattern templates (`C`=consonant, `V`=vowel, `L`=letter, `D`=digit).
- **Concurrency & Rate Limiting**:
  - Configurable worker threads (default: 3).
  - Adaptive rate limiter with exponential backoff on HTTP 429.
  - Multi-key rotation support.
  - HTTP and SOCKS5 proxy support.
- **Data & Exporting**:
  - SQLite cache (`namesniper.db`) prevents duplicate lookups.
  - Automatic real-time output to `exports/available_names.txt` and `exports/available_names.csv`.

---

## Pre-compiled Release

Pre-built binaries for Windows 64-bit are published under GitHub Releases:

1. Download `Namesniper-v1.0.0-windows-x64.zip`.
2. Extract the archive.
3. Run `Namesniper.exe`.

---

## Running from Source

### Requirements

- Python 3.10 or higher (Windows 10/11 recommended).
- Microsoft Edge WebView2 runtime (installed by default on Windows 10/11).

### Setup

```powershell
git clone https://github.com/<username>/Namesniper.git
cd Namesniper
python -m pip install -r requirements.txt
```

---

## Usage

### Launch GUI (Default)

```powershell
python main.py
```

### Launch Interactive CLI

```powershell
python main.py --cli
```

### CLI Command-Line Arguments

```powershell
# Check curated wordlist with custom thread count
python main.py --cli -w og -t 4

# Check short 3-letter combinations
python main.py --cli -w 3l

# Check short 4-letter words
python main.py --cli -w 4l

# Check custom file
python main.py --cli -w path/to/words.txt

# Run generator for 4-letter pronounceable handles
python main.py --cli -g 4l -t 4

# Test API key validity
python main.py --test-key "YOUR_KEY"

# Print database statistics
python main.py --stats
```

---

## Faceit API Key Setup

Faceit Data API access requires a free developer key:

1. Sign in to the [Faceit Developer Portal](https://developers.faceit.com/).
2. Open **App Studio** and click **New App**.
3. Under the **API Keys** tab, generate a **Server Side** key.
4. Open Namesniper Settings, paste the key into the input field, and save.

Multiple keys can be supplied as comma-separated values to enable round-robin rotation across workers.

---

## Steam API Key Setup (Optional)

The Steam vanity checker operates via public XML profiles by default without an API key. For higher rate limit resilience and API resolution fallback, a free key can be registered:

1. Sign in to the [Steam Community Developer Key Registration](https://steamcommunity.com/dev/apikey).
2. Enter any domain name (e.g., `localhost` or `namesniper`).
3. Agree to the terms and click **Register**.
4. Paste the Web API key into Namesniper Settings > Steam API key.

---

## Configuration

Settings are saved in `config.json` (see `config.example.json`):

```json
{
    "api_keys": [],
    "active_key": "",
    "threads": 3,
    "delay_between_requests": 0.35,
    "save_taken": false,
    "filter_min_length": 3,
    "filter_max_length": 12,
    "detect_idle_accounts": true,
    "skip_already_checked": true,
    "proxies": [],
    "proxy_enabled": false,
    "export_format": "txt"
}
```

---

## Tests

Run automated test suite:

```powershell
python -m unittest discover tests
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
