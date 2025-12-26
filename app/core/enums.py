from enum import Enum

class EmailFolder(str, Enum):
    INBOX = "INBOX"     
    SENT = "SENT"      
    ARCHIVE = "ARCHIVE"
    TRASH = "TRASH"     

class EmailStatus(str, Enum):
    ALL = "ALL"         
    UNREAD = "UNREAD"   
    STARRED = "STARRED" 