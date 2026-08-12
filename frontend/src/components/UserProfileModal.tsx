import React, { useState, useEffect } from 'react';
import { User, Mail, Shield, Key, Calendar, Check, AlertCircle, X, Sparkles, Save, UserCheck, Lock } from 'lucide-react';
import { getUserProfile, updateUserProfile } from '../lib/api';

interface Props {
    isOpen: boolean;
    onClose: () => void;
    onProfileUpdated?: (newUsername: string) => void;
}

export default function UserProfileModal({ isOpen, onClose, onProfileUpdated }: Props) {
    const [activeTab, setActiveTab] = useState<'details' | 'security' | 'preferences'>('details');
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [successMessage, setSuccessMessage] = useState('');
    const [errorMessage, setErrorMessage] = useState('');

    // Form state
    const [username, setUsername] = useState(localStorage.getItem('username') || '');
    const [email, setEmail] = useState('');
    const [firstName, setFirstName] = useState('');
    const [lastName, setLastName] = useState('');
    const [dateJoined, setDateJoined] = useState('');
    const [isStaff, setIsStaff] = useState(false);

    // Password state
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');

    // Preferences state
    const [browserEngine, setBrowserEngine] = useState('Chromium Headless');
    const [autoRetryCount, setAutoRetryCount] = useState('2');

    useEffect(() => {
        if (isOpen) {
            fetchProfile();
        }
    }, [isOpen]);

    const fetchProfile = async () => {
        setLoading(true);
        setErrorMessage('');
        try {
            const data = await getUserProfile();
            if (data) {
                setUsername(data.username || '');
                setEmail(data.email || '');
                setFirstName(data.first_name || '');
                setLastName(data.last_name || '');
                setIsStaff(!!data.is_staff);
                if (data.date_joined) {
                    setDateJoined(new Date(data.date_joined).toLocaleDateString(undefined, {
                        year: 'numeric', month: 'long', day: 'numeric'
                    }));
                }
            }
        } catch (err: any) {
            // Fallback to local storage
            setUsername(localStorage.getItem('username') || 'QA Engineer');
        } finally {
            setLoading(false);
        }
    };

    const handleSaveProfile = async (e: React.FormEvent) => {
        e.preventDefault();
        setSaving(true);
        setSuccessMessage('');
        setErrorMessage('');

        if (activeTab === 'security') {
            if (newPassword && newPassword !== confirmPassword) {
                setErrorMessage('New passwords do not match.');
                setSaving(false);
                return;
            }
            if (newPassword && !currentPassword) {
                setErrorMessage('Please enter your current password to set a new password.');
                setSaving(false);
                return;
            }
        }

        try {
            const payload: any = {
                username,
                email,
                first_name: firstName,
                last_name: lastName,
            };

            if (newPassword && currentPassword) {
                payload.current_password = currentPassword;
                payload.new_password = newPassword;
            }

            const res = await updateUserProfile(payload);
            setSuccessMessage('Profile information updated successfully!');

            if (res?.user?.username) {
                localStorage.setItem('username', res.user.username);
                if (onProfileUpdated) onProfileUpdated(res.user.username);
            }

            // Clear password fields
            setCurrentPassword('');
            setNewPassword('');
            setConfirmPassword('');

            setTimeout(() => {
                setSuccessMessage('');
            }, 3000);
        } catch (err: any) {
            const msg = err.response?.data?.error || err.response?.data?.detail || 'Failed to update profile settings.';
            setErrorMessage(msg);
        } finally {
            setSaving(false);
        }
    };

    if (!isOpen) return null;

    const userInitial = (username || 'U').charAt(0).toUpperCase();

    return (
        <div style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(5, 3, 15, 0.85)',
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
            padding: '20px'
        }}>
            <div style={{
                position: 'relative',
                width: '100%',
                maxWidth: '680px',
                borderRadius: '24px',
                border: '1px solid rgba(139, 92, 246, 0.35)',
                background: 'linear-gradient(180deg, rgba(22, 17, 45, 0.98) 0%, rgba(12, 9, 26, 0.98) 100%)',
                boxShadow: '0 25px 70px rgba(0, 0, 0, 0.6), 0 0 40px rgba(139, 92, 246, 0.15)',
                overflow: 'hidden',
                display: 'flex',
                flexDirection: 'column'
            }}>
                {/* Header Bar */}
                <div style={{
                    padding: '24px 30px',
                    borderBottom: '1px solid rgba(139, 92, 246, 0.2)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    background: 'rgba(255, 255, 255, 0.02)'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                        {/* User Avatar Badge */}
                        <div style={{
                            width: '52px',
                            height: '52px',
                            borderRadius: '16px',
                            background: 'linear-gradient(135deg, #7c3aed, #06b6d4)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            color: '#ffffff',
                            fontSize: '1.4rem',
                            fontWeight: 800,
                            boxShadow: '0 0 20px rgba(124, 58, 237, 0.4)',
                            border: '1px solid rgba(255, 255, 255, 0.3)'
                        }}>
                            {userInitial}
                        </div>
                        <div>
                            <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#ffffff', margin: 0, display: 'flex', alignItems: 'center', gap: '10px' }}>
                                {username || 'QA User'}
                                <span style={{ fontSize: '0.72rem', fontWeight: 700, color: '#38bdf8', background: 'rgba(56, 189, 248, 0.12)', border: '1px solid rgba(56, 189, 248, 0.3)', padding: '2px 10px', borderRadius: '9999px' }}>
                                    {isStaff ? 'Admin / Lead Tester' : 'QA Engineer'}
                                </span>
                            </h3>
                            <p style={{ fontSize: '0.8rem', color: '#94a3b8', margin: '4px 0 0 0' }}>
                                {email || 'user@qa-platform.local'}
                            </p>
                        </div>
                    </div>

                    <button
                        onClick={onClose}
                        style={{
                            background: 'rgba(255, 255, 255, 0.06)',
                            border: '1px solid rgba(255, 255, 255, 0.15)',
                            color: '#94a3b8',
                            borderRadius: '12px',
                            padding: '8px',
                            cursor: 'pointer',
                            transition: 'all 0.2s'
                        }}
                    >
                        <X size={18} />
                    </button>
                </div>

                {/* Sub-Navigation Tabs */}
                <div style={{
                    display: 'flex',
                    gap: '8px',
                    padding: '14px 30px',
                    borderBottom: '1px solid rgba(139, 92, 246, 0.15)',
                    background: 'rgba(0, 0, 0, 0.2)'
                }}>
                    <button
                        onClick={() => setActiveTab('details')}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '8px 16px',
                            borderRadius: '10px',
                            fontSize: '0.82rem',
                            fontWeight: 700,
                            border: 'none',
                            cursor: 'pointer',
                            background: activeTab === 'details' ? 'rgba(124, 58, 237, 0.25)' : 'transparent',
                            color: activeTab === 'details' ? '#c084fc' : '#94a3b8',
                            boxShadow: activeTab === 'details' ? 'inset 0 0 10px rgba(124, 58, 237, 0.2)' : 'none'
                        }}
                    >
                        <User size={15} />
                        <span>Profile Details</span>
                    </button>

                    <button
                        onClick={() => setActiveTab('security')}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '8px 16px',
                            borderRadius: '10px',
                            fontSize: '0.82rem',
                            fontWeight: 700,
                            border: 'none',
                            cursor: 'pointer',
                            background: activeTab === 'security' ? 'rgba(124, 58, 237, 0.25)' : 'transparent',
                            color: activeTab === 'security' ? '#c084fc' : '#94a3b8',
                            boxShadow: activeTab === 'security' ? 'inset 0 0 10px rgba(124, 58, 237, 0.2)' : 'none'
                        }}
                    >
                        <Key size={15} />
                        <span>Security & Password</span>
                    </button>

                    <button
                        onClick={() => setActiveTab('preferences')}
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '8px 16px',
                            borderRadius: '10px',
                            fontSize: '0.82rem',
                            fontWeight: 700,
                            border: 'none',
                            cursor: 'pointer',
                            background: activeTab === 'preferences' ? 'rgba(124, 58, 237, 0.25)' : 'transparent',
                            color: activeTab === 'preferences' ? '#c084fc' : '#94a3b8',
                            boxShadow: activeTab === 'preferences' ? 'inset 0 0 10px rgba(124, 58, 237, 0.2)' : 'none'
                        }}
                    >
                        <Shield size={15} />
                        <span>Preferences</span>
                    </button>
                </div>

                {/* Body Content */}
                <form onSubmit={handleSaveProfile} style={{ padding: '24px 30px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
                    {/* Notifications */}
                    {successMessage && (
                        <div style={{ padding: '12px 16px', borderRadius: '12px', background: 'rgba(6, 78, 59, 0.6)', border: '1px solid rgba(16, 185, 129, 0.4)', color: '#6ee7b7', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <Check size={16} />
                            <span>{successMessage}</span>
                        </div>
                    )}
                    {errorMessage && (
                        <div style={{ padding: '12px 16px', borderRadius: '12px', background: 'rgba(136, 19, 55, 0.6)', border: '1px solid rgba(244, 63, 94, 0.4)', color: '#fda4af', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <AlertCircle size={16} />
                            <span>{errorMessage}</span>
                        </div>
                    )}

                    {loading ? (
                        <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: '0.85rem' }}>
                            Loading user profile info...
                        </div>
                    ) : activeTab === 'details' ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                <div>
                                    <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: '#94a3b8', marginBottom: '8px' }}>
                                        Username
                                    </label>
                                    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                                        <User size={16} style={{ position: 'absolute', left: '12px', color: '#94a3b8' }} />
                                        <input
                                            type="text"
                                            value={username}
                                            onChange={e => setUsername(e.target.value)}
                                            required
                                            style={{
                                                width: '100%',
                                                background: 'rgba(2, 6, 23, 0.75)',
                                                border: '1px solid rgba(139, 92, 246, 0.3)',
                                                borderRadius: '12px',
                                                padding: '10px 12px 10px 38px',
                                                color: '#ffffff',
                                                fontSize: '0.85rem',
                                                outline: 'none'
                                            }}
                                        />
                                    </div>
                                </div>

                                <div>
                                    <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: '#94a3b8', marginBottom: '8px' }}>
                                        Email Address
                                    </label>
                                    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                                        <Mail size={16} style={{ position: 'absolute', left: '12px', color: '#94a3b8' }} />
                                        <input
                                            type="email"
                                            value={email}
                                            onChange={e => setEmail(e.target.value)}
                                            required
                                            style={{
                                                width: '100%',
                                                background: 'rgba(2, 6, 23, 0.75)',
                                                border: '1px solid rgba(139, 92, 246, 0.3)',
                                                borderRadius: '12px',
                                                padding: '10px 12px 10px 38px',
                                                color: '#ffffff',
                                                fontSize: '0.85rem',
                                                outline: 'none'
                                            }}
                                        />
                                    </div>
                                </div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                <div>
                                    <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: '#94a3b8', marginBottom: '8px' }}>
                                        First Name
                                    </label>
                                    <input
                                        type="text"
                                        placeholder="Optional"
                                        value={firstName}
                                        onChange={e => setFirstName(e.target.value)}
                                        style={{
                                            width: '100%',
                                            background: 'rgba(2, 6, 23, 0.75)',
                                            border: '1px solid rgba(139, 92, 246, 0.3)',
                                            borderRadius: '12px',
                                            padding: '10px 14px',
                                            color: '#ffffff',
                                            fontSize: '0.85rem',
                                            outline: 'none'
                                        }}
                                    />
                                </div>

                                <div>
                                    <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: '#94a3b8', marginBottom: '8px' }}>
                                        Last Name
                                    </label>
                                    <input
                                        type="text"
                                        placeholder="Optional"
                                        value={lastName}
                                        onChange={e => setLastName(e.target.value)}
                                        style={{
                                            width: '100%',
                                            background: 'rgba(2, 6, 23, 0.75)',
                                            border: '1px solid rgba(139, 92, 246, 0.3)',
                                            borderRadius: '12px',
                                            padding: '10px 14px',
                                            color: '#ffffff',
                                            fontSize: '0.85rem',
                                            outline: 'none'
                                        }}
                                    />
                                </div>
                            </div>

                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(255, 255, 255, 0.02)', padding: '14px 18px', borderRadius: '14px', border: '1px solid rgba(255, 255, 255, 0.08)' }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#94a3b8', fontSize: '0.82rem' }}>
                                    <Calendar size={16} className="text-purple-400" />
                                    <span>Account Created: <strong>{dateJoined || 'Active'}</strong></span>
                                </div>
                                <span style={{ fontSize: '0.75rem', color: '#34d399', fontWeight: 700, background: 'rgba(6, 78, 59, 0.5)', padding: '3px 10px', borderRadius: '9999px', border: '1px solid rgba(16, 185, 129, 0.3)' }}>
                                    Verified Account
                                </span>
                            </div>
                        </div>
                    ) : activeTab === 'security' ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: '#94a3b8', marginBottom: '8px' }}>
                                    Current Password
                                </label>
                                <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                                    <Lock size={16} style={{ position: 'absolute', left: '12px', color: '#94a3b8' }} />
                                    <input
                                        type="password"
                                        placeholder="••••••••••••"
                                        value={currentPassword}
                                        onChange={e => setCurrentPassword(e.target.value)}
                                        style={{
                                            width: '100%',
                                            background: 'rgba(2, 6, 23, 0.75)',
                                            border: '1px solid rgba(139, 92, 246, 0.3)',
                                            borderRadius: '12px',
                                            padding: '10px 12px 10px 38px',
                                            color: '#ffffff',
                                            fontSize: '0.85rem',
                                            outline: 'none'
                                        }}
                                    />
                                </div>
                            </div>

                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                <div>
                                    <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: '#94a3b8', marginBottom: '8px' }}>
                                        New Password
                                    </label>
                                    <input
                                        type="password"
                                        placeholder="Min 8 characters"
                                        value={newPassword}
                                        onChange={e => setNewPassword(e.target.value)}
                                        style={{
                                            width: '100%',
                                            background: 'rgba(2, 6, 23, 0.75)',
                                            border: '1px solid rgba(139, 92, 246, 0.3)',
                                            borderRadius: '12px',
                                            padding: '10px 14px',
                                            color: '#ffffff',
                                            fontSize: '0.85rem',
                                            outline: 'none'
                                        }}
                                    />
                                </div>

                                <div>
                                    <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: '#94a3b8', marginBottom: '8px' }}>
                                        Confirm New Password
                                    </label>
                                    <input
                                        type="password"
                                        placeholder="Re-enter new password"
                                        value={confirmPassword}
                                        onChange={e => setConfirmPassword(e.target.value)}
                                        style={{
                                            width: '100%',
                                            background: 'rgba(2, 6, 23, 0.75)',
                                            border: '1px solid rgba(139, 92, 246, 0.3)',
                                            borderRadius: '12px',
                                            padding: '10px 14px',
                                            color: '#ffffff',
                                            fontSize: '0.85rem',
                                            outline: 'none'
                                        }}
                                    />
                                </div>
                            </div>
                        </div>
                    ) : (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '18px' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: '#94a3b8', marginBottom: '8px' }}>
                                    Default Test Automation Engine
                                </label>
                                <select
                                    value={browserEngine}
                                    onChange={e => setBrowserEngine(e.target.value)}
                                    style={{
                                        width: '100%',
                                        background: 'rgba(2, 6, 23, 0.75)',
                                        border: '1px solid rgba(139, 92, 246, 0.3)',
                                        borderRadius: '12px',
                                        padding: '10px 14px',
                                        color: '#ffffff',
                                        fontSize: '0.85rem',
                                        outline: 'none'
                                    }}
                                >
                                    <option value="Chromium Headless">Playwright Chromium (Headless Default)</option>
                                    <option value="Firefox Headless">Playwright Firefox (Headless)</option>
                                    <option value="WebKit Safari">Playwright WebKit (Safari)</option>
                                </select>
                            </div>

                            <div>
                                <label style={{ display: 'block', fontSize: '0.78rem', fontWeight: 700, color: '#94a3b8', marginBottom: '8px' }}>
                                    Automated Self-Healing & Retry Threshold
                                </label>
                                <select
                                    value={autoRetryCount}
                                    onChange={e => setAutoRetryCount(e.target.value)}
                                    style={{
                                        width: '100%',
                                        background: 'rgba(2, 6, 23, 0.75)',
                                        border: '1px solid rgba(139, 92, 246, 0.3)',
                                        borderRadius: '12px',
                                        padding: '10px 14px',
                                        color: '#ffffff',
                                        fontSize: '0.85rem',
                                        outline: 'none'
                                    }}
                                >
                                    <option value="1">1 Retry on Failure</option>
                                    <option value="2">2 Retries (Recommended)</option>
                                    <option value="3">3 Retries with AI Self-Healing</option>
                                </select>
                            </div>
                        </div>
                    )}

                    {/* Modal Footer Actions */}
                    <div style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'flex-end',
                        gap: '12px',
                        marginTop: '10px',
                        paddingTop: '18px',
                        borderTop: '1px solid rgba(139, 92, 246, 0.15)'
                    }}>
                        <button
                            type="button"
                            onClick={onClose}
                            style={{
                                padding: '10px 20px',
                                borderRadius: '12px',
                                background: 'rgba(255, 255, 255, 0.05)',
                                border: '1px solid rgba(255, 255, 255, 0.15)',
                                color: '#94a3b8',
                                fontSize: '0.82rem',
                                fontWeight: 600,
                                cursor: 'pointer'
                            }}
                        >
                            Cancel
                        </button>

                        <button
                            type="submit"
                            disabled={saving}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                padding: '10px 24px',
                                borderRadius: '12px',
                                background: 'linear-gradient(90deg, #7c3aed, #4f46e5)',
                                color: '#ffffff',
                                fontSize: '0.82rem',
                                fontWeight: 700,
                                border: 'none',
                                cursor: 'pointer',
                                boxShadow: '0 0 20px rgba(124, 58, 237, 0.4)',
                                opacity: saving ? 0.6 : 1
                            }}
                        >
                            <Save size={15} />
                            <span>{saving ? 'Saving Changes...' : 'Save Profile Changes'}</span>
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
