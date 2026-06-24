from pathlib import Path
import json
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

DATASET_CSV = Path('data/ml_dataset.csv')
MODEL_DIR = Path('data/models_bidirectional')
REPORT_PATH = Path('data/ml_bidirectional_report.json')

FEATURES = [
    'text', 'source', 'kind', 'topic',
    'score', 'trust', 'is_trump', 'is_scheduled',
    'market_ret_1h', 'market_ret_4h', 'market_volatility_12h', 'market_volume_ratio',
]
TARGETS = [
    'label_up_5m', 'label_down_5m',
    'label_up_15m', 'label_down_15m',
    'label_up_30m', 'label_down_30m',
    'label_up_1h', 'label_down_1h',
    'label_up_4h', 'label_down_4h',
    'label_up_24h', 'label_down_24h',
]


def build_preprocessor():
    return ColumnTransformer(
        transformers=[
            ('text', TfidfVectorizer(max_features=6000, ngram_range=(1, 2), min_df=2), 'text'),
            ('cat', Pipeline([
                ('imputer', SimpleImputer(strategy='most_frequent')),
                ('onehot', OneHotEncoder(handle_unknown='ignore')),
            ]), ['source', 'kind', 'topic']),
            ('num', Pipeline([
                ('imputer', SimpleImputer(strategy='constant', fill_value=0)),
            ]), ['score', 'trust', 'is_trump', 'is_scheduled', 'market_ret_1h', 'market_ret_4h', 'market_volatility_12h', 'market_volume_ratio']),
        ],
        sparse_threshold=0.3,
    )


def train_one(df: pd.DataFrame, target_col: str):
    sdf = df.dropna(subset=[target_col]).copy()
    if len(sdf) < 80:
        return {'target': target_col, 'skipped': True, 'reason': f'not enough rows: {len(sdf)}'}

    sdf['text'] = (sdf.get('title', '').fillna('') + ' ' + sdf.get('summary', '').fillna(''))
    X = sdf[FEATURES].copy()
    y = sdf[target_col].astype(int)
    pos = int(y.sum())
    neg = int((1 - y).sum())
    if pos < 8 or neg < 8:
        return {'target': target_col, 'skipped': True, 'reason': f'class imbalance too severe pos={pos} neg={neg}'}

    preprocessor = build_preprocessor()
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    X_train_t = preprocessor.fit_transform(X_train)
    X_test_t = preprocessor.transform(X_test)

    scale_pos_weight = max(1.0, float((len(y_train) - int(y_train.sum())) / max(1, int(y_train.sum()))))
    model = XGBClassifier(
        n_estimators=500,
        max_depth=5,
        learning_rate=0.04,
        subsample=0.9,
        colsample_bytree=0.8,
        min_child_weight=2,
        gamma=0.0,
        reg_lambda=1.5,
        objective='binary:logistic',
        eval_metric='logloss',
        random_state=42,
        scale_pos_weight=scale_pos_weight,
    )
    model.fit(X_train_t, y_train)
    pred = model.predict(X_test_t)
    proba = model.predict_proba(X_test_t)[:, 1]
    report = classification_report(y_test, pred, zero_division=0, output_dict=True)
    cm = confusion_matrix(y_test, pred).tolist()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out = MODEL_DIR / f'{target_col}.joblib'
    joblib.dump({'prep': preprocessor, 'model': model}, out)

    return {
        'target': target_col,
        'skipped': False,
        'rows': len(sdf),
        'positive': pos,
        'negative': neg,
        'accuracy': report.get('accuracy'),
        'precision_1': report.get('1', {}).get('precision', 0.0),
        'recall_1': report.get('1', {}).get('recall', 0.0),
        'f1_1': report.get('1', {}).get('f1-score', 0.0),
        'precision_0': report.get('0', {}).get('precision', 0.0),
        'recall_0': report.get('0', {}).get('recall', 0.0),
        'f1_0': report.get('0', {}).get('f1-score', 0.0),
        'macro_f1': report.get('macro avg', {}).get('f1-score', 0.0),
        'weighted_f1': report.get('weighted avg', {}).get('f1-score', 0.0),
        'confusion_matrix': cm,
        'scale_pos_weight': scale_pos_weight,
        'model_path': str(out),
    }


def main():
    if not DATASET_CSV.exists():
        print('dataset not found')
        return
    df = pd.read_csv(DATASET_CSV)
    results = [train_one(df, target) for target in TARGETS]
    REPORT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
