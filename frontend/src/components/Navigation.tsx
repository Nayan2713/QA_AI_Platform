import React from 'react';

interface NavigationProps {
  username?: string;
  onLogout: () => void;
  onNavigate: (view: 'dashboard' | 'bugs') => void;
  currentView: string;
}

export const Navigation: React.FC<NavigationProps> = ({ 
  username, 
  onLogout, 
  onNavigate,
  currentView
}) => {
  return (
    <nav className="glass-nav">
      <div className="nav-container">
        <div className="nav-brand" onClick={() => onNavigate('dashboard')}>
          <span className="brand-icon">⚡</span>
          <span className="brand-text">QA Engineer MVP</span>
        </div>
        
        {username && (
          <div className="nav-menu">
            <button 
              className={`nav-link ${currentView === 'dashboard' ? 'active' : ''}`}
              onClick={() => onNavigate('dashboard')}
            >
              🖥️ Dashboard
            </button>
            <button 
              className={`nav-link ${currentView === 'bugs' ? 'active' : ''}`}
              onClick={() => onNavigate('bugs')}
            >
              🐞 All Bugs
            </button>
            
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
