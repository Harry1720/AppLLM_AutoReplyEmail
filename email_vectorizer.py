from langchain_text_splitters import RecursiveCharacterTextSplitter
# from langchain_openai import OpenAIEmbeddings
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from gmail_reader import get_sent_emails
import os
from dotenv import load_dotenv

load_dotenv()

def process_emails():
    # Khởi tạo OpenAI embeddings
    # embeddings = OpenAIEmbeddings()
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

    
    # Tạo text splitter
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,  # Kích thước chunk nhỏ hơn để truy xuất tốt hơn
        chunk_overlap=100,  # Giảm overlap để tăng hiệu suất
        separators=["\n\n", "\n", ".", "!", "?", " ", ""]  # Tối ưu việc tách văn bản
    )
    
    # Lấy emails từ Gmail
    emails = get_sent_emails()
    
    # Folder lưu vector DB
    persist_dir = "./vector_db"

    # Tạo database vector
    db_name = "vector_db"
    # Nếu DB cũ tồn tại → xóa để tạo mới
    if os.path.exists(persist_dir):
        import shutil
        shutil.rmtree(persist_dir)

    # Tạo vectorstore Chroma
    vectorstore = Chroma(
        collection_name="emails",
        embedding_function=embeddings,
        persist_directory=persist_dir
    )

    # Xử lý từng email
    count_chunks = 0
    for email in emails:
        full_content = f"""
From: {email['from']}
To: {email['to']}
Subject: {email['subject']}
Date: {email['date']}

{email['body']}
"""
        # Tách chunk
        chunks = text_splitter.split_text(full_content)

        # Thêm vào vector DB
        ids = [f"{email['id']}_{i}" for i in range(len(chunks))]
        metadatas = [{
            "email_id": email['id'],
            "subject": email['subject'],
            "from": email['from'],
            "to": email['to'],
            "date": email['date'],
            "chunk_id": i
        } for i in range(len(chunks))]

        vectorstore.add_texts(texts=chunks, metadatas=metadatas, ids=ids)
        count_chunks += len(chunks)

    vectorstore.persist()
    print(f"Đã vector hóa {len(emails)} email thành {count_chunks} chunks.")
    return vectorstore

if __name__ == "__main__":
    process_emails()