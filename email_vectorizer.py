import os
import sys
import logging
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import SupabaseVectorStore
from supabase.client import Client, create_client
from gmail_reader import get_sent_emails

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# Tải biến môi trường (.env)
load_dotenv()

def process_emails():
    # 1. KHỞI TẠO HÀM EMBEDDINGS (Giữ nguyên)
    logging.info("🚀 Khởi tạo mô hình embeddings (HuggingFace)...")
    embeddings = HuggingFaceEmbeddings(
        model_name="sentence-transformers/all-MiniLM-L6-v2"
    )

    # 2. KHỞI TẠO BỘ CHIA VĂN BẢN (Giữ nguyên)
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", ".", "!", "?", " ", ""]
    )
    
    # 3. LẤY EMAILS TỪ GMAIL
    logging.info("📧 Đang lấy email đã gửi từ Gmail...")
    try:
        emails = get_sent_emails()
        logging.info(f"✓ Lấy được {len(emails)} email.")
        if not emails:
            logging.warning("Không tìm thấy email nào. Dừng lại.")
            return
    except Exception as e:
        logging.error(f"❌ Lỗi khi gọi get_sent_emails(): {e}")
        return

    # 4. KẾT NỐI VỚI SUPABASE CLOUD (THAY THẾ CHROMA)
    logging.info("☁️ Đang kết nối tới Supabase Cloud...")
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_SERVICE_KEY")
    
    if not supabase_url or not supabase_key:
        logging.error("❌ Lỗi: SUPABASE_URL và SUPABASE_SERVICE_KEY chưa được đặt trong .env")
        sys.exit(1) # Dừng hẳn

    try:
        supabase_client: Client = create_client(supabase_url, supabase_key)
        logging.info("✓ Kết nối Supabase thành công.")
    except Exception as e:
        logging.error(f"❌ Lỗi khi kết nối Supabase: {e}")
        return

    # 5. [TÙY CHỌN] XÓA DỮ LIỆU CŨ (Giống logic xóa folder)
    logging.info("🗑️ Đang xóa dữ liệu cũ trên bảng 'documents'...")
    # Xóa tất cả các hàng có id không phải là UUID rỗng (xóa tất cả)
    supabase_client.table("documents").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
    logging.info("✓ Xóa dữ liệu cũ thành công.")


    # 6. KHỞI TẠO SUPABASE VECTOR STORE (THAY THẾ CHROMA)
    vectorstore = SupabaseVectorStore(
        client=supabase_client,
        embedding=embeddings,
        table_name="documents",      # Tên bảng bạn tạo ở SQL
        query_name="match_documents" # Tên hàm bạn tạo ở SQL
    )

    # 7. XỬ LÝ VÀ NẠP DỮ LIỆU LÊN CLOUD
    logging.info("⏳ Bắt đầu vector hóa và nạp (upload) dữ liệu...")
    count_chunks = 0
    total_emails = len(emails)
    
    for i, email in enumerate(emails):
        try:
            logging.info(f"  -> Đang xử lý email {i+1}/{total_emails}: {email['subject'][:40]}...")
            
            full_content = f"""
From: {email['from']}
To: {email['to']}
Subject: {email['subject']}
Date: {email['date']}

{email['body']}
"""
            chunks = text_splitter.split_text(full_content)
            
            metadatas = [{
                "email_id": email.get('id', f'unknown_{i}'),
                "subject": email.get('subject', 'No Subject'),
                "from": email.get('from', 'Unknown Sender'),
                "to": email.get('to', 'Unknown Recipient'),
                "date": email.get('date', 'No Date'),
                "chunk_id": chunk_index
            } for chunk_index in range(len(chunks))]

            # NẠP DỮ LIỆU LÊN SUPABASE (Bỏ `ids=ids`)
            vectorstore.add_texts(texts=chunks, metadatas=metadatas)
            
            count_chunks += len(chunks)
        except Exception as e:
            logging.warning(f"  ⚠️ Lỗi khi xử lý email ID {email.get('id')}: {e}")
            # Bỏ qua email này và tiếp tục

    # 8. HOÀN THÀNH (Bỏ `vectorstore.persist()`)
    logging.info("\n" + "="*30)
    logging.info("✅ HOÀN THÀNH!")
    logging.info(f"Đã vector hóa {total_emails} email thành {count_chunks} chunks.")
    logging.info("Dữ liệu đã được lưu trên Supabase Cloud (dùng 384 chiều).")
    logging.info("="*30)
    return vectorstore

if __name__ == "__main__":
    process_emails()