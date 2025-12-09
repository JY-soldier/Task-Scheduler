# llm_parser.py：負責呼叫 Groq LLM 或使用內建 demo，將自然語言轉成結構化排程資料

from datetime import date, datetime, timedelta  # 用於 demo 資料產生時間
from typing import Optional  # Optional 型別註解

from models import DifficultyResult, ParsedInput, PastTask, TodoTask, FixedEvent  # 匯入資料模型類別


# 👉 想用哪個 Groq 模型改這行即可
#GROQ_MODEL_NAME = "llama-3.1-8b-instant"  # Groq LLM 使用的模型名稱
GROQ_MODEL_NAME = "openai/gpt-oss-120b"

# 有 Groq API 就用 True，沒有就設 False 只用 demo 資料
USE_GROQ = True  # 控制是否實際呼叫 Groq，若改為 False 則一律用 fallback demo 資料


def _parse_with_groq(raw_text: str, assignment_file: str, schedule_start: date, schedule_days: int) -> Optional[ParsedInput]:
    """
    嘗試使用 Groq LLM 解析使用者輸入的自然語言。
    成功時回傳 ParsedInput，失敗時回傳 None。
    """
    from typing import Optional  # 再次匯入 Optional（其實前面已匯入，這行可以視為冗餘）

    try:
        from groq import Groq  # 匯入 Groq 客戶端套件
        import os  # 匯入 os 用來讀環境變數
        import re  # 匯入 re 用來處理字串中的 ```json code block

        api_key = os.getenv("GROQ_API_KEY")  # 從環境變數讀取 Groq API key
        if not api_key:  # 若沒有設定 API key
            #print("⚠ GROQ_API_KEY 未設定，改用內建測試資料")  # 印出警告訊息
            print("⚠ GROQ_API_KEY 未設定，呼叫 LLM 失敗")  # 印出警告訊息
            return None  # 回傳 None，呼叫端會改用 demo 資料

        client = Groq(api_key=api_key)  # 建立 Groq API client 實例

        schedule_end = schedule_start + timedelta(days=schedule_days - 1) # 排程結束日計算

        # 定義給 Groq 的 system prompt，根據說明檔判定難易度
        system_prompt1 = """
        你是一個幫忙估計學生作業、報告和考試難易程度的助理。
        現在要為學生判斷作業、報告和考試的難易程度。
        使用者會貼出自然語言說明他的作業、報告和考試。
        請你根據"已完成作業 / 考試說明檔(past_tasks)"和"未完成作業 / 考試說明檔(todos)"輸出JSON，格式為：
        {
          "past_tasks": [
            {
              "title": "string",
              "difficulty": 1
            }
          ],
          "todos": [
            {
              "title": "string",
              "difficulty": 1
            }
          ]
        }
        
        重要規則：
        1. "title" 根據說明檔的檔名設定。
        2. "difficulty" 必須是正整數，難度越大則 difficulty 越大，與完成作業所需時間成正比。
        3. 第一個判斷的說明檔的 "difficulty" 必須設定為 10，其他說明檔的 difficulty 以第一個說明檔的難易度為基準做判斷。
        4. 只輸出合法 JSON，不要加註解或多餘文字。
        """

        if assignment_file:
            # 呼叫 Groq 的 chat.completions API 產生回應
            completion = client.chat.completions.create(
                model=GROQ_MODEL_NAME,  # 指定模型名稱
                messages=[
                    {"role": "system", "content": system_prompt1},  # system 訊息，定義任務與格式
                    {"role": "user", "content": assignment_file},  # user 訊息，放使用者輸入的原始文字
                ],
                temperature=0.2,  # 溫度設比較低，結果更穩定
            )

            # 取得 LLM 回傳的主要文字內容
            content = completion.choices[0].message.content
            raw = content.strip()  # 去掉前後空白

            # 1️⃣ 如果有 ```json ... ``` code block，先去掉外層
            if raw.startswith("```"):  # 檢查是否以 ``` 開頭（包含 ```json）
                # 去掉開頭 ``` 或 ```json 這一行
                raw = re.sub(r"^```[a-zA-Z0-9]*\s*", "", raw)
                # 去掉最後的 ```，以及前面的空白換行
                raw = re.sub(r"\s*```$", "", raw).strip()

            # 2️⃣ 只抓第一個 { 到最後一個 } 之間的內容
            first = raw.find("{")  # 找到第一個 '{' 的位置
            last = raw.rfind("}")  # 找到最後一個 '}' 的位置
            if first == -1 or last == -1:  # 若找不到大括號
                print("⚠ Groq 回傳內容找不到大括號，原始內容：", content)  # 印出原始內容
                return None  # 回傳 None，讓上層改用 demo

            json_str = raw[first: last + 1]  # 取出完整 JSON 字串範圍
            #print("====================")
            #print(json_str)

            # 3️⃣ 丟給 Pydantic 解析
            difficulty_result = DifficultyResult.model_validate_json(json_str)  # 使用 Pydantic 的 JSON 解析功能
            print("==================== 難度解析結果 ====================")
            print(difficulty_result)
            print("====================================================")

            if difficulty_result.past_tasks or difficulty_result.todos:
                lines = []
                lines.append("以下是作業 / 考試難易度評估：")
                for t in difficulty_result.past_tasks:
                    lines.append(f"[已完成] {t.title} 難度={t.difficulty}")
                for t in difficulty_result.todos:
                    lines.append(f"[未完成] {t.title} 難度={t.difficulty}")
                raw_text += "\n\n" + "\n".join(lines) + "\n\n"

        # 定義給 Groq 的 system prompt，說明要的 JSON 格式與規則
        system_prompt2 = f"""
        你是一個幫忙整理學生行程的助理。
        現在要為學生在 {schedule_start:%Y-%m-%d} 到 {schedule_end:%Y-%m-%d} 這段期間安排時程。
        使用者會貼出自然語言說明他的作業、考試和已經排好的行程。
        請你輸出 JSON，格式為：
        {{
          "past_tasks": [
            {{
              "title": "string",
              "subject": "string or null",
              "time_spent_minutes": 90,
              "difficulty": 1
            }}
          ],
          "todos": [
            {{
              "title": "string",
              "subject": "string or null",
              "deadline": "2025-12-05T23:59",
              "estimated_time_minutes": 120,
              "difficulty": 1,
              "priority": 1,
              "exam_or_not": false
            }}
          ],
          "fixed_events": [
            {{
              "title": "string",
              "start": "2025-12-02T18:00",
              "end": "2025-12-02T20:00"
            }}
          ]
        }}
        
        重要規則：
        1. "fixed_events" 必須展開成「實際的每一次行程」。
           - 如果文字中出現「每週三晚上 6 點到 9 點補習」這種表達，
             你要在 {schedule_start:%Y-%m-%d} ~ {schedule_end:%Y-%m-%d} 這段期間內，
             找出所有符合「週三」的日期，並為每一天建立一筆固定行程。
           - 例如，如果排程期間包含 2025-12-10, 2025-12-17, 2025-12-24 這三個週三，
             則 fixed_events 要包含三筆 "補習" 事件，時間分別為：
               2025-12-10 19:00~21:00
               2025-12-17 19:00~21:00
               2025-12-24 19:00~21:00
        2. 如果文字中只有寫「12/11 晚上 7 點到 8 點和家人吃飯」這種單次活動， 就只建立一筆 fixed_event。
        3. 所有日期時間一律使用 ISO 8601 格式，例如 "2025-12-05T23:59"。
        4. "difficulty" 的設定只做抄寫，根據輸入文字後半段的JSON內容抄寫，沒寫的不要自己猜。
        5. 如果文字中出現「作業 / 考試難易度評估」這種表達，則根據文字後半段JSON格式的內容中 "title"(特別注意:"演算法作業1"和"演算法作業2"兩個是不同事件，不能共用或推斷彼此的 difficulty) 和「已完成(past_tasks)/未完成(todos)」填寫對應 "difficulty" ，如果輸出JSON格式中需要填寫 "difficulty" ，但是輸入文字後半段JSON中並未寫明，則一律設定成-1。
        6. "estimated_time_minutes" 絕對不能是 0 或負數。
        7. (1) 如果past_tasks和todos中有相似的事件，則根據使用者類似事件的 past_tasks 耗時和對應事件的"difficulty"，自動推估未完成作業的 estimated_time_minutes(difficulty越大則estimated_time_minutes越大)。 (2) 如果past_tasks和todos中相似事件的difficulty有缺漏(例如已完成線代作業1的difficulty=8、未完成線代作業2的difficulty=-1)，則用past_tasks和todos各項之間的關聯性推算。 (3) 推算不出來的話則同科目和同類型(例如都是考試) → 採用平均值或近似推估。 (4) 資訊嚴重不足時根據未完成作業自己的已知資訊和常識推算。
        8. 如果文字中有出現「必須優先處理」、「優先排程」、「a>b>c」等表達，則給對應事件設定 "priority"，優先級越高則priority越小，範圍為0~100之間的正整數；其他未說明優先級的事件，priority一律設定成101。
        9. 未完成事件(todos)的 "title" 中如果有出現「考試」、「小考」、「期中考」、「期末考」等文字，則將對應的 "exam_or_not" 設定成 true，沒有出現則設定成 false。
        10. 只輸出合法 JSON，不要加註解或多餘文字。
        """

        # 呼叫 Groq 的 chat.completions API 產生回應
        completion = client.chat.completions.create(
            model=GROQ_MODEL_NAME,  # 指定模型名稱
            messages=[
                {"role": "system", "content": system_prompt2},  # system 訊息，定義任務與格式
                {"role": "user", "content": raw_text},  # user 訊息，放使用者輸入的原始文字
            ],
            temperature=0.2,  # 溫度設比較低，結果更穩定
        )

        # 取得 LLM 回傳的主要文字內容
        content = completion.choices[0].message.content
        raw = content.strip()  # 去掉前後空白

        # 1️⃣ 如果有 ```json ... ``` code block，先去掉外層
        if raw.startswith("```"):  # 檢查是否以 ``` 開頭（包含 ```json）
            # 去掉開頭 ``` 或 ```json 這一行
            raw = re.sub(r"^```[a-zA-Z0-9]*\s*", "", raw)
            # 去掉最後的 ```，以及前面的空白換行
            raw = re.sub(r"\s*```$", "", raw).strip()

        # 2️⃣ 只抓第一個 { 到最後一個 } 之間的內容
        first = raw.find("{")  # 找到第一個 '{' 的位置
        last = raw.rfind("}")  # 找到最後一個 '}' 的位置
        if first == -1 or last == -1:  # 若找不到大括號
            print("⚠ Groq 回傳內容找不到大括號，原始內容：", content)  # 印出原始內容
            return None  # 回傳 None，讓上層改用 demo

        json_str = raw[first : last + 1]  # 取出完整 JSON 字串範圍

        # 3️⃣ 丟給 Pydantic 解析
        parsed = ParsedInput.model_validate_json(json_str)  # 使用 Pydantic 的 JSON 解析功能
        return parsed  # 回傳解析後的 ParsedInput 實例

    except Exception as e:  # 若在上述任一步驟發生例外
        print("⚠ Groq 解析失敗：", e)  # 印出錯誤訊息
        return None  # 回傳 None，呼叫端會改用 demo 資料


