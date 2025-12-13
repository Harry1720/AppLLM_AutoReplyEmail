'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { exchangeCodeForToken, syncAiData, checkSyncStatus } from '@/services/api';

export default function AuthCallbackPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(true);
  const [syncMessage, setSyncMessage] = useState<string>('Đang xác thực...');

  useEffect(() => {
    const handleCallback = async () => {
      // Get the authorization code from URL
      const code = searchParams.get('code');
      const errorParam = searchParams.get('error');

      if (errorParam) {
        setError('Đăng nhập bị hủy hoặc thất bại');
        setIsProcessing(false);
        setTimeout(() => {
          router.push('/');
        }, 3000);
        return;
      }

      if (!code) {
        setError('Không tìm thấy mã xác thực');
        setIsProcessing(false);
        setTimeout(() => {
          router.push('/');
        }, 3000);
        return;
      }

      try {
        // Exchange code for token
        setSyncMessage('Đang xác thực...');
        const data = await exchangeCodeForToken(code);
        
        console.log('Login successful:', data);
        
        // Check if sync is needed
        setSyncMessage('Kiểm tra ngữ cảnh...');
        const syncStatus = await checkSyncStatus();
        
        if (!syncStatus.synced) {
          // Start AI sync and wait for it
          setSyncMessage('Đang xử lý lấy ngữ cảnh từ email đã gửi...');
          await syncAiData();
          
          // Poll sync status until complete (max 60 seconds)
          const maxAttempts = 30; // 30 attempts × 2 seconds = 60 seconds
          let attempts = 0;
          
          while (attempts < maxAttempts) {
            await new Promise(resolve => setTimeout(resolve, 2000)); // Wait 2 seconds
            
            const status = await checkSyncStatus();
            if (status.synced) {
              setSyncMessage(`✅ Đã lấy ngữ cảnh`);
              break;
            }
            
            attempts++;
            setSyncMessage(`Đang xử lý lấy ngữ cảnh...`);
          }
          
          if (attempts >= maxAttempts) {
            setSyncMessage('⚠️ Quá thời gian chờ. Ngữ cảnh sẽ được xử lý trong nền.');
          }
        } else {
          setSyncMessage(`✅ Đã có sẵn ngữ cảnh`);
        }
        
        // Wait a moment before redirect
        await new Promise(resolve => setTimeout(resolve, 1000));
        
        // Redirect to workspace
        router.push('/workspace');
      } catch (err: unknown) {
        console.error('Authentication error:', err);
        const errorMessage = err instanceof Error ? err.message : 'Đăng nhập thất bại. Vui lòng thử lại.';
        setError(errorMessage);
        setIsProcessing(false);
        setTimeout(() => {
          router.push('/');
        }, 3000);
      }
    };

    handleCallback();
  }, [searchParams, router]);

  return (
    <div className="min-h-screen bg-gradient-to-br to-sky-100 flex items-center justify-center px-4">
      <div className="max-w-md w-full bg-white rounded-lg shadow-lg p-8 text-center">
        {isProcessing ? (
          <>
            <div className="animate-spin rounded-full h-16 w-16 border-b-4 border-blue-500 mx-auto mb-4"></div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              {syncMessage.includes('✅') ? 'Hoàn tất!' : 'Đang xử lý...'}
            </h2>
            <p className="text-gray-600">
              {syncMessage}
            </p>
            {syncMessage.includes('Đang xử lý lấy ngữ cảnh') && (
              <div className="mt-4">
                <div className="w-full bg-gray-200 rounded-full h-2">
                  <div className="bg-blue-500 h-2 rounded-full animate-pulse" style={{width: '60%'}}></div>
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  Hệ thống đang phân tích email đã gửi để cải thiện chất lượng gợi ý AI. Vui lòng đợi một lát.
                </p>
              </div>
            )}
          </>
        ) : error ? (
          <>
            <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mx-auto mb-4">
              <svg
                className="w-8 h-8 text-red-500"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            </div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              Lỗi xác thực
            </h2>
            <p className="text-red-600 mb-4">{error}</p>
            <p className="text-sm text-gray-500">
              Đang chuyển hướng về trang chủ...
            </p>
          </>
        ) : null}
      </div>
    </div>
  );
}
