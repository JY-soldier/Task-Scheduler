# app.py：Streamlit 前端主程式，負責 UI、呼叫 LLM 解析與排程、顯示結果

import streamlit as st  # 匯入 Streamlit 做網頁介面
from datetime import datetime, date, timedelta  # 匯入日期時間相關類別
from io import BytesIO  # 匯入 BytesIO 方便處理檔案 in-memory

from llm_parser import parse_input_with_llm  # 從 llm_parser 匯入文字解析函式
from scheduler import build_schedule  # 從 scheduler 匯入排程產生函式
from ics_export import schedule_to_ics, split_schedule_to_ics_for_google  # 匯入匯出 .ics 相關函式

today = datetime.today().date()

# 設定 Streamlit 頁面的標題與版面寬度
st.set_page_config(page_title="作業時間排程 Demo", layout="wide")

# 頁面主標題
st.title("作業時間排程器")

# 說明文字：提示使用者要輸入什麼內容
st.markdown(
    "請貼上你的作業 / 考試 / 固定行程描述（可以是自然語言），"
    "也可以另外上傳作業說明檔（作業要求、講義等）。"
)

# 預設範例文字，顯示在輸入框中
default_example = f"""已完成：
1. 上週高等演算法作業1，寫了大概 7 小時。
2. 上週數位影像處理作業1，寫了大概 12 小時。
3. 上次線代小考前複習 3 小時。
4. 上次計算機圖學期中考複習 8 小時。

未完成：
1. {(today-timedelta(days=1)).strftime("%m/%d")} 早上9點要考線性代數小考 1。
2. {(today+timedelta(days=1)).strftime("%m/%d")} 晚上11:59要交高等演算法作業 2。
3. {(today+timedelta(days=2)).strftime("%m/%d")} 晚上11:59要交數位影像處理作業 2。
4. {(today+timedelta(days=6)).strftime("%m/%d")} 晚上11:59要交高等演算法作業 3。
5. {(today+timedelta(days=7)).strftime("%m/%d")} 早上9點要考線性代數小考 2。
6. {(today+timedelta(days=12)).strftime("%m/%d")} 早上9點要考計算機圖學期末考。
7. {(today+timedelta(days=8)).strftime("%m/%d")} 下午1點要考高等網路期末考。
8. {(today+timedelta(days=10)).strftime("%m/%d")} 早上10點要考高等演算法期末考。

優先級 : 線性代數小考 1 > 線性代數小考 2 > 高等演算法作業 3

固定行程：
1. 每週二晚上 7 點到 9 點補習。
2. {(today+timedelta(days=3)).strftime("%m/%d")} 晚上 6 點到 8 點和家人吃飯。
"""


# ---- 檔案讀取 helper ----
def read_uploaded_file(file) -> str:
    """
    將上傳檔案轉成純文字字串。
    支援：
    - .txt / .md：以 UTF-8 解碼
    - .pdf：用 PyPDF2 讀取文字
    其他格式會回傳提示字串。
    """
    try:
        import PyPDF2  # 嘗試匯入 PyPDF2，用於讀取 PDF
    except ImportError:
        PyPDF2 = None  # 若未安裝則設為 None，後面用來判斷是否可讀 PDF

    filename = file.name  # 取得檔名字串
    data = file.read()  # 讀取檔案內容為 bytes

    mime = file.type or ""  # 取得 MIME type（可能為空字串）
    name_lower = filename.lower()  # 檔名轉成小寫方便判斷副檔名

    # 純文字類（txt / md 或 text/* MIME）
    if (
        mime.startswith("text/")  # 若 MIME 類型是 text/*
        or name_lower.endswith(".txt")  # 或副檔名為 .txt
        or name_lower.endswith(".md")  # 或副檔名為 .md
    ):
        try:
            # 嘗試用 UTF-8 解碼成字串，忽略錯誤
            return data.decode("utf-8", errors="ignore")
        except Exception:
            # 若解碼失敗則回傳錯誤訊息
            return f"[無法以 UTF-8 解讀文字檔：{filename}]"

    # PDF 類型
    if mime == "application/pdf" or name_lower.endswith(".pdf"):  # 判斷是否 PDF
        if PyPDF2 is None:  # 若前面匯入失敗
            return f"[尚未安裝 PyPDF2，無法讀取 PDF：{filename}]"

        try:
            reader = PyPDF2.PdfReader(BytesIO(data))  # 用 BytesIO 包裝 bytes，建立 PDF reader
            texts = []  # 用來累積每一頁文字的 list
            for page in reader.pages:  # 逐頁讀取
                page_text = page.extract_text() or ""  # 取出該頁文字，若為 None 則改為空字串
                texts.append(page_text)  # 加入列表
            # 將所有頁文字合併後去掉前後空白，若沒有內容則回傳提示字串
            return "\n".join(texts).strip() or f"[PDF 檔 {filename} 未偵測到文字內容]"
        except Exception as e:  # 若讀取 PDF 過程出錯
            return f"[讀取 PDF 時發生錯誤 {filename}：{e}]"

    # 其他不支援的格式
    return f"[不支援的檔案格式：{filename}]"


