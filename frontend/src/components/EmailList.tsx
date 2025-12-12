'use client';

import { Email } from '@/types/email';

interface EmailListProps {
  emails: Email[];
  selectedEmail: Email | null;
  onEmailSelect: (email: Email) => void;
  selectedEmailIds?: string[];
  onEmailCheckboxChange?: (emailId: string, checked: boolean) => void;
  hasNextPage?: boolean;
  onLoadMore?: () => void;
  isLoadingMore?: boolean;
}

export default function EmailList({ 
  emails, 
  selectedEmail, 
  onEmailSelect,
  selectedEmailIds = [],
  onEmailCheckboxChange,
  hasNextPage = false,
  onLoadMore,
  isLoadingMore = false
}: EmailListProps) {
  const formatTime = (timestamp: string) => {
    const date = new Date(timestamp);
    const now = new Date();
    const diff = now.getTime() - date.getTime();
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    
    if (days === 0) {
      return date.toLocaleTimeString('vi-VN', { 
        hour: 'numeric', 
        minute: '2-digit',
        hour12: false
      });
    } else if (days === 1) {
      return 'Hôm qua';
    } else if (days < 7) {
      return date.toLocaleDateString('vi-VN', { weekday: 'short' });
    } else {
      return date.toLocaleDateString('vi-VN', { 
        month: 'short', 
        day: 'numeric' 
      });
    }
  };

  const handleCheckboxChange = (e: React.ChangeEvent<HTMLInputElement>, emailId: string) => {
    e.stopPropagation(); // Prevent triggering email selection
    if (onEmailCheckboxChange) {
      onEmailCheckboxChange(emailId, e.target.checked);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 divide-y divide-gray-200 overflow-y-auto">
        {emails.map((email) => (
          <div
            key={email.id}
            className={`p-4 cursor-pointer hover:bg-gray-50 transition-colors ${
              selectedEmail?.id === email.id 
                ? 'bg-blue-50 border-r-2 border-blue-500' 
                : ''
            }`}
          >
            <div className="flex items-start space-x-3">
              {/* Checkbox */}
              {onEmailCheckboxChange && (
                <input
                  type="checkbox"
                  checked={selectedEmailIds.includes(email.id)}
                  onChange={(e) => handleCheckboxChange(e, email.id)}
                  onClick={(e) => e.stopPropagation()}
                  disabled={email.aiReplyGenerated || email.replySent}
                  className="mt-1 h-4 w-4 text-blue-600 rounded border-gray-300 focus:ring-blue-500 cursor-pointer flex-shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
                />
              )}
              
              {/* Email Content */}
              <div 
                className="flex-1 min-w-0"
                onClick={() => onEmailSelect(email)}
              >
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center space-x-2 min-w-0 flex-1">
                    <span className={`font-medium truncate ${
                      email.isRead 
                        ? 'text-gray-700' 
                        : 'text-gray-900'
                    }`}>
                      {email.sender}
                    </span>
                    {email.replySent && (
                      <span className="text-blue-600 text-xs font-medium" title="Đã gửi trả lời">
                        Đã gửi trả lời
                      </span>
                    )}
                    {!email.replySent && email.aiReplyGenerated && (
                      <span className="text-yellow-500 text-sm" title="AI reply generated">
                        ✨
                      </span>
                    )}
                    {/* {email.hasAiSuggestion && (
                      <span className="text-yellow-500 text-sm" title="AI suggestion available">
                        
                      </span>
                    )} */}
                  </div>
                  <span className="text-xs text-gray-500 flex-shrink-0 ml-2">
                    {formatTime(email.timestamp)}
                  </span>
                </div>
                
                <h3 className={`text-sm mb-1 truncate ${
                  email.isRead 
                    ? 'text-gray-700' 
                    : 'text-gray-900 font-medium'
                }`}>
                  {email.subject}
                </h3>
                
                <p className="text-xs text-gray-500 line-clamp-2">
                  {email.snippet}
                </p>
              </div>
            </div>
          </div>
        ))}
        
        {/* Load More Button - Inside scrollable area */}
        {hasNextPage && (
          <div className="p-3">
            <button
              onClick={onLoadMore}
              disabled={isLoadingMore}
              className="w-full py-2 px-4 text-sm font-medium text-blue-600 hover:bg-blue-50 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoadingMore ? (
                <span className="flex items-center justify-center">
                  <svg className="animate-spin h-4 w-4 mr-2" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Đang tải...
                </span>
              ) : (
                'Tải thêm email'
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}