from operations import evaluate_paper_health, generate_daily_report, get_store
from paper_live import get_audit_payload


def get_operations_payload():
    store = get_store()
    audit = get_audit_payload()
    health = evaluate_paper_health(audit, store=store)
    alerts = store.list_alerts(limit=200)
    return {
        "health": health,
        "active_count": sum(alert["status"] == "active" for alert in alerts),
        "critical_count": sum(alert["status"] == "active" and alert["severity"] == "critical" for alert in alerts),
        "alerts": alerts,
        "audit": audit,
    }


def get_daily_report():
    return generate_daily_report(notify=False)


def send_daily_report():
    return generate_daily_report(notify=True)
