import time
import traceback
from paper_live import load_state, update_session
from operations import emit_operational_alert, get_store
from security import mask_text


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
            get_store().resolve("paper.worker.exception")
        except Exception as exc:
            try:
                emit_operational_alert(
                    dedup_key="paper.worker.exception",
                    category="worker",
                    severity="critical",
                    message="Paper worker update failed",
                    details={"error_type": type(exc).__name__, "error": mask_text(str(exc)), "traceback": mask_text(traceback.format_exc(limit=5))},
                )
            except Exception:
                pass
        time.sleep(interval)


if __name__ == "__main__":
    main()
