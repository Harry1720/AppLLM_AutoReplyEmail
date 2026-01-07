import logging
from app.infra.ai.vectorizer import EmailVectorizer

class SyncEmailsUseCase:
    def __init__(self, user_id: str, token_data: dict):
        self.user_id = user_id
        self.token_data = token_data
        # Khởi tạo Service Vectorizer (Tầng Infra)
        self.vectorizer = EmailVectorizer(user_id, token_data)

    def execute(self):
              
        try:
            # Gọi hàm sync từ service
            result = self.vectorizer.sync_user_emails()
            
            # Log kết quả
            if result.get('synced_count', 0) > 0:
                logging.info(f"✨ [UseCase] Đã học xong {result['synced_count']} kiến thức mới!")
            else:
                logging.info(f"💤 [UseCase] Không có dữ liệu mới để học.")
                
            return result
            
        except Exception as e:
            logging.error(f" [UseCase] Lỗi đồng bộ: {str(e)}")
            raise e