from pathlib import Path
import joblib
import pandas as pd

MODEL_DIR = Path('data/models_bidirectional')
TARGETS = [
    'label_up_5m', 'label_down_5m',
    'label_up_15m', 'label_down_15m',
    'label_up_30m', 'label_down_30m',
    'label_up_1h', 'label_down_1h',
    'label_up_4h', 'label_down_4h',
    'label_up_24h', 'label_down_24h',
]


def _predict_one(event: dict, target_col: str):
    model_path = MODEL_DIR / f'{target_col}.joblib'
    if not model_path.exists():
        return {'ok': False, 'reason': 'model not found'}
    bundle = joblib.load(model_path)
    prep = bundle['prep']
    model = bundle['model']
    row = {
        'text': f"{event.get('title', '')} {event.get('summary', '')}",
        'source': event.get('source'),
        'kind': event.get('kind'),
        'topic': event.get('topic'),
        'score': event.get('score', 0.0),
        'trust': event.get('trust', 0.0),
        'is_trump': event.get('is_trump', False),
        'is_scheduled': event.get('is_scheduled', False),
        'market_ret_1h': event.get('market_ret_1h', 0.0),
        'market_ret_4h': event.get('market_ret_4h', 0.0),
        'market_volatility_12h': event.get('market_volatility_12h', 0.0),
        'market_volume_ratio': event.get('market_volume_ratio', 0.0),
    }
    X = pd.DataFrame([row])
    Xt = prep.transform(X)
    pred = int(model.predict(Xt)[0])
    proba = model.predict_proba(Xt)[0].tolist() if hasattr(model, 'predict_proba') else [1 - pred, pred]
    return {'ok': True, 'pred': pred, 'proba': proba, 'model_path': str(model_path)}


def predict_event_bidirectional(event: dict):
    return {target: _predict_one(event, target) for target in TARGETS}