# ✅ 初始化 session_state：確保有 parsed 和 schedule 這兩個 key

if "parsed" not in st.session_state:  # 若 session_state 中還沒有 "parsed"
    st.session_state["parsed"] = None  # 初始化為 None

if "schedule" not in st.session_state:  # 若 session_state 中還沒有 "schedule"
    st.session_state["schedule"] = None  # 初始化為 None


# ---- 排程設定 ----
col1, col2, col3 = st.columns([6, 3, 1])

with col1:
    st.subheader("排程設定")  # 小標題：排程設定區塊

with col3:  # 右欄：把考試複習時間安排在緊鄰考試前
    cram_or_not: bool = st.checkbox("臨時抱佛腳模式", value=True)

col_cfg1, col_cfg2= st.columns(2)  # 建立兩欄，左邊放開始日，右邊放每天最多小時

with col_cfg1:  # 左欄：排程開始日設定
    today = datetime.today().date()  # 取得今天日期（不含時間）
    start_date: date = st.date_input(
        "排程開始日",  # 欄位標題
        value=today,  # 預設值為今天
        min_value=today,  # 不允許選今天以前
        help="從這一天開始往後排作業/複習時段（不可早於今天）。",  # 提示文字
    )

with col_cfg2:  # 右欄：每天最多安排幾小時作業/複習
    max_hours_per_day: int = st.number_input(
        "每天最多安排幾小時（作業/複習）",  # 欄位標題
        min_value=1,  # 最小值 1 小時
        max_value=16,  # 最大值 16 小時
        value=4,  # 預設值 4 小時
        step=1,  # 每次調整步階為 1
        help="只計算作業/複習時間，不包含固定行程。",  # 提示文字
    )

# 再建立三欄，用來放排程天數、開始時間、結束時間
col_cfg3, col_cfg4, col_cfg5 = st.columns(3)

with col_cfg3:  # 排程天數設定欄
    schedule_days: int = st.number_input(
        "排程天數（往後幾天）",  # 欄位標題
        min_value=1,  # 最少 1 天
        max_value=60,  # 最多 60 天
        value=7,  # 預設 7 天
        step=1,  # 每次加減 1 天
        help="從排程開始日往後要排幾天，想排到一個月可以設 30。",  # 提示文字
    )

with col_cfg4:  # 每天排程開始小時欄
    study_start_hour: int = st.number_input(
        "每天排程開始小時（0–23）",  # 欄位標題
        min_value=0,  # 最小 0（凌晨 0 點）
        max_value=23,  # 最大 23（23 點）
        value=19,  # 預設 19（晚上 7 點）
        step=1,  # 每次加減 1 小時
        help="例如晚上 7 點就填 19。",  # 提示文字
    )

with col_cfg5:  # 每天排程結束小時欄
    study_end_hour: int = st.number_input(
        "每天排程結束小時（0–23）",  # 欄位標題
        min_value=0,  # 最小 0
        max_value=23,  # 最大 23
        value=23,  # 預設 23（晚上 11 點）
        step=1,  # 每次加減 1 小時
        help="例如晚上 11 點就填 23。若小於等於開始時間，程式會自動略微調整。",  # 提示文字
    )

if cram_or_not:
    st.write("*** 臨時抱佛腳模式已啟用，把複習時間安排在緊鄰考試前 ***")
else:
    st.write("*** 臨時抱佛腳模式未啟用，考試複習時程安排方式與作業相同 ***")

# 分隔線，讓 UI 區塊更清楚
st.markdown("---")

# ---- 上傳作業說明檔 ----
st.subheader("上傳作業說明檔（選用）")  # 小標題：檔案上傳區

st.caption(
    "可上傳 .txt / .md / .pdf，例如作業要求、講義截圖轉文字等。"
    "這些內容會一併提供給 LLM 解析。"
)  # 說明上傳檔案用途與格式

# 建立兩欄，上傳已完成作業說明檔與未完成作業 / 考試說明檔
col_files1, col_files2 = st.columns(2)

with col_files1:  # 左欄：已完成作業相關說明檔
    done_files = st.file_uploader(
        "已完成作業 / 考試相關說明檔",  # 上傳框標題
        type=["txt", "md", "pdf"],  # 限制副檔名
        accept_multiple_files=True,  # 允許一次上傳多個檔案
    )

