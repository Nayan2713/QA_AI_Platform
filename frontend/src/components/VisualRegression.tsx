import { useState } from 'react';
import { Eye, Sparkles, Layers, ShieldCheck, Bell, CheckCircle2, Lock } from 'lucide-react';

interface Props {
    appId: number;
    latestTestRunId?: number;
}

export default function VisualRegression({ appId }: Props) {
    const [subscribed, setSubscribed] = useState(false);

    return (
        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: '24px', paddingBottom: '60px', gap: '48px' }}>
            {/* Main Centered Coming Soon Hero Card */}
            <div style={{
                position: 'relative',
                width: '100%',
                borderRadius: '24px',
                border: '1px solid rgba(168, 85, 247, 0.3)',
                background: 'linear-gradient(180deg, rgba(28, 18, 59, 0.95) 0%, rgba(18, 13, 41, 0.95) 50%, rgba(11, 8, 24, 0.95) 100%)',
                padding: '48px 32px',
                textAlign: 'center',
                boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center'
            }}>
                {/* Background Ambient Glow Orbs */}
                <div style={{
                    position: 'absolute',
                    top: '-60px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: '350px',
                    height: '350px',
                    borderRadius: '50%',
                    background: 'rgba(168, 85, 247, 0.12)',
                    filter: 'blur(70px)',
                    pointerEvents: 'none'
                }} />

                <div style={{ position: 'relative', zIndex: 10, display: 'flex', flexDirection: 'column', alignItems: 'center', maxWidth: '640px', margin: '0 auto', gap: '20px' }}>
                    {/* Top Status Pill */}
                    <div style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '8px',
                        background: 'linear-gradient(90deg, rgba(168, 85, 247, 0.18), rgba(244, 63, 94, 0.18))',
                        border: '1px solid rgba(168, 85, 247, 0.4)',
                        padding: '6px 16px',
                        borderRadius: '9999px',
                        color: '#e9d5ff',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        boxShadow: '0 0 15px rgba(168, 85, 247, 0.25)'
                    }}>
                        <Sparkles size={14} className="text-purple-400 animate-pulse" />
                        <span>NEXT-GEN FEATURE · COMING SOON</span>
                    </div>

                    {/* Icon Halo */}
                    <div style={{
                        padding: '20px',
                        background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.2), rgba(244, 63, 94, 0.2))',
                        border: '1px solid rgba(168, 85, 247, 0.4)',
                        borderRadius: '24px',
                        color: '#e9d5ff',
                        boxShadow: '0 0 40px rgba(168, 85, 247, 0.35)',
                        margin: '8px 0'
                    }}>
                        <Eye size={44} />
                    </div>

                    {/* Title */}
                    <h2 style={{
                        fontSize: '2.2rem',
                        fontWeight: 800,
                        color: '#ffffff',
                        letterSpacing: '-0.5px',
                        lineHeight: 1.2,
                        margin: 0
                    }}>
                        Visual Regression & Layout Intelligence
                    </h2>

                    {/* Description */}
                    <p style={{
                        fontSize: '0.88rem',
                        color: 'rgba(255, 255, 255, 0.75)',
                        lineHeight: 1.6,
                        margin: 0,
                        maxWidth: '520px'
                    }}>
                        Pixel-perfect automated screenshot comparisons, CSS breakage detection, and visual heatmap overlays are currently in private beta testing.
                    </p>

                    {/* Notification Form / Status */}
                    <div style={{ marginTop: '16px', width: '100%', maxWidth: '440px' }}>
                        {subscribed ? (
                            <div style={{
                                width: '100%',
                                background: 'rgba(6, 78, 59, 0.6)',
                                border: '1px solid rgba(16, 185, 129, 0.4)',
                                borderRadius: '16px',
                                padding: '16px',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '8px',
                                color: '#6ee7b7',
                                fontSize: '0.82rem',
                                fontWeight: 600,
                                boxShadow: '0 0 20px rgba(16, 185, 129, 0.25)'
                            }}>
                                <CheckCircle2 size={16} />
                                <span>You are registered for Early Beta Access!</span>
                            </div>
                        ) : (
                            <div style={{
                                width: '100%',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: '10px',
                                background: 'rgba(2, 6, 23, 0.85)',
                                padding: '8px 12px',
                                borderRadius: '16px',
                                border: '1px solid rgba(168, 85, 247, 0.3)'
                            }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '4px 8px', color: '#94a3b8', fontSize: '0.8rem', fontFamily: 'var(--font-mono)' }}>
                                    <Lock size={14} style={{ color: '#c084fc' }} />
                                    <span>Early Access — Releasing in Q3</span>
                                </div>
                                <button
                                    onClick={() => setSubscribed(true)}
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '6px',
                                        background: 'linear-gradient(90deg, #9333ea, #db2777)',
                                        color: '#ffffff',
                                        fontSize: '0.8rem',
                                        fontWeight: 700,
                                        padding: '10px 20px',
                                        borderRadius: '12px',
                                        border: 'none',
                                        cursor: 'pointer',
                                        boxShadow: '0 0 15px rgba(168, 85, 247, 0.35)',
                                        whiteSpace: 'nowrap'
                                    }}
                                >
                                    <Bell size={14} />
                                    <span>Notify Me</span>
                                </button>
                            </div>
                        )}
                    </div>
                </div>
            </div>

            {/* Upcoming Roadmap Feature Cards Grid */}
            <div style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '24px' }}>
                <div style={{ textAlign: 'center' }}>
                    <span style={{ color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1.5px', display: 'flex', alignItems: 'center', gap: '8px', justifyContent: 'center' }}>
                        <Layers size={16} style={{ color: '#c084fc' }} />
                        <span>What's Arriving in Visual Regression v2</span>
                    </span>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '24px', width: '100%' }}>
                    {/* Feature 1 */}
                    <div style={{
                        background: 'linear-gradient(180deg, rgba(24, 18, 48, 0.9) 0%, rgba(14, 10, 31, 0.9) 100%)',
                        borderRadius: '16px',
                        border: '1px solid rgba(168, 85, 247, 0.2)',
                        padding: '24px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '10px',
                        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)'
                    }}>
                        <div style={{ width: '44px', height: '44px', borderRadius: '12px', background: 'rgba(168, 85, 247, 0.1)', border: '1px solid rgba(168, 85, 247, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#c084fc' }}>
                            <Eye size={20} />
                        </div>
                        <h4 style={{ color: '#ffffff', fontWeight: 700, fontSize: '0.95rem', margin: 0 }}>Automated Baseline Capture</h4>
                        <p style={{ color: '#94a3b8', fontSize: '0.82rem', lineHeight: 1.5, margin: 0 }}>
                            Captures golden-master screenshots across desktop, tablet, and mobile viewports on every test execution step automatically.
                        </p>
                    </div>

                    {/* Feature 2 */}
                    <div style={{
                        background: 'linear-gradient(180deg, rgba(24, 18, 48, 0.9) 0%, rgba(14, 10, 31, 0.9) 100%)',
                        borderRadius: '16px',
                        border: '1px solid rgba(168, 85, 247, 0.2)',
                        padding: '24px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '10px',
                        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)'
                    }}>
                        <div style={{ width: '44px', height: '44px', borderRadius: '12px', background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fb7185' }}>
                            <Layers size={20} />
                        </div>
                        <h4 style={{ color: '#ffffff', fontWeight: 700, fontSize: '0.95rem', margin: 0 }}>Pixel-by-Pixel Diff Heatmap</h4>
                        <p style={{ color: '#94a3b8', fontSize: '0.82rem', lineHeight: 1.5, margin: 0 }}>
                            OpenCV-powered pixel comparison engine highlights alignment shifts, text overflows, and missing elements in magenta.
                        </p>
                    </div>

                    {/* Feature 3 */}
                    <div style={{
                        background: 'linear-gradient(180deg, rgba(24, 18, 48, 0.9) 0%, rgba(14, 10, 31, 0.9) 100%)',
                        borderRadius: '16px',
                        border: '1px solid rgba(168, 85, 247, 0.2)',
                        padding: '24px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '10px',
                        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)'
                    }}>
                        <div style={{ width: '44px', height: '44px', borderRadius: '12px', background: 'rgba(6, 182, 212, 0.1)', border: '1px solid rgba(6, 182, 212, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#22d3ee' }}>
                            <Sparkles size={20} />
                        </div>
                        <h4 style={{ color: '#ffffff', fontWeight: 700, fontSize: '0.95rem', margin: 0 }}>AI Dynamic Element Masking</h4>
                        <p style={{ color: '#94a3b8', fontSize: '0.82rem', lineHeight: 1.5, margin: 0 }}>
                            Smart AI filters ignore dynamic timestamps, avatars, and ads to prevent false positive regression alerts.
                        </p>
                    </div>

                    {/* Feature 4 */}
                    <div style={{
                        background: 'linear-gradient(180deg, rgba(24, 18, 48, 0.9) 0%, rgba(14, 10, 31, 0.9) 100%)',
                        borderRadius: '16px',
                        border: '1px solid rgba(168, 85, 247, 0.2)',
                        padding: '24px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '10px',
                        boxShadow: '0 8px 32px rgba(0, 0, 0, 0.3)'
                    }}>
                        <div style={{ width: '44px', height: '44px', borderRadius: '12px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#34d399' }}>
                            <ShieldCheck size={20} />
                        </div>
                        <h4 style={{ color: '#ffffff', fontWeight: 700, fontSize: '0.95rem', margin: 0 }}>One-Click Suite Approvals</h4>
                        <p style={{ color: '#94a3b8', fontSize: '0.82rem', lineHeight: 1.5, margin: 0 }}>
                            Approve intended UI redesigns with one click to instantly update visual reference baselines across all pages.
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
}