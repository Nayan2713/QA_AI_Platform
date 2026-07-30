import React, { useState, useEffect, useRef } from 'react';
import api from '../lib/api';
import { useNavigate } from 'react-router-dom';

export interface NotificationItem {
  id: number;
  title: string;
  message: string;
  level: 'info' | 'success' | 'warning' | 'error';
  link?: string;
  is_read: boolean;
  created_at: string;
}

interface NotificationCenterProps {
  notifications: NotificationItem[];
  onRefreshNotifications: () => void;
}

export const NotificationCenter: React.FC<NotificationCenterProps> = ({
  notifications,
  onRefreshNotifications
}) => {
  const [isOpen, setIsOpen] = useState<boolean>(false);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  const unreadCount = notifications.filter(n => !n.is_read).length;

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleMarkAsRead = async (id: number, link?: string) => {
    try {
      await api.post(`notifications/${id}/mark_read/`);
      onRefreshNotifications();
      if (link) {
        setIsOpen(false);
        navigate(link);
      }
    } catch (err) {
      console.error("Failed to mark notification as read:", err);
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await api.post('notifications/mark_all_read/');
      onRefreshNotifications();
    } catch (err) {
      console.error("Failed to mark all as read:", err);
    }
  };

  const handleDeleteNotification = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    try {
      await api.delete(`notifications/${id}/`);
      onRefreshNotifications();
    } catch (err) {
      console.error("Failed to delete notification:", err);
    }
  };

  const handleClearAll = async () => {
    try {
      await api.delete('notifications/clear_all/');
      onRefreshNotifications();
    } catch (err) {
      console.error("Failed to clear all notifications:", err);
    }
  };

  const getLevelBadgeClass = (level: string) => {
    switch (level) {
      case 'success': return 'notif-level-success';
      case 'warning': return 'notif-level-warning';
      case 'error': return 'notif-level-error';
      default: return 'notif-level-info';
    }
  };

  const getLevelIcon = (level: string) => {
    switch (level) {
      case 'success': return '✅';
      case 'warning': return '⚠️';
      case 'error': return '❌';
      default: return 'ℹ️';
    }
  };

  return (
    <div className="notif-center-container" ref={dropdownRef}>
      {/* Bell Trigger Button */}
      <button
        className="notif-bell-btn"
        onClick={() => setIsOpen(!isOpen)}
        title="Notifications"
      >
        <span className="bell-icon">🔔</span>
        {unreadCount > 0 && (
          <span className="notif-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
        )}
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="notif-dropdown">
          <div className="notif-header">
            <div className="notif-header-title">
              <strong>Notifications</strong>
              {unreadCount > 0 && <span className="notif-sub-count">{unreadCount} new</span>}
            </div>
            <div className="notif-header-actions">
              {unreadCount > 0 && (
                <button onClick={handleMarkAllRead} className="notif-mark-all-btn">
                  Mark read
                </button>
              )}
              {notifications.length > 0 && (
                <button onClick={handleClearAll} className="notif-clear-all-btn">
                  Clear all
                </button>
              )}
            </div>
          </div>

          <div className="notif-list">
            {notifications.length === 0 ? (
              <div className="notif-empty">
                <span style={{ fontSize: '24px', display: 'block', marginBottom: '8px' }}>🔕</span>
                No notifications yet
              </div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className={`notif-item ${n.is_read ? 'read' : 'unread'}`}
                  onClick={() => handleMarkAsRead(n.id, n.link)}
                >
                  <div className="notif-icon">{getLevelIcon(n.level)}</div>
                  <div className="notif-content">
                    <div className="notif-item-title">
                      <span className={`notif-level-tag ${getLevelBadgeClass(n.level)}`}>
                        {n.level.toUpperCase()}
                      </span>
                      {n.title}
                    </div>
                    <div className="notif-item-msg">{n.message}</div>
                    <div className="notif-item-time">{n.created_at}</div>
                  </div>
                  <button
                    className="notif-delete-btn"
                    onClick={(e) => handleDeleteNotification(e, n.id)}
                    title="Delete notification"
                  >
                    🗑️
                  </button>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
};
