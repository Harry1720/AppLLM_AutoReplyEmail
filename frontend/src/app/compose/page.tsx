'use client';

import { useState, useEffect, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { Email } from '@/types/email';
import EmailList from '@/components/EmailList';
import EmailComposer from '@/components/EmailComposer';
import EmailDetail from '@/components/EmailDetail';
import Header from '@/components/Header';
import { fetchSentEmails, fetchEmailDetail, getAuthToken, sendEmail } from '@/services/api';
import { useToast } from '@/components/ToastContainer';

export default function ComposePage() {
  const router = useRouter();
  const { showToast } = useToast();
  const [emails, setEmails] = useState<Email[]>([]);
  const [selectedEmail, setSelectedEmail] = useState<Email | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [nextPageToken, setNextPageToken] = useState<string | null>(null);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [showComposer, setShowComposer] = useState(false);

  // Check authentication on mount
  useEffect(() => {
    const token = getAuthToken();
    if (!token) {
      router.push('/');
    }
  }, [router]);

  // Load sent emails
  const loadSentEmails = useCallback(async (pageToken?: string, append = false) => {
    try {
      if (append) {
        setIsLoadingMore(true);
      } else {
        setIsLoading(true);
      }
      setError(null);
      
      // Fetch sent emails
      const data = await fetchSentEmails(10, pageToken);
      
      console.log('📧 Sent emails data:', data);
      
      // Transform backend email format to frontend format
      interface EmailFromAPI {
        id: string;
        threadId?: string;
        subject?: string;
        snippet?: string;
        from?: string;
        to?: string;
        date?: string;
        labelIds?: string[];
      }

      const transformedEmails: Email[] = data.emails.map((email: EmailFromAPI) => {
          console.log('📧 Processing email:', email.id, 'to:', email.to, 'from:', email.from);
          
          // For SENT emails, we want to show the recipient (To), not sender (From)
          // Parse "To" header for sent emails  
          const parseTo = (toHeader?: string) => {
            // Xử lý trường hợp null, undefined hoặc chuỗi rỗng ""
            if (!toHeader || toHeader.trim() === '') {
              return { 
                name: 'Người nhận ẩn danh (BCC)', 
                email: 'Không hiển thị' 
              };
            }

            // Extract first recipient only (if multiple recipients)
            const firstRecipient = toHeader.split(',')[0].trim();
            
            // Check if has <email> format
            const emailMatch = firstRecipient.match(/<(.+?)>/);
            
            if (emailMatch) {
              // Format: "Name <email@domain.com>"
              const emailAddr = emailMatch[1].trim();
              let name = firstRecipient.replace(/<.*>/, '').trim();
              // Remove surrounding quotes (both single and double)
              name = name.replace(/^["']|["']$/g, '');
              // If name is empty, use email username
              name = name || emailAddr.split('@')[0];
              return { name, email: emailAddr };
            } else {
              // Plain email address: "email@domain.com"
              const emailAddr = firstRecipient.trim();
              const name = emailAddr.split('@')[0];
              return { name, email: emailAddr };
            }
          };

          // For sent emails, use "to" field to show recipient
          const { name: recipientName, email: recipientEmail } = parseTo(email.to);

          return {
            id: email.id,
            sender: recipientName,
            senderEmail: recipientEmail,
            subject: email.subject?.trim() || '(No Subject)',
            snippet: email.snippet || '',
            body: email.snippet || '',
            timestamp: email.date || new Date().toISOString(),
            // hasAiSuggestion: false,
            // aiReplyGenerated: false,
          };
        });
      
      if (append) {
        setEmails(prev => [...prev, ...transformedEmails]);
      } else {
        setEmails(transformedEmails);
      }
      
      // Backend có thể trả về nextPageToken hoặc next_page_token
      setNextPageToken(data.nextPageToken || data.next_page_token || null);
      // console.log('📧 Next page token:', data.nextPageToken || data.next_page_token);
    } catch (error: any) {
      console.error('Error loading sent emails:', error);
      setError(error.message || 'Failed to load sent emails');
      
      if (error.message.includes('Authentication expired')) {
        router.push('/');
      }
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  }, [router]);

  useEffect(() => {
    // Load sent emails or show composer based on localStorage
    const savedDraft = localStorage.getItem('email_draft');
    if (savedDraft) {
      setShowComposer(true);
    }
    loadSentEmails();
  }, [loadSentEmails]);

  const handleEmailSelect = async (email: Email) => {
    try {
      setShowComposer(false);
      setSelectedEmail(null);
      setError(null);
      
      const detail = await fetchEmailDetail(email.id);
      
      console.log('📧 Email detail response:', detail);
      
      // Backend trả về {data: {...}}
      const emailData = detail.data || detail;
      
      setSelectedEmail({
        ...email,
        body: emailData.body || emailData.snippet || '',
        attachments: emailData.attachments || [],
      });
    } catch (error: any) {
      console.error('Error loading email detail:', error);
      setError(error.message || 'Failed to load email detail');
    }
  };

  const handleNewEmail = () => {
    setSelectedEmail(null);
    setShowComposer(true);
  };

  const handleSendEmail = async (to: string, subject: string, body: string, files?: File[]) => {
    try {
      await sendEmail(to, subject, body, files);
      
      // Clear draft from localStorage
      localStorage.removeItem('email_draft');
      
      // Show success toast
      showToast('Email đã được gửi thành công!', 'success');
      
      // Reload sent emails
      await loadSentEmails();
      
      // Close composer
      setShowComposer(false);
      
      return { success: true };
    } catch (error: any) {
      console.error('Error sending email:', error);
      throw error;
    }
  };

  const handleLoadMore = () => {
    if (nextPageToken && !isLoadingMore) {
      loadSentEmails(nextPageToken, true);
    }
  };

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <Header />
      
      <main className="flex-1 flex overflow-hidden">
        {/* Left Panel - Email List */}
        <div className="w-96 border-r border-gray-200 bg-white flex flex-col">
          <div className="p-4 border-b border-gray-200 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Hộp thư đã gửi</h2>
            <button
              onClick={handleNewEmail}
              className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-colors"
              title="Soạn email mới"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>
          
          <div className="flex-1 overflow-hidden">
            {isLoading ? (
              <div className="h-full flex items-center justify-center">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              </div>
            ) : error ? (
              <div className="h-full flex items-center justify-center p-4">
                <div className="text-center">
                  <p className="text-red-600 mb-2">{error}</p>
                  <button
                    onClick={() => loadSentEmails()}
                    className="text-blue-600 hover:underline"
                  >
                    Thử lại
                  </button>
                </div>
              </div>
            ) : (
              <EmailList
                emails={emails}
                selectedEmail={showComposer ? null : selectedEmail}
                onEmailSelect={handleEmailSelect}
                onLoadMore={handleLoadMore}
                hasNextPage={!!nextPageToken}
                isLoadingMore={isLoadingMore}
              />
            )}
          </div>
        </div>

        {/* Right Panel - Email Detail or Composer */}
        <div className="flex-1 bg-white">
          {showComposer ? (
            <EmailComposer onSend={handleSendEmail} />
          ) : selectedEmail ? (
            <EmailDetail email={selectedEmail} />
          ) : (
            <div className="h-full flex items-center justify-center text-gray-400">
              <div className="text-center">
                <svg className="w-16 h-16 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <p className="text-lg">Chọn một email để xem hoặc nhấn + để soạn email mới</p>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
