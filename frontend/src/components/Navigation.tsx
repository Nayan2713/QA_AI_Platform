import React from 'react';
import { Link, useLocation } from 'react-router-dom';

interface NavigationProps {
  username?: string;
  onLogout: () => void;
}

export const Navigation: React.FC<NavigationProps> = ({ 
  username, 
  onLogout 
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
