#!/usr/bin/env python3
"""
Strava → Google Sheets Marathon Training Sync
==============================================
Pulls your latest Strava activities and writes distance + pace
data into your Google Sheets marathon training tracker.

Usage:
    python strava_sheets_sync.py              # sync today's activities
    python strava_sheets_sync.py --days 7     # sync last 7 days
    python strava_sheets_sync.py --auth       # initial Strava OAuth setup

Requires config.json (copy from config.example.json and fill in your keys).
"""

import argparse
import json
import os
import sys
import time
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

import requests
import gspread
from google.oauth2.service_account import Credentials


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, "config.json")


def load_config():
    """Load configuration from config.json."""
    if not os.path.exists(CONFIG_PATH):
        print("ERROR: config.json not found. Copy config.example.json → config.json and fill in your keys.")
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        return json.load(f)


def save_config(config):
    """Save updated config (e.g. refreshed tokens) back to config.json."""
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


# ---------------------------------------------------------------------------
# Strava OAuth2
# ---------------------------------------------------------------------------

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Tiny HTTP handler to capture the OAuth redirect."""
    auth_code = None

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        OAuthCallbackHandler.auth_code = query.get("code", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<html><body><h2>Authorization successful!</h2>"
                         b"<p>You can close this tab and return to the terminal.</p></body></html>")

    def log_message(self, format, *args):
        pass  # suppress console noise


def strava_initial_auth(config):
    """
    Run the one-time OAuth2 authorization flow for Strava.
    Opens a browser, captures the code via a local redirect, and exchanges
    it for access + refresh tokens which are saved to config.json.
    """
    client_id = config["strava"]["client_id"]
    client_secret = config["strava"]["client_secret"]
    redirect_uri = "http://localhost:8089/callback"

    auth_url = (
        f"https://www.strava.com/oauth/authorize"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope=activity:read_all"
        f"&approval_prompt=auto"
    )

    print("\n🏃 Opening Strava in your browser for authorization...")
    print(f"   If the browser doesn't open, visit:\n   {auth_url}\n")
    webbrowser.open(auth_url)

    server = HTTPServer(("localhost", 8089), OAuthCallbackHandler)
    server.timeout = 120
    print("   Waiting for authorization (timeout: 2 minutes)...")
    server.handle_request()

    code = OAuthCallbackHandler.auth_code
    if not code:
        print("ERROR: No authorization code received.")
        sys.exit(1)

    # Exchange code for tokens
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
    })
    resp.raise_for_status()
    tokens = resp.json()

    config["strava"]["access_token"] = tokens["access_token"]
    config["strava"]["refresh_token"] = tokens["refresh_token"]
    config["strava"]["token_expires_at"] = tokens["expires_at"]
    save_config(config)

    print("✅ Strava authorization complete. Tokens saved to config.json.\n")


def ensure_strava_token(config):
    """Refresh the Strava access token if it has expired."""
    expires_at = config["strava"].get("token_expires_at", 0)
    if time.time() < expires_at - 60:
        return config["strava"]["access_token"]

    print("   Refreshing Strava access token...")
    resp = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": config["strava"]["client_id"],
        "client_secret": config["strava"]["client_secret"],
        "grant_type": "refresh_token",
        "refresh_token": config["strava"]["refresh_token"],
    })
    resp.raise_for_status()
    tokens = resp.json()

    config["strava"]["access_token"] = tokens["access_token"]
    config["strava"]["refresh_token"] = tokens["refresh_token"]
    config["strava"]["token_expires_at"] = tokens["expires_at"]
    save_config(config)

    return tokens["access_token"]


# ---------------------------------------------------------------------------
# Strava API — Fetch Activities
# ---------------------------------------------------------------------------

def fetch_activities(access_token, after_timestamp, activity_type="Run"):
    """
    Fetch activities from Strava after a given Unix timestamp.
    Returns a list of activity dicts filtered to runs (by default).
    """
    activities = []
    page = 1
    per_page = 50

    while True:
        resp = requests.get(
            "https://www.strava.com/api/v3/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"after": int(after_timestamp), "page": page, "per_page": per_page},
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        activities.extend(batch)
        if len(batch) < per_page:
            break
        page += 1

    # Filter to the desired type
    if activity_type:
        activities = [a for a in activities if a.get("type") == activity_type]

    return activities


def parse_activity(activity, units="miles"):
    """
    Extract the fields we care about from a Strava activity dict.
    Returns a dict with: date, distance, pace, duration, name.
    """
    # Distance: Strava returns meters
    distance_m = activity["distance"]
    if units == "miles":
        distance = distance_m / 1609.344
        unit_label = "mi"
    else:
        distance = distance_m / 1000.0
        unit_label = "km"

    # Pace: minutes per unit
    moving_time_s = activity["moving_time"]
    if distance > 0:
        pace_total_seconds = moving_time_s / distance
        pace_min = int(pace_total_seconds // 60)
        pace_sec = int(pace_total_seconds % 60)
        pace_str = f"{pace_min}:{pace_sec:02d}"
    else:
        pace_str = "N/A"

    # Duration as HH:MM:SS
    hours = moving_time_s // 3600
    mins = (moving_time_s % 3600) // 60
    secs = moving_time_s % 60
    if hours:
        duration_str = f"{int(hours)}:{int(mins):02d}:{int(secs):02d}"
    else:
        duration_str = f"{int(mins)}:{int(secs):02d}"

    # Date (local to the activity)
    start_local = activity.get("start_date_local", activity["start_date"])
    dt = datetime.fromisoformat(start_local.replace("Z", "+00:00"))
    date_str = dt.strftime("%Y-%m-%d")

    return {
        "date": date_str,
        "distance": round(distance, 2),
        "pace": pace_str,
        "duration": duration_str,
        "name": activity.get("name", ""),
    }


# ---------------------------------------------------------------------------
# Google Sheets — Write Data
# ---------------------------------------------------------------------------

def open_sheet(config):
    """Authenticate with Google and open the target spreadsheet."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_file(
        config["google"]["service_account_json"],
        scopes=scopes,
    )
    gc = gspread.authorize(creds)

    spreadsheet_id = config["google"]["spreadsheet_id"]
    return gc.open_by_key(spreadsheet_id)


