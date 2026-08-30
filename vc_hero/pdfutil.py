"""PDF 纯文本抽取。抽取失败或正文过短时视为上传失败。"""
from pypdf import PdfReader


class PdfExtractError(Exception):
    pass


def extract_text(pdf_path):
    try:
        reader = PdfReader(pdf_path)
        parts = []
        for page in reader.pages:
            parts.append(page.extract_text() or "")
        text = "\n".join(parts).strip()
    except Exception as e:
        raise PdfExtractError(f"PDF 解析失败: {e}")
    if len(text) < 20:
        raise PdfExtractError("无法从 PDF 中抽取有效文本（可能是扫描件图片型 PDF）")
    return text
