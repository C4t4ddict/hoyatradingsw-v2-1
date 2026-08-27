from pathlib import Path
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier
from ml_training import chronological_purged_split

DATASET_CSV = Path("data/ml_dataset.csv")
MODEL_DIR = Path("data/models_xgb")


def train_one(df: pd.DataFrame, target_col: str):
    sdf = df.dropna(subset=[target_col]).copy()
    if len(sdf) < 40:
        print(f"not enough rows for {target_col}: {len(sdf)}")
        return

    sdf["text"] = (sdf.get("title", "").fillna("") + " " + sdf.get("summary", "").fillna(""))
    features = [
        "text", "source", "kind", "topic",
        "score", "trust", "is_trump", "is_scheduled",
        "market_ret_1h", "market_ret_4h", "market_volatility_12h", "market_volume_ratio",
    ]
    try:
        split = chronological_purged_split(sdf, target_col)
    except ValueError as exc:
        print(exc)
        return

    preprocessor = ColumnTransformer(
        transformers=[
            ("text", TfidfVectorizer(max_features=4000, ngram_range=(1, 2)), "text"),
            ("cat", Pipeline([
                ("imputer", SimpleImputer(strategy="most_frequent")),
                ("onehot", OneHotEncoder(handle_unknown="ignore")),
            ]), ["source", "kind", "topic"]),
            ("num", Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
            ]), ["score", "trust", "is_trump", "is_scheduled", "market_ret_1h", "market_ret_4h", "market_volatility_12h", "market_volume_ratio"]),
        ],
        sparse_threshold=0.3,
    )

    X_train = split.train[features].copy()
    X_test = split.test[features].copy()
    y_train = split.train[target_col].astype(int)
    y_test = split.test[target_col].astype(int)
    X_train_t = preprocessor.fit_transform(X_train)
    X_test_t = preprocessor.transform(X_test)

    model = XGBClassifier(
        n_estimators=300,
        max_depth=4,
        learning_rate=0.05,
        subsample=0.9,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(X_train_t, y_train)
    pred = model.predict(X_test_t)
    print(f"===== {target_col} (XGB) =====")
    print(classification_report(y_test, pred, zero_division=0))

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out = MODEL_DIR / f"{target_col}.joblib"
    joblib.dump({"prep": preprocessor, "model": model}, out)
    print(f"saved model: {out}")


def main():
    if not DATASET_CSV.exists():
        print("dataset not found")
        return
    df = pd.read_csv(DATASET_CSV)
    for target_col in ["label_up_5m", "label_up_15m", "label_up_1h", "label_up_4h", "label_up_24h"]:
        train_one(df, target_col)


if __name__ == "__main__":
    main()
