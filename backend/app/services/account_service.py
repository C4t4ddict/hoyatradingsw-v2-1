from webhook_server import account_status

def get_account_payload(market_type: str = 'futures'):
    return account_status(market_type=market_type)
