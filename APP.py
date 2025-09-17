import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ----------------------------
# Config
# ----------------------------
st.set_page_config(page_title="Aircraft Presence (McCall/Palmer)", layout="wide")
st.title("Aircraft Presence — McCall & Palmer")

DATA_PATH = "./csv_reports/latest_report.csv"

# Auto-refresh every 60s (adjust as needed)
st_autorefresh(interval=60 * 1000, key="gpsfeedrefresh")

# ----------------------------
# Helpers
# ----------------------------
def load_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        st.error(f"CSV not found at `{path}`. Make sure your email fetcher wrote the file.")
        return pd.DataFrame(columns=["Name", "Last Seen UTC", "Last Location"])

    df = pd.read_csv(path)

    # Normalize column names
    df.columns = [c.strip() for c in df.columns]

    # Parse datetime
    def try_parse(ts: str):
        ts = str(ts).strip()
        for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M"):
            try:
                return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            except Exception:
                continue
        try:
            return pd.to_datetime(ts, utc=True).to_pydatetime()
        except Exception:
            return pd.NaT

    df["Last Seen UTC"] = df["Last Seen UTC"].apply(try_parse)
    df["Last Location"] = df["Last Location"].astype(str).str.strip()

    return df


def split_status(df: pd.DataFrame, current_window_min: int = 15, recent_window_hr: int = 24):
    now = datetime.now(timezone.utc)
    current_delta = timedelta(minutes=current_window_min)
    recent_delta = timedelta(hours=recent_window_hr)

    df = df.copy()
    df["is_current"] = (now - df["Last Seen UTC"]) <= current_delta
    df["is_recent"] = (now - df["Last Seen UTC"]) <= recent_delta

    current_df = df[df["is_current"]].copy()
    recent_df = df[(df["is_recent"]) & (~df["is_current"])].copy()

    return current_df, recent_df, now


def render_location_block(location: str, current_df: pd.DataFrame, recent_df: pd.DataFrame):
    st.subheader(location)

    curr_loc = current_df[current_df["Last Location"] == location]
    rec_loc = recent_df[recent_df["Last Location"] == location]

    c1, c2 = st.columns(2)
    c1.metric("Current (≤15m)", len(curr_loc))
    c2.metric("Recent (≤24h, not current)", len(rec_loc))

    # Current list (no timestamps)
    if len(curr_loc):
        st.markdown("**Current Location**")
        st.write("\n".join(f"• {row['Name']}" for _, row in curr_loc.sort_values("Name").iterrows()))
    else:
        st.caption("No aircraft currently in window.")

    # Recent list (with timestamps)
    if len(rec_loc):
        st.markdown("**Seen in Last 24h**")
        table = rec_loc[["Name", "Last Seen UTC"]].sort_values("Last Seen UTC", ascending=False)
        st.dataframe(table, use_container_width=True)
    else:
        st.caption("No recent aircraft outside the current window.")


# ----------------------------
# Main
# ----------------------------
df = load_csv(DATA_PATH)

if df.empty:
    st.stop()

current_df, recent_df, now_utc = split_status(df)

st.caption(f"Last refresh (UTC): **{now_utc.strftime('%Y-%m-%d %H:%M:%S')}**")
st.divider()

# Show McCall & Palmer first
for site in ["McCall", "Palmer Hangar", "Palmer"]:
    if site in set(df["Last Location"]):
        render_location_block(site, current_df, recent_df)

# Show any other locations
other_sites = sorted(set(df["Last Location"]) - {"McCall", "Palmer Hangar", "Palmer"})
if other_sites:
    st.divider()
    st.subheader("Other Locations")
    for site in other_sites:
        render_location_block(site, current_df, recent_df)
