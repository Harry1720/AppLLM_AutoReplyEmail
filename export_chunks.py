#Chỉ dùng để xuất kết quả lưu chunks
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
import pandas as pd

persist_dir = "./vector_db"

embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")

vectorstore = Chroma(
    collection_name="emails",
    embedding_function=embeddings,
    persist_directory=persist_dir
)

data = vectorstore.get()
rows = []

for text, meta in zip(data["documents"], data["metadatas"]):
    row = meta.copy()
    row["chunk"] = text
    rows.append(row)

df = pd.DataFrame(rows)
# Thêm encoding UTF-8 với BOM để Excel đọc đúng tiếng Việt
df.to_csv("email_chunks_export.csv", encoding="utf-8-sig", index=False)

print("✅ Đã xuất ra file: email_chunks_export.csv")