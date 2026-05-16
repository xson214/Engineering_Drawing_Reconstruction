# pipelines/inference_pipeline.py
import json
import time
from pathlib import Path
from PIL import Image
import sys
import cv2
sys.path.append(str(Path(__file__).parent.parent))

from src.detector.models import LayoutDetector,TableDetector
from utils.image_utils import draw_bboxes, save_cropped_regions, get_image_info,save_cropped_regions_model2
from utils.read_json import get_table_image_paths
from config.config import OUTPUT_DIR, BASE_DIR
from  src.detector.ocr_result import process_all_jsons


def _merge_overlap_boxes(boxes, axis='y', tol=8):
    """Gộp các bbox row/column gần trùng nhau theo trục chỉ định.

    Khi TableDetector trả về vài bbox row/col chỉ lệch nhau vài pixel
    (do hạ threshold), việc giao chéo sẽ sinh nhiều ô con không cần thiết
    và làm sai cấu trúc bảng. Hàm này gộp chúng lại.
    """
    if not boxes:
        return []
    key_lo = 1 if axis == 'y' else 0
    key_hi = 3 if axis == 'y' else 2
    sorted_boxes = sorted(boxes, key=lambda d: d['bbox'][key_lo])
    merged = []
    for box in sorted_boxes:
        bbox = list(box['bbox'])
        conf = float(box.get('confidence', 0))
        if merged and abs(bbox[key_lo] - merged[-1]['bbox'][key_lo]) <= tol:
            last = merged[-1]
            last['bbox'][key_lo] = min(last['bbox'][key_lo], bbox[key_lo])
            last['bbox'][key_hi] = max(last['bbox'][key_hi], bbox[key_hi])
            last['confidence'] = max(last['confidence'], conf)
            continue
        merged.append({
            "class_name": box.get('class_name', ''),
            "confidence": conf,
            "bbox": bbox,
        })
    return merged

