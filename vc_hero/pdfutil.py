"""文本抽取：PDF 简历与训练上下文文件（pdf/txt/md/docx）。抽取失败或正文过短视为失败。"""
import io
import os
import re
import tempfile
import zipfile

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


def _docx_text(data):
    """从 docx（zip 包内的 word/document.xml）抽取纯文本，无需第三方依赖。"""
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
    except Exception as e:
        raise PdfExtractError(f"DOCX 解析失败: {e}")
    xml = re.sub(r"</w:p>", "\n", xml)
    text = re.sub(r"<[^>]+>", "", xml)
    text = (text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
                .replace("&quot;", '"').replace("&apos;", "'"))
    return text.strip()


def extract_uploaded_text(filename, data):
    """按扩展名抽取上传文件的纯文本（训练上下文用）。"""
    name = (filename or "").lower()
    try:
        if name.endswith(".pdf"):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            try:
                tmp.write(data)
                tmp.close()
                return extract_text(tmp.name)
            finally:
                try:
                    os.remove(tmp.name)
                except OSError:
                    pass
        if name.endswith(".docx"):
            text = _docx_text(data)
        elif name.endswith(".txt") or name.endswith(".md"):
            text = data.decode("utf-8", "ignore").strip()
        else:
            raise PdfExtractError("仅支持 PDF / TXT / MD / DOCX 文件")
    except PdfExtractError:
        raise
    except Exception as e:
        raise PdfExtractError(f"文件解析失败: {e}")
    if len(text) < 10:
        raise PdfExtractError("文件中没有可读取的文本内容")
    return text
