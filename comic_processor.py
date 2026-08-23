import os
import sys
import json
import base64
import zipfile
import requests
from PIL import Image
from reportlab.pdfgen import canvas
import gdrive_helper
import telegram_helper

TASK_ID = os.environ.get("TASK_ID", "task_comic_001")
TASK_PAYLOAD = os.environ.get("TASK_PAYLOAD", "")
DRIVE_ROOT = os.environ.get("GDRIVE_FOLDER_ID", "")

def parse_payload():
    if not TASK_PAYLOAD:
        return {"task_id": TASK_ID, "title": TASK_ID, "chapters": [], "chat_id": "", "post_id": ""}
    try:
        decoded = base64.b64decode(TASK_PAYLOAD).decode("utf-8")
        return json.loads(decoded)
    except Exception as e:
        return {"task_id": TASK_ID, "title": TASK_ID, "chapters": [], "chat_id": "", "post_id": ""}

def images_to_pdf(image_paths, output_pdf):
    if not image_paths:
        return False
    valid_imgs = []
    for p in image_paths:
        try:
            with Image.open(p) as img:
                img.verify()
            valid_imgs.append(p)
        except Exception:
            pass
    if not valid_imgs:
        return False

    c = canvas.Canvas(output_pdf)
    for p in valid_imgs:
        with Image.open(p) as img:
            w, h = img.size
            c.setPageSize((w, h))
            c.drawImage(p, 0, 0, width=w, height=h)
            c.showPage()
    c.save()
    return os.path.exists(output_pdf)

def images_to_cbz(image_paths, output_cbz):
    with zipfile.ZipFile(output_cbz, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in image_paths:
            zf.write(p, arcname=os.path.basename(p))
    return os.path.exists(output_cbz)

def main():
    print(f"📚 Starting Graphic & Comic Processor for: {TASK_ID}")
    data = parse_payload()
    title = data.get("title", TASK_ID)
    chapters = data.get("chapters", [])
    chat_id = data.get("chat_id", "")
    post_id = data.get("post_id", "")

    work_dir = "./temp_downloads"
    os.makedirs(work_dir, exist_ok=True)

    # Resumable processing per chapter
    for idx, chap in enumerate(chapters):
        chap_title = chap.get("name", f"Chapter_{idx+1}")
        img_urls = chap.get("images", [])
        chap_dir = os.path.join(work_dir, f"chap_{idx+1}")
        os.makedirs(chap_dir, exist_ok=True)

        img_paths = []
        for img_idx, url in enumerate(img_urls):
            img_path = os.path.join(chap_dir, f"page_{img_idx+1:03d}.jpg")
            if not os.path.exists(img_path) or os.path.getsize(img_path) == 0:
                try:
                    r = requests.get(url, timeout=30)
                    if r.status_code == 200:
                        with open(img_path, "wb") as f:
                            f.write(r.content)
                except Exception:
                    pass
            if os.path.exists(img_path):
                img_paths.append(img_path)

        if not img_paths:
            continue

        pdf_path = os.path.join(work_dir, f"{title}_{chap_title}.pdf")
        cbz_path = os.path.join(work_dir, f"{title}_{chap_title}.cbz")

        images_to_pdf(img_paths, pdf_path)
        images_to_cbz(img_paths, cbz_path)

        # Upload GDrive
        try:
            folder_id = gdrive_helper.get_or_create_folder(title, DRIVE_ROOT)
            gdrive_helper.upload_file_to_drive(pdf_path, os.path.basename(pdf_path), folder_id)
            gdrive_helper.upload_file_to_drive(cbz_path, os.path.basename(cbz_path), folder_id)
        except Exception as e:
            print(f"⚠️ GDrive upload error: {e}")

        # Send to TG comments
        if chat_id and post_id:
            caption = f"📖 <b>{chap_title}</b> | {title}"
            telegram_helper.send_document(chat_id, pdf_path, caption=f"{caption} (PDF)", reply_to_message_id=int(post_id))
            telegram_helper.send_document(chat_id, cbz_path, caption=f"{caption} (CBZ)", reply_to_message_id=int(post_id))

    print("🎉 Comic packaging & publishing completed.")

if __name__ == "__main__":
    main()
