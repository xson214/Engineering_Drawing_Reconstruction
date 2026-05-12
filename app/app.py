import streamlit as st
import json
from PIL import Image
from pathlib import Path
import shutil
import os
import subprocess
import time
import sys
import pandas as pd

# ================== CẤU HÌNH ==================
st.set_page_config(page_title="OCR Viewer - Engineering Drawings", page_icon="📄", layout="wide")

# Project root = thư mục cha của app/
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
VISUALIZE_DIR = OUTPUTS_DIR / "visualize"
JSON_PATH = OUTPUTS_DIR / "ocr_results" / "web_demo_results.json"
UPLOAD_IMAGES_DIR = BASE_DIR / "uploaded_images"
MAIN_PY_PATH = BASE_DIR / "main.py"


# Tạo thư mục
for dir_path in [OUTPUTS_DIR, VISUALIZE_DIR, UPLOAD_IMAGES_DIR, OUTPUTS_DIR / "ocr_results"]:
    dir_path.mkdir(parents=True, exist_ok=True)

# Session State
if 'json_data' not in st.session_state:
    st.session_state.json_data = None
if 'uploaded_images' not in st.session_state:
    st.session_state.uploaded_images = {}
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'last_stdout' not in st.session_state:
    st.session_state.last_stdout = None
if 'last_stderr' not in st.session_state:
    st.session_state.last_stderr = None

