import axios from 'axios';

const apiBase = (import.meta as any).env.VITE_API_URL || (typeof window !== 'undefined' ? window.location.origin + '/api/' : 'http://127.0.0.1:8000/api/');

const api = axios.create({
  baseURL: apiBase,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Attach JWT access token to every request
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// On 401, try refreshing the token once, then log the user out
api.interceptors.response.use(
  (response) => {
    // If response matches our global wrapper, log and unwrap the actual data payload
    const responseData = response.data;
    if (responseData && typeof responseData === 'object' && 'status_code' in responseData && 'data' in responseData) {
      console.log(`[API Response] ${response.config.method?.toUpperCase()} ${response.config.url} - Status: ${responseData.status_code}`, responseData);
      response.data = responseData.data;
    }
    return response;
  },
  async (error) => {
    if (axios.isCancel(error) || error?.name === 'CanceledError' || error?.message === 'canceled') {
      return Promise.reject(error);
    }

    const originalRequest = error.config;

    // Log real API errors globally
    if (error.response) {
      const errorData = error.response.data;
      const status = error.response.status;
      if (errorData && typeof errorData === 'object' && 'status_code' in errorData) {
        console.error(`[API Error] ${originalRequest?.method?.toUpperCase()} ${originalRequest?.url} - Status: ${errorData.status_code}`, errorData);
      } else {
        console.error(`[API Error] ${originalRequest?.method?.toUpperCase()} ${originalRequest?.url} - Status: ${status}`, errorData);
      }
    } else {
      console.error(`[API Error] Network/Request Error:`, error.message);
    }

    const isAuthEndpoint = originalRequest?.url?.includes('auth/login') ||
                           originalRequest?.url?.includes('auth/register') ||
                           originalRequest?.url?.includes('auth/refresh');

    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');

      if (refreshToken) {
        try {
          const refreshUrl = apiBase.endsWith('/') ? `${apiBase}auth/refresh/` : `${apiBase}/auth/refresh/`;
          const res = await axios.post(refreshUrl, {
            refresh: refreshToken,
          });
          // Handle both wrapped and unwrapped format
          const newAccess = res.data.data?.access || res.data.access;
          if (newAccess) {
            localStorage.setItem('access_token', newAccess);
            originalRequest.headers.Authorization = `Bearer ${newAccess}`;
            return api(originalRequest);
          }
        } catch {
          // Refresh failed — clear storage cleanly without forcing location.reload
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          localStorage.removeItem('username');
          window.dispatchEvent(new Event('auth:logout'));
        }
      } else {
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('username');
        window.dispatchEvent(new Event('auth:logout'));
      }
    }

    return Promise.reject(error);
  }
);

export default api;