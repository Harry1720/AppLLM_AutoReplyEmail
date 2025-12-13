export interface Email {
  id: string;
  sender: string;
  senderEmail: string;
  subject: string;
  snippet: string;
  body: string;
  timestamp: string;
  hasAiSuggestion?: boolean;
  isRead?: boolean;
  draftId?: string; // ID của draft được tạo bởi AI
  aiReplyGenerated?: boolean; // Đã tạo câu trả lời AI chưa
  replySent?: boolean; // Đã gửi trả lời chưa
  attachments?: EmailAttachment[]; // File đính kèm
}

export interface EmailAttachment {
  filename: string;
  mimeType: string;
  size?: number;
  attachmentId?: string;
}

export interface AiSuggestion {
  id: string;
  emailId: string;
  content: string;
  confidence: number;
  createdAt: string;
}

export interface User {
  id: string;
  name: string;
  email: string;
  avatar?: string;
}

export interface EmailThread {
  id: string;
  emails: Email[];
  participants: string[];
  subject: string;
  lastActivity: string;
}