with col_files2:  # 右欄：未完成作業 / 考試相關說明檔
    todo_files = st.file_uploader(
        "未完成作業 / 考試相關說明檔",  # 上傳框標題
        type=["txt", "md", "pdf"],  # 限制副檔名
        accept_multiple_files=True,  # 允許多檔上傳
    )

# 再畫一條分隔線
st.markdown("---")

# ---- 文字輸入 ----
# 主要文字輸入區，使用者貼上自然語言描述
raw_text = st.text_area("文字輸入內容：(請輸入你的作業 / 考試 / 固定行程描述，可以設定優先級，優先級高者先排程)", value=default_example, height=250)


# 當按下「生成排程」按鈕時，更新 session_state
if st.button("生成排程"):  # 建立一個按鈕，按下時執行以下區塊
    # 把檔案內容讀出來，附註清楚是什麼類型
    extra_sections = []  # 用來累積上傳檔案文字內容的 list

    if done_files:  # 若有上傳已完成作業說明檔
        for f in done_files:  # 逐一處理每個檔案
            content = read_uploaded_file(f)  # 讀取並轉為文字
            # 加上標頭標明來源是哪個檔案
            extra_sections.append(
                f"[已完成作業 / 考試說明檔：{f.name}]\n{content}"
            )

    if todo_files:  # 若有上傳未完成作業 / 考試說明檔
        for f in todo_files:  # 逐一處理每個檔案
            content = read_uploaded_file(f)  # 讀取並轉為文字
            # 加上標頭標明來源
            extra_sections.append(
                f"[未完成作業 / 考試說明檔：{f.name}]\n{content}"
            )

    # 合併成送給 LLM 的完整文字
    assignment_file = ""  # 先從文字輸入框內容開始
    if extra_sections:  # 若有任何上傳檔案
        assignment_file += (  # 在原文字後加上區隔和各檔案內容
            "\n\n=== 以下為上傳的作業說明檔內容 ===\n\n"
            + "\n\n---\n\n".join(extra_sections)
        )

    # 呼叫 LLM 解析使用者輸入
    with st.spinner("解析輸入內容中（呼叫 Groq LLM）..."):
        parsed = parse_input_with_llm(raw_text, assignment_file, start_date, schedule_days)  # 使用 llm_parser 將文字解析成結構化物件
        if not parsed: st.error("⚠ 發生錯誤 ⚠\n\n可能原因如下 :\n1. GROQ_API_KEY 未設定，呼叫 LLM 失敗\n2. 輸入檔案過大或文字過多，超出 LLM 請求上限\n3. 其他原因，詳情請查看執行檔案畫面")  # 紅色錯誤提示
        else:
                st.session_state["parsed"] = parsed  # 存進 session_state 以便後續使用

    # 根據解析結果進行排程
    with st.spinner("排程中..."):
        if parsed:
            schedule = build_schedule(
                parsed,  # 解析後的結構化資料
                days=schedule_days,  # 往後排幾天，由使用者輸入
                start_date=start_date,  # 排程開始日期
                max_hours_per_day=max_hours_per_day,  # 每天最多作業/複習小時
                study_start_hour=int(study_start_hour),  # 每天排程開始小時（轉成 int）
                study_end_hour=int(study_end_hour),  # 每天排程結束小時（轉成 int）
                cram_or_not=cram_or_not, # 考試複習時間安排模式
            )
            st.session_state["schedule"] = schedule  # 排好的結果存到 session_state


# ✅ 顯示 LLM 解析結果 + 逾期任務
if st.session_state["parsed"] is not None:  # 若已經有解析結果
    parsed = st.session_state["parsed"]  # 取出解析結果物件

    #st.subheader("LLM 解析結果（debug 用，可之後關掉）")  # Debug 用的小標題
    #st.json(parsed.model_dump(), expanded=False)  # 將 Pydantic 模型轉成 dict 再以 JSON 顯示

    # 🔶 額外：找出「逾期任務」（deadline <= 現在）
    now = datetime.now()  # 取得現在時間（含日期與時間）
    overdue_todos = [t for t in parsed.todos if t.deadline <= now]  # 篩選截止時間已過的任務

    if overdue_todos:  # 若有逾期任務
        st.subheader("逾期任務")  # 小標題
        st.warning("以下任務的截止時間已經過去，因此不會被排入未來的時程中：")  # 黃色警告文字

        # 將逾期任務整理成表格資料
        overdue_table = [
            {
                "標題": t.title,  # 任務標題
                "科目": t.subject or "",  # 科目名稱（可能為 None）
                "截止時間": t.deadline.strftime("%Y-%m-%d %H:%M"),  # 格式化截止時間
                "預估時間(分鐘)": t.estimated_time_minutes,  # 預估所需時間
            }
            for t in overdue_todos
        ]
        st.table(overdue_table)  # 用表格顯示逾期任務


