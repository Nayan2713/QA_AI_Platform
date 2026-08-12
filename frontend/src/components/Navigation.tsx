import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { NotificationCenter, NotificationItem } from './NotificationCenter';

interface NavigationProps {
  username?: string;
  onLogout: () => void;
  onOpenTeamModal?: () => void;
  onOpenProfileModal?: () => void;
  notifications?: NotificationItem[];
  onRefreshNotifications?: () => void;
}

export const Navigation: React.FC<NavigationProps> = ({ 
  username, 
  onLogout,
  onOpenTeamModal,
  onOpenProfileModal,
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
            
            <button
              onClick={onOpenProfileModal}
              className="nav-user"
              style={{
                background: 'rgba(6, 182, 212, 0.12)',
                border: '1px solid rgba(6, 182, 212, 0.3)',
                padding: '5px 12px',
                borderRadius: '10px',
                color: '#22d3ee',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                transition: 'all 0.2s',
                fontSize: '0.85rem',
                fontWeight: 600
              }}
              title="Click to view & edit profile"
            >
              <span className="user-avatar">👤</span>
              <span className="user-name" style={{ color: '#22d3ee' }}>{username}</span>
            </button>
            
            <button className="btn-logout" onClick={onLogout}>
              Logout ➡️
            </button>
          </div>
        )}
      </div>
    </nav>
  );
};
