# scheduler.py：排程核心邏輯，將 ParsedInput 轉成一連串 ScheduledBlock

from datetime import datetime, timedelta, date  # 匯入時間與日期相關類別
from typing import List, Optional  # 匯入 List 與 Optional 型別註解

from models import ParsedInput, ScheduledBlock  # 匯入解析後輸入和排程區塊資料模型
from config import DEFAULT_STUDY_START_HOUR, DEFAULT_STUDY_END_HOUR, BLOCK_MINUTES  # 匯入預設設定值


def _iter_study_slots(
    start_dt: datetime,
    days: int,
    study_start_hour: int,
    study_end_hour: int,
):
    """
    從 start_dt 開始，產生連續 days 天的可讀書時段起始時間，
    每格長度為 BLOCK_MINUTES。
    每天時間範圍為 [study_start_hour, study_end_hour)。
    """
    for d in range(days):  # 對於從第 0 天到第 days-1 天
        day = (start_dt + timedelta(days=d)).replace(
            hour=study_start_hour,  # 設定為當天讀書開始小時
            minute=0,  # 分鐘設為 0
            second=0,  # 秒數設為 0
            microsecond=0,  # 微秒設為 0
        )
        # 在當天的 [study_start_hour, study_end_hour) 範圍內，以 BLOCK_MINUTES 間隔產生時段
        while day.hour < study_end_hour:
            yield day  # 回傳當前時段開始時間
            day += timedelta(minutes=BLOCK_MINUTES)  # 向後推進一個時間區塊長度


