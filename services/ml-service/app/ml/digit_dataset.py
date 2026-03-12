"""
Synthetic digit dataset generator for training the digit classifier.

Generates synthetic printed digit images (0–9, where 0 = empty cell)
using OpenCV rendering with data augmentation.
"""

import random
from pathlib import Path

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

CELL_SIZE = 64
DIGITS = list(range(10))  # 0 = empty, 1–9 = digits


def _render_digit(digit: int, size: int = CELL_SIZE) -> np.ndarray:
    """Render a single digit as a grayscale image."""
    img = np.ones((size, size), dtype=np.uint8) * 255  # White background

    if digit == 0:
        # Empty cell — just white/near-white with slight noise
        noise = np.random.randint(0, 20, (size, size), dtype=np.uint8)
        img = np.clip(img.astype(np.int16) - noise, 0, 255).astype(np.uint8)
        return img

    # Render digit text
    text = str(digit)
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = random.uniform(1.2, 1.8)
    thickness = random.randint(2, 3)

    text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
    x = (size - text_size[0]) // 2 + random.randint(-3, 3)
    y = (size + text_size[1]) // 2 + random.randint(-3, 3)

    cv2.putText(img, text, (x, y), font, font_scale, 0, thickness)

    return img


def _augment(img: np.ndarray) -> np.ndarray:
    """Apply random augmentations: rotation, blur, brightness, noise."""
    h, w = img.shape[:2]

    # Rotation (±5°)
    angle = random.uniform(-5, 5)
    M = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    img = cv2.warpAffine(img, M, (w, h), borderValue=255)

    # Blur
    if random.random() < 0.3:
        ksize = random.choice([3, 5])
        img = cv2.GaussianBlur(img, (ksize, ksize), 0)

    # Brightness shift
    shift = random.randint(-30, 30)
    img = np.clip(img.astype(np.int16) + shift, 0, 255).astype(np.uint8)

    # Salt-and-pepper noise
    if random.random() < 0.2:
        noise_mask = np.random.random(img.shape)
        img[noise_mask < 0.01] = 0
        img[noise_mask > 0.99] = 255

    return img


def generate_digit_dataset(
    samples_per_class: int = 500,
    output_dir: str | None = None,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Generate synthetic digit images with augmentation.

    Args:
        samples_per_class: Number of images per digit class.
        output_dir: If provided, save images to disk.
        seed: Random seed.

    Returns:
        (images, labels) arrays.
    """
    if cv2 is None:
        raise ImportError("opencv-python-headless required")

    np.random.seed(seed)
    random.seed(seed)

    images = []
    labels = []

    for digit in DIGITS:
        for _ in range(samples_per_class):
            img = _render_digit(digit)
            img = _augment(img)
            images.append(img)
            labels.append(digit)

    images = np.array(images, dtype=np.uint8)
    labels = np.array(labels, dtype=np.int64)

    # Shuffle
    indices = np.random.permutation(len(images))
    images = images[indices]
    labels = labels[indices]

    if output_dir:
        _save_dataset(images, labels, output_dir)

    return images, labels


def _save_dataset(images: np.ndarray, labels: np.ndarray, output_dir: str) -> None:
    """Save dataset as numpy arrays."""
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    np.save(path / "images.npy", images)
    np.save(path / "labels.npy", labels)


if __name__ == "__main__":
    imgs, lbls = generate_digit_dataset(samples_per_class=500, output_dir="data/digits", seed=42)
    print(f"Generated {len(imgs)} digit images → data/digits/")
    print(f"  Shape: {imgs.shape}, Labels: {lbls.shape}")
    from collections import Counter
    print(f"  Distribution: {dict(sorted(Counter(lbls.tolist()).items()))}")
