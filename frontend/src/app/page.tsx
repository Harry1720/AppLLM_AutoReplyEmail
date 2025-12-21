'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { getAuthToken } from '@/services/api';

export default function LandingPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);

  // Redirect to workspace if already logged in
  useEffect(() => {
    const token = getAuthToken();
    if (token) {
      router.push('/workspace');
    }
  }, [router]);

  const handleGoogleLogin = () => {
    setIsLoading(true);
    
    // Google OAuth URL with all required parameters
    const googleAuthUrl = 'https://accounts.google.com/o/oauth2/v2/auth?' + new URLSearchParams({
      client_id: process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || '',
      redirect_uri: process.env.NEXT_PUBLIC_GOOGLE_REDIRECT_URI || '',
      response_type: 'code',
      scope: 'email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.modify',
      access_type: 'offline',
      prompt: 'select_account'
    }).toString();
    
    // Redirect to Google OAuth
    window.location.href = googleAuthUrl;
  };

  return (
    <div className="min-h-screen bg-gradient-to-br to-sky-100 flex items-center justify-center px-4">
      <div className="max-w-2xl w-full space-y-8 text-center">
        <div className="space-y-4">
          {/* Logo */}
          {/* <div className="mx-auto w-20 h-20 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-2xl flex items-center justify-center">
            <svg
              className="w-12 h-12 text-white"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
              />
            </svg>
          </div> */}
          <div className="mx-auto mb-0 flex items-center justify-center w-64 h-64">
            <Image
              src="/logo.png"
              alt="Logo"
              width={256}
              height={256}
              className="rounded-2xl"
              priority
            />
          </div>

          {/* App Name & Description */}
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-3">
              Trợ lý Email thông minh
            </h1>
            <p className="text-gray-600 text-lg">
              Ứng dụng trả lời email tự động thông minh với Trí tuệ nhân tạo
            </p>
          </div>

          {/* Features */}
          <div className="space-y-3 text-1xl text-gray-700">
            <div className="flex items-center justify-center space-x-2">
              <span className="text-green-500">✨</span>
              <span>Gợi ý trả lời các email bạn nhận được</span>
            </div>
            <div className="flex items-center justify-center space-x-2">
              <span className="text-blue-500">🎯</span>
              <span>Phân tích ngữ cảnh thông minh từ các email bạn đã gửi</span>
            </div>
            <div className="flex items-center justify-center space-x-2">
              <span className="text-purple-500">⚡</span>
              <span>Liên kết với Gmail của bạn rất tiện lợi thao tác</span>
            </div>
          </div>
        </div>

        {/* Google Login Button */}
        <div className="pt-6">
          <button
            onClick={handleGoogleLogin}
            disabled={isLoading}
            className="w-full bg-white border border-gray-300 rounded-lg px-6 py-3 text-gray-700 font-medium hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 transition duration-200 flex items-center justify-center space-x-3 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
          >
            {isLoading ? (
              <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-500"></div>
            ) : (
              <>
                {/* <svg className="w-5 h-5" viewBox="0 0 24 24">
                  <path
                    fill="currentColor"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="currentColor"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                  />
                  <path
                    fill="currentColor"
                    d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                  />
                  <path
                    fill="currentColor"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                  />
                </svg> */}
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="32px" height="32px">
                  <path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/>
                  <path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.25 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-18.55z"/>
                  <path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.28-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24s.92 7.54 2.55 10.78l7.98-6.19z"/>
                  <path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/>
                  <path fill="none" d="M0 0h48v48H0z"/>
                </svg>

                <span className='font-semibold'>Đăng nhập bằng Google</span>
              </>
            )}
          </button>
        </div>

        {/* Footer */}
        <div className="pt-2 text-1xl text-amber-700">
          <p>Bằng cách đăng nhập, bạn đồng ý với điều khoản sử dụng của chúng tôi.</p>
        </div>
        <div className="pt-2 text-1xl text-black">
          <p>Thực hiện: Quốc Bảo - Thái Bình.</p>
        </div>
      </div>
    </div>
  );
}
