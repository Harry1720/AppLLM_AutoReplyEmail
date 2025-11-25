# app/core/enums.py
from enum import Enum

class EmailFolder(str, Enum):
    INBOX = "INBOX"     # Hộp thư đến
    SENT = "SENT"       # Thư đã gửi
    ARCHIVE = "ARCHIVE" # Thư lưu trữ
    TRASH = "TRASH"     # Thùng rác

class EmailStatus(str, Enum):
    ALL = "ALL"         # Tất cả
    UNREAD = "UNREAD"   # Chưa đọc
    STARRED = "STARRED" # Có gắn sao