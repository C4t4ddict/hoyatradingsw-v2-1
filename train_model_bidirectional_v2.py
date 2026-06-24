from pathlib import Path
import json
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

DATASET_CSV = Path('data/ml_dataset.csv')
MODEL_DIR = Path('data/models_bidirectional_v2')
REPORT_PATH = Path('data/ml_bidirectional_report_v2.json')

TARGETS = [
    'label_up_5m', 'label_down_5m',
    'label_up_15m', 'label_down_15m',
    'label_up_30m', 'label_down_30m',
    'label_up_1h', 'label_down_1h',
    'label_up_4h', 'label_down_4h',
    'label_up_24h', 'label_down_24h',
]


def build_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out['title'] = out.get('title', '').fillna('')
    out['summary'] = out.get('summary', '').fillna('')
    out['text'] = (out['title'] + ' ' + out['summary']).str.strip()
    out['title_len'] = out['title'].str.len()
    out['summary_len'] = out['summary'].str.len()
    out['has_question'] = out['text'].str.contains('\?', regex=True).astype(int)
    out['has_number'] = out['text'].str.contains(r'\d', regex=True).astype(int)
    out['score_abs'] = out.get('score', 0).abs()
    out['ret_vol_ratio'] = out.get('market_ret_1h', 0).fillna(0) / (out.get('market_volatility_12h', 0).fillna(0).abs() + 1e-6)
    event_time = pd.to_datetime(out.get('event_time'), utc=True, errors='coerce')
    out['event_hour'] = event_time.dt.hour.fillna(0)
    out['event_weekday'] = event_time.dt.weekday.fillna(0)
    return out


def build_preprocessor():
    return ColumnTransformer([
        ('text', TfidfVectorizer(max_features=8000, ngram_range=(1,2), min_df=2, sublinear_tf=True), 'text'),
        ('cat', Pipeline([
            ('imputer', SimpleImputer(strategy='most_frequent')),
            ('onehot', OneHotEncoder(handle_unknown='ignore')),
        ]), ['source','kind','topic','event_hour','event_weekday']),
        ('num', Pipeline([
            ('imputer', SimpleImputer(strategy='constant', fill_value=0)),
        ]), ['score','score_abs','trust','is_trump','is_scheduled','market_ret_1h','market_ret_4h','market_volatility_12h','market_volume_ratio','title_len','summary_len','has_question','has_number','ret_vol_ratio']),
    ], sparse_threshold=0.3)


def time_split(sdf: pd.DataFrame):
    sdf = sdf.sort_values('event_time').reset_index(drop=True)
    cut = max(1, int(len(sdf) * 0.8))
    train = sdf.iloc[:cut].copy()
    test = sdf.iloc[cut:].copy()
    return train, test


def train_one(df: pd.DataFrame, target_col: str):
    sdf = df.dropna(subset=[target_col, 'event_time']).copy()
    if len(sdf) < 100:
        return {'target': target_col, 'skipped': True, 'reason': f'not enough rows: {len(sdf)}'}

    y_all = sdf[target_col].astype(int)
    pos = int(y_all.sum())
    neg = int((1 - y_all).sum())
    if pos < 12 or neg < 12:
        return {'target': target_col, 'skipped': True, 'reason': f'class imbalance too severe pos={pos} neg={neg}'}

    train_df, test_df = time_split(sdf)
    if train_df[target_col].nunique() < 2 or test_df[target_col].nunique() < 2:
        return {'target': target_col, 'skipped': True, 'reason': 'time split lacks both classes'}

    features = ['text','source','kind','topic','event_hour','event_weekday','score','score_abs','trust','is_trump','is_scheduled','market_ret_1h','market_ret_4h','market_volatility_12h','market_volume_ratio','title_len','summary_len','has_question','has_number','ret_vol_ratio']
    X_train = train_df[features].copy()
    y_train = train_df[target_col].astype(int)
    X_test = test_df[features].copy()
    y_test = test_df[target_col].astype(int)

    prep = build_preprocessor()
    Xt_train = prep.fit_transform(X_train)
    Xt_test = prep.transform(X_test)

    scale_pos_weight = max(1.0, float((len(y_train) - int(y_train.sum())) / max(1, int(y_train.sum()))))
    model = XGBClassifier(
        n_estimators=700,
        max_depth=4,
        learning_rate=0.03,
        subsample=0.85,
        colsample_bytree=0.8,
        min_child_weight=1,
        gamma=0.1,
        reg_lambda=2.0,
        objective='binary:logistic',
        eval_metric='logloss',
        random_state=42,
        scale_pos_weight=scale_pos_weight,
    )
    model.fit(Xt_train, y_train)
    pred = model.predict(Xt_test)
    report = classification_report(y_test, pred, zero_division=0, output_dict=True)
    cm = confusion_matrix(y_test, pred).tolist()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out = MODEL_DIR / f'{target_col}.joblib'
    joblib.dump({'prep': prep, 'model': model}, out)

    return {
        'target': target_col,
        'skipped': False,
        'rows': len(sdf),
        'positive': pos,
        'negative': neg,
        'train_rows': len(train_df),
        'test_rows': len(test_df),
        'accuracy': report.get('accuracy'),
        'precision_1': report.get('1', {}).get('precision', 0.0),
        'recall_1': report.get('1', {}).get('recall', 0.0),
        'f1_1': report.get('1', {}).get('f1-score', 0.0),
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
    raw = pd.read_csv(DATASET_CSV)
    df = build_df(raw)
    results = [train_one(df, t) for t in TARGETS]
    REPORT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
