'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Email } from '@/types/email';
import EmailList from '@/components/EmailList';
import EmailContent from '@/components/EmailContent';
import AiSuggestionPanel from '@/components/AiSuggestionPanel';
import Header from '@/components/Header';
import { fetchEmails, fetchEmailDetail, getAuthToken, getUserInfo, generateAiReply, sendEmail, getAllDrafts, getSentEmails } from '@/services/api';
import { useToast } from '@/components/ToastContainer';

export default function WorkspacePage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [emails, setEmails] = useState<Email[]>([]);
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSyncing, setIsSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextPageToken, setNextPageToken] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [sentEmails, setSentEmails] = useState<Set<string>>(new Set());
  
  // Checkbox states
  const [selectedEmailIds, setSelectedEmailIds] = useState<string[]>([]);
  const [isGeneratingAi, setIsGeneratingAi] = useState(false);

  // Check authentication on mount
  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      router.push('/');
    }
  }, [router]);

  // Sử dụng useCallback để tránh re-create function
  const loadEmails = useCallback(async (pageToken?: string, showLoading = true, append = false) => {
    try {
      if (showLoading) {
        if (append) {
          setIsLoadingMore(true);
        } else {
          setIsLoading(true);
        }
      }
      setError(null);
      
      const data = await fetchEmails(20, pageToken);
      
      // Transform backend email format to frontend format
      interface EmailFromAPI {
        id: string;
        threadId?: string;
        subject?: string;
        snippet?: string;
        from?: string;
        date?: string;
        labelIds?: string[];
      }

      const transformedEmails: Email[] = data.emails.map((email: EmailFromAPI) => {
        // Parse "From" header: "Nguyen Van A <nguyen.a@gmail.com>" hoặc "\"Bảo Huỳnh\" <baohuynh4107@gmail.com>"
        const parseFrom = (fromHeader?: string) => {
          if (!fromHeader) return { name: 'Unknown', email: '' };
          
          // Check if fromHeader has <email> format
          const emailMatch = fromHeader.match(/<(.+?)>/);
          
          if (emailMatch) {
            // Format: "Name <email@domain.com>"
            const emailAddr = emailMatch[1].trim();
            let name = fromHeader.replace(/<.*>/, '').trim();
            // Remove surrounding quotes (both single and double)
            name = name.replace(/^["']|["']$/g, '');
            // If name is empty after removing email part, use email username
            name = name || emailAddr.split('@')[0];
            return { name, email: emailAddr };
          } else {
            // Plain email address without name: "email@domain.com"
            const emailAddr = fromHeader.trim();
            const name = emailAddr.split('@')[0]; // Extract username before @
            return { name, email: emailAddr };
          }
        };

        const { name: senderName, email: senderEmail } = parseFrom(email.from);

        return {
          id: email.id,
          sender: senderName,
          senderEmail: senderEmail,
          subject: email.subject?.trim() || '(No Subject)',
          snippet: email.snippet || '',
          body: email.snippet || '',
          timestamp: email.date || new Date().toISOString(),
          hasAiSuggestion: false,
          aiReplyGenerated: false,
          // isRead: !email.labelIds?.includes('UNREAD'), // Gmail dùng label UNREAD để đánh dấu chưa đọc
        };
      });
      
      // Fetch drafts from Supabase to mark emails with existing drafts
      let emailsWithDrafts = transformedEmails;
      try {
        console.log('📧 Fetching drafts from Supabase...');
        const draftsResponse = await getAllDrafts();
        console.log('📧 Drafts response:', draftsResponse);
        const drafts = draftsResponse.drafts || [];
        console.log('📧 Number of drafts found:', drafts.length);
        
        // Fetch sent email IDs from server
        console.log('📧 Fetching sent emails from server...');
        const sentResponse = await getSentEmails();
        const sentEmailIds = new Set(sentResponse.sent_email_ids || []);
        console.log('📧 Number of sent emails:', sentEmailIds.size);
        setSentEmails(sentEmailIds);
        
        // Create map of email_id -> draft_id
        const draftMap = new Map();
        drafts.forEach((draft: { email_id: string; draft_id: string }) => {
          console.log(`📧 Mapping email_id ${draft.email_id} -> draft_id ${draft.draft_id}`);
          draftMap.set(draft.email_id, draft.draft_id);
        });
        
        // Mark emails that have drafts or have been sent
        emailsWithDrafts = transformedEmails.map(email => {
          const hasDraft = draftMap.has(email.id);
          const draftId = draftMap.get(email.id);
          const isSent = sentEmailIds.has(email.id);
          console.log(`📧 Email ${email.id}: hasDraft=${hasDraft}, draftId=${draftId}, isSent=${isSent}`);
          return {
            ...email,
            aiReplyGenerated: hasDraft && !isSent,
            draftId: draftId || undefined,
            hasAiSuggestion: hasDraft && !isSent,
            replySent: isSent
          };
        });
        console.log('📧 Final emails with drafts:', emailsWithDrafts);
      } catch (draftErr) {
        console.error('❌ Error fetching drafts:', draftErr);
        // Continue without draft info
      }
      
      if (append) {
        setEmails((prev) => [...prev, ...emailsWithDrafts]);
      } else {
        setEmails(emailsWithDrafts);
      }
      setNextPageToken(data.next_page_token);
      
    } catch (err: unknown) {
      console.error('Error loading emails:', err);
      const errorMessage = err instanceof Error ? err.message : 'Không thể tải email. Vui lòng thử lại.';
      setError(errorMessage);
      
      // If authentication error, redirect to login
      if (err instanceof Error && err.message.includes('Authentication')) {
        setTimeout(() => {
          router.push('/');
        }, 2000);
      }
    } finally {
      setIsLoading(false);
      setIsSyncing(false);
      setIsLoadingMore(false);
    }
  }, [router]);

  // Chỉ load lần đầu khi component mount
  useEffect(() => {
    const token = getAuthToken();
    const userInfo = getUserInfo();

    if (!token || !userInfo) {
      router.push('/');
      return;
    }

    // Load emails lần đầu
    loadEmails(undefined, true);
  }, [router, loadEmails]);

  // Handler cho sync từ header - không reload toàn bộ trang
  const handleSyncFromHeader = useCallback(async () => {
    if (isSyncing) return; // Tránh sync nhiều lần
    
    setIsSyncing(true);
    await loadEmails(undefined, false); // Sync mà không show loading spinner
  }, [isSyncing, loadEmails]);

  const handleEmailSelect = async (email: Email) => {
    try {
      const detailResponse = await fetchEmailDetail(email.id);
      const emailDetail = detailResponse.data;

      const parseFrom = (fromHeader?: string) => {
        if (!fromHeader) return { name: 'Unknown', email: '' };
        
        // Check if fromHeader has <email> format
        const emailMatch = fromHeader.match(/<(.+?)>/);
        
        if (emailMatch) {
          // Format: "Name <email@domain.com>"
          const emailAddr = emailMatch[1].trim();
          let name = fromHeader.replace(/<.*>/, '').trim();
          // Remove surrounding quotes (both single and double)
          name = name.replace(/^["']|["']$/g, '');
          // Remove escaped quotes
          name = name.replace(/\\"/g, '"');
          // If name is empty after removing email part, use email username
          name = name || emailAddr.split('@')[0];
          return { name, email: emailAddr };
        } else {
          // Plain email address without name: "email@domain.com"
          const emailAddr = fromHeader.trim();
          const name = emailAddr.split('@')[0]; // Extract username before @
          return { name, email: emailAddr };
        }
      };

      const { name: senderName, email: senderEmail } = parseFrom(emailDetail.from);
      
      // Extract body - ưu tiên HTML, fallback về plain text
      let body = emailDetail.body || emailDetail.snippet || '';
      
      // Nếu body là object với parts (multipart email)
      if (typeof body === 'object' && body.parts) {
        // Tìm HTML part trước
        const htmlPart = body.parts.find((p: { mimeType: string }) => p.mimeType === 'text/html');
        const textPart = body.parts.find((p: { mimeType: string }) => p.mimeType === 'text/plain');
        body = htmlPart?.body || textPart?.body || emailDetail.snippet || '';
      }

      const fullEmail: Email = {
        id: email.id,
        sender: senderName || 'Unknown',
        senderEmail: senderEmail || '',
        subject: emailDetail.subject || '(No Subject)',
        snippet: emailDetail.snippet || '',
        body: body,
        timestamp: emailDetail.date || email.timestamp,
        hasAiSuggestion: email.hasAiSuggestion || false,
        isRead: true,
        draftId: email.draftId, // Preserve draft info from original email
        aiReplyGenerated: email.aiReplyGenerated || false,
        replySent: email.replySent || false
      };
      
      console.log('📧 Selected email with draft info:', fullEmail);
      setSelectedEmail(fullEmail);
      
      setEmails((prev: Email[]) => prev.map((e: Email) => 
        e.id === email.id ? { ...e, isRead: true } : e
      ));
    } catch (err) {
      console.error('Error loading email detail:', err);
      setSelectedEmail(email);
      setEmails((prev: Email[]) => prev.map((e: Email) => 
        e.id === email.id ? { ...e, isRead: true } : e
      ));
    }
  };

  const handleSendReply = async (content: string) => {
    if (!selectedEmail) return;
    
    try {
      // Extract reply subject - add "Re: " prefix if not already present
      const replySubject = selectedEmail.subject.startsWith('Re: ') 
        ? selectedEmail.subject 
        : `Re: ${selectedEmail.subject}`;
      
      // Send email using API (already sent by AiSuggestionPanel, this is just callback)
      // await sendEmail(selectedEmail.senderEmail, replySubject, content);
      
      // Mark email as sent (status will be saved to DB by backend)
      setEmails((prev) => prev.map((e) => 
        e.id === selectedEmail.id 
          ? { ...e, replySent: true } 
          : e
      ));
      
      // Update selected email
      setSelectedEmail({ 
        ...selectedEmail, 
        replySent: true 
      });
      
      // Update local sentEmails state
      const newSentEmails = new Set(sentEmails);
      newSentEmails.add(selectedEmail.id);
      setSentEmails(newSentEmails);
      
      // Note: Không cần localStorage nữa, status đã được lưu vào DB (email_drafts.status='sent')
      
      // alert('Email đã được gửi thành công!'); // Already shown in AiSuggestionPanel
    } catch (err) {
      console.error('Error updating reply status:', err);
    }
  };

  const handleRegenerateAi = async (emailId: string) => {
    console.log('Regenerating AI suggestion for:', emailId);
    try {
      setIsGeneratingAi(true);
      const response = await generateAiReply(emailId);
      
      // Update email with draft info
      setEmails((prev) => prev.map((e) => 
        e.id === emailId 
          ? { ...e, aiReplyGenerated: true, draftId: response.draft_id, hasAiSuggestion: true } 
          : e
      ));
      
      // Update selected email if it's the current one - force new object to trigger re-render
      if (selectedEmail?.id === emailId) {
        setSelectedEmail({ 
          ...selectedEmail, 
          aiReplyGenerated: true, 
          draftId: response.draft_id,
          hasAiSuggestion: true 
        });
      }
      
      showToast('Gợi ý AI đã được tạo lại!', 'success');
    } catch (err) {
      console.error('Error regenerating AI:', err);
      const errorMessage = err instanceof Error ? err.message : 'Không thể tạo gợi ý AI';
      showToast(`Lỗi: ${errorMessage}`, 'error');
    } finally {
      setIsGeneratingAi(false);
    }
  };

  // Handle checkbox change
  const handleEmailCheckboxChange = (emailId: string, checked: boolean) => {
    if (checked && selectedEmailIds.length >= 5) {
      showToast('Bạn chỉ có thể chọn tối đa 5 email', 'warning');
      return;
    }
    
    setSelectedEmailIds((prev) => {
      if (checked) {
        return [...prev, emailId];
      } else {
        return prev.filter((id) => id !== emailId);
      }
    });
  };

  // Generate AI replies for selected emails
  const handleGenerateAiReplies = async () => {
    if (selectedEmailIds.length === 0) {
      showToast('Vui lòng chọn ít nhất 1 email', 'warning');
      return;
    }

    setIsGeneratingAi(true);
    const results: { id: string; success: boolean; error?: string }[] = [];

    for (const emailId of selectedEmailIds) {
      try {
        const response = await generateAiReply(emailId);
        
        // Update email with draft info
        setEmails((prev) => prev.map((e) => 
          e.id === emailId 
            ? { ...e, aiReplyGenerated: true, draftId: response.draft_id, hasAiSuggestion: true } 
            : e
        ));
        
        // Update selected email if it's the current one
        if (selectedEmail?.id === emailId) {
          setSelectedEmail({ 
            ...selectedEmail, 
            aiReplyGenerated: true, 
            draftId: response.draft_id,
            hasAiSuggestion: true 
          });
        }
        
        results.push({ id: emailId, success: true });
      } catch (err) {
        console.error(`Error generating AI reply for ${emailId}:`, err);
        results.push({ 
          id: emailId, 
          success: false, 
          error: err instanceof Error ? err.message : 'Unknown error' 
        });
      }
    }

    setIsGeneratingAi(false);
    setSelectedEmailIds([]); // Clear selection after generation

    const successCount = results.filter((r) => r.success).length;
    const failCount = results.filter((r) => !r.success).length;
    
    showToast(`Đã tạo xong!\nThành công: ${successCount}\nThất bại: ${failCount}`, 'info', 5000);
  };

  // Load more emails
  const handleLoadMore = () => {
    if (nextPageToken && !isLoadingMore) {
      loadEmails(nextPageToken, true, true);
    }
  };

  // Show loading state
  if (isLoading) {
    return (
      <div className="h-screen flex flex-col bg-gray-50">
        <Header onSync={handleSyncFromHeader} />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-500 mx-auto mb-4"></div>
            <p className="text-gray-600">Đang tải email...</p>
          </div>
        </div>
      </div>
    );
  }

  // Show error state
  if (error) {
    return (
      <div className="h-screen flex flex-col bg-gray-50">
        <Header onSync={handleSyncFromHeader} />
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center max-w-md">
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-900 mb-2">Lỗi tải dữ liệu</h3>
            <p className="text-red-600 mb-4">{error}</p>
            <button
              onClick={() => loadEmails()}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition"
            >
              Thử lại
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <Header onSync={handleSyncFromHeader} isSyncing={isSyncing} />
      
      <div className="flex-1 flex overflow-hidden">
        {/* Left Panel - Email List */}
        <div className="w-90 bg-white border-r border-gray-200 flex flex-col overflow-hidden">
          <div className="p-4 border-b border-gray-200 flex-shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-gray-900">
                  Hộp thư của bạn
                </h2>
                {selectedEmailIds.length > 0 && (
                  <p className="text-xs text-gray-500 mt-1">
                    Đã chọn {selectedEmailIds.length}/5 email
                  </p>
                )}
              </div>
              {isSyncing && (
                <div className="flex items-center text-sm text-blue-600">
                  <svg className="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Đang đồng bộ...
                </div>
              )}
            </div>
          </div>
          <div className="flex-1 overflow-hidden">
            <EmailList 
            emails={emails}
            selectedEmail={selectedEmail}
            onEmailSelect={handleEmailSelect}
            selectedEmailIds={selectedEmailIds}
            onEmailCheckboxChange={handleEmailCheckboxChange}
            hasNextPage={!!nextPageToken}
            onLoadMore={handleLoadMore}
            isLoadingMore={isLoadingMore}
          />
          </div>
        </div>

        {/* Middle Panel - Email Content */}
        <div className="flex-1 w-2xl bg-white border-r border-gray-200 flex flex-col">
          {/* Generate AI Button */}
          {selectedEmailIds.length > 0 && (
            <div className="border-b border-gray-200 p-4 bg-blue-50">
              <button
                onClick={handleGenerateAiReplies}
                disabled={isGeneratingAi}
                className="w-full py-3 px-4 bg-gradient-to-r from-purple-600 to-blue-600 text-white font-medium rounded-lg hover:from-purple-700 hover:to-blue-700 transition-all shadow-md disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center space-x-2 cursor-pointer"
              >
                {isGeneratingAi ? (
                  <>
                    <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    <span>Đang tạo câu trả lời. Vui lòng đợi một lát...</span>
                  </>
                ) : (
                  <>
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                    <span>Tạo câu trả lời với AI ({selectedEmailIds.length})</span>
                  </>
                )}
              </button>
            </div>
          )}
          
          {/* Email Content */}
          <div className="flex-1 overflow-y-auto">
            {selectedEmail ? (
              <EmailContent email={selectedEmail} />
            ) : (
              <div className="h-full flex items-center justify-center text-gray-500">
                <div className="text-center">
                  <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  <h3 className="mt-2 text-sm font-medium text-gray-900">Email của bạn</h3>
                  <p className="mt-1 text-sm text-gray-500">
                    Chọn một email từ danh sách để xem nội dung chi tiết. <br />Lưu ý khi nhấp chọn một email vui lòng đợi một lát để ứng dụng hiển thị.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right Panel - AI Suggestions */}
        <div className="flex-1 max-w-120 bg-white">
          {selectedEmail ? (
            <AiSuggestionPanel 
              email={selectedEmail}
              onSendReply={handleSendReply}
              onRegenerateAi={handleRegenerateAi}
            />
          ) : (
            <div className="h-full flex items-center justify-center text-gray-500">
              <div className="text-center px-4">
                <svg className="mx-auto h-12 w-12 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                <h3 className="mt-2 text-sm font-medium text-gray-900">Trợ lý AI</h3>
                <p className="mt-1 text-sm text-gray-500">
                  Gợi ý trả lời email từ AI. <br />Hãy chọn tối đa 5 email từ danh sách để AI giúp bạn trả lời.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}