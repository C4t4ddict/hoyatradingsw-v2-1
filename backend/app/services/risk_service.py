from webhook_server import health

def get_risk_payload():
    h = health()
    return {'risk_guard': h.get('risk_guard'), 'execution_policy': h.get('execution_policy')}
