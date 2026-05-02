#!/usr/bin/env python3
"""Inspect saved Keras .keras checkpoints: shapes, IO, quick forward pass."""
import os
import sys
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import numpy as np

models_dir = _ROOT / "models" / "saved"

for f in sorted(models_dir.glob("*.keras")):
    print(f"\n{'='*60}")
    print(f"FILE: {f.name}  ({f.stat().st_size/1e6:.1f} MB)")
    try:
        import tensorflow as tf

        m = tf.keras.models.load_model(str(f), compile=False)

        print(f"INPUT  shape : {m.input_shape}")
        print(f"OUTPUT shape : {m.output_shape}")
        print(f"TOTAL params : {m.count_params():,}")
        print(f"LAYERS       : {len(m.layers)}")
        print(f"FIRST layer  : {m.layers[0].name} — {m.layers[0].__class__.__name__}")
        print(f"LAST layer   : {m.layers[-1].name} — {m.layers[-1].__class__.__name__}")

        input_shape = m.input_shape  # (None, H, W, C) or (None, D, H, W, C)
        if len(input_shape) == 5:
            _, d, h, w, c = input_shape
            if d is None:
                d, h, w, c = 96, 96, 96, c or 1
            fake = np.random.rand(1, int(d), int(h), int(w), int(c)).astype(np.float32)
        else:
            _, h, w, c = input_shape
            if h is None:
                h, w, c = 224, 224, 3
            fake = np.random.rand(1, int(h), int(w), int(c)).astype(np.float32)

        out = m.predict(fake, verbose=0)
        o0 = out[0]
        print(f"OUTPUT shape (per sample): {o0.shape}")
        flat = o0.reshape(-1)
        if flat.size <= 16:
            print(f"OUTPUT sample: {o0.round(4)}")
        else:
            print(f"OUTPUT sample (first 8): {flat[:8].round(4)}")

        if o0.ndim == 1 and o0.shape[0] == 4:
            s = float(o0.sum())
            print(f"OUTPUT sum   : {s:.4f}  (should be ~1.0 if softmax)")
            classes = ["glioma", "meningioma", "pituitary", "notumor"]
            pred_idx = int(o0.argmax())
            print(f"PREDICTED    : {classes[pred_idx]} ({float(o0[pred_idx]):.3f})")
        elif o0.ndim >= 4 and o0.shape[-1] == 2:
            flatp = o0.reshape(-1, o0.shape[-1])
            sums = flatp.sum(axis=-1).mean()
            print(f"Per-voxel mean class sum: {sums:.4f}")
            print("CLASSES      : [background, wmh_lesion] — segmentation-style output")
        else:
            ts = (
                float(o0.sum())
                if o0.size == o0.shape[0]
                else float(np.array(o0).reshape(-1, o0.shape[-1]).sum(axis=-1).mean())
            )
            print(f"OUTPUT sum-ish   : {ts:.4f}")

    except Exception as e:
        import traceback

        print(f"ERROR: {e}")
        traceback.print_exc()
