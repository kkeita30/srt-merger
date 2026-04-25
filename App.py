import os
import tempfile

import srt
import streamlit as st

from merge_srt import dummy_convert, merge_subtitles

st.title("SRTマージャー")

st.info(
    "音声認識ソフトで書き出したSRTファイルの字幕を整形するツールです。\n"
    "形態素解析を使って不自然な途中切れをマージし、句読点の削除・漢数字の変換・"
    "タイムスタンプの連結などを自動で行います。\n"
    "誤字脱字・誤変換の修正機能はありません。\n"
    "また、完全な自動修正ではないため、出力後に手動での調整が必要です。"
)

# ---- サイドバー：検索置換 ----
st.sidebar.header("検索置換")

if "replacements" not in st.session_state:
    st.session_state["replacements"] = []

with st.sidebar.form("add_replacement", clear_on_submit=True):
    search_word  = st.text_input("検索語")
    replace_word = st.text_input("置換後")
    submitted = st.form_submit_button("追加")
    if submitted and search_word:
        st.session_state["replacements"].append({"from": search_word, "to": replace_word})

if st.session_state["replacements"]:
    st.sidebar.subheader("登録済み")
    for i, r in enumerate(st.session_state["replacements"]):
        col_label, col_del = st.sidebar.columns([4, 1])
        col_label.text(f"{r['from']} → {r['to']}")
        if col_del.button("✕", key=f"del_{i}"):
            st.session_state["replacements"].pop(i)
            st.rerun()

# ---- メイン ----
mode = st.radio("モード", ["通常マージ", "ダミー変換"])

if mode == "ダミー変換":
    gap_sec = st.number_input("無音ギャップ（秒）", min_value=1.0, max_value=60.0, value=10.0, step=1.0)

uploaded = st.file_uploader("SRTファイルをアップロード", type=["srt"])

col_run, col_dl = st.columns([1, 2])

with col_run:
    run = st.button("実行", disabled=not uploaded)

if run and uploaded:
    replacements = {r["from"]: r["to"] for r in st.session_state["replacements"]}

    with tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode="wb") as f:
        f.write(uploaded.read())
        tmp_path = f.name

    try:
        if mode == "通常マージ":
            result = merge_subtitles(tmp_path, replacements=replacements)
        else:
            result = dummy_convert(tmp_path, gap_sec=gap_sec)
    finally:
        os.unlink(tmp_path)

    st.session_state["result"] = result
    st.session_state["mode"] = mode

if "result" in st.session_state:
    result = st.session_state["result"]
    is_dummy = st.session_state["mode"] == "ダミー変換"
    filename = "output_dummy.srt" if is_dummy else "output_merged.srt"

    with col_dl:
        st.download_button(
            label="処理済みSRTをダウンロード",
            data=srt.compose(result),
            file_name=filename,
            mime="text/plain",
        )

    st.subheader(f"処理結果（先頭30ブロック / 合計 {len(result)} ブロック）")
    for sub in result[:30]:
        st.text(
            f"{sub.index}  "
            f"{srt.timedelta_to_srt_timestamp(sub.start)} --> "
            f"{srt.timedelta_to_srt_timestamp(sub.end)}"
        )
        st.text(sub.content)
        st.divider()
