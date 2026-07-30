import React, { useState, useEffect } from 'react';
import { TeamMember } from '../lib/types';
import api from '../lib/api';

interface TeamModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentUser?: string;
}

export const TeamModal: React.FC<TeamModalProps> = ({
  isOpen,
  onClose,
  currentUser
}) => {
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [newEmail, setNewEmail] = useState<string>('');
  const [newPassword, setNewPassword] = useState<string>('');
  const [newRole, setNewRole] = useState<string>('member');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  const fetchMembers = async () => {
    setIsLoading(true);
    try {
      const res = await api.get('team/');
      setMembers(Array.isArray(res.data) ? res.data : res.data.results || []);
    } catch (err) {
      console.error('Failed to fetch team members:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      fetchMembers();
      setErrorMsg(null);
      setSuccessMsg(null);
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleAddMember = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmedEmail = newEmail.trim().toLowerCase();
    if (!trimmedEmail) return;

    if (members.some(m => m.email.toLowerCase() === trimmedEmail)) {
      setErrorMsg("This user is already a member of your team.");
      return;
    }

    setIsSubmitting(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const res = await api.post('team/', {
        email: trimmedEmail,
        role: newRole,
        password: newPassword.trim() || undefined
      });

      const message = newPassword.trim() 
        ? `Successfully added ${res.data.email}! Account created with assigned password.`
        : `Successfully invited ${res.data.email} to your team!`;

      setSuccessMsg(message);
      setNewEmail('');
      setNewPassword('');
      fetchMembers();
    } catch (err: any) {
      console.error('Failed to add team member:', err);
      const data = err.response?.data;
      if (data) {
        if (typeof data.email === 'string') setErrorMsg(data.email);
        else if (Array.isArray(data.email)) setErrorMsg(data.email[0]);
        else if (typeof data.detail === 'string') setErrorMsg(data.detail);
        else if (typeof data.non_field_errors === 'object' && Array.isArray(data.non_field_errors)) setErrorMsg(data.non_field_errors[0]);
        else setErrorMsg('Failed to add team member. Please verify email and try again.');
      } else {
        setErrorMsg('Failed to add team member. Please verify email and try again.');
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRemoveMember = async (id: number, email: string) => {
    if (!window.confirm(`Are you sure you want to revoke access for ${email}?`)) return;

    try {
      await api.delete(`team/${id}/`);
      setSuccessMsg(`Revoked access for ${email}`);
      fetchMembers();
    } catch (err) {
      console.error('Failed to remove team member:', err);
    }
  };

  const handleRoleChange = async (id: number, newRole: string) => {
    try {
      await api.patch(`team/${id}/`, { role: newRole });
      fetchMembers();
    } catch (err) {
      console.error('Failed to update role:', err);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0, left: 0, right: 0, bottom: 0,
      background: 'rgba(0, 0, 0, 0.8)',
      zIndex: 9999,
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      padding: '20px',
      backdropFilter: 'blur(8px)'
    }}>
      <div style={{
        background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
        border: '1px solid rgba(255, 255, 255, 0.15)',
        borderRadius: '20px',
        padding: '32px',
        maxWidth: '720px',
        width: '100%',
        boxShadow: '0 25px 60px rgba(0,0,0,0.6)',
        color: '#fff',
        maxHeight: '90vh',
        overflowY: 'auto'
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '1.8rem' }}>👥</span>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, background: 'linear-gradient(90deg, #38bdf8, #a855f7)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                Team Members & Access
              </h2>
            </div>
            <p style={{ margin: '6px 0 0 0', color: '#94a3b8', fontSize: '0.85rem' }}>
              Grant team members shared access to view, run tests, and inspect QA reports in your workspace.
            </p>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'rgba(255,255,255,0.08)',
              border: 'none',
              color: '#94a3b8',
              width: '36px',
              height: '36px',
              borderRadius: '50%',
              fontSize: '1.2rem',
              cursor: 'pointer'
            }}
          >
            ✕
          </button>
        </div>

        {/* Feedback Messages */}
        {errorMsg && (
          <div style={{ background: 'rgba(239, 68, 68, 0.15)', border: '1px solid rgba(239, 68, 68, 0.3)', color: '#f87171', padding: '10px 14px', borderRadius: '8px', fontSize: '0.85rem', marginBottom: '16px' }}>
            ⚠️ {errorMsg}
          </div>
        )}
        {successMsg && (
          <div style={{ background: 'rgba(16, 185, 129, 0.15)', border: '1px solid rgba(16, 185, 129, 0.3)', color: '#34d399', padding: '10px 14px', borderRadius: '8px', fontSize: '0.85rem', marginBottom: '16px' }}>
            ✓ {successMsg}
          </div>
        )}

        {/* Add Team Member Form */}
        <form onSubmit={handleAddMember} style={{
          background: 'rgba(15, 23, 42, 0.6)',
          border: '1px solid rgba(255, 255, 255, 0.1)',
          borderRadius: '12px',
          padding: '18px',
          marginBottom: '28px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px'
        }}>
          <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600, color: '#f1f5f9' }}>
            ➕ Invite / Add New Team Member
          </h4>
          
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '12px',
            alignItems: 'center'
          }}>
            <input
              type="email"
              required
              placeholder="Email address (e.g. alex@co.com)"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
              style={{
                background: 'rgba(30, 41, 59, 0.9)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '8px',
                padding: '10px 14px',
                color: '#fff',
                fontSize: '0.85rem',
                width: '100%',
                boxSizing: 'border-box'
              }}
            />

            <input
              type="password"
              placeholder="Initial password (optional)"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              style={{
                background: 'rgba(30, 41, 59, 0.9)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '8px',
                padding: '10px 14px',
                color: '#fff',
                fontSize: '0.85rem',
                width: '100%',
                boxSizing: 'border-box'
              }}
            />

            <div style={{ display: 'flex', gap: '10px', width: '100%' }}>
              <select
                value={newRole}
                onChange={(e) => setNewRole(e.target.value)}
                style={{
                  background: 'rgba(30, 41, 59, 0.9)',
                  border: '1px solid rgba(255, 255, 255, 0.2)',
                  borderRadius: '8px',
                  padding: '10px 12px',
                  color: '#fff',
                  fontSize: '0.85rem',
                  flex: '1',
                  minWidth: '110px'
                }}
              >
                <option value="admin">👑 Admin</option>
                <option value="member">🛠️ Member</option>
                <option value="viewer">👁️ Viewer</option>
              </select>

              <button
                type="submit"
                disabled={isSubmitting}
                style={{
                  background: 'linear-gradient(135deg, #a855f7 0%, #6366f1 100%)',
                  color: '#fff',
                  border: 'none',
                  padding: '10px 20px',
                  borderRadius: '8px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  fontSize: '0.85rem',
                  whiteSpace: 'nowrap',
                  minWidth: '120px',
                  boxShadow: '0 4px 14px rgba(168, 85, 247, 0.3)'
                }}
              >
                {isSubmitting ? 'Adding...' : '➕ Add Member'}
              </button>
            </div>
          </div>
        </form>

        {/* Team Members List */}
        <div>
          <h4 style={{ margin: '0 0 14px 0', fontSize: '0.95rem', fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Active Team Members ({members.length + 1})
          </h4>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* Account Owner Row */}
            <div style={{
              background: 'rgba(30, 41, 59, 0.5)',
              border: '1px solid rgba(168, 85, 247, 0.3)',
              borderRadius: '12px',
              padding: '14px 18px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '1.4rem' }}>👑</span>
                <div>
                  <span style={{ fontWeight: 700, fontSize: '0.95rem', color: '#fff', display: 'block' }}>
                    {currentUser || 'Account Owner'}
                  </span>
                  <span style={{ fontSize: '0.75rem', color: '#a855f7', fontWeight: 600 }}>Primary Owner</span>
                </div>
              </div>

              <span style={{
                background: 'rgba(168, 85, 247, 0.2)',
                border: '1px solid rgba(168, 85, 247, 0.4)',
                color: '#c084fc',
                padding: '4px 12px',
                borderRadius: '6px',
                fontSize: '0.75rem',
                fontWeight: 700
              }}>
                OWNER
              </span>
            </div>

            {/* List Team Members */}
            {isLoading ? (
              <div style={{ textAlign: 'center', padding: '20px', color: '#94a3b8' }}>Loading team members...</div>
            ) : members.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '24px', color: '#64748b', fontSize: '0.85rem', background: 'rgba(15,23,42,0.4)', borderRadius: '12px', border: '1px dashed rgba(255,255,255,0.1)' }}>
                No extra team members added yet. Enter an email above to share workspace access.
              </div>
            ) : (
              members.map(member => (
                <div
                  key={member.id}
                  style={{
                    background: 'rgba(30, 41, 59, 0.6)',
                    border: '1px solid rgba(255, 255, 255, 0.08)',
                    borderRadius: '12px',
                    padding: '14px 18px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '12px',
                    flexWrap: 'wrap'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    <span style={{ fontSize: '1.3rem' }}>👤</span>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontWeight: 600, fontSize: '0.95rem', color: '#f8fafc' }}>
                          {member.member_username || member.email}
                        </span>
                        <span style={{
                          fontSize: '0.7rem',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          fontWeight: 600,
                          backgroundColor: member.status === 'active' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(234, 179, 8, 0.15)',
                          color: member.status === 'active' ? '#4ade80' : '#fde047',
                          border: member.status === 'active' ? '1px solid rgba(34, 197, 94, 0.3)' : '1px solid rgba(234, 179, 8, 0.3)'
                        }}>
                          {member.status === 'active' ? 'Active' : 'Pending Invite'}
                        </span>
                      </div>
                      <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>{member.email}</span>
                    </div>
                  </div>

                  <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                    {/* Role Selector */}
                    <select
                      value={member.role}
                      onChange={(e) => handleRoleChange(member.id, e.target.value)}
                      style={{
                        background: 'rgba(15, 23, 42, 0.8)',
                        border: '1px solid rgba(255, 255, 255, 0.15)',
                        color: member.role === 'admin' ? '#c084fc' : member.role === 'member' ? '#38bdf8' : '#94a3b8',
                        borderRadius: '6px',
                        padding: '4px 10px',
                        fontSize: '0.8rem',
                        fontWeight: 600,
                        cursor: 'pointer'
                      }}
                    >
                      <option value="admin">👑 Admin</option>
                      <option value="member">🛠️ Member</option>
                      <option value="viewer">👁️ Viewer</option>
                    </select>

                    {/* Revoke Access */}
                    <button
                      onClick={() => handleRemoveMember(member.id, member.email)}
                      style={{
                        background: 'rgba(239, 68, 68, 0.15)',
                        border: '1px solid rgba(239, 68, 68, 0.3)',
                        color: '#f87171',
                        padding: '4px 10px',
                        borderRadius: '6px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        cursor: 'pointer'
                      }}
                    >
                      Revoke
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
