# Strava → Google Sheets Sync

Automatically sync your Strava running data to Google Sheets for seamless marathon training tracking.

## Overview

This Python script pulls your latest Strava activities and writes distance, pace, and duration data into your Google Sheets training tracker. Perfect for runners who want to track their training progress without manual data entry.

## Features

- **Automatic Data Sync**: Pulls distance, pace, duration, and activity names from Strava
- **OAuth Authentication**: Secure authentication with Strava API
- **Google Sheets Integration**: Uses service account for automated access
- **Flexible Scheduling**: Support for daily automated syncing via launchd (macOS) or cron (Linux)
- **Date Matching**: Intelligently matches activities to your existing training schedule by date
- **Multiple Units**: Support for miles or kilometers

## Quick Start

1. **Prerequisites**
   - Python 3.8+
   - A Strava account with recorded activities
   - A Google Sheets training tracker

2. **Setup**
   - See [SETUP_GUIDE.md](SETUP_GUIDE.md) for detailed installation and configuration instructions

3. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initial Authentication**
   ```bash
   python strava_sheets_sync.py --auth
   ```

## Usage

```bash
# Sync today's activities
python strava_sheets_sync.py

# Sync the last 7 days
python strava_sheets_sync.py --days 7

# Preview without writing (dry run)
python strava_sheets_sync.py --days 7 --dry-run
```

## How It Works

1. Fetches your run activities from Strava using the API
2. Matches activity dates with rows in your Google Sheet
3. Writes distance, pace, and duration into configured columns
4. Can be scheduled to run automatically every day

## Tech Stack

- **Python 3.8+**
- **Strava API** - OAuth2 authentication and activity data
- **Google Sheets API** - Service account integration
- **Dependencies**: `requests`, `gspread`, `google-auth`

## Configuration

Copy `config.example.json` to `config.json` and fill in:
- Strava API credentials (client ID & secret)
- Google service account file path
- Google Sheets spreadsheet ID
- Column mappings for your sheet layout

See [SETUP_GUIDE.md](SETUP_GUIDE.md) for step-by-step setup instructions.

## License

MIT
