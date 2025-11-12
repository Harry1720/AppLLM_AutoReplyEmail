from email_reasoning_system import create_reasoning_workflow, EmailReasoningState
import logging

logging.basicConfig(level=logging.INFO)

def demo_with_sample_email():
    """Demo với email mẫu"""
    
    # Email mẫu để test
    sample_email = {
        'id': 'demo_123',
        'subject': 'Hỏi về dự án TikTok',
        'from': 'client@example.com',
        'date': 'Mon, 1 Jan 2024 10:00:00 +0700',
        'body': 'Chào bạn, tôi muốn hỏi về tiến độ dự án chia sẻ video TikTok. Khi nào có thể hoàn thành?',
        'snippet': 'Hỏi về tiến độ dự án TikTok'
    }
    
    # Tạo workflow
    app = create_reasoning_workflow()
    
    # State với email mẫu
    initial_state = EmailReasoningState(
        new_email=sample_email,
        relevant_emails=[],
        context="",
        draft_reply="",
        final_reply="",
        confidence_score=0.0
    )
    
    # Chạy từ bước tìm kiếm (bỏ qua read_email)
    print("🧪 DEMO: Chạy với email mẫu")
    
    # Tạo system để test manual
    from email_reasoning_system import EmailReasoningSystem
    system = EmailReasoningSystem()
    
    # Chạy từng bước
    state = initial_state
    state = system.find_relevant_past_emails(state)
    state = system.create_context(state)
    state = system.draft_reply_with_llm(state)
    state = system.review_draft(state)
    
    # Hiển thị kết quả
    print("\n" + "="*50)
    print("📧 KẾT QUẢ DEMO")
    print("="*50)
    print(f"Email gốc: {sample_email['subject']}")
    print(f"Từ: {sample_email['from']}")
    print(f"Nội dung: {sample_email['body']}")
    print(f"\n🔍 Tìm thấy: {len(state['relevant_emails'])} email liên quan")
    print(f"\n🤖 Bản nháp trả lời (Confidence: {state['confidence_score']:.1%}):")
    print("-" * 30)
    print(state['final_reply'])
    print("-" * 30)

if __name__ == "__main__":
    demo_with_sample_email()