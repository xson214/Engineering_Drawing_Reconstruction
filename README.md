# Engineering Drawing Reconstruction

A powerful AI-driven pipeline that converts complex engineering and technical drawing images into fully editable Microsoft Word (`.docx`) documents while preserving their exact spatial layout.

## Overview
This project uses state-of-the-art Deep Learning models to analyze engineering drawings, extract structured elements (tables, text notes, pictures), and reconstruct them dynamically. 

Key technical features include:
- **Layout Detection:** Utilizes Hugging Face's `DetrForSegmentation` to detect regions like Tables, Pictures, and Notes.
- **Table Structure Recognition:** Implements Microsoft's `TableTransformerForObjectDetection` with a custom Spatial Intersection algorithm to perfectly recover grid structures (rows, columns, and spanning cells).
- **OCR Engine:** Integrates `PaddleOCR` for robust multi-lingual text extraction.
- **Absolute Rendering Engine:** Leverages raw OOXML manipulations via `python-docx` to enforce absolute positioning, floating tables, and zero-margin elements to prevent layout breakage from Word's auto-reflow.

## Project Structure
- `app/`: Streamlit web interface for uploading images and previewing results.
- `src/detector/`: Core AI pipeline scripts (Model wrapping, Inference, OCR execution).
- `src/reconstruction/`: The rendering engine (`engine.py`) responsible for generating the pixel-perfect `.docx`.
- `pipelines/`: Orchestrator linking models, OCR, and Document generation.
- `config/`: Configuration parameters (image processing rules, output paths).

## Usage
1. Install dependencies:
```bash
pip install -r requirements.txt
```
2. Run the Streamlit interface:
```bash
streamlit run app/app.py
```
3. Upload an engineering drawing. The system will automatically process the image and provide a `.docx` download link.
