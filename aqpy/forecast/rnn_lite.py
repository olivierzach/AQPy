import numpy as np


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def init_gru_encoder(hidden_dim=8, seed=42):
    rng = np.random.default_rng(seed)
    scale = 0.2
    return {
        "hidden_dim": int(hidden_dim),
        "Wz": rng.normal(0.0, scale, size=(1, hidden_dim)),
        "Uz": rng.normal(0.0, scale, size=(hidden_dim, hidden_dim)),
        "bz": np.zeros(hidden_dim),
        "Wr": rng.normal(0.0, scale, size=(1, hidden_dim)),
        "Ur": rng.normal(0.0, scale, size=(hidden_dim, hidden_dim)),
        "br": np.zeros(hidden_dim),
        "Wh": rng.normal(0.0, scale, size=(1, hidden_dim)),
        "Uh": rng.normal(0.0, scale, size=(hidden_dim, hidden_dim)),
        "bh": np.zeros(hidden_dim),
    }


def _step(encoder, x_scalar, h_prev):
    x = np.array([[float(x_scalar)]], dtype=float)
    h = h_prev.reshape(1, -1)
    z = _sigmoid(x @ encoder["Wz"] + h @ encoder["Uz"] + encoder["bz"])
    r = _sigmoid(x @ encoder["Wr"] + h @ encoder["Ur"] + encoder["br"])
    h_tilde = np.tanh(x @ encoder["Wh"] + (r * h) @ encoder["Uh"] + encoder["bh"])
    h_new = (1.0 - z) * h + z * h_tilde
    return h_new.reshape(-1)


def encode_sequence(encoder, seq):
    h = np.zeros(encoder["hidden_dim"], dtype=float)
    for value in seq:
        h = _step(encoder, value, h)
    return h


def build_sequence_dataset(values, seq_len):
    if len(values) <= seq_len:
        raise ValueError(f"Need > {seq_len} rows, got {len(values)}")
    X_seq = []
    y = []
    for i in range(seq_len, len(values)):
        X_seq.append(values[i - seq_len : i])
        y.append(values[i])
    return np.array(X_seq, dtype=float), np.array(y, dtype=float)


def _to_head_matrix(encoder, X_seq):
    H = [encode_sequence(encoder, seq) for seq in X_seq]
    return np.array(H, dtype=float)


def fit_gru_lite_head(values, seq_len=24, hidden_dim=8, ridge=1e-3, seed=42, init=None):
    x_mean = float(np.mean(values))
    x_std = float(np.std(values))
    if x_std < 1e-8:
        x_std = 1.0
    vals = (np.array(values, dtype=float) - x_mean) / x_std

    X_seq, y = build_sequence_dataset(vals, seq_len=seq_len)
    encoder = init_gru_encoder(hidden_dim=hidden_dim, seed=seed) if init is None else init
    H = _to_head_matrix(encoder, X_seq)
    y_col = y.reshape(-1, 1)
    I = np.eye(H.shape[1], dtype=float)
    w = np.linalg.solve(H.T @ H + ridge * I, H.T @ y_col).reshape(-1)
    b = 0.0

    y_hat = H @ w + b
    train_loss = float(np.mean((y_hat - y) ** 2))
    return {
        "model_type": "rnn_lite_gru",
        "seq_len": int(seq_len),
        "hidden_dim": int(hidden_dim),
        "x_mean": x_mean,
        "x_std": x_std,
        "encoder": {
            k: (v.tolist() if isinstance(v, np.ndarray) else v) for k, v in encoder.items()
        },
        "head_w": w.tolist(),
        "head_b": float(b),
        "ridge": float(ridge),
        "train_loss": train_loss,
    }


def _restore_encoder(model):
    enc = model["encoder"]
    return {
        "hidden_dim": int(enc["hidden_dim"]),
        "Wz": np.array(enc["Wz"], dtype=float),
        "Uz": np.array(enc["Uz"], dtype=float),
        "bz": np.array(enc["bz"], dtype=float),
        "Wr": np.array(enc["Wr"], dtype=float),
        "Ur": np.array(enc["Ur"], dtype=float),
        "br": np.array(enc["br"], dtype=float),
        "Wh": np.array(enc["Wh"], dtype=float),
        "Uh": np.array(enc["Uh"], dtype=float),
        "bh": np.array(enc["bh"], dtype=float),
    }


def predict_next(model, history_values):
    vals = np.array(history_values, dtype=float)
    vals = (vals - float(model["x_mean"])) / float(model["x_std"])
    seq_len = int(model["seq_len"])
    seq = vals[-seq_len:]
    encoder = _restore_encoder(model)
    h = encode_sequence(encoder, seq)
    w = np.array(model["head_w"], dtype=float)
    pred_scaled = float(h @ w + float(model["head_b"]))
    return float(pred_scaled * float(model["x_std"]) + float(model["x_mean"]))


def predict_batch(model, X_seq_raw):
    out = []
    for seq in X_seq_raw:
        out.append(predict_next(model, seq))
    return np.array(out, dtype=float)


def recursive_predict(model, values, horizon_steps):
    history = list(values)
    preds = []
    for _ in range(horizon_steps):
        pred = predict_next(model, history)
        history.append(pred)
        preds.append(pred)
    return preds
