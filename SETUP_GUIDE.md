# Strava → Google Sheets Sync — Setup Guide

This script automatically pulls your run data (distance, pace, duration) from Strava and writes it into your Google Sheets marathon training tracker.

---

## Prerequisites

- Python 3.8+
- A Strava account with recorded activities
- A Google Sheets training tracker with dates in one column

---

## Step 1: Create a Strava API Application

1. Go to [https://www.strava.com/settings/api](https://www.strava.com/settings/api)
2. Fill in the form:
   - **Application Name:** Marathon Tracker Sync (or anything you like)
   - **Category:** Data Importer
   - **Club:** (leave blank)
   - **Website:** `http://localhost`
   - **Authorization Callback Domain:** `localhost`
3. Click **Create**
4. Note your **Client ID** and **Client Secret** — you'll need these for `config.json`

---

## Step 2: Set Up Google Sheets API Access

You need a Google Cloud **service account** so the script can write to your sheet without manual login each time.

### 2a. Create a Google Cloud Project

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Click the project dropdown (top-left) → **New Project**
3. Name it (e.g., "Strava Sync") → **Create**
4. Make sure the new project is selected

### 2b. Enable the APIs

1. Go to **APIs & Services → Library**
2. Search for and enable:
   - **Google Sheets API**
   - **Google Drive API**

### 2c. Create a Service Account

1. Go to **APIs & Services → Credentials**
2. Click **Create Credentials → Service Account**
3. Name it (e.g., "strava-sync") → **Create and Continue**
4. Skip the optional role/access steps → **Done**
5. Click on the service account you just created
6. Go to the **Keys** tab → **Add Key → Create new key → JSON**
7. Download the JSON file and save it as `service-account.json` in the same folder as the script

### 2d. Share Your Google Sheet with the Service Account

1. Open the downloaded JSON file and find the `client_email` field (looks like `strava-sync@project-name.iam.gserviceaccount.com`)
2. Open your Google Sheet
3. Click **Share** → paste the service account email → give **Editor** access
4. Click **Send** (uncheck "Notify people" if prompted)

---

## Step 3: Configure the Script

1. Copy the example config:
   ```bash
   cp config.example.json config.json
   ```

2. Edit `config.json` with your details. To find your **spreadsheet ID**, look at your Google Sheet URL — it's the long string between `/d/` and `/edit`:
   ```
   https://docs.google.com/spreadsheets/d/THIS_PART_IS_YOUR_ID/edit
   ```
   Your spreadsheet ID is already pre-filled in the example config.

   ```json
   {
     "strava": {
       "client_id": "123456",
       "client_secret": "abcdef1234567890..."
     },
     "google": {
       "service_account_json": "service-account.json",
       "spreadsheet_id": "YOUR_SPREADSHEET_ID_HERE"
     },
     "sheet_mapping": {
       "sheet_name": "Sheet1",
       "date_column": 1,
       "distance_column": 3,
       "pace_column": 4,
       "duration_column": 5,
       "notes_column": null
     },
     "units": "miles"
   }
   ```

### Sheet Mapping Explained

The `sheet_mapping` section tells the script where to find and write data. Column numbers are 1-indexed (A=1, B=2, C=3, etc.).

| Field | What it does | Example |
|---|---|---|
| `sheet_name` | The tab/worksheet name | `"Sheet1"` or `"Training Log"` |
| `date_column` | Column containing your training dates | `1` (column A) |
| `distance_column` | Column to write actual distance into | `3` (column C) |
| `pace_column` | Column to write actual pace into | `4` (column D) |
| `duration_column` | Column to write duration (optional, set `null` to skip) | `5` (column E) |
| `notes_column` | Column to write Strava activity name (optional) | `null` |

**Important:** The script matches Strava activities to rows by looking up the activity date in your date column. Make sure your sheet has dates for the days you want to sync.

### Units

Set `"units"` to `"miles"` or `"km"` depending on your preference. Pace will be displayed as min/mi or min/km accordingly.

---

## Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Step 5: Authorize Strava (One-Time)

Run the auth flow — this opens your browser to grant the script access to your Strava data:

```bash
python strava_sheets_sync.py --auth
```

Click **Authorize** in the browser. The script will capture the tokens and save them to `config.json`. You only need to do this once.

---

## Step 6: Run the Sync

```bash
# Sync today's activities
python strava_sheets_sync.py

# Sync the last 7 days
python strava_sheets_sync.py --days 7

# Preview without writing (dry run)
python strava_sheets_sync.py --days 7 --dry-run
```

---

## Step 7: Automate Daily Syncing

### macOS — using launchd (recommended)

Unlike cron, **launchd** will automatically run missed jobs when your Mac wakes from sleep, so you never skip a sync.

1. Create the plist file at `~/Library/LaunchAgents/com.strava.sheets-sync.plist`:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
     "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.strava.sheets-sync</string>

       <key>ProgramArguments</key>
       <array>
           <string>/usr/bin/python3</string>
           <string>strava_sheets_sync.py</string>
           <string>--days</string>
           <string>1</string>
       </array>

       <key>WorkingDirectory</key>
       <string>/path/to/strava-sheets-sync</string>

       <key>StartCalendarInterval</key>
       <dict>
           <key>Hour</key>
           <integer>22</integer>
           <key>Minute</key>
           <integer>0</integer>
       </dict>

       <key>StandardOutPath</key>
       <string>/path/to/strava-sheets-sync/sync.log</string>

       <key>StandardErrorPath</key>
       <string>/path/to/strava-sheets-sync/sync.log</string>
   </dict>
   </plist>
   ```
   Replace `/path/to/strava-sheets-sync` with your actual folder path and adjust the Python path if needed (`which python3` to find it).

2. Load the job:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.strava.sheets-sync.plist
   ```

3. To verify it's loaded:
   ```bash
   launchctl list | grep strava
   ```

4. To stop/unload it later:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.strava.sheets-sync.plist
   ```

### Linux — using cron

1. Open your crontab:
   ```bash
   crontab -e
   ```

2. Add a line to run the script daily at 10 PM:
   ```
   0 22 * * * cd /path/to/strava-sheets-sync && /usr/bin/python3 strava_sheets_sync.py --days 1 >> sync.log 2>&1
   ```
   Replace `/path/to/strava-sheets-sync` with the actual folder path and adjust the Python path if needed (`which python3` to find it).
   
   > **Note:** cron only runs when the machine is awake. If your Linux machine sleeps, consider using an `anacron` or `systemd timer` instead.

---

## Troubleshooting

**"No runs found"** — The script only fetches activities of type "Run". If your Strava activities are logged as a different type (Walk, Hike, etc.), you may need to adjust the `activity_type` parameter in the code.

**"Could not find matching date rows"** — The dates in your Google Sheet need to match the dates of your Strava activities. The script tries several date formats (YYYY-MM-DD, MM/DD/YYYY, etc.) but if yours is unusual, check the `normalize_date` function.

**"Token refresh failed"** — Your Strava refresh token may have been revoked. Run `python strava_sheets_sync.py --auth` again.

**"Permission denied" on Google Sheets** — Make sure you shared the sheet with the service account email (see Step 2d).
