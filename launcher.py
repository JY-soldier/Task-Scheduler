"""
launcher.py
打包成 exe 後用來啟動 Streamlit 的啟動器。

- frozen 狀態 (dist/launcher/launcher.exe)：從 PyInstaller 的執行目錄中
  自動尋找 app.py (包含 _internal 的情況)
- 開發狀態 (python launcher.py)：直接用當前資料夾的 app.py
"""

import os
import sys
import threading
import time
import webbrowser

from streamlit.web import cli as stcli


def _find_project_dir() -> str:
    """回傳專案根目錄 (有 app.py 的那一層)."""
    if getattr(sys, "frozen", False):
        candidates = []

        # ① PyInstaller 提供的基底路徑（在 onedir 模式多半會指到 _internal）
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(meipass)

        # ② exe 所在資料夾（dist/launcher）
        exe_dir = os.path.dirname(sys.executable)
        candidates.append(exe_dir)

        # ③ exe 下的 _internal（PyInstaller 6 預設 contents 目錄）
        candidates.append(os.path.join(exe_dir, "_internal"))

        # 依序找哪一個有 app.py
        for c in candidates:
            app_candidate = os.path.join(c, "app.py")
            if os.path.exists(app_candidate):
                return c

        # 找不到就退回 exe 同層（理論上不會走到這裡）
        return exe_dir
    else:
        # 開發時：launcher.py 跟 app.py 在同一層 (HWScheduler)
        return os.path.dirname(os.path.abspath(__file__))


def _open_browser_later(url: str, delay: float = 1.5) -> None:
    """延遲幾秒後自動開瀏覽器，避免 server 還沒起來。"""
    def _worker():
        time.sleep(delay)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def main() -> None:
    """啟動 Streamlit 的入口點。"""
    project_dir = _find_project_dir()
    app_path = os.path.join(project_dir, "app.py")

    if not os.path.exists(app_path):
        print(f"找不到 app.py，預期位置：{app_path}")
        input("按 Enter 結束...")
        return

    # 強制用正式模式，不要 Node dev server (local URL 會變成 8501)
    # 並且指定 port = 8501
    sys.argv = [
        "streamlit",
        "run",
        app_path,
        "--server.port",
        "8501",
        "--server.headless",
        "true",
        "--global.developmentMode",
        "false",
    ]

    # 我們自己開 http://localhost:8501，避免 Streamlit 去開 3000
    _open_browser_later("http://localhost:8501", delay=2.0)

    # 啟動 Streamlit
    stcli.main()


if __name__ == "__main__":
    main()
