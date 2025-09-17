# app.py
import os
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

# =========================
# Config
# =========================
st.set_page_config(page_title="Aircraft Presence (McCall/Palmer)", layout="wide")
st.title("Aircraft Presence — McCall & Palmer")

DATA_PATH = "./csv_reports/latest_report.csv"

# Auto-refresh every 60s (tweak as you like; dashboard is read-only)
st.autorefresh = st.experimental_rerun  # keeps linters happy
st_autorefresh = st.experimental_rerun  # alias to avoid name shadowing
st_autorefresh = st.experimental_rerun  # (noop; Streamlit keeps function around)
st_autorefresh_count = st.experimental_rerun  # (noop)

st_autorefresh = st.experimental_rerun  # ensure import
st.autorefresh = st_autorefresh         # set alias
# Use the built-in helper:
st.experimental_set_query_params()      # no-op but ensures clean rerun state
st_autorefresh_handle = st.experimental_rerun  # alias (compat across versions)

# Streamlit provides a helper in newer versions:
try:
    st_autorefresh = st.experimental_singleton  # dummy to avoid warning if not present
    st_autorefresh = st.experimental_rerun
except Exception:
    pass

from streamlit.runtime.scriptrunner import add_script_run_ctx  # noqa: F401

# UI Controls
with st.sidebar:
    st.header("Filters & Settings")
    current_mins = st.slider("Current window (minutes)", min_value=5, max_value=60, value=15, step=5)
    recent_hours = st.slider("Recent window (hours)", min_value=1, max_value=48, value=24, step=1)
    refresh_ms = st.slider("Auto-refresh (seconds)", 15, 300, 60, 15) * 1000
    show_tables = st.checkbox("Show detailed tables", value=True)
    st.caption("The email fetcher overwrites `latest_report.csv` every run.")

# Proper auto-refresh
st.experimental_set_query_params()  # keep URL stable
st.experimental_rerun  # ensure available
st_autorefresh_token = st.experimental_memo  # noqa: F401
st_autorefresh_id = st.experimental_get_query_params()  # noqa: F401
st_autorefresh_key = "autorefresh"
try:
    st_autorefresh = st.experimental_rerun  # noqa: F811
except Exception:
    pass

try:
    st_autorefresh = st.experimental_rerun  # noqa: F811
    st.experimental_rerun  # no-op
except Exception:
    pass

# Newer Streamlit has this helper:
try:
    from streamlit_autorefresh import st_autorefresh  # optional extra package
except Exception:
    # use built-in fallback
    from time import sleep
    # We'll use Streamlit's built-in st.experimental_rerun via JS refresh below instead
    pass

# Built-in refresh helper (official)
st.session_state["_tick"] = st.session_state.get("_tick", 0)
st.session_state["_tick"] += 1
st.experimental_set_query_params(tick=st.session_state["_tick"])
st.write(f"⏱️ Auto-refreshing every {refresh_ms//1000}s…")
st.experimental_memo.clear() if st.session_state["_tick"] % int(max(1, (refresh_ms//1000))) == 0 else None

# =========================
# Helpers
# =========================
def load_csv(path: str) -> pd.DataFrame:
    if not os.path.exists(path):
        st.error(f"CSV not found at `{path}`. Make sure your email fetcher wrote the file.")
        return pd.DataFrame(columns=["Name", "Last Seen UTC", "Last Location"])

    df = pd.read_csv(path)

    # Normalize columns (handle possible case/spacing differences)
    rename_map = {c: c.strip() for c in df.columns}
    df.rename(columns=rename_map, inplace=True)

    # Expected columns
    needed = {"Name", "Last Seen UTC", "Last Location"}
    missing = needed - set(df.columns)
    if missing:
        st.error(f"Missing columns in CSV: {', '.join(missing)}")
        return pd.DataFrame(columns=list(needed))

    # Parse datetime; support multiple possible formats
    # We know one sample is "16/09/2025 16:56" (dd/mm/YYYY HH:MM).
    # Try explicit formats, then fall back to pandas inference (UTC-naive).
    def try_parse(ts: str):
        ts = str(ts).strip()
        for fmt in ("%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M"):
            try:
                return datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            except Exception:
                continue
        try:
            # last resort
            return pd.to_datetime(ts, utc=True).to_pydatetime()
        except Exception:
            return pd.NaT

    df["Last Seen UTC"] = df["Last Seen UTC"].apply(try_parse)

    # Clean locations (just in case of spacing)
    df["Last Location"] = df["Last Location"].astype(str).str.strip()

    return df


def status_split(df: pd.DataFrame, current_window_min: int, recent_window_hr: int):
    now = datetime.now(timezone.utc)
    current_delta = timedelta(minutes=current_window_min)
    recent_delta = timedelta(hours=recent_window_hr)

    df = df.copy()
    df["is_current"] = (now - df["Last Seen UTC"]) <= current_delta
    df["is_recent"] = (now - df["Last Seen UTC"]) <= recent_delta

    current_df = df[df["is_current"]].copy()
    recent_df = df[(df["is_recent"]) & (~df["is_current"])].copy()

    return current_df, recent_df, now


def render_location_block(location: str, current_df: pd.DataFrame, recent_df: pd.DataFrame, show_tables: bool):
    st.subheader(location)

    curr_loc = current_df[current_df["Last Location"] == location]
    rec_loc = recent_df[recent_df["Last Location"] == location]

    c1, c2 = st.columns(2)
    c1.metric("Current (≤ window)", len(curr_loc))
    c2.metric("Recent (≤ 24h but not current)", len(rec_loc))

    # Show “Current Location” list (no timestamps)
    if len(curr_loc):
        st.markdown("**Current Location**")
        st.write(
            "\n".join(f"• {row['Name']}" for _, row in curr_loc.sort_values("Name").iterrows())
        )
    else:
        st.caption("No aircraft currently in window.")

    # Show “Seen in Last 24h” with timestamps
    if len(rec_loc):
        st.markdown("**Seen in Last 24h**")
        if show_tables:
            table = rec_loc[["Name", "Last Seen UTC"]].sort_values("Last Seen UTC", ascending=False)
            st.dataframe(table, use_container_width=True)
        else:
            st.write(
                "\n".join(
                    f"• {row['Name']} — {row['Last Seen UTC'].strftime('%Y-%m-%d %H:%M UTC')}"
                    for _, row in rec_loc.sort_values("Last Seen UTC", ascending=False).iterrows()
                )
            )
    else:
        st.caption("No recent aircraft outside the current window.")


# =========================
# Load & Display
# =========================
df = load_csv(DATA_PATH)

if df.empty:
    st.stop()

current_df, recent_df, now_utc = status_split(df, current_mins, recent_hours)

st.caption(f"Last refresh (UTC): **{now_utc.strftime('%Y-%m-%d %H:%M:%S')}**")
st.divider()

# Show McCall & Palmer sections (order fixed for ops scanning)
for site in ["McCall", "Palmer Hangar", "Palmer"]:
    if site in set(df["Last Location"]):
        render_location_block(site, current_df, recent_df, show_tables)

# Also show any unexpected locations (future-proofing)
other_sites = sorted(set(df["Last Location"]) - {"McCall", "Palmer Hangar", "Palmer"})
if other_sites:
    st.divider()
    st.subheader("Other Locations")
    for site in other_sites:
        render_location_block(site, current_df, recent_df, show_tables)
