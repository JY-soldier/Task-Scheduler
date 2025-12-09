# models.py：定義排程系統中用到的資料模型（使用 Pydantic BaseModel）

from datetime import datetime  # 用於 datetime 型別欄位
from typing import List, Optional  # 匯入 List 和 Optional 型別註解
from pydantic import BaseModel  # 匯入 Pydantic BaseModel 作為資料模型基底類別


class DifficultyPastTask(BaseModel):
    title: str
    difficulty: int

class DifficultyTodo(BaseModel):
    title: str
    difficulty: int

class DifficultyResult(BaseModel):
    past_tasks: List[DifficultyPastTask]
    todos: List[DifficultyTodo]


class PastTask(BaseModel):
    """
    過去已完成的作業 / 複習紀錄，用來推估未來所需時間的可能參考。
    """
    title: str  # 任務標題（例如：「離散數學作業 3」）
    subject: Optional[str] = None  # 科目名稱（可為 None）
    time_spent_minutes: int  # 完成這個任務實際花費的時間（分鐘）

    difficulty: Optional[int] = None # 如果有說明檔->計算難易度


class TodoTask(BaseModel):
    """
    未完成的作業 / 考試等，需要在排程中分配時間。
    """
    title: str  # 任務標題（例如：「交離散數學作業 4」）
    subject: Optional[str] = None  # 科目名稱（可為 None）
    deadline: datetime  # 任務的截止時間（日期 + 時間）
    estimated_time_minutes: int  # 預估需要多少分鐘來完成（或準備）

    difficulty: Optional[int] = None # 如果有說明檔->計算難易度
    priority: Optional[int] = None # 如果使用者要求->排程優先級
    exam_or_not: bool # 判斷是否是考試


class FixedEvent(BaseModel):
    """
    使用者已經排定、不能更改的行程（例如上課、吃飯、聚會）。
    """
    title: str  # 行程標題（例如：「離散數學上課」）
    start: datetime  # 行程開始時間
    end: datetime  # 行程結束時間


class ParsedInput(BaseModel):
    """
    LLM 或 demo 解析完後的整體輸入結構：
    - past_tasks：過去任務清單
    - todos：未完成的任務清單
    - fixed_events：固定行程清單
    """
    past_tasks: List[PastTask]  # 過去已完成任務列表
    todos: List[TodoTask]  # 未來要完成的任務列表
    fixed_events: List[FixedEvent]  # 已排定的固定行程列表


class ScheduledBlock(BaseModel):
    """
    排程結果中最小的時間區塊單位。
    """
    title: str  # 此區塊對應的任務或行程標題
    start: datetime  # 區塊開始時間
    end: datetime  # 區塊結束時間
    kind: str  # 區塊種類，"todo" 代表作業/複習，"fixed" 代表固定行程
