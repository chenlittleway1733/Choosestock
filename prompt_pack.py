"""Essential-data prompt-pack panel."""

import json

from ui_common import components, st


def render_prompt_pack_panel(*, curr_id, prompt):
    """Render one compact prompt; missing fields are omitted by its builder."""
    with st.expander("📋 點此複製【精簡提示詞】至 Gemini Advanced 或 ChatGPT 發問", expanded=True):
        selected_prompt = str(prompt or "").strip()
        st.caption("只打包系統已取得的核心資料；缺失欄位不放入資料包，但提示詞會要求外部 AI 先上網查詢、儘量補齊後再判斷。")

        safe_prompt_js = json.dumps(selected_prompt, ensure_ascii=False)
        components.html(
            f"""
            <div style="margin:10px 0 12px 0;font-family:sans-serif;">
                <button onclick="copyPromptToClipboard()" style="width:100%;padding:13px 14px;border-radius:10px;border:1px solid #4b5563;background:#2563eb;color:white;font-size:16px;font-weight:700;cursor:pointer;">
                    📋 一鍵複製目前版本精簡提示詞
                </button>
                <div id="copyStatus" style="margin-top:8px;color:#16a34a;font-size:14px;"></div>
            </div>
            <script>
            async function copyPromptToClipboard() {{
                const text = {safe_prompt_js};
                const status = document.getElementById("copyStatus");
                try {{
                    await navigator.clipboard.writeText(text);
                    status.innerText = "✅ 已複製核心資料精簡提示詞。";
                }} catch (err) {{
                    const textarea = document.createElement("textarea");
                    textarea.value = text;
                    textarea.style.position = "fixed";
                    textarea.style.left = "-9999px";
                    document.body.appendChild(textarea);
                    textarea.focus();
                    textarea.select();
                    try {{
                        document.execCommand("copy");
                        status.innerText = "✅ 已複製核心資料精簡提示詞。";
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

        st.text_area(
            "提示詞內容",
            value=selected_prompt,
            height=330,
            label_visibility="collapsed",
            key=f"copy_prompt_textarea_{curr_id}_{abs(hash(selected_prompt)) % 100000000}",
        )