# ====================== HÀM ======================
@st.cache_data(ttl=5)
def load_json_data():
    try:
        if JSON_PATH.exists():
            with open(JSON_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None
    except:
        return None


def run_ocr_pipeline():
    if not MAIN_PY_PATH.exists():
        return False, "", f"Không tìm thấy main.py tại: {MAIN_PY_PATH}"

    try:
        VISUALIZE_DIR.mkdir(parents=True, exist_ok=True)
        python_exe = sys.executable
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        st.info(f"🔧 Đang chạy: {MAIN_PY_PATH.name}")
        st.info(f"📁 Thư mục: {BASE_DIR}")

        result = subprocess.run(
            [python_exe, str(MAIN_PY_PATH)],
            capture_output=True,
            text=True,
            timeout=900,
            cwd=BASE_DIR,
            env=env,
            check=False
        )

        # Không dùng st.expander ở đây vì nó sẽ biến mất sau st.rerun()
        return result.returncode == 0, result.stdout, result.stderr

    except Exception as e:
        return False, "", str(e)


def save_uploaded_image(uploaded_file):
    try:
        save_path = UPLOAD_IMAGES_DIR / uploaded_file.name
        with open(save_path, 'wb') as f:
            f.write(uploaded_file.getbuffer())
        return save_path
    except Exception as e:
        st.error(f"Lỗi lưu file: {e}")
        return None


def find_visualized_image(image_name):
    for directory in [VISUALIZE_DIR, OUTPUTS_DIR]:
        if not directory.exists():
            continue
        for ext in ['*.jpg', '*.jpeg', '*.png', '*.JPG', '*.PNG']:
            for file in directory.glob(ext):
                if image_name.lower() in file.stem.lower():
                    return file
    # Lấy file mới nhất nếu không tìm theo tên
    all_files = []
    for directory in [VISUALIZE_DIR, OUTPUTS_DIR]:
        if directory.exists():
            all_files.extend([f for f in directory.glob("*.png")] + [f for f in directory.glob("*.jpg")])
    if all_files:
        return max(all_files, key=lambda x: x.stat().st_mtime)
    return None


def clean_directories_content():
    for directory in [BASE_DIR / "cropped_regions", OUTPUTS_DIR / "cropped_model2",
                      OUTPUTS_DIR / "ocr_results", OUTPUTS_DIR, UPLOAD_IMAGES_DIR]:
        if directory.exists():
            shutil.rmtree(directory, ignore_errors=True)
    # Tạo lại thư mục cần thiết
    for dir_path in [VISUALIZE_DIR, UPLOAD_IMAGES_DIR, OUTPUTS_DIR / "ocr_results"]:
        dir_path.mkdir(parents=True, exist_ok=True)


# ====================== MAIN APP ======================
def main():
    st.title("📄 Engineering Drawings OCR Viewer")
    st.markdown("---")

    # Load JSON
    if st.session_state.json_data is None:
        st.session_state.json_data = load_json_data()

    # ================== SIDEBAR ==================
    with st.sidebar:
        st.header("⚙️ Điều khiển")
        with st.expander("📖 HƯỚNG DẪN SỬ DỤNG", expanded=True):
            st.markdown("""
            ### 🚀 Các bước thực hiện:

            1. **📤 Tải ảnh lên**
               - Nhấn nút "Browse files" trong phần "Tải ảnh lên"
               - Chọn ảnh định dạng PNG, JPG hoặc JPEG
               - Có thể tải nhiều ảnh cùng lúc

            2. **🚀 Chạy OCR Pipeline**
               - Sau khi tải ảnh xong, nhấn nút "Run OCR Pipeline"
               - Quá trình xử lý có thể mất vài phút tùy số lượng ảnh
               - Theo dõi output và log trong các mục mở rộng

            3. **📷 Xem kết quả**
               - Chuyển sang tab "Ảnh kết quả"
               - Chọn ảnh từ dropdown để xem:
                 - Ảnh gốc đã upload
                 - Ảnh đã vẽ bounding boxes từ OCR

            4. **📊 Xem dữ liệu JSON**
               - Chuyển sang tab "Dữ liệu JSON"
               - Xem bảng kết quả OCR với các thông tin:
                 - Loại đối tượng (class)
                 - Text nhận dạng được
                 - Độ tin cậy (confidence)
                 - Tọa độ bounding box
               - Tải file JSON về máy nếu cần

            ### 🧹 Dọn dẹp:
            -  click vào dấu x để gỡ ảnh 
            - Xóa ảnh đã tải: Xóa ảnh vừa upload mà chưa xử lý
            - Xóa toàn bộ outputs: Xóa sạch kết quả OCR cũ

            ### ⚠️ Lưu ý:
            - để test ảnh tiếp theo vui lòng thực hiện các đủ 3 bước dọn dẹp để tránh xung đột giữa các file 
            - Đợi quá trình OCR hoàn tất trước khi chuyển tab
            - File JSON sẽ được lưu tại: `outputs/ocr_results/web_demo_results.json`
            - Ảnh kết quả được lưu tại: `outputs/visualize/`
            """)

        st.markdown("---")
        if st.session_state.json_data:
            total = st.session_state.json_data.get('total_ocr_cells', 0)
            st.success(f"✅ JSON có {total} ô OCR")
        else:
            st.warning("⚠️ Chưa có dữ liệu JSON")

        st.markdown("---")

        # === UPLOAD ẢNH ===
        st.subheader("📤 1. Tải ảnh lên")
        uploaded_files = st.file_uploader(
            "Chọn ảnh (PNG, JPG, JPEG)",
            type=['png', 'jpg', 'jpeg'],
            accept_multiple_files=True,
            key="uploader"   # Quan trọng: thêm key để reset sau khi xóa
        )

        if uploaded_files:
            new_files = 0
            for file in uploaded_files:
                if file.name not in st.session_state.uploaded_images:
                    save_path = save_uploaded_image(file)
                    if save_path:
                        try:
                            pil_img = Image.open(file)
                            st.session_state.uploaded_images[file.name] = {
                                'name': file.name,
                                'pil_image': pil_img
                            }
                            new_files += 1
                        except:
                            pass
            if new_files > 0:
                st.success(f"✅ Đã tải {new_files} ảnh lên thành công!")
                time.sleep(0.5)
                st.rerun()

        st.markdown("---")

        # === RUN OCR ===
        st.subheader("🚀 2. Chạy OCR Pipeline")
        pending_files = len(list(UPLOAD_IMAGES_DIR.glob("*")))

        if pending_files > 0:
            st.info(f"📸 Có {pending_files} ảnh đang chờ xử lý")

        run_disabled = st.session_state.processing or pending_files == 0

        if st.button("🚀 Run OCR Pipeline", type="primary", use_container_width=True, disabled=run_disabled):
            st.session_state.processing = True
            st.rerun()

        # Xử lý OCR (sau rerun)
        if st.session_state.processing:
            with st.spinner("🔄 Đang xử lý OCR... Có thể mất vài phút"):
                success, stdout, stderr = run_ocr_pipeline()
                
                st.session_state.last_success = success
                st.session_state.last_stdout = stdout
                st.session_state.last_stderr = stderr

                if success:
                    # Xóa ảnh đã upload sau khi xử lý
                    for f in list(UPLOAD_IMAGES_DIR.iterdir()):
                        if f.is_file():
                            f.unlink()
                    st.session_state.uploaded_images.clear()

                st.cache_data.clear()
                st.session_state.json_data = load_json_data()
                st.session_state.processing = False
                st.rerun()

        # Hiển thị kết quả / Lỗi sau khi xử lý xong
        if st.session_state.get('last_success') is False:
            st.error("❌ Xử lý thất bại! Xem log bên dưới:")
            with st.expander("⚠️ Chi tiết lỗi (Log)", expanded=True):
                st.code(st.session_state.last_stderr, language="bash")
                
            if st.button("🗑️ Xóa log lỗi"):
                st.session_state.last_success = None
                st.session_state.last_stderr = None
                st.rerun()
        elif st.session_state.get('last_success') is True:
            st.success("✅ Xử lý OCR thành công!")
            # Có thể hiển thị thêm log nếu cần
            if st.session_state.last_stderr:
                with st.expander("📋 Log từ quá trình xử lý (Progress bars)"):
                    st.code(st.session_state.last_stderr, language="bash")

        st.markdown("---")

        # Dọn dẹp
        st.subheader("🧹 Dọn dẹp")
        if st.button("🗑️ Xóa ảnh đã tải"):
            st.session_state.uploaded_images.clear()
            for f in list(UPLOAD_IMAGES_DIR.iterdir()):
                if f.is_file():
                    f.unlink()
            st.success("✅ Đã xóa ảnh")
            st.rerun()

        if st.button("💣 Xóa toàn bộ outputs"):
            with st.spinner("Đang xóa..."):
                clean_directories_content()
                st.cache_data.clear()
                st.session_state.json_data = load_json_data()
                st.session_state.uploaded_images.clear()
                st.success("✅ Đã xóa toàn bộ outputs")
                st.rerun()

    # ================== MAIN CONTENT ==================
    tab1, tab2 = st.tabs(["📷 Ảnh kết quả", "📊 Dữ liệu JSON"])

    with tab1:
        st.header("🖼️ Ảnh kết quả (đã vẽ bounding boxes)")
        if st.session_state.uploaded_images:
            selected_name = st.selectbox("Chọn ảnh để xem", options=list(st.session_state.uploaded_images.keys()))
            data = st.session_state.uploaded_images[selected_name]

            st.subheader("📸 Ảnh gốc")
            st.image(data['pil_image'], use_container_width=True)

            stem = Path(selected_name).stem
            vis_path = find_visualized_image(stem)

            if vis_path and vis_path.exists():
                st.subheader("🎯 Ảnh đã vẽ Bounding Boxes")
                st.image(str(vis_path), use_container_width=True)
                st.caption(f"Đường dẫn: {vis_path}")
            else:
                st.info("💡 Chưa có ảnh kết quả. Hãy nhấn **Run OCR Pipeline**")
        else:
            st.info("👈 Vui lòng tải ảnh lên từ sidebar")

    with tab2:
        st.header("📊 Dữ liệu JSON")
        if st.session_state.json_data:
            # ... (giữ nguyên phần hiển thị JSON như cũ)
            objects = []
            if 'results' in st.session_state.json_data:
                for i, item in enumerate(st.session_state.json_data['results']):
                    bbox = item.get('bbox', [])
                    bbox_str = ', '.join(map(str, bbox)) if bbox else 'N/A'
                    objects.append({
                        'STT': i+1,
                        'Kiểu': '🖼️ Ảnh' if item.get('type') == 'image' else '📝 Chữ',
                        'Loại': item.get('class', 'Unknown'),
                        'Text': item.get('text', '')[:60],
                        'Confidence': round(item.get('confidence', 0), 3),
                        'BBox': bbox_str
                    })
            if objects:
                st.dataframe(pd.DataFrame(objects), use_container_width=True)
                st.download_button("📥 Tải JSON",
                                  json.dumps(st.session_state.json_data, ensure_ascii=False, indent=2),
                                  "ocr_results.json")
            else:
                st.warning("Không có dữ liệu results")
        else:
            st.info("Chạy OCR pipeline để xem dữ liệu")

if __name__ == "__main__":
    main()