from email_reasoning_system import EmailReasoningSystem, GraphState
import logging

logging.basicConfig(level=logging.INFO)

def test_with_sample_email():
    """Test with a sample email"""
    
    # Sample email for testing
    sample_email = {
        'id': 'test_123',
        'subject': 'Hỏi về dự án website',
        'from': 'client@example.com',
        'date': 'Mon, 1 Jan 2024 10:00:00 +0700',
        'body': 'Chào bạn, tôi muốn hỏi về tiến độ dự án website của chúng ta. Khi nào có thể hoàn thành?',
        'snippet': 'Hỏi về tiến độ dự án website'
    }
    
    # Initialize system
    system = EmailReasoningSystem()
    
    # Test individual steps
    state = GraphState(
        new_email_id="test_123",
        user_id="me",
        email_content=sample_email,
        context_emails=[],
        draft_reply={},
        error=""
    )
    
    # Test context retrieval
    print("🧪 Testing context retrieval...")
    state = system.retrieve_context_node(state)
    
    # Test reply generation
    print("🧪 Testing LLAMA 3 reply generation...")
    state = system.generate_reply_node(state)
    
    # Display results
    print("\n" + "="*50)
    print("📧 TEST RESULTS")
    print("="*50)
    print(f"Original email: {sample_email['subject']}")
    print(f"From: {sample_email['from']}")
    print(f"Content: {sample_email['body']}")
    print(f"\n🔍 Found: {len(state['context_emails'])} relevant emails")
    
    if state.get('draft_reply'):
        print(f"\n🤖 Generated reply:")
        print(f"Subject: {state['draft_reply']['subject']}")
        print("-" * 30)
        print(state['draft_reply']['body'])
        print("-" * 30)
    
    if state.get('error'):
        print(f"\n❌ Error: {state['error']}")

if __name__ == "__main__":
    test_with_sample_email()