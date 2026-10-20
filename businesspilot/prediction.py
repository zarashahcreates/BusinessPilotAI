import pandas as pd
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler, LabelEncoder
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, brier_score_loss
from sklearn.calibration import CalibratedClassifierCV

from .forecasting import forecast_series, apply_scenario, risk_indicators, ForecastResult  # noqa: F401  (public re-export)


def train_probability_model(df: pd.DataFrame, target: str, date_col: str | None = None) -> dict:
    """Train a baseline classifier for a categorical/binary historical outcome.

    This is a starter educational workflow. It intentionally refuses tiny or single-class datasets.
    """
    if target not in df.columns:
        raise ValueError("Target column was not found.")
    work = df.dropna(subset=[target]).copy()
    if len(work) < 40:
        raise ValueError("Need at least 40 labelled rows for this starter evaluation. More data is strongly recommended.")
    y_raw = work[target].astype(str)
    if y_raw.nunique() < 2:
        raise ValueError("The target column must contain at least two outcome classes.")
    if y_raw.nunique() > 20:
        raise ValueError("This starter model supports classification targets with at most 20 distinct classes. Group or redefine the target.")
    X = work.drop(columns=[target])
    # Avoid identifiers and source filename columns as leakage/noisy predictors.
    X = X.drop(columns=[c for c in X.columns if str(c).lower() in {"id", "customer_id", "invoice_id", "order_id"} or str(c).startswith("__")], errors="ignore")
    # The date column is used only to order rows for the chronological split, never as a feature.
    if date_col:
        X = X.drop(columns=[date_col], errors="ignore")
    if X.shape[1] == 0:
        raise ValueError("No usable predictor columns remain after removing target and identifiers.")
    # Convert numeric-looking columns into numeric values.
    for col in X.columns:
        converted = pd.to_numeric(X[col], errors="coerce")
        if converted.notna().mean() >= 0.75:
            X[col] = converted
        else:
            X[col] = X[col].astype("string").fillna("Unknown")
    numeric = X.select_dtypes(include=["number"]).columns.tolist()
    categorical = [c for c in X.columns if c not in numeric]
    transformers = []
    if numeric:
        transformers.append(("num", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric))
    if categorical:
        transformers.append(("cat", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("onehot", OneHotEncoder(handle_unknown="ignore"))]), categorical))
    preprocess = ColumnTransformer(transformers=transformers)
    # Stratification needs at least two samples per class.
    counts = y_raw.value_counts()
    if counts.min() < 2:
        raise ValueError("Each target class needs at least two labelled examples.")
    if date_col and date_col in work.columns and pd.to_datetime(work[date_col], errors="coerce").notna().mean() > 0.8:
        # Time-aware split: train on the earliest 75% of rows, test on the most recent 25% (no look-ahead).
        order = pd.to_datetime(work[date_col], errors="coerce").sort_values(kind="stable").index
        cut = int(len(order) * 0.75)
        X_train, X_test = X.loc[order[:cut]], X.loc[order[cut:]]
        y_train, y_test = y_raw.loc[order[:cut]], y_raw.loc[order[cut:]]
        evaluation = "Chronological holdout (earliest 75% train / most recent 25% test)."
        if y_train.nunique() < 2 or y_test.empty:
            raise ValueError("The chronological split leaves a single outcome class in training data; more varied history is needed.")
    else:
        X_train, X_test, y_train, y_test = train_test_split(
            X, y_raw, test_size=0.25, random_state=42, stratify=y_raw
        )
        evaluation = "Random stratified holdout (75% train / 25% test). Not time-aware: add a date column for a chronological split."
    model = Pipeline([
        ("preprocess", preprocess),
        ("classifier", LogisticRegression(max_iter=2000, class_weight="balanced"))
    ])
    model.fit(X_train, y_train)
    proba = model.predict_proba(X_test)
    classes = list(model.named_steps["classifier"].classes_)
    pred = model.predict(X_test)
    # Multiclass Brier score: mean squared error across one-hot classes.
    y_test_values = list(y_test)
    onehot = np.zeros_like(proba)
    class_idx = {c:i for i,c in enumerate(classes)}
    for i, val in enumerate(y_test_values):
        onehot[i, class_idx[val]] = 1.0
    brier = float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))
    # Baseline: always predict the training class frequencies / majority class.
    prior = y_train.value_counts(normalize=True)
    base_proba = np.tile([prior.get(c, 0.0) for c in classes], (len(y_test_values), 1))
    base_brier = float(np.mean(np.sum((base_proba - onehot) ** 2, axis=1)))
    majority = prior.idxmax()
    base_acc = float(np.mean(np.array(y_test_values) == majority))
    predictions = pd.DataFrame({"actual": y_test_values, "predicted": pred})
    for i, cls in enumerate(classes):
        predictions[f"probability_{cls}"] = proba[:, i]
    return {
        "target": target,
        "evaluation": evaluation,
        "accuracy": float(accuracy_score(y_test, pred)),
        "brier_score": brier,
        "baseline_accuracy": base_acc,
        "baseline_brier": base_brier,
        "beats_baseline": bool(brier < base_brier),
        "n_train": int(len(y_train)), "n_test": int(len(y_test)),
        "meaning": "Each probability is the model's estimate that a row like this has that outcome, learned from your labelled history. "
                   "It is not a forecast interval and is only as good as the labelled data; compare the Brier score with the baseline.",
        "predictions": predictions.reset_index(drop=True),
        "classes": classes,
    }
