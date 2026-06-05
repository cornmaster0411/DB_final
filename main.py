import sys
from scheduler_manager import SchedulerManager

def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    manager = SchedulerManager()
    
    if len(sys.argv) > 1 and sys.argv[1] == "update":
        print("=== 進入手動維護模式：單次更新 ===")
        manager.run_manual_update()
        print("\n🎉 單次更新完畢，系統結束。")
    elif len(sys.argv) > 1 and sys.argv[1] == "update_institutional":
        print("=== 進入手動維護模式：補齊三大法人資料 ===")
        manager.run_institutional_update()
        print("\n🎉 三大法人資料補齊完畢，系統結束。")
    else:
        print("=== 啟動自動化排程模式 ===")
        try:
            # 將排程器啟動包在 try 裡面
            manager.start()
        except (KeyboardInterrupt, SystemExit):
            # 當使用者按下 Ctrl+C 時，會跳到這裡
            print("\n🛑 收到中斷訊號，正在關閉排程器...")
            # 安全地關閉 scheduler
            if manager.scheduler.running:
                manager.scheduler.shutdown(wait=False)
            print("👋 系統已安全結束。")

if __name__ == "__main__":
    main()
