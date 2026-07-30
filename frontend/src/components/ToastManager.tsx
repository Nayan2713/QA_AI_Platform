import React from 'react';

export interface ToastItem {
  id: string;
  title: string;
  message: string;
  level: 'info' | 'success' | 'warning' | 'error';
}

interface ToastManagerProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}

export const ToastManager: React.FC<ToastManagerProps> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  const getIcon = (level: string) => {
    switch (level) {
      case 'success': return '🎉';
      case 'warning': return '⚠️';
      case 'error': return '🚨';
      default: return '📢';
    }
  };

  return (
    <div className="toast-manager-container">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast-card toast-${toast.level}`}>
          <div className="toast-icon">{getIcon(toast.level)}</div>
          <div className="toast-body">
            <div className="toast-title">{toast.title}</div>
            <div className="toast-message">{toast.message}</div>
          </div>
          <button className="toast-close-btn" onClick={() => onDismiss(toast.id)}>
            ✕
          </button>
        </div>
      ))}
    </div>
  );
};
