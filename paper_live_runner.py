import time
from paper_live import load_state, update_session


def main():
    while True:
        s = load_state()
        if not s.get("running"):
            break
        cfg = s.get("config") or {}
        interval = int(cfg.get("live_refresh_sec", 30))
        interval = max(5, min(300, interval))
        try:
            update_session()
        except Exception:
            pass
        time.sleep(interval)


if __name__ == "__main__":
    main()
