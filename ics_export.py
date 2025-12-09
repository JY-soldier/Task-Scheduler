# ics_export.py：負責將排程結果轉成 .ics 行事曆格式字串

from datetime import datetime  # 匯入 datetime 以產生時間戳記
from typing import List, Tuple  # 匯入型別註解 List 和 Tuple

from models import ScheduledBlock  # 從 models 匯入 ScheduledBlock 資料模型

CAL_TZ = "Asia/Taipei"  # 行事曆使用的時區，這裡固定為台北時間


def schedule_to_ics(blocks: List[ScheduledBlock]) -> str:
    """
    將排程結果(List[ScheduledBlock]) 轉成一個 .ics 格式字串。
    """
    # 建立 .ics 檔案開頭的標準欄位
    lines = [
        "BEGIN:VCALENDAR",  # 行事曆開始
        "VERSION:2.0",  # iCalendar 版本
        "PRODID:-//HW Scheduler//TW//",  # 自訂產品 ID
        "CALSCALE:GREGORIAN",  # 使用格里高利曆
        "METHOD:PUBLISH",  # 發布型態
    ]

    # 產生一個通用的時間戳記，用於所有事件的 DTSTAMP 欄位（使用 UTC）
    dtstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    # 走訪所有排程區塊，逐一轉成 VEVENT
    for idx, b in enumerate(blocks):
        # 將開始、結束時間格式化成 iCalendar 用的本地時間字串（不含時區後綴）
        dtstart_local = b.start.strftime("%Y%m%dT%H%M%S")
        dtend_local = b.end.strftime("%Y%m%dT%H%M%S")
        # 產生這個事件的 UID，使用 index + 開始時間組合成唯一字串
        uid = f"{idx}-{b.start.strftime('%Y%m%dT%H%M%S')}@hwscheduler"

        # DESCRIPTION 欄位顯示中文類別說明
        desc = "固定行程" if b.kind == "fixed" else "作業/複習"
        # CATEGORIES 欄位用英文字串，方便在部分行事曆中過濾
        categories = "Fixed" if b.kind == "fixed" else "Task"

        # 將一個 VEVENT 的欄位依序加入行事曆文字
        lines.extend(
            [
                "BEGIN:VEVENT",  # 事件開始
                f"UID:{uid}",  # 事件唯一 ID
                f"DTSTAMP:{dtstamp}",  # 建立/更新時間（UTC）
                f"DTSTART;TZID={CAL_TZ}:{dtstart_local}",  # 事件開始時間，附帶時區
                f"DTEND;TZID={CAL_TZ}:{dtend_local}",  # 事件結束時間，附帶時區
                f"SUMMARY:{b.title}",  # 事件標題
                f"DESCRIPTION:{desc}",  # 事件說明（中文類別）
                f"CATEGORIES:{categories}",  # 事件分類（英文）
                "END:VEVENT",  # 事件結束
            ]
        )

    lines.append("END:VCALENDAR")  # 行事曆結尾
    return "\r\n".join(lines)  # 以 CRLF 組合所有行，回傳整個 .ics 字串


def split_schedule_to_ics_for_google(
    blocks: List[ScheduledBlock],
) -> Tuple[str, str]:
    """
    給 Google Calendar 用：
    回傳兩個 .ics 字串：
    - 第一個：只包含固定行程 (kind == "fixed")
    - 第二個：只包含作業/複習 (kind == "todo")

    這樣就可以：
    1. 在 Google Calendar 建兩個日曆（例如「固定行程」「作業/複習」）
    2. 分別匯入這兩個 .ics
    3. 各自設定不同顏色
    """
    # 過濾出所有 kind == "fixed" 的排程區塊
    fixed_blocks = [b for b in blocks if b.kind == "fixed"]
    # 過濾出所有 kind == "todo" 的排程區塊
    todo_blocks = [b for b in blocks if b.kind == "todo"]

    # 將兩種區塊各自轉成 .ics 字串
    fixed_ics = schedule_to_ics(fixed_blocks)
    todo_ics = schedule_to_ics(todo_blocks)

    # 回傳 (固定行程 .ics, 作業/複習 .ics)
    return fixed_ics, todo_ics
