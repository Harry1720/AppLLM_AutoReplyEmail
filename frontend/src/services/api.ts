// API service for backend communication

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

// Store token in sessionStorage
export const setAuthToken = (token: string) => {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem('auth_token', token);
  }
};

export const getAuthToken = (): string | null => {
  if (typeof window !== 'undefined') {
    return sessionStorage.getItem('auth_token');
  }
  return null;
};

export const removeAuthToken = () => {
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem('auth_token');
  }
};

// User interface for sessionStorage
interface UserInfo {
  id: string;
  email: string;
  name: string;
  picture?: string;
}

// Store user info
export const setUserInfo = (user: UserInfo) => {
  if (typeof window !== 'undefined') {
    sessionStorage.setItem('user_info', JSON.stringify(user));
  }
};

export const getUserInfo = () => {
  if (typeof window !== 'undefined') {
    const userInfo = sessionStorage.getItem('user_info');
    return userInfo ? JSON.parse(userInfo) : null;
  }
  return null;
};

export const removeUserInfo = () => {
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem('user_info');
  }
};

// Exchange Google authorization code for JWT token
export const exchangeCodeForToken = async (code: string) => {
  try {
    const response = await fetch(`${API_BASE_URL}/auth/google-login`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ code }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Authentication failed');
    }

    const data = await response.json();
    
    // Store the JWT token and user info
    if (data.access_token) {
      setAuthToken(data.access_token);
    }
    if (data.user) {
      setUserInfo(data.user);
    }

    return data;
  } catch (error) {
    console.error('Error exchanging code for token:', error);
    throw error;
  }
};

// Fetch emails from backend
export const fetchEmails = async (limit: number = 10, pageToken?: string) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    let url = `${API_BASE_URL}/emails?limit=${limit}`;
    if (pageToken) {
      url += `&page_token=${pageToken}`;
    }

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      if (response.status === 401) {
        // Token expired or invalid
        removeAuthToken();
        removeUserInfo();
        throw new Error('Authentication expired. Please login again.');
      }
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch emails');
    }

    const data = await response.json();
    return data;
  } catch (error) {
    console.error('Error fetching emails:', error);
    throw error;
  }
};

// Send email
export const sendEmail = async (to: string, subject: string, body: string, files?: File[]) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const formData = new FormData();
    formData.append('to', to);
    formData.append('subject', subject);
    formData.append('body', body);
    
    // Add files if provided
    if (files && files.length > 0) {
      files.forEach(file => {
        formData.append('files', file);
      });
    }

    const response = await fetch(`${API_BASE_URL}/emails/send`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        // Don't set Content-Type header - browser will set it automatically with boundary for FormData
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to send email');
    }

    return await response.json();
  } catch (error) {
    console.error('Error sending email:', error);
    throw error;
  }
};

// Delete email
export const deleteEmail = async (messageId: string) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/emails/${messageId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete email');
    }

    return await response.json();
  } catch (error) {
    console.error('Error deleting email:', error);
    throw error;
  }
};

// Fetch email detail
export const fetchEmailDetail = async (messageId: string) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/emails/${messageId}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      if (response.status === 401) {
        removeAuthToken();
        removeUserInfo();
        throw new Error('Authentication expired. Please login again.');
      }
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch email detail');
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching email detail:', error);
    throw error;
  }
};

// Fetch user profile
export const fetchUserProfile = async () => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/users/me`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      if (response.status === 401) {
        removeAuthToken();
        removeUserInfo();
        throw new Error('Authentication expired. Please login again.');
      }
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch user profile');
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching user profile:', error);
    throw error;
  }
};

// Update user profile
export const updateUserProfile = async (name: string, picture?: string) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/users/me`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ name, picture }),
    });

    if (!response.ok) {
      if (response.status === 401) {
        removeAuthToken();
        removeUserInfo();
        throw new Error('Authentication expired. Please login again.');
      }
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update user profile');
    }

    return await response.json();
  } catch (error) {
    console.error('Error updating user profile:', error);
    throw error;
  }
};

// Delete user account
export const deleteUserAccount = async () => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/users/me`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      if (response.status === 401) {
        removeAuthToken();
        removeUserInfo();
        throw new Error('Authentication expired. Please login again.');
      }
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete user account');
    }

    // Clear local storage after successful deletion
    removeAuthToken();
    removeUserInfo();

    return await response.json();
  } catch (error) {
    console.error('Error deleting user account:', error);
    throw error;
  }
};

// Logout function
export const logout = () => {
  removeAuthToken();
  removeUserInfo();
};

// Sync AI data (POST /ai/sync)
export const syncAiData = async () => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/ai/sync`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to sync AI data');
    }

    return await response.json();
  } catch (error) {
    console.error('Error syncing AI data:', error);
    throw error;
  }
};

// Generate AI reply for an email (POST /ai/generate)
export const generateAiReply = async (msgId: string) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/ai/generate`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ msg_id: msgId }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to generate AI reply');
    }

    return await response.json();
  } catch (error) {
    console.error('Error generating AI reply:', error);
    throw error;
  }
};

// Check sync status (GET /ai/sync-status)
export const checkSyncStatus = async () => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/ai/sync-status`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to check sync status');
    }

    return await response.json();
  } catch (error) {
    console.error('Error checking sync status:', error);
    throw error;
  }
};

// Send existing draft (POST /drafts/{draft_id}/send)
export const sendDraft = async (draftId: string) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/drafts/${draftId}/send`, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to send draft');
    }

    return await response.json();
  } catch (error) {
    console.error('Error sending draft:', error);
    throw error;
  }
};

// Update existing draft (PUT /drafts/{draft_id})
export const updateDraft = async (draftId: string, to: string, subject: string, body: string) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const formData = new FormData();
    formData.append('to', to);
    formData.append('subject', subject);
    formData.append('body', body);

    const response = await fetch(`${API_BASE_URL}/drafts/${draftId}`, {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
      },
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to update draft');
    }

    return await response.json();
  } catch (error) {
    console.error('Error updating draft:', error);
    throw error;
  }
};

// Get draft detail (GET /drafts/{draft_id})
export const getDraftDetail = async (draftId: string) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/drafts/${draftId}`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to get draft detail');
    }

    return await response.json();
  } catch (error) {
    console.error('Error getting draft detail:', error);
    throw error;
  }
};

// Delete draft (DELETE /drafts/{draft_id})
export const deleteDraft = async (draftId: string) => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/drafts/${draftId}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to delete draft');
    }

    return await response.json();
  } catch (error) {
    console.error('Error deleting draft:', error);
    throw error;
  }
};

// Get all drafts for current user (to check which emails have drafts)
export const getAllDrafts = async () => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/drafts`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch drafts');
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching drafts:', error);
    throw error;
  }
};

// Get list of sent email IDs from server
export const getSentEmails = async () => {
  const token = getAuthToken();
  
  if (!token) {
    throw new Error('No authentication token found');
  }

  try {
    const response = await fetch(`${API_BASE_URL}/drafts/sent-emails`, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch sent emails');
    }

    return await response.json();
  } catch (error) {
    console.error('Error fetching sent emails:', error);
    throw error;
  }
};