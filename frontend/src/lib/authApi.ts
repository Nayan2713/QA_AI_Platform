import axios from "axios";

const apiBase = (import.meta as any).env.VITE_API_URL || (typeof window !== 'undefined' ? window.location.origin + '/api/' : 'http://127.0.0.1:8000/api/');
const API = apiBase.endsWith('/') ? `${apiBase}auth` : `${apiBase}/auth`;

export const registerUser = (
  data: any
) => axios.post(
  `${API}/register/`,
  data
);

export const loginUser = (
  data: any
) => axios.post(
  `${API}/login/`,
  data
);

export const changePassword = (
  data: { current_password: string; new_password: string }
) => {
  const token = localStorage.getItem('access_token');
  return axios.post(`${API}/change-password/`, data, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
  });
};

export const forgotPassword = (
  data: { email: string }
) => axios.post(
  `${API}/forgot-password/`,
  data
);

export const resetPassword = (
  data: { email: string; token: string; new_password: string; confirm_password: string }
) => axios.post(
  `${API}/reset-password/`,
  data
);