
import cv2
import numpy as np
from PIL import Image, ImageDraw
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path
import sys
import json
sys.path.append(str(Path(__file__).parent.parent))
from typing import List
from config.config import (
    CROP_DIR, IMAGE_SIZE, IMAGE_MEAN,
    IMAGE_STD, RESCALE_FACTOR, DO_NORMALIZE, DO_RESCALE
)


def preprocess_image_for_model(image):
    """
    Tiền xử lý ảnh đúng theo config của model

    Args:
        image: PIL Image hoặc numpy array

    Returns:
        numpy array đã được resize và normalize
    """
    if isinstance(image, Image.Image):
        image = np.array(image).astype(np.float32)

    # Rescale từ [0, 255] sang [0, 1]
    if DO_RESCALE:
        image = image * RESCALE_FACTOR

    # Resize về đúng kích thước model yêu cầu
    target_w, target_h = IMAGE_SIZE["width"], IMAGE_SIZE["height"]
    image_resized = cv2.resize(image, (target_w, target_h))

    # Normalize
    if DO_NORMALIZE:
        image_normalized = (image_resized - IMAGE_MEAN) / IMAGE_STD
    else:
        image_normalized = image_resized

    # Chuyển từ (H, W, C) sang (C, H, W)
    image_tensor = np.transpose(image_normalized, (2, 0, 1))

    # Thêm batch dimension
    image_batch = np.expand_dims(image_tensor, axis=0).astype(np.float32)

    return image_batch


def crop_region(image, bbox, save_path=None, padding=0):
    """
    Crop vùng ảnh theo bounding box

    Args:
        image: PIL Image hoặc numpy array
        bbox: [x1, y1, x2, y2]
        save_path: Đường dẫn để lưu crop (nếu có)
        padding: Số pixel thêm vào xung quanh (tùy chọn)

    Returns:
        PIL Image hoặc numpy array của vùng crop
    """
    x1, y1, x2, y2 = bbox

    # Thêm padding nếu cần
    if padding > 0:
        x1 = max(0, x1 - padding)
        y1 = max(0, y1 - padding)
        x2 = min(image.width if isinstance(image, Image.Image) else image.shape[1], x2 + padding)
        y2 = min(image.height if isinstance(image, Image.Image) else image.shape[0], y2 + padding)

    if isinstance(image, Image.Image):
        cropped = image.crop((x1, y1, x2, y2))
    else:
        cropped = image[y1:y2, x1:x2]

    if save_path:
        if isinstance(cropped, Image.Image):
            cropped.save(save_path)
        else:
            cv2.imwrite(str(save_path), cv2.cvtColor(cropped, cv2.COLOR_RGB2BGR))

    return cropped


def draw_bboxes(image, detections, class_colors=None, save_path=None):
    """
    Vẽ bounding boxes lên ảnh

    Args:
        image: PIL Image
        detections: list of dict với keys: bbox, class_name, confidence
        class_colors: dict mapping class_name -> color
        save_path: Đường dẫn lưu ảnh kết quả

    Returns:
        matplotlib figure
    """
    if isinstance(image, np.ndarray):
        image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    fig, ax = plt.subplots(1, figsize=(12, 8))
    ax.imshow(image)

    # Tạo màu mặc định nếu không có
    if class_colors is None:
        unique_classes = list(set(d['class_name'] for d in detections))
        colors = plt.cm.tab20(np.linspace(0, 1, len(unique_classes)))
        class_colors = {cls: colors[i] for i, cls in enumerate(unique_classes)}

    for det in detections:
        x1, y1, x2, y2 = det['bbox']
        class_name = det['class_name']
        confidence = det['confidence']

        color = class_colors.get(class_name, 'red')

        # Vẽ rectangle
        rect = patches.Rectangle(
            (x1, y1), x2 - x1, y2 - y1,
            linewidth=2, edgecolor=color, facecolor="none"
        )
        ax.add_patch(rect)

        # Vẽ label
        label = f"{class_name}: {confidence:.2f}"
        ax.text(
            x1, y1 - 5, label,
            fontsize=9, color=color,
            bbox=dict(facecolor="white", alpha=0.8, edgecolor="none")
        )

    ax.axis("off")
    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"✅ Saved visualization to {save_path}")

    return fig


