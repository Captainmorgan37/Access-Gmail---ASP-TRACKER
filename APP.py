import imaplib
import email
from datetime import datetime, timedelta, timezone
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from zoneinfo import ZoneInfo

# ----------------------------
# Config
# ----------------------------
st.set_page_config(page_title="Aircraft Presence (McCall/Palmer)", layout="wide")
st.title("Aircraft Presence — McCall & Palmer")

# Auto-refresh every 60s
st_autorefresh(interval=60 * 1000, key="gpsfeedrefresh")

# Load credentials from secrets
EMAIL_ACCOUNT = st.secrets["EMAIL_ACCOUNT"]
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
IMAP_SERVER = st.secrets.get("IMAP_SERVER", "imap.gmail.com")

SENDER = "no-reply@telematics.guru"
SUBJECT = "ASP TRACKING EMAIL"
FILENAME = "IOCCReport-2ndIteration.csv"

# Local timezone (Mountain Time)
LOCAL_TZ = ZoneInfo("America/Edmonton")


# ----------------------------
# Helpers
# ----------------------------
def fetch_latest_csv() -> pd.DataFrame:
    """Fetch the latest CSV attachment from Gmail and return as DataFrame"""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ACCOUNT, EMAIL_PASSWORD)
        mail.select("inbox")

        # Search by sender + subject
        status, messages = mail.search(
            None, f'(FROM "{SENDER}" SUBJECT "{SUBJECT}")'
        )

        if status != "OK" or not messages[0]:
            st.warning("No matching emails found.")
            return pd.DataFrame()

        latest_id = messages[0].split()[-1]
        status, msg_data = mail.fetch(latest_id, "(RFC822)")
        msg = email.message_from_bytes(msg_data[0][1])

        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            if part.get("Content-Disposition") is None:
                continue
            filename = part.get_filename()
            if filename and filename == FILENAME:
                payload = part.get_payload(decode=True)
                df = pd.read_csv(pd.io.common.BytesIO(payload))
                return df

        st.error("CSV attachment not found in latest email.")
        return pd.DataFrame()

    except Exception as e:
        st.error(f"Error fetching email: {e}")
        return pd.DataFrame()


def parse_df(df: pd.DataFrame):
    """Parse timestamps as local Mountain Time and clean columns"""
    if df.empty:
        return df

    df.columns = [c.strip() for c in df.columns]

    if "Last Seen UTC" in df.columns:
        df.rename(columns={"Last Seen UTC": "Last Seen (MT)"}, inplace=True)

    def parse_local(ts: str):
        ts = str(ts).strip()
        for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M"):
            try:
                return datetime.strptime(ts, fmt).replace(tzinfo=LOCAL_TZ)
            except Exception:
                continue
        try:
            dt = pd.to_datetime(ts, errors="coerce")
            if pd.isna(dt):
                return pd.NaT
            if dt.tzinfo is None:
                return dt.to_pydatetime().replace(tzinfo=LOCAL_TZ)
            return dt.to_pydatetime().astimezone(LOCAL_TZ)
        except Exception:
            return pd.NaT

    df["Last Seen (MT)"] = df["Last Seen (MT)"].apply(parse_local)
    df["Last Location"] = df["Last Location"].astype(str).str.strip()
    return df


def split_status(df: pd.DataFrame, current_window_min: int = 15, recent_window_hr: int = 24):
    now = datetime.now(LOCAL_TZ)
    current_delta = timedelta(minutes=current_window_min)
    recent_delta = timedelta(hours=recent_window_hr)

    df = df.copy()
    seen = df["Last Seen (MT)"]

    df["is_current"] = (now - seen) <= current_delta
    df["is_recent"] = (now - seen) <= recent_delta

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
        st.markdown("**Current Location (local MT time)**")
        st.write("\n".join(f"• {row['Name']}" for _, row in curr_loc.sort_values("Name").iterrows()))
    else:
        st.caption("No aircraft currently in window.")

    # Recent list (with MT timestamps)
    if len(rec_loc):
        st.markdown("**Seen in Last 24h (MT)**")
        table = rec_loc[["Name", "Last Seen (MT)"]].copy()
        table["Last Seen (MT)"] = table["Last Seen (MT)"].dt.strftime("%Y-%m-%d %H:%M %Z")
        table = table.sort_values("Last Seen (MT)", ascending=False)
        st.dataframe(table, use_container_width=True)
    else:
        st.caption("No recent aircraft outside the current window.")


# ----------------------------
# Main
# ----------------------------
df = fetch_latest_csv()
df = parse_df(df)

if df.empty:
    st.stop()

current_df, recent_df, now_mt = split_status(df)
now_utc = now_mt.astimezone(timezone.utc)

st.caption(
    f"Last refresh — Local (MT): **{now_mt.strftime('%Y-%m-%d %H:%M:%S %Z')}**  |  "
    f"UTC: **{now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}**"
)
st.info("Note: Source timestamps are **local Mountain Time**; the original CSV header was mislabeled as UTC.")
st.divider()

# McCall & Palmer first
for site in ["McCall", "Palmer Hangar", "Palmer"]:
    if site in set(df["Last Location"]):
        render_location_block(site, current_df, recent_df)

# Other locations
other_sites = sorted(set(df["Last Location"]) - {"McCall", "Palmer Hangar", "Palmer"})
if other_sites:
    st.divider()
    st.subheader("Other Locations")
    for site in other_sites:
        render_location_block(site, current_df, recent_df)
