import gspread
import pandas as pd
import streamlit as st
from google.oauth2.service_account import Credentials

st.set_page_config(page_title="Order Management", layout="wide")

STATUS_OPTIONS = ["New", "In Progress", "Done"]
STATUS_COLORS = {
    "New": "blue",
    "In Progress": "orange",
    "Done": "green",
}
EXPECTED_COLUMNS = [
    "Submission ID",
    "Submission time",
    "Name of business",
    "Name of person",
    "Telephone number",
    "Order",
    "Status",
]


@st.cache_resource
def get_worksheet():
    """Authenticate via Streamlit secrets and return the first worksheet."""
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]),
        scopes=scopes,
    )
    client = gspread.authorize(creds)
    sheet = client.open_by_url(st.secrets["sheet_url"])
    return sheet.sheet1


def load_orders(worksheet) -> pd.DataFrame:
    """Fetch all rows and preserve exact 1-based Google Sheet row numbers."""
    raw_values = worksheet.get_all_values()
    if len(raw_values) <= 1:
        return pd.DataFrame(columns=["_sheet_row"] + EXPECTED_COLUMNS)

    headers = [h.strip() for h in raw_values[0]]
    rows = raw_values[1:]

    padded_rows = [
        row + [""] * (len(headers) - len(row)) for row in rows
    ]
    df = pd.DataFrame(padded_rows, columns=headers)

    df["_sheet_row"] = range(2, len(df) + 2)

    if "Status" not in df.columns:
        df["Status"] = "New"
    df["Status"] = df["Status"].apply(
        lambda x: x.strip() if x.strip() in STATUS_OPTIONS else "New"
    )

    return df


def format_card_header(row: pd.Series) -> str:
    """Build a status-colored expander header."""
    status = row["Status"]
    color = STATUS_COLORS.get(status, "gray")
    return (
        f":{color}[**{status}**] — "
        f"**{row['Name of business']}** ({row['Name of person']} • {row['Telephone number']})"
    )


# --- UI Layout ---
st.title("Wholesale Order Manager")

try:
    ws = get_worksheet()
except Exception as e:
    st.error(f"Failed to connect to Google Sheets: {e}")
    st.stop()

col_refresh, col_filter = st.columns([1, 3])
with col_refresh:
    if st.button("Refresh Orders", use_container_width=True):
        st.rerun()

df = load_orders(ws)

if df.empty:
    st.info("No orders found in the sheet yet.")
    st.stop()

# Summary metrics
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Orders", len(df))
m2.metric("New", int((df["Status"] == "New").sum()))
m3.metric("In Progress", int((df["Status"] == "In Progress").sum()))
m4.metric("Done", int((df["Status"] == "Done").sum()))

st.divider()

with col_filter:
    selected_statuses = st.multiselect(
        "Filter by Status",
        options=STATUS_OPTIONS,
        default=["New", "In Progress"],
    )

search_query = st.text_input(
    "Search by Submission ID, business, contact, phone, or order details"
)

filtered_df = df[df["Status"].isin(selected_statuses)].copy()
if search_query.strip():
    q = search_query.strip().lower()
    searchable_cols = [
        c
        for c in [
            "Submission ID",
            "Name of business",
            "Name of person",
            "Telephone number",
            "Order",
        ]
        if c in filtered_df.columns
    ]
    mask = pd.Series(False, index=filtered_df.index)
    for col in searchable_cols:
        mask = mask | filtered_df[col].str.lower().str.contains(q, na=False)
    filtered_df = filtered_df[mask]

if filtered_df.empty:
    st.info("No orders match the current filters.")
    st.stop()

sheet_headers = [h.strip() for h in ws.row_values(1)]
status_col_idx = sheet_headers.index("Status") + 1

for _, row in filtered_df.iterrows():
    sheet_row_num = int(row["_sheet_row"])
    with st.expander(format_card_header(row), expanded=False):
        col_order, col_status = st.columns([3, 1])

        with col_order:
            st.caption(
                f"Submitted: {row['Submission time']} | Submission ID: {row['Submission ID']}"
            )
            st.markdown("**Order Items:**")
            st.text(row["Order"])

        with col_status:
            current_idx = (
                STATUS_OPTIONS.index(row["Status"])
                if row["Status"] in STATUS_OPTIONS
                else 0
            )
            new_status = st.selectbox(
                "Status",
                options=STATUS_OPTIONS,
                index=current_idx,
                key=f"status_{sheet_row_num}",
            )
            if st.button("Update Status", key=f"save_{sheet_row_num}", type="primary"):
                if new_status != row["Status"]:
                    ws.update_cell(sheet_row_num, status_col_idx, new_status)
                    st.success("Status updated in Google Sheets.")
                    st.rerun()
                else:
                    st.info("Status is already set to that value.")