def find_date_row(worksheet, date_str, date_col):
    """
    Find the row number in the worksheet where the date column matches date_str.
    Returns the row number (1-indexed) or None if not found.
    """
    date_values = worksheet.col_values(date_col)
    for i, val in enumerate(date_values, start=1):
        # Normalize the date format for comparison
        normalized = normalize_date(val)
        if normalized == date_str:
            return i
    return None


def normalize_date(val):
    """Try to parse various date formats into YYYY-MM-DD."""
    if not val:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(val.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return val.strip()


def update_sheet(config, activities_parsed):
    """
    Write parsed activity data into the Google Sheet.
    Matches rows by date and writes distance + pace into the configured columns.
    """
    mapping = config["sheet_mapping"]
    sheet_name = mapping.get("sheet_name", "Sheet1")
    date_col = mapping["date_column"]             # e.g. 1 for column A
    distance_col = mapping["distance_column"]     # e.g. 5 for column E
    pace_col = mapping["pace_column"]             # e.g. 6 for column F
    duration_col = mapping.get("duration_column") # optional
    notes_col = mapping.get("notes_column")       # optional — writes activity name

    spreadsheet = open_sheet(config)
    worksheet = spreadsheet.worksheet(sheet_name)

    updates = 0
    skipped = []

    for act in activities_parsed:
        row = find_date_row(worksheet, act["date"], date_col)
        if row is None:
            skipped.append(act["date"])
            continue

        # Build batch of cells to update
        cells_to_update = [
            gspread.Cell(row, distance_col, act["distance"]),
            gspread.Cell(row, pace_col, act["pace"]),
        ]
        if duration_col:
            cells_to_update.append(gspread.Cell(row, duration_col, act["duration"]))
        if notes_col and act["name"]:
            cells_to_update.append(gspread.Cell(row, notes_col, act["name"]))

        worksheet.update_cells(cells_to_update, value_input_option='USER_ENTERED')
        updates += 1
        print(f"   ✅ {act['date']}: {act['distance']} — {act['pace']}")

    return updates, skipped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Sync Strava activities to Google Sheets")
    parser.add_argument("--auth", action="store_true", help="Run initial Strava OAuth setup")
    parser.add_argument("--days", type=int, default=1, help="Number of days to look back (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and display data without writing to Sheets")
    args = parser.parse_args()

    config = load_config()

    # --- Auth flow ---
    if args.auth:
        strava_initial_auth(config)
        return

    # --- Preflight checks ---
    if not config["strava"].get("refresh_token"):
        print("ERROR: No Strava tokens found. Run with --auth first.")
        sys.exit(1)

    if not os.path.exists(config["google"]["service_account_json"]):
        print(f"ERROR: Google service account file not found at: {config['google']['service_account_json']}")
        sys.exit(1)

    # --- Fetch ---
    access_token = ensure_strava_token(config)
    after = datetime.now(timezone.utc) - timedelta(days=args.days)
    after_ts = after.timestamp()

    print(f"\n🏃 Fetching Strava runs from the last {args.days} day(s)...")
    activities = fetch_activities(access_token, after_ts)

    if not activities:
        print("   No runs found in that time range.")
        return

    units = config.get("units", "miles")
    parsed = [parse_activity(a, units=units) for a in activities]
    parsed.sort(key=lambda x: x["date"])

    print(f"   Found {len(parsed)} run(s):\n")
    for p in parsed:
        print(f"   📅 {p['date']}  |  {p['distance']} {units}  |  {p['pace']}  |  {p['duration']}  |  {p['name']}")

    if args.dry_run:
        print("\n   (Dry run — no data written to Google Sheets)")
        return

    # --- Write ---
    print(f"\n📊 Writing to Google Sheets...")
    updates, skipped = update_sheet(config, parsed)

    print(f"\n✅ Done! Updated {updates} row(s).")
    if skipped:
        print(f"   ⚠️  Could not find matching date rows for: {', '.join(skipped)}")
        print("   (Make sure those dates exist in your sheet's date column.)")


if __name__ == "__main__":
    main()
