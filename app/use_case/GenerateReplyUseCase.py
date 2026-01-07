from app.infra.ai.reasoning import create_single_email_workflow, GraphState

class GenerateReplyUseCase:
    def __init__(self, user_id: str, token_data: dict):
        self.user_id = user_id
        self.token_data = token_data

    def execute(self, msg_id: str):
        # 1. Khởi tạo Workflow
        app = create_single_email_workflow(self.user_id, self.token_data)
        
        # 2. Tạo trạng thái ban đầu
        initial_state = GraphState(
            user_id=self.user_id,
            target_email_id=msg_id,
            current_email={},
            context_emails=[],
            draft_reply={},
            error=""
        )
        
        # 3. Chạy quy trình
        print(f" [UseCase] Đang gọi AI xử lý email {msg_id}...")
        result = app.invoke(initial_state)
        
        if result.get("error"):
             raise Exception(result["error"])

        # 4. Trả về kết quả
        draft_data = result.get("draft_reply", {})
        return {
            "message": "Đã tạo bản nháp thành công", 
            "draft": draft_data,
            "draft_id": draft_data.get("draft_id") 
        }