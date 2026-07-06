import axios from "axios";

const apiBase = (import.meta as any).env.VITE_API_URL || 'http://127.0.0.1:8000/api/';
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