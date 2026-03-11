#!/usr/bin/env python3
"""
Optional: evaluate saliency maps against ground-truth segmentation masks.

Use when you have a dataset with both:
  - classification labels (or use classifier prediction), and
  - segmentation masks (binary or multi-class, same size as image).

Metrics: e.g. Dice or IoU between binarized saliency (e.g. top 20% of pixels) and GT mask.

Usage (after implementing paths and loader for your mask dataset):
  python scripts/evaluate_saliency_vs_mask.py --config configs/data.yaml --model custom_cnn --mask_dir path/to/masks

This script is a stub: implement mask loading and paths for your dataset (e.g. BraTS-style).
See docs/roadmap-radiologist-questions.md for context.
"""
from pathlib import Path


def main():
    print("Saliency-vs-mask evaluation stub. Implement mask loading and dataset paths for your data.")
    print("See docs/roadmap-radiologist-questions.md for the intended workflow.")


if __name__ == "__main__":
    main()