# ✅ 顯示排程結果 + 排不完任務 + 下載 .ics
if st.session_state["schedule"] is not None:  # 若已有排程結果
    st.subheader("排程結果")  # 小標題：排程結果
    schedule = st.session_state["schedule"]  # 取出排程結果列表
    parsed = st.session_state["parsed"]  # 再取一次解析結果，方便後續比對

    # ---- 1. 計算哪些任務「排不完」 ----
    # 依標題統計實際已排的分鐘數（只計算 kind == "todo"）
    scheduled_minutes_by_title = {}  # dict：key 為標題，value 為已排總分鐘數
    for b in schedule:  # 逐一檢查所有排程區塊
        if b.kind != "todo":  # 若不是作業/複習類型，就跳過
            continue
        # 計算此區塊長度（分鐘）
        minutes = int((b.end - b.start).total_seconds() // 60)
        # 累加到同標題的總分鐘數
        scheduled_minutes_by_title[b.title] = (
            scheduled_minutes_by_title.get(b.title, 0) + minutes
        )

    now = datetime.now()  # 再取得現在時間，避免前後差異太大
    unschedulable = []  # 用來存放「無法完全安排」的任務資訊列表
    for t in parsed.todos:  # 逐一檢查每一個待辦
        # 忽略已逾期（已在上一段顯示）
        if t.deadline <= now:
            continue

        est = t.estimated_time_minutes or 0  # 預估時間，若為 None 則視為 0
        scheduled = scheduled_minutes_by_title.get(t.title, 0)  # 已排時間，若沒有記錄則為 0
        if scheduled < est:  # 若已排時間小於預估時間
            unschedulable.append(
                {
                    "標題": t.title,  # 任務標題
                    "科目": t.subject or "",  # 科目名稱
                    "截止時間": t.deadline.strftime("%Y-%m-%d %H:%M"),  # 截止時間字串
                    "預估時間(分鐘)": est,  # 預估時間（分鐘）
                    "已排時間(分鐘)": scheduled,  # 已經排進去的總分鐘數
                    "尚未排入(分鐘)": est - scheduled,  # 還差多少分鐘沒排入
                }
            )

    if unschedulable:  # 若有任何任務無法完全安排
        st.markdown("#### 無法完全安排的任務")  # 小標題
        st.error(
            "以下任務在目前設定的排程天數 / 每日作業上限 / 每天排程時段內，無法完全排完預估所需時間："
        )  # 紅色錯誤提示
        st.table(unschedulable)  # 顯示詳細列表

    # ---- 2. 正常排程列表（表格）----
    st.markdown("#### 排程列表")  # 小標題：排程列表
    # 將所有排程區塊整理成表格資料
    table_data = [
        {
            "標題": b.title,  # 事件標題
            "開始": b.start.strftime("%Y-%m-%d %H:%M"),  # 開始時間字串
            "結束": b.end.strftime("%Y-%m-%d %H:%M"),  # 結束時間字串
            "種類": "作業/複習" if b.kind == "todo" else "固定行程",  # 依 kind 顯示中文種類
        }
        for b in schedule
    ]
    st.table(table_data)  # 用表格顯示所有已排事件

    # 畫一條分隔線
    st.markdown("---")

    # ---- 3. 下載 .ics ----

    st.subheader("匯入 Google Calendar")  # 小標題：Google Calendar 區塊
    st.caption("( 或者其他支援.ics檔的日曆 )")

    st.markdown("#### 單一日曆下載")  # 小標題：Google Calendar 區塊

    # 3-1 全部一起版本
    all_ics = schedule_to_ics(schedule)  # 將完整排程轉成單一 .ics 字串
    st.download_button(
        label="【全部行程】.ics",  # 按鈕文字
        data=all_ics,  # .ics 檔案內容
        file_name="study_schedule_all.ics",  # 下載檔名
        mime="text/calendar",  # MIME 型別
    )

    # 3-2 Google Calendar 兩個日曆版本
    fixed_ics, todo_ics = split_schedule_to_ics_for_google(schedule)  # 拆成兩份 .ics

    st.markdown("#### 分成兩個日曆下載")  # 小標題：Google Calendar 區塊
    st.caption("方便分開匯入不同日曆，以顯示不同顏色")

    # 下載固定行程 .ics
    st.download_button(
        label="【固定行程】.ics",  # 按鈕文字
        data=fixed_ics,  # 固定行程 .ics 內容
        file_name="fixed_events.ics",  # 檔名
        mime="text/calendar",  # MIME 型別
    )

    # 下載作業 / 複習 .ics
    st.download_button(
        label="【作業/考試複習】.ics",  # 按鈕文字
        data=todo_ics,  # 作業 / 複習 .ics 內容
        file_name="tasks_events.ics",  # 檔名
        mime="text/calendar",  # MIME 型別
    )
