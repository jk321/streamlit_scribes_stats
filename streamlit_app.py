import streamlit as st
from notion_client import Client
import pandas as pd

# ------------- Notion helpers -------------

def get_text_from_property(prop):
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
    return str(prop)


def fetch_notion_rows(notion: Client, database_id: str):
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
    records = []
    for r in rows:
        props = r.get("properties", {})

        scribal_hand = get_text_from_property(props.get("scribal hand id"))
        scribe_name = get_text_from_property(props.get("scribe's name"))
        shelfmark = get_text_from_property(props.get("shelfmark"))

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
    st.set_page_config(layout="wide")

    # 🔒 Hide Streamlit menu/header/footer
    st.markdown(
        """
        <style>
        #MainMenu {visibility: hidden;}
        header {visibility: hidden;}
        footer {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )

    notion_api_key = st.secrets["NOTION_API_KEY"]
    database_id = st.secrets["DATABASE_ID"]
    notion = Client(auth=notion_api_key)

    rows = fetch_notion_rows(notion, database_id)
    df = rows_to_dataframe(rows)

    if df.empty:
        st.error("No data returned from Notion.")
        return

    df["scribal_hand_id"] = df["scribal_hand_id"].astype(str)
    df = df[df["scribal_hand_id"].str.strip() != ""]

    # scribal_hand_id -> label (scribal hand id — first scribe name)
    mapping = {}
    for shid, group in df.groupby("scribal_hand_id"):
        non_empty_names = group["scribe_name"][group["scribe_name"].astype(str).str.strip() != ""]
        label_name = non_empty_names.iloc[0] if not non_empty_names.empty else ""
        label = f"{shid} — {label_name}" if label_name else shid
        mapping[shid] = label

    if not mapping:
        st.error("No scribal hand ids found.")
        return

    options = sorted(mapping.keys(), key=lambda k: mapping[k])

    # Small sidebar selector only
    selected_shid = st.sidebar.selectbox(
        "scribal hand",
        options=options,
        format_func=lambda k: mapping[k],
    )

    sub = df[df["scribal_hand_id"] == selected_shid]

    # 1) Manuscripts associated (unique shelfmarks)
    unique_shelfmarks = sorted(
        {s for s in sub["shelfmark"].astype(str).str.strip().tolist() if s}
    )
    num_shelfmarks = len(unique_shelfmarks)
    shelfmarks_str = ", ".join(unique_shelfmarks)

    # 2) Number of colophons (addition checked)
    num_colophons = sub["addition"].astype(bool).sum()

    # 🔹 Minimal output
    st.markdown(
        f"**Manuscripts associated:** {num_shelfmarks}"
        + (f" : {shelfmarks_str}" if shelfmarks_str else "")
    )
    st.markdown(f"**Number of colophons:** {num_colophons}")


if __name__ == "__main__":
    main()
