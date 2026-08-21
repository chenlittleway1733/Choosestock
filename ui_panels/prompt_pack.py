"""Prompt-pack panel extracted from ui_main.py."""

import json

from ui_common import components, st


def render_prompt_pack_panel(
    *,
    curr_id,
    buy_decision_prompt,
    research_prompt,
    build_technical_suffix,
):
    """Render the copyable prompt-pack panel.

    `build_technical_suffix` stays in ui_main for now because it depends on the
    current stock chart locals. Keeping it as a callback lets this panel move
    without changing prompt behavior.
    """
    with st.expander("📋 點此複製【打包提示詞】至 Gemini Advanced 或 ChatGPT 發問", expanded=True):
        prompt_mode = st.radio(
            "提示詞版本",
            ["買進決策版（精簡，建議平常使用）", "研究完整版（完整，適合深度分析）"],
            horizontal=True,
            key=f"prompt_pack_mode_{curr_id}",
        )
        technical_pack_mode = st.radio(
            "技術面打包選項",
            ["不加入技術面", "加入技術面摘要", "加入技術面摘要 + 技術線圖輔助規則"],
            horizontal=True,
            key=f"prompt_technical_pack_mode_{curr_id}",
        )

        selected_prompt = buy_decision_prompt if prompt_mode.startswith("買進決策版") else research_prompt
        technical_suffix = build_technical_suffix(technical_pack_mode)
        if technical_suffix:
            selected_prompt = selected_prompt.rstrip() + "\n\n" + technical_suffix
        st.caption("買進決策版只保留會影響是否買進的採用值、系統/AI差異、估值層級、產業模型、Dynamic Cap 與燈號；研究完整版保留較完整資料品質與來源摘要。技術面可選擇不加入、加入摘要，或加入摘要與線圖輔助規則。")

        safe_prompt_js = json.dumps(selected_prompt, ensure_ascii=False)
        components.html(
            f"""
            <div style="margin: 10px 0 12px 0; font-family: sans-serif;">
                <button
                    onclick="copyPromptToClipboard()"
                    style="
                        width: 100%;
                        padding: 13px 14px;
                        border-radius: 10px;
                        border: 1px solid #4b5563;
                        background: #2563eb;
                        color: white;
                        font-size: 16px;
                        font-weight: 700;
                        cursor: pointer;
                    "
                >
                    📋 一鍵複製目前版本提示詞
                </button>
                <div id="copyStatus" style="margin-top: 8px; color: #16a34a; font-size: 14px;"></div>
            </div>

            <script>
            async function copyPromptToClipboard() {{
                const text = {safe_prompt_js};
                const status = document.getElementById("copyStatus");

                try {{
                    await navigator.clipboard.writeText(text);
                    status.innerText = "✅ 已複製目前版本提示詞，可直接貼到 Gemini Advanced 或 ChatGPT。";
                }} catch (err) {{
                    const textarea = document.createElement("textarea");
                    textarea.value = text;
                    textarea.style.position = "fixed";
                    textarea.style.left = "-9999px";
                    textarea.style.top = "0";
                    document.body.appendChild(textarea);
                    textarea.focus();
                    textarea.select();

                    try {{
                        document.execCommand("copy");
                        status.innerText = "✅ 已複製目前版本提示詞，可直接貼上使用。";
                    }} catch (fallbackErr) {{
                        status.style.color = "#dc2626";
                        status.innerText = "⚠️ 手機瀏覽器限制自動複製，請改用下方文字框長按複製。";
                    }}

                    document.body.removeChild(textarea);
                }}
            }}
            </script>
            """,
            height=105,
        )

        mode_key = "buy" if prompt_mode.startswith("買進決策版") else "research"
        st.text_area(
            "提示詞內容",
            value=selected_prompt,
            height=330,
            label_visibility="collapsed",
            key=f"copy_prompt_textarea_{curr_id}_{mode_key}_{abs(hash(selected_prompt)) % 100000000}",
        )