class InferencePipeline:
    """Pipeline inference hoàn chỉnh"""

    def __init__(self):
        """
        Khởi tạo pipeline

        Args:
            detector: LayoutDetector instance (nếu None sẽ tự tạo)
        """
        self.detector = LayoutDetector(
            model_path=str(BASE_DIR / "models" / "Engineering Drawings"),
            threshold=0.7,
            verbose=True
        )
        self.detector2 = TableDetector(
            model_path=str(BASE_DIR / "models" / "transdetect"),
            threshold=0.3,
        )


        # Mapping từ class DETR sang class yêu cầu
        self.class_mapping = {
            "Picture": "PartDrawing",
            "Text": "Note",
            "Table": "Table"
        }

        print("✅ InferencePipeline initialized")


    def process_image(self, image_path, save_crops=True, save_vis=True, verbose=True):
        """
        Xử lý một ảnh với cả 2 model.
        - Model 1: xử lý layout bình thường
        - Model 2: chỉ xử lý các Table đã crop từ Model 1, lưu crop vào folder riêng
        """
        start_time = time.time()
        image_pil = Image.open(image_path).convert("RGB")

        image_name = Path(image_path).stem

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"📷 Processing: {image_path}")
            print(f"   Image size: {image_pil.size}")

        # ====================== MODEL 1 ======================
        detections = self.detector.detect(image_pil)

        if verbose:
            print(f"   [Model 1] Detected {len(detections)} objects")

        # Crop và Visualization cho Model 1 (giữ nguyên logic cũ)
        cropped_paths_model1 = []
        if save_crops and len(detections) > 0:
            if verbose:
                print("   [Model 1] Saving cropped regions...")
            cropped_paths_model1 = save_cropped_regions(image_pil, detections, prefix=image_name)

        if save_vis and len(detections) > 0:
            vis_path = OUTPUT_DIR / f"{image_name}_vis_model1.png"
            draw_bboxes(image_pil, detections, save_path=vis_path)
        output = {
            "image": f"{image_name}.jpg",
            "image_info": {
                "width": image_pil.width,
                "height": image_pil.height,
                "mode": image_pil.mode
            },
            "processing_time_ms": round((time.time() - start_time) * 1000, 2),
            "num_objects": len(detections),
            "detection_threshold": self.detector.threshold,
            "objects": []
        }

        # Thêm objects từ Model 1
        for i, det in enumerate(detections):
            class_name = det['class_name']
            mapped_class = self.class_mapping.get(class_name, class_name)

            obj = {
                "id": i + 1,
                "class": mapped_class,
                "original_class": class_name,
                "confidence": det['confidence'],
                "bbox": {
                    "x1": int(det['bbox'][0]),
                    "y1": int(det['bbox'][1]),
                    "x2": int(det['bbox'][2]),
                    "y2": int(det['bbox'][3])
                },
                "crop_path": str(cropped_paths_model1[i]) if i < len(cropped_paths_model1) else None,
            }
            output["objects"].append(obj)

        # Lưu JSON
        json_path = OUTPUT_DIR / f"{image_name}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2, ensure_ascii=False)

        if verbose:
            print(f"   ✅ Saved JSON: {json_path}")
            print(f"   ⏱️  Total time: {output['processing_time_ms']} ms")
            print(f"{'=' * 60}")
        # ====================== MODEL 2 - Chỉ xử lý Table ======================
        detections2_list = []
        cropped_paths_model2 = []

        if save_crops:
            folder_path = str(OUTPUT_DIR)
            image_paths = get_table_image_paths(folder_path)

            if image_paths:
                print(f"   [Model 2] Tìm thấy {len(image_paths)} ảnh Table để xử lý...")

                model2_crop_dir = OUTPUT_DIR / "cropped_model2"
                model2_crop_dir.mkdir(parents=True, exist_ok=True)




                for i, img_path in enumerate(image_paths, 1):
                    try:
                        image_cv = cv2.imread(img_path)
                        if image_cv is None:
                            continue
                        image_rgb = cv2.cvtColor(image_cv, cv2.COLOR_BGR2RGB)
                        pil_image = Image.fromarray(image_rgb)
                        if verbose:
                            print(f"   [Model 2] Processing Table {i}/{len(image_paths)}: {Path(img_path).name}")

                        detections2 = self.detector2.detect(pil_image)

                        # --- THUẬT TOÁN GIAO CẮT HÀNG VÀ CỘT (INTERSECTION) ---
                        # 1. Tách các Hàng, Cột và Header
                        raw_rows = [d for d in detections2 if d['class_name'] == 'table row']
                        raw_cols = [d for d in detections2 if d['class_name'] == 'table column']
                        column_headers = [d for d in detections2 if d['class_name'] == 'table column header']
                        other_dets = [d for d in detections2
                                      if d['class_name'] not in ('table row', 'table column')]

                        # 2. Dedupe row/col gần trùng (do hạ threshold detector dễ sinh trùng)
                        rows = _merge_overlap_boxes(raw_rows, axis='y', tol=8)
                        cols = _merge_overlap_boxes(raw_cols, axis='x', tol=8)

                        # 3. Promote "table column header" thành row nếu không có row nào
                        # phủ vùng đó (TableDetector hay miss header do style khác data row).
                        for header in column_headers:
                            hy_center = (header['bbox'][1] + header['bbox'][3]) / 2
                            if not any(r['bbox'][1] <= hy_center <= r['bbox'][3] for r in rows):
                                rows.append({
                                    'class_name': 'table row',
                                    'confidence': float(header['confidence']),
                                    'bbox': list(header['bbox']),
                                })
                                if verbose:
                                    print(f"   [Model 2] Promoted column header -> row @y={int(hy_center)}")

                        rows = _merge_overlap_boxes(rows, axis='y', tol=8)

                        # 4. Sinh cells bằng giao chéo row × col
                        cells = []
                        for row in rows:
                            for col in cols:
                                x1 = max(row['bbox'][0], col['bbox'][0])
                                y1 = max(row['bbox'][1], col['bbox'][1])
                                x2 = min(row['bbox'][2], col['bbox'][2])
                                y2 = min(row['bbox'][3], col['bbox'][3])
                                if x2 > x1 and y2 > y1:
                                    cells.append({
                                        "class_name": "table cell",
                                        "confidence": min(row['confidence'], col['confidence']),
                                        "bbox": [x1, y1, x2, y2]
                                    })

                        # 5. Ghép lại detections2: giữ các class khác + rows/cols đã dedupe + cells mới
                        detections2 = other_dets + rows + cols + cells
                        # --------------------------------------------------------
                        
                        detections2_list.append({
                            "image_path": img_path,
                            "detections": detections2
                        })

                        # Lưu crop cho Model 2
                        table_prefix = f"{image_name}_table_{i}"
                        crops = save_cropped_regions_model2(image_cv, detections2, model2_crop_dir, table_prefix)
                        cropped_paths_model2.extend(crops)

                    except Exception as e:
                        print(f"❌ Lỗi Model 2 khi xử lý {img_path}: {e}")

        #model 3
        result = process_all_jsons()


        return output

    def process_batch(self, image_paths, **kwargs):
        """
        Xử lý nhiều ảnh

        Args:
            image_paths: List đường dẫn ảnh

        Returns:
            list: Kết quả cho từng ảnh
        """
        results = []
        for i, image_path in enumerate(image_paths):
            print(f"\n[{i + 1}/{len(image_paths)}]")
            result = self.process_image(image_path, **kwargs)
            results.append(result)
        return results

    def get_pipeline_info(self):
        """Lấy thông tin pipeline"""
        model_info = self.detector.get_model_info()
        return {
            "model": model_info,
            "class_mapping": self.class_mapping,
            "output_dir": str(OUTPUT_DIR)
        }