from webhook_server import account_status

def get_account_payload(market_type: str = 'futures', webhook_token: str = None):
    return account_status(market_type=market_type, x_webhook_token=webhook_token)
