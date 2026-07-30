import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { NotificationCenter, NotificationItem } from './NotificationCenter';

interface NavigationProps {
  username?: string;
  onLogout: () => void;
  onOpenTeamModal?: () => void;
  notifications?: NotificationItem[];
  onRefreshNotifications?: () => void;
}

export const Navigation: React.FC<NavigationProps> = ({ 
  username, 
  onLogout,
  onOpenTeamModal,
  notifications = [],
  onRefreshNotifications = () => {}
}) => {
  const location = useLocation();

  return (
    <nav className="glass-nav">
      <div className="nav-container">
        <Link to="/dashboard" className="nav-brand">
          <span className="brand-icon">⚡</span>
          <span className="brand-text">QA Engineer MVP</span>
        </Link>
        
        {username && (
          <div className="nav-menu">
            <Link 
              to="/dashboard" 
              className={`nav-link ${location.pathname === '/dashboard' ? 'active' : ''}`}
            >
              🖥️ Dashboard
            </Link>

            {onOpenTeamModal && (
              <button 
                onClick={onOpenTeamModal}
                className="nav-link"
                style={{
                  background: 'rgba(168, 85, 247, 0.15)',
                  border: '1px solid rgba(168, 85, 247, 0.3)',
                  color: '#c084fc',
                  padding: '6px 14px',
                  borderRadius: '8px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontSize: '0.85rem'
                }}
              >
                👥 Team Access
              </button>
            )}
            
            <NotificationCenter
              notifications={notifications}
              onRefreshNotifications={onRefreshNotifications}
            />

            <div className="nav-divider"></div>
            
            <div className="nav-user">
              <span className="user-avatar">👤</span>
              <span className="user-name">{username}</span>
            </div>
            
            <button className="btn-logout" onClick={onLogout}>
              Logout ➡️
            </button>
          </div>
        )}
      </div>
    </nav>
  );
};