def _fallback_demo_data() -> ParsedInput:
    """
    不呼叫任何 LLM，直接回傳一份固定的測試資料。
    方便在沒 API 或 API 爆掉時依然可以測排程和 UI。
    """
    now = datetime.now()  # 取得現在時間，用來產生相對時間的 demo 資料

    # 建立過去完成的作業紀錄列表
    past_tasks = [
        PastTask(
            title="離散數學作業 3",  # 任務標題
            subject="離散數學",  # 科目
            time_spent_minutes=120,  # 花費時間（分鐘）
        ),
        PastTask(
            title="線代小考前複習",
            subject="線性代數",
            time_spent_minutes=180,
        ),
    ]

    # 建立未完成的作業 / 考試列表（todos）
    todos = [
        TodoTask(
            title="線性代數小考",  # 未來要考的小考
            subject="線性代數",  # 科目
            deadline=(now + timedelta(days=3)).replace(
                hour=23, minute=59, second=0, microsecond=0
            ),  # 截止時間：3 天後 23:59
            estimated_time_minutes=180,  # 3 小時預估準備時間
        ),
        TodoTask(
            title="交離散數學作業 4",
            subject="離散數學",
            deadline=(now + timedelta(days=5)).replace(
                hour=23, minute=59, second=0, microsecond=0
            ),  # 截止時間：5 天後 23:59
            estimated_time_minutes=240,  # 4 小時預估寫作業時間
        ),
    ]

    # 建立固定行程列表
    fixed_events = [
        FixedEvent(
            title="離散數學上課",  # 課堂行程
            start=now.replace(hour=19, minute=0, second=0, microsecond=0),  # 今日 19:00 開始
            end=now.replace(hour=21, minute=0, second=0, microsecond=0),  # 今日 21:00 結束
        ),
        FixedEvent(
            title="和同學吃飯",  # 吃飯行程
            start=(now + timedelta(days=1)).replace(
                hour=18, minute=0, second=0, microsecond=0
            ),  # 明天 18:00 開始
            end=(now + timedelta(days=1)).replace(
                hour=20, minute=0, second=0, microsecond=0
            ),  # 明天 20:00 結束
        ),
    ]

    # 將三種資料組合成 ParsedInput 回傳
    return ParsedInput(
        past_tasks=past_tasks,  # 過去任務列表
        todos=todos,  # 未來任務列表
        fixed_events=fixed_events,  # 固定行程列表
    )


def parse_input_with_llm(raw_text: str, assignment_file: str, schedule_start: date, schedule_days: int) -> ParsedInput:
    """
    對外的統一介面：
    - 若 USE_GROQ=True，先試著用 Groq 解析，失敗就 fallback。
    - 若 USE_GROQ=False，直接用內建 demo 資料。
    """
    if USE_GROQ:  # 若設定為使用 Groq
        parsed = _parse_with_groq(raw_text, assignment_file, schedule_start, schedule_days)  # 嘗試呼叫 Groq 解析自然語言
        if parsed is not None:  # 若成功取得解析結果
            return parsed  # 直接回傳 Groq 結果
        print("⚠ GROQ_API_KEY 未設定，呼叫 LLM 失敗")  # Groq 失敗時印出警告

    # 若 USE_GROQ=False 或 Groq 解析失敗，回傳 demo 資料
    #return _fallback_demo_data()
    return False