def save_cropped_regions(image, detections, prefix="region"):
    """
    Lưu tất cả các vùng crop vào thư mục

    Args:
        image: PIL Image hoặc numpy array
        detections: list of dict
        prefix: Tiền tố cho tên file

    Returns:
        list: Đường dẫn các file đã lưu
    """
    saved_paths = []

    for i, det in enumerate(detections):
        bbox = det['bbox']
        class_name = det['class_name']

        filename = f"{prefix}_{i:03d}_{class_name}.jpg"
        save_path = CROP_DIR / filename

        cropped = crop_region(image, bbox, save_path)
        saved_paths.append(save_path)

        print(f"  Saved crop: {filename}")

    return saved_paths


def get_image_info(image):
    """Lấy thông tin về ảnh"""
    if isinstance(image, Image.Image):
        return {
            "width": image.width,
            "height": image.height,
            "mode": image.mode,
            "size": image.size
        }
    else:
        h, w = image.shape[:2]
        return {
            "width": w,
            "height": h,
            "mode": "RGB",
            "size": (w, h)
        }
CELL_CROP_PADDING = 4
MIN_CELL_SIZE = 5


def save_cropped_regions_model2(image, detections, output_dir: Path, prefix: str) -> List[Path]:
        """Lưu crop cho Model 2 và xuất metadata bảng (rows/cols/cells) ra JSON."""
        cropped_paths = []
        cells_metadata = []
        rows_metadata = []
        cols_metadata = []
        output_dir.mkdir(parents=True, exist_ok=True)
        h_img, w_img = image.shape[:2]

        # Pass 1: thu metadata row/col (chỉ cần bbox để engine dựng cấu trúc bảng,
        # không cần crop ảnh row/col).
        for det in detections:
            cls = det.get('class_name', '')
            bbox = det.get('bbox')
            if not bbox or len(bbox) < 4:
                continue
            entry = {
                "bbox": [int(b) for b in bbox],
                "confidence": float(det.get('confidence', 0)),
            }
            if cls == 'table row':
                rows_metadata.append(entry)
            elif cls == 'table column':
                cols_metadata.append(entry)

        # Pass 2: crop cells với padding để OCR không bị mất nét chữ sát mép.
        for i, det in enumerate(detections):
            class_name = det.get('class_name', '')
            if class_name not in ['table cell', 'table spanning cell']:
                continue
            bbox = det.get('bbox')
            if not bbox or len(bbox) < 4:
                continue

            x1, y1, x2, y2 = map(int, bbox)
            x1 = max(0, x1 - CELL_CROP_PADDING)
            y1 = max(0, y1 - CELL_CROP_PADDING)
            x2 = min(w_img, x2 + CELL_CROP_PADDING)
            y2 = min(h_img, y2 + CELL_CROP_PADDING)
            if x2 - x1 < MIN_CELL_SIZE or y2 - y1 < MIN_CELL_SIZE:
                continue

            cropped = image[y1:y2, x1:x2]
            crop_name = f"{prefix}_model2_crop_{i + 1:03d}.jpg"
            crop_path = output_dir / crop_name
            cv2.imwrite(str(crop_path), cropped)
            cropped_paths.append(crop_path)

            cells_metadata.append({
                "cell_index": i,
                "class_name": class_name,
                "bbox": [x1, y1, x2, y2],
                "cropped_image_path": str(crop_path),
            })

        metadata = {
            "rows": rows_metadata,
            "cols": cols_metadata,
            "cells": cells_metadata,
        }
        json_path = output_dir / f"{prefix}_metadata.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"   📁 Đã lưu metadata vào: {json_path}")

        return cropped_paths
