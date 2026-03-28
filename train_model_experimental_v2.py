from pathlib import Path
import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBClassifier

DATASET_CSV = Path("data/ml_dataset.csv")
MODEL_DIR = Path("data/models_experimental_v2")
REPORT_PATH = Path("data/models_experimental_v2/report.json")


def train_one(df: pd.DataFrame, target_col: str):
    sdf = df.dropna(subset=[target_col]).copy()
    if len(sdf) < 40:
        print(f"not enough rows for {target_col}: {len(sdf)}")
        return None

    sdf["text"] = (sdf.get("title", "").fillna("") + " " + sdf.get("summary", "").fillna(""))
    sdf["text_len"] = sdf["text"].str.len().fillna(0)
    sdf["score_x_trust"] = sdf.get("score", 0).fillna(0) * sdf.get("trust", 0).fillna(0)
    # 고품질/의미 있는 이벤트만 우대하는 가중치
    sdf["sample_weight"] = 1.0 + (sdf.get("trust", 0).fillna(0) * 0.7) + (sdf.get("score", 0).abs().fillna(0) * 0.05)
    sdf.loc[sdf.get("is_scheduled", False) == True, "sample_weight"] += 0.25
    sdf.loc[sdf.get("is_trump", False) == True, "sample_weight"] += 0.15

    X = sdf[[
        "text", "source", "kind", "topic", "score", "trust", "is_trump", "is_scheduled",
        "market_ret_1h", "market_ret_4h", "market_volatility_12h", "market_volume_ratio",
        "text_len", "score_x_trust",
    ]].copy()
    y = sdf[target_col].astype(int)
    w = sdf["sample_weight"].astype(float)

    prep = ColumnTransformer([
        ("text", TfidfVectorizer(max_features=5000, ngram_range=(1, 2), min_df=2), "text"),
        ("cat", Pipeline([
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]), ["source", "kind", "topic"]),
        ("num", Pipeline([
            ("imputer", SimpleImputer(strategy="constant", fill_value=0)),
        ]), [
            "score", "trust", "is_trump", "is_scheduled", "market_ret_1h", "market_ret_4h",
            "market_volatility_12h", "market_volume_ratio", "text_len", "score_x_trust",
        ]),
    ], sparse_threshold=0.3)

    X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(
        X, y, w, test_size=0.2, random_state=42, stratify=y
    )
    Xt_train = prep.fit_transform(X_train)
    Xt_test = prep.transform(X_test)

    model = XGBClassifier(
        n_estimators=600,
        max_depth=5,
        learning_rate=0.035,
        subsample=0.9,
        colsample_bytree=0.85,
        reg_lambda=1.5,
        reg_alpha=0.15,
        min_child_weight=2,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
    )
    model.fit(Xt_train, y_train, sample_weight=w_train)

    prob = model.predict_proba(Xt_test)[:, 1]
    # 실전용: 애매한 신호 줄이기 위해 threshold 상향
    threshold = 0.60 if target_col in ["label_up_1h", "label_up_4h", "label_up_24h"] else 0.58
    pred = (prob >= threshold).astype(int)

    print(f"===== {target_col} (experimental_v2) =====")
    print(classification_report(y_test, pred, zero_division=0))

    precision = float(precision_score(y_test, pred, zero_division=0))
    recall = float(recall_score(y_test, pred, zero_division=0))
    accepted = float((prob >= threshold).mean())

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    out = MODEL_DIR / f"{target_col}.joblib"
    joblib.dump({"prep": prep, "model": model, "threshold": threshold}, out)
    print(f"saved model: {out}")
    return {
        "target": target_col,
        "precision": precision,
        "recall": recall,
        "accept_rate": accepted,
        "threshold": threshold,
        "rows": int(len(sdf)),
    }


def main():
    df = pd.read_csv(DATASET_CSV)
    results = []
    for col in ["label_up_1h", "label_up_4h", "label_up_24h"]:
        r = train_one(df, col)
        if r:
            results.append(r)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(pd.DataFrame(results).to_json(orient="records", force_ascii=False, indent=2), encoding="utf-8")
    print(f"saved report: {REPORT_PATH}")


if __name__ == "__main__":
    main()