def build_schedule(
    parsed: ParsedInput,
    days: int = 7,
    start_date: Optional[date] = None,
    max_hours_per_day: Optional[int] = None,
    study_start_hour: Optional[int] = None,
    study_end_hour: Optional[int] = None,
    cram_or_not: bool = False,
) -> List[ScheduledBlock]:
    """
    建立排程：

    - 從 start_date 開始往後 days 天排作業/複習。
      若 start_date=None，預設從「今天」開始。
    - 若 max_hours_per_day 不為 None，限制每天最多安排多少小時的「作業/複習」。
      固定行程不受此上限限制。
    - study_start_hour / study_end_hour：每天可排程時段（預設使用 config.py 的值）
    """
    now = datetime.now()  # 取得現在時間，用於判斷逾期任務
    today = now.date()  # 只取日期部分，作為今天的日期

    # 決定排程起始日期（不允許在今天以前）
    if start_date is None:  # 若呼叫方沒給定 start_date
        effective_date = today  # 使用今天作為起始日
    else:
        # 就算有人手動傳過去的日期，也會 clamp 到今天
        effective_date = max(start_date, today)  # 取 start_date 與 today 中較晚的日期

    # 決定每天的排程時段（預設使用 config）
    if study_start_hour is None:  # 若未指定排程開始小時
        study_start_hour = DEFAULT_STUDY_START_HOUR  # 使用 config 中的預設值
    if study_end_hour is None:  # 若未指定排程結束小時
        study_end_hour = DEFAULT_STUDY_END_HOUR  # 使用 config 中的預設值

    # 安全防呆：若結束小時 <= 開始小時，至少保留 1 小時
    if study_end_hour <= study_start_hour:
        # 若結束時間不合理，強制設為開始後 1 小時，且不超過 23 點
        study_end_hour = min(study_start_hour + 1, 23)

    # 把 date 變成當天 00:00，再由 _iter_study_slots 設為 study_start_hour
    start_base = datetime.combine(effective_date, datetime.min.time())

    # 每日作業/複習上限（分鐘）
    max_minutes_per_day: Optional[int] = None  # 預設為 None 代表無上限
    if max_hours_per_day is not None:  # 若有設定每日上限小時數
        max_minutes_per_day = max_hours_per_day * 60  # 轉成分鐘數

    # ✅ 確保每個待辦都有合理的 estimated_time_minutes
    for t in parsed.todos:  # 走訪所有待辦任務
        if t.estimated_time_minutes is None or t.estimated_time_minutes <= 0:
            # 如果 LLM 沒給或給 0，就先給 120 分鐘
            t.estimated_time_minutes = 120

    # 固定行程先變成 block
    blocks: List[ScheduledBlock] = [
        ScheduledBlock(title=e.title, start=e.start, end=e.end, kind="fixed")
        for e in parsed.fixed_events
    ]  # 將所有 fixed_events 轉成 ScheduledBlock 放入 blocks

    # 依 deadline 排序 todo（最近截止的先排）
    todos = sorted(parsed.todos, key=lambda x: x.deadline)

    # 依 priority 排序 todo（優先級最高的先排）
    todos = sorted(todos, key=lambda x: x.priority)

    # 每天已安排的「作業/複習」分鐘數
    day_todo_minutes = {}  # key: date（某天的日期）, value: 當天已排的 todo 總分鐘數

    def is_free(start: datetime, end: datetime) -> bool:
        """檢查這個時間區間有沒有被占用"""
        for b in blocks:  # 檢查所有已存在的排程區塊
            # 若時間上有重疊（不是完全在前或完全在後），代表被占用
            if not (end <= b.start or start >= b.end):
                return False  # 發現重疊直接回傳 False
        return True  # 若沒有與任何 block 重疊則回傳 True

    # 依序處理每一個 todo 任務
    for todo in todos:
        remaining = todo.estimated_time_minutes  # 剩餘尚需安排的分鐘數

        # 若截止時間已經在 now 之前，就不排（之後在 UI 顯示為逾期）
        if todo.deadline <= now:
            continue  # 直接跳過這個 todo

        # 在可用的讀書時間格中嘗試安排這個任務
        for slot_start in _iter_study_slots(
            start_base,  # 排程起始時間（合併日期 + 00:00）
            days,  # 要排幾天
            study_start_hour,  # 每天排程開始小時
            study_end_hour,  # 每天排程結束小時
        ):
            if slot_start >= todo.deadline:
                # 已經超過這份作業的截止時間，不再往後排
                break

            if remaining <= 0:
                break  # 代表已排完此任務所需時間，不需再找時段

            # 臨時抱佛腳模式開啟
            if cram_or_not == True and todo.exam_or_not == True:
                num_of_days = todo.deadline.day - slot_start.day - 1
                num_of_minutes = num_of_days * max_minutes_per_day
                num_of_minutes += max((study_end_hour - slot_start.hour), 0) * 60
                num_of_minutes += max((todo.deadline.hour - study_start_hour), 0) * 60
                for slot in _iter_study_slots(slot_start, num_of_days+2, study_start_hour, study_end_hour, ):
                    if not is_free(slot, slot+timedelta(minutes=BLOCK_MINUTES)):
                        num_of_minutes -= BLOCK_MINUTES
                if num_of_minutes > todo.estimated_time_minutes: continue

            slot_end = slot_start + timedelta(minutes=BLOCK_MINUTES)  # 計算此區塊結束時間

            # 每日上限檢查（只算作業/複習，不算固定行程）
            if max_minutes_per_day is not None:  # 若有設定每日上限
                day_key = slot_start.date()  # 取出該區塊屬於哪一天
                used = day_todo_minutes.get(day_key, 0)  # 該天目前已排的 todo 分鐘數
                if used + BLOCK_MINUTES > max_minutes_per_day:
                    # 這一天的作業時間已經達上限，換下一格
                    continue  # 不在這格安排，直接看下一個時段

            if is_free(slot_start, slot_end):  # 若此時間區間沒有被其他 block 占用
                blocks.append(
                    ScheduledBlock(
                        title=todo.title,  # 使用任務標題
                        start=slot_start,  # 區塊開始時間
                        end=slot_end,  # 區塊結束時間
                        kind="todo",  # 標註為 todo 類別
                    )
                )
                remaining -= BLOCK_MINUTES  # 此任務尚需安排的分鐘數減去一個區塊

                if max_minutes_per_day is not None:  # 若有每日上限
                    day_key = slot_start.date()  # 取得當天日期
                    day_todo_minutes[day_key] = (
                        day_todo_minutes.get(day_key, 0) + BLOCK_MINUTES
                    )  # 更新當天已排的總分鐘數

    # 依時間排序輸出（確保時間線上是從早到晚）
    blocks.sort(key=lambda b: b.start)
    return blocks  # 回傳完整的 ScheduledBlock 列表
