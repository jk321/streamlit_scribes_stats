import streamlit as st
from notion_client import Client
import pandas as pd

# ------------- Notion helpers -------------

def get_text_from_property(prop):
    """
    Safely extract plain text from various Notion property types.
    Adjust if your schema is different.
    """
    if prop is None:
        return ""

    t = prop.get("type")

    if t == "title":
        return "".join([r.get("plain_text", "") for r in prop["title"]])
    if t == "rich_text":
        return "".join([r.get("plain_text", "") for r in prop["rich_text"]])
    if t == "select":
        return prop["select"]["name"] if prop["select"] else ""
    if t == "multi_select":
        return ", ".join([o["name"] for o in prop["multi_select"]])
    if t == "people":
        return ", ".join([p.get("name", "") for p in prop["people"]])
    if t == "number":
        return prop["number"]
    if t == "checkbox":
        return prop["checkbox"]
    # fallback
    return str(prop)


def fetch_notion_rows(notion: Client, database_id: str):
    """Fetch all rows from the Notion database (with pagination)."""
    results = []
    cursor = None

    while True:
        kwargs = {"database_id": database_id}
        if cursor:
            kwargs["start_cursor"] = cursor

        resp = notion.databases.query(**kwargs)
        results.extend(resp["results"])

        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")

    return results


def rows_to_dataframe(rows):
    """
    Convert Notion rows to a pandas DataFrame with the properties we care about:
    - scribal hand id
    - scribe's name
    - shelfmark
    - addition (checkbox)
    """

    records = []
    for r in rows:
        props = r.get("properties", {})

        scribal_hand = get_text_from_property(props.get("scribal hand id"))
        scribe_name = get_text_from_property(props.get("scribe's name"))
        shelfmark = get_text_from_property(props.get("shelfmark"))

        # "addition" is a checkbox property
        addition_raw = props.get("addition", {})
        addition_val = False
        if addition_raw and addition_raw.get("type") == "checkbox":
            addition_val = bool(addition_raw.get("checkbox"))

        records.append(
            {
                "scribal_hand_id": scribal_hand,
                "scribe_name": scribe_name,
                "shelfmark": shelfmark,
                "addition": addition_val,
            }
        )

    df = pd.DataFrame(records)
    return df


# ------------- Streamlit app -------------

def main():
    st.set_page_config(page_title="Scribal Hand Explorer", layout="wide")
    st.title("📜 Scribal Hand Explorer")

    # Load Notion client from Streamlit secrets
    notion_api_key = st.secrets["NOTION_API_KEY"]
    database_id = st.secrets["DATABASE_ID"]
    notion = Client(auth=notion_api_key)

    st.info("Fetching data from Notion…")
    rows = fetch_notion_rows(notion, database_id)
    df = rows_to_dataframe(rows)

    if df.empty:
        st.error("No data returned from Notion. Check DB ID & integration permissions.")
        return

    # Drop blank scribal hand ids
    df["scribal_hand_id"] = df["scribal_hand_id"].astype(str)
    df = df[df["scribal_hand_id"].str.strip() != ""]

    # 1) Build mapping: scribal_hand_id -> first non-empty scribe_name
    mapping = {}
    for shid, group in df.groupby("scribal_hand_id"):
        non_empty_names = group["scribe_name"][group["scribe_name"].astype(str).str.strip() != ""]
        label_name = non_empty_names.iloc[0] if not non_empty_names.empty else ""
        if label_name:
            label = f"{shid} — {label_name}"
        else:
            label = shid
        mapping[shid] = label

    if not mapping:
        st.error("No scribal hand ids found in the data.")
        return

    options = sorted(mapping.keys(), key=lambda k: mapping[k])

    st.sidebar.header("Select scribal hand")
    selected_shid = st.sidebar.selectbox(
        "Scribal hand",
        options=options,
        format_func=lambda k: mapping[k],
    )

    sub = df[df["scribal_hand_id"] == selected_shid]

    st.subheader(f"Scribal hand: {mapping[selected_shid]}")

    # 1) Shelfmarks: unique list + count
    unique_shelfmarks = sorted(
        {s for s in sub["shelfmark"].astype(str).str.strip().tolist() if s}
    )
    num_shelfmarks = len(unique_shelfmarks)

    st.markdown("### 1. Shelfmarks")
    st.write(f"**Number of shelfmarks for this scribal hand id:** `{num_shelfmarks}`")

    if num_shelfmarks > 0:
        st.write("**Shelfmark list:**")
        st.write(unique_shelfmarks)
    else:
        st.write("_No shelfmarks found for this scribal hand id._")

    # 2) Number of colophons (rows where `addition` checkbox is checked)
    num_colophons = sub["addition"].astype(bool).sum()

    st.markdown("### 2. Colophons (rows with `addition` checked)")
    st.write(f"**Number of colophons:** `{num_colophons}`")

    with st.expander("Show raw rows for this scribal hand id"):
        st.dataframe(sub)


if __name__ == "__main__":
    main()
