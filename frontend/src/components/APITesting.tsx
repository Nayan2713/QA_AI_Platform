import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { 
  Zap, Play, RefreshCw, CheckCircle2, XCircle, Clock, 
  ChevronDown, ChevronRight, Trash2, Search, AlertTriangle, 
  Code2, Check, ShieldCheck, Sparkles, Server, Copy, Info, HelpCircle
} from 'lucide-react';
import { getAPITestCases, getAPITestRuns, generateAndRunAPITests, runSingleAPITest, deleteAPITestCase } from '../lib/api';
import { APITestCase, APITestRun } from '../lib/types';

interface Props {
    appId: number;
}

const METHOD_THEMES: Record<string, { bg: string; text: string; border: string; glow: string }> = {
    GET: { 
        bg: 'bg-cyan-500/10', 
        text: 'text-cyan-400', 
        border: 'border-cyan-500/30',
        glow: 'shadow-[0_0_12px_rgba(6,182,212,0.2)]'
    },
    POST: { 
        bg: 'bg-violet-500/10', 
        text: 'text-violet-400', 
        border: 'border-violet-500/30',
        glow: 'shadow-[0_0_12px_rgba(139,92,246,0.2)]'
    },
    PUT: { 
        bg: 'bg-amber-500/10', 
        text: 'text-amber-400', 
        border: 'border-amber-500/30',
        glow: 'shadow-[0_0_12px_rgba(245,158,11,0.2)]'
    },
    PATCH: { 
        bg: 'bg-orange-500/10', 
        text: 'text-orange-400', 
        border: 'border-orange-500/30',
        glow: 'shadow-[0_0_12px_rgba(249,115,22,0.2)]'
    },
    DELETE: { 
        bg: 'bg-rose-500/10', 
        text: 'text-rose-400', 
        border: 'border-rose-500/30',
        glow: 'shadow-[0_0_12px_rgba(244,63,94,0.2)]'
    },
};

function MethodBadge({ method }: { method: string }) {
    const theme = METHOD_THEMES[method.toUpperCase()] || {
        bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30', glow: ''
    };
    return (
        <span className={`text-xs font-mono font-bold tracking-wider px-3 py-1.5 rounded-xl border ${theme.bg} ${theme.text} ${theme.border} ${theme.glow} shrink-0`}>
            {method.toUpperCase()}
        </span>
    );
}

function StatusPill({ code, passed }: { code: number | null; passed?: boolean }) {
    if (code === null) return <span className="text-zinc-500 text-xs font-mono">—</span>;
    
    let cls = 'bg-zinc-900/80 text-zinc-400 border-zinc-700/60';
    if (passed) {
        cls = 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40 shadow-[0_0_8px_rgba(16,185,129,0.15)]';
    } else if (code >= 500) {
        cls = 'bg-purple-950/60 text-purple-300 border-purple-500/40 shadow-[0_0_8px_rgba(168,85,247,0.15)]';
    } else if (code >= 400 || !passed) {
        cls = 'bg-rose-950/60 text-rose-300 border-rose-500/40 shadow-[0_0_8px_rgba(244,63,94,0.15)]';
    } else if (code >= 200 && code < 300) {
        cls = 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40 shadow-[0_0_8px_rgba(16,185,129,0.15)]';
    }

    return (
        <span className={`text-xs font-mono font-bold px-3 py-1 rounded-lg border ${cls} inline-flex items-center gap-1.5`}>
            HTTP {code}
        </span>
    );
}

function RunRow({ run }: { run: APITestRun }) {
    const [open, setOpen] = useState(false);
    const [copied, setCopied] = useState(false);

    const handleCopy = (e: React.MouseEvent) => {
        e.stopPropagation();
        if (run.response_body) {
            navigator.clipboard.writeText(run.response_body);
            setCopied(true);
            setTimeout(() => setCopied(false), 2000);
        }
    };

    return (
        <div className={`rounded-2xl border backdrop-blur-md transition-all duration-300 overflow-hidden ${
            run.passed 
                ? 'border-violet-500/20 bg-slate-950/40 hover:border-violet-500/40 shadow-md' 
                : 'border-rose-500/30 bg-rose-950/20 hover:border-rose-500/50 shadow-md'
        }`}>
            <div
                className="flex items-center justify-between px-6 py-4.5 cursor-pointer select-none gap-4"
                onClick={() => setOpen(!open)}
            >
                <div className="flex items-center gap-4 min-w-0 flex-wrap">
                    {run.passed ? (
                        <div className="flex items-center gap-1.5 bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 px-3 py-1 rounded-full text-xs font-semibold shadow-[0_0_10px_rgba(16,185,129,0.15)]">
                            <CheckCircle2 size={14} className="shrink-0" />
                            <span>PASSED</span>
                        </div>
                    ) : (
                        <div className="flex items-center gap-1.5 bg-rose-500/10 text-rose-400 border border-rose-500/30 px-3 py-1 rounded-full text-xs font-semibold shadow-[0_0_10px_rgba(244,63,94,0.15)]">
                            <XCircle size={14} className="shrink-0" />
                            <span>FAILED</span>
                        </div>
                    )}

                    <StatusPill code={run.actual_status_code} passed={run.passed} />

                    {run.response_time_ms !== null && (
                        <span className={`flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-lg border ${
                            run.response_time_ms < 300 
                                ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20' :
                            run.response_time_ms < 1000 
                                ? 'text-amber-400 bg-amber-500/10 border-amber-500/20' :
                                'text-rose-400 bg-rose-500/10 border-rose-500/20'
                        }`}>
                            <Clock size={12} /> {run.response_time_ms.toFixed(0)}ms
                        </span>
                    )}

                    {!run.passed && run.failure_reason && (
                        <span className="text-rose-300/90 text-xs font-mono truncate max-w-md hidden sm:inline-block ml-2">
                            {run.failure_reason}
                        </span>
                    )}
                </div>

                <div className="flex items-center gap-4 shrink-0">
                    <span className="text-zinc-400 text-xs font-mono">
                        {new Date(run.created_at).toLocaleTimeString()}
                    </span>
                    <div className="text-zinc-400 hover:text-white transition-colors p-1">
                        {open ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                    </div>
                </div>
            </div>

            {open && (
                <div className="px-6 pb-6 border-t border-violet-500/15 pt-4 space-y-4 bg-black/40 text-xs">
                    {!run.passed && run.failure_reason && (
                        <div className="bg-rose-950/40 border border-rose-800/50 rounded-xl p-4 flex items-start gap-3">
                            <AlertTriangle size={16} className="text-rose-400 shrink-0 mt-0.5" />
                            <div>
                                <p className="text-rose-200 font-semibold mb-1">Assertion Failure</p>
                                <p className="text-rose-300/90 font-mono text-xs leading-relaxed">{run.failure_reason}</p>
                            </div>
                        </div>
                    )}

                    {run.error && (
                        <div className="bg-purple-950/40 border border-purple-800/50 rounded-xl p-4">
                            <p className="text-purple-300 font-semibold mb-1">Execution Exception</p>
                            <p className="text-purple-200 font-mono text-xs whitespace-pre-wrap leading-relaxed">{run.error}</p>
                        </div>
                    )}

                    {run.response_body && (
                        <div className="pt-2">
                            <div className="flex items-center justify-between mb-2">
                                <span className="text-zinc-300 text-xs font-semibold flex items-center gap-2">
                                    <Code2 size={15} className="text-cyan-400" />
                                    Response Payload Body
                                </span>
                                <button
                                    onClick={handleCopy}
                                    className="text-xs text-zinc-300 hover:text-white bg-violet-900/40 hover:bg-violet-800/60 border border-violet-500/30 px-3 py-1.5 rounded-xl transition-all flex items-center gap-1.5"
                                >
                                    {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                                    {copied ? 'Copied to Clipboard' : 'Copy JSON Payload'}
                                </button>
                            </div>
                            <pre className="text-xs text-cyan-300/90 bg-[#090612] rounded-2xl p-4.5 border border-violet-500/20 overflow-auto max-h-64 font-mono leading-relaxed shadow-inner">
                                {(() => {
                                    try { 
                                        return JSON.stringify(JSON.parse(run.response_body), null, 2); 
                                    } catch { 
                                        return run.response_body; 
                                    }
                                })()}
                            </pre>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

function TestCaseCard({ tc, appId }: { tc: APITestCase; appId: number }) {
    const qc = useQueryClient();
    const [open, setOpen] = useState(false);

    const runMutation = useMutation({
        mutationFn: () => runSingleAPITest(tc.id),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['api-test-runs', appId] }),
    });

    const deleteMutation = useMutation({
        mutationFn: () => deleteAPITestCase(tc.id),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['api-test-cases', appId] }),
    });

    return (
        <div className="bg-gradient-to-b from-[#181230]/90 to-[#0e0a1f]/90 backdrop-blur-xl rounded-2xl border border-violet-500/20 hover:border-violet-500/45 transition-all duration-300 overflow-hidden shadow-xl hover:shadow-[0_8px_32px_rgba(139,92,246,0.15)]">
            <div className="flex items-center justify-between px-6 py-5 gap-5">
                <div
                    className="flex items-center gap-4 flex-1 cursor-pointer min-w-0"
                    onClick={() => setOpen(!open)}
                >
                    <MethodBadge method={tc.method} />
                    
                    <div className="min-w-0 flex-1 pr-2">
                        <p className="text-white text-sm font-semibold truncate hover:text-cyan-400 transition-colors">
                            {tc.title}
                        </p>
                        <p className="text-zinc-400 text-xs font-mono truncate mt-1">
                            {tc.url}
                        </p>
                    </div>

                    <div className="flex items-center gap-2.5 shrink-0">
                        {tc.ai_generated && (
                            <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-purple-300 bg-purple-500/15 border border-purple-500/30 px-3 py-1 rounded-full shadow-[0_0_10px_rgba(168,85,247,0.2)]">
                                <Sparkles size={11} className="text-purple-400" /> AI
                            </span>
                        )}
                        {tc.auth_required && (
                            <span className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-amber-300 bg-amber-500/15 border border-amber-500/30 px-3 py-1 rounded-full shadow-[0_0_10px_rgba(245,158,11,0.2)]">
                                <ShieldCheck size={11} className="text-amber-400" /> Auth Required
                            </span>
                        )}
                    </div>
                </div>

                <div className="flex items-center gap-3 shrink-0">
                    <button
                        onClick={() => runMutation.mutate()}
                        disabled={runMutation.isPending}
                        className="flex items-center gap-2 bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 active:from-violet-700 active:to-indigo-700 disabled:opacity-50 text-white text-xs font-semibold px-4.5 py-2.5 rounded-xl shadow-[0_0_15px_rgba(139,92,246,0.3)] transition-all transform hover:-translate-y-0.5"
                    >
                        <Play size={13} className={runMutation.isPending ? 'animate-pulse' : ''} />
                        {runMutation.isPending ? 'Executing…' : 'Run Test'}
                    </button>
                    <button
                        onClick={() => deleteMutation.mutate()}
                        disabled={deleteMutation.isPending}
                        className="text-zinc-500 hover:text-rose-400 hover:bg-rose-500/10 p-2.5 rounded-xl border border-transparent hover:border-rose-500/20 transition-all"
                        title="Delete Test Case"
                    >
                        <Trash2 size={15} />
                    </button>
                </div>
            </div>

            {open && (
                <div className="px-6 pb-6 border-t border-violet-500/15 pt-5 space-y-5 bg-black/40 backdrop-blur-md text-xs">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                        <div className="bg-slate-900/60 rounded-2xl p-4 border border-violet-500/15">
                            <span className="text-zinc-400 text-xs font-semibold block mb-2">Expected Response Status</span>
                            <StatusPill code={tc.expected_status} passed={tc.expected_status < 400} />
                        </div>

                        {tc.expected_body_contains && tc.expected_body_contains.length > 0 && (
                            <div className="bg-slate-900/60 rounded-2xl p-4 border border-violet-500/15">
                                <span className="text-zinc-400 text-xs font-semibold block mb-2">Required Schema Assertions</span>
                                <div className="flex flex-wrap gap-2">
                                    {tc.expected_body_contains.map(k => (
                                        <span key={k} className="bg-emerald-950/60 text-emerald-300 border border-emerald-500/30 px-3 py-1 rounded-lg font-mono text-xs shadow-[0_0_8px_rgba(16,185,129,0.1)]">
                                            ✓ {k}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>

                    {tc.body && Object.keys(tc.body).length > 0 && (
                        <div className="pt-1">
                            <span className="text-zinc-300 text-xs font-semibold block mb-2">Request Payload</span>
                            <pre className="bg-[#090612] rounded-2xl p-4 text-zinc-300 border border-violet-500/20 overflow-auto max-h-48 font-mono text-xs shadow-inner leading-relaxed">
                                {JSON.stringify(tc.body, null, 2)}
                            </pre>
                        </div>
                    )}

                    {runMutation.data && (
                        <div className="pt-3 border-t border-violet-500/15">
                            <span className="text-zinc-300 text-xs font-semibold block mb-2.5">Latest Execution Result</span>
                            <RunRow run={runMutation.data} />
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

export default function APITesting({ appId }: Props) {
    const qc = useQueryClient();
    const [searchQuery, setSearchQuery] = useState('');
    const [selectedMethod, setSelectedMethod] = useState<string>('ALL');
    const [showHelpGuide, setShowHelpGuide] = useState(false);

    const { data: testCases = [], isLoading: loadingCases } = useQuery({
        queryKey: ['api-test-cases', appId],
        queryFn: () => getAPITestCases(appId),
    });

    const { data: runs = [], isLoading: loadingRuns } = useQuery({
        queryKey: ['api-test-runs', appId],
        queryFn: () => getAPITestRuns(appId),
    });

    const generateMutation = useMutation({
        mutationFn: () => generateAndRunAPITests(appId, true),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['api-test-cases', appId] });
            qc.invalidateQueries({ queryKey: ['api-test-runs', appId] });
        },
    });

    const runAllMutation = useMutation({
        mutationFn: () => generateAndRunAPITests(appId, false),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['api-test-runs', appId] }),
    });

    // Filter test cases
    const filteredCases = testCases.filter(tc => {
        const matchesMethod = selectedMethod === 'ALL' || tc.method.toUpperCase() === selectedMethod;
        const matchesSearch = !searchQuery || 
            tc.title.toLowerCase().includes(searchQuery.toLowerCase()) || 
            tc.url.toLowerCase().includes(searchQuery.toLowerCase());
        return matchesMethod && matchesSearch;
    });

    const recentRuns = runs.slice(0, 15);
    const passedCount = runs.filter(r => r.passed).length;
    const failedCount = runs.filter(r => !r.passed).length;
    const passRate = runs.length > 0
        ? Math.round((passedCount / runs.length) * 100)
        : null;

    return (
        <div className="flex flex-col gap-10 pt-6 pb-16">
            {/* SECTION 1: Header Hero Banner */}
            <section style={{
                position: 'relative',
                width: '100%',
                borderRadius: '24px',
                border: '1px solid rgba(139, 92, 246, 0.25)',
                background: 'linear-gradient(90deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 20, 56, 0.95) 50%, rgba(15, 23, 42, 0.95) 100%)',
                padding: '28px 32px',
                boxShadow: '0 12px 40px rgba(0, 0, 0, 0.45)',
                overflow: 'hidden'
            }}>
                <div style={{ position: 'absolute', top: '-40px', right: '-40px', width: '220px', height: '220px', borderRadius: '50%', background: 'rgba(139, 92, 246, 0.12)', filter: 'blur(50px)', pointerEvents: 'none' }} />
                <div style={{ position: 'absolute', bottom: '-40px', left: '33%', width: '220px', height: '220px', borderRadius: '50%', background: 'rgba(6, 182, 212, 0.12)', filter: 'blur(50px)', pointerEvents: 'none' }} />

                <div style={{ position: 'relative', zIndex: 10, display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: '24px', flexWrap: 'wrap', width: '100%' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '18px', flex: 1, minWidth: '280px' }}>
                        <div style={{ padding: '14px', background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.2), rgba(6, 182, 212, 0.2))', border: '1px solid rgba(139, 92, 246, 0.35)', borderRadius: '18px', color: '#22d3ee', boxShadow: '0 0 25px rgba(6, 182, 212, 0.25)', flexShrink: 0 }}>
                            <Zap size={28} />
                        </div>
                        <div>
                            <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#ffffff', letterSpacing: '-0.3px', margin: 0, display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                                <span>API Security & Endpoint Suite</span>
                                <span style={{ fontSize: '0.75rem', fontWeight: 700, color: '#22d3ee', background: 'rgba(6, 182, 212, 0.12)', border: '1px solid rgba(6, 182, 212, 0.3)', padding: '3px 12px', borderRadius: '9999px' }}>
                                    {testCases.length} endpoints
                                </span>
                            </h2>
                            <p style={{ fontSize: '0.82rem', color: '#94a3b8', margin: '6px 0 0 0', lineHeight: 1.5, maxWidth: '580px' }}>
                                Automated API assertions, JWT authentication headers, status code verifications, and payload schema validation.
                            </p>
                        </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0, flexWrap: 'wrap' }}>
                        <button
                            onClick={() => setShowHelpGuide(!showHelpGuide)}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                background: 'rgba(139, 92, 246, 0.12)',
                                border: '1px solid rgba(139, 92, 246, 0.3)',
                                color: '#c084fc',
                                fontSize: '0.8rem',
                                fontWeight: 700,
                                padding: '10px 16px',
                                borderRadius: '14px',
                                cursor: 'pointer',
                                transition: 'all 0.2s'
                            }}
                        >
                            <HelpCircle size={15} />
                            <span>{showHelpGuide ? 'Hide Guide' : 'How it Works'}</span>
                        </button>

                        <button
                            onClick={() => runAllMutation.mutate()}
                            disabled={runAllMutation.isPending || testCases.length === 0}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                background: 'rgba(15, 23, 42, 0.85)',
                                border: '1px solid rgba(139, 92, 246, 0.3)',
                                color: '#ffffff',
                                fontSize: '0.8rem',
                                fontWeight: 700,
                                padding: '10px 20px',
                                borderRadius: '14px',
                                cursor: 'pointer',
                                transition: 'all 0.2s',
                                opacity: (runAllMutation.isPending || testCases.length === 0) ? 0.4 : 1
                            }}
                        >
                            <Play size={14} className={runAllMutation.isPending ? 'animate-pulse text-cyan-400' : 'text-cyan-400'} />
                            <span>{runAllMutation.isPending ? 'Running Suite…' : 'Run All Tests'}</span>
                        </button>

                        <button
                            onClick={() => generateMutation.mutate()}
                            disabled={generateMutation.isPending}
                            style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '8px',
                                background: 'linear-gradient(90deg, #7c3aed, #9333ea, #0891b2)',
                                border: 'none',
                                color: '#ffffff',
                                fontSize: '0.8rem',
                                fontWeight: 800,
                                padding: '10px 22px',
                                borderRadius: '14px',
                                cursor: 'pointer',
                                boxShadow: '0 0 25px rgba(124, 58, 237, 0.35)',
                                transition: 'all 0.2s',
                                opacity: generateMutation.isPending ? 0.5 : 1
                            }}
                        >
                            <RefreshCw size={14} className={generateMutation.isPending ? 'animate-spin' : ''} />
                            <span>{generateMutation.isPending ? 'Generating…' : 'Generate & Run'}</span>
                        </button>
                    </div>
                </div>
            </section>

            {/* Optional Collapsible Help Guide Banner */}
            {showHelpGuide && (
                <div style={{
                    position: 'relative',
                    width: '100%',
                    borderRadius: '24px',
                    border: '1px solid rgba(6, 182, 212, 0.35)',
                    background: 'linear-gradient(180deg, rgba(22, 16, 46, 0.95) 0%, rgba(12, 9, 29, 0.95) 100%)',
                    padding: '26px 30px',
                    boxShadow: '0 15px 45px rgba(0, 0, 0, 0.45)',
                    boxSizing: 'border-box',
                    overflow: 'hidden'
                }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', color: '#22d3ee', fontSize: '0.95rem', fontWeight: 800, marginBottom: '18px' }}>
                        <Info size={20} />
                        <span>Guide: How API Testing Works & What You Get</span>
                    </div>

                    <div style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                        gap: '18px',
                        width: '100%'
                    }}>
                        <div style={{
                            background: 'rgba(15, 23, 42, 0.65)',
                            padding: '18px 20px',
                            borderRadius: '16px',
                            border: '1px solid rgba(139, 92, 246, 0.25)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px'
                        }}>
                            <strong style={{ color: '#ffffff', fontSize: '0.85rem', fontWeight: 700, display: 'block' }}>
                                1. Endpoint Discovery
                            </strong>
                            <p style={{ color: '#94a3b8', fontSize: '0.8rem', margin: 0, lineHeight: 1.5 }}>
                                The platform automatically discovers backend REST API URLs (GET, POST, PUT, DELETE) during website crawling.
                            </p>
                        </div>

                        <div style={{
                            background: 'rgba(15, 23, 42, 0.65)',
                            padding: '18px 20px',
                            borderRadius: '16px',
                            border: '1px solid rgba(139, 92, 246, 0.25)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px'
                        }}>
                            <strong style={{ color: '#ffffff', fontSize: '0.85rem', fontWeight: 700, display: 'block' }}>
                                2. Automated Execution
                            </strong>
                            <p style={{ color: '#94a3b8', fontSize: '0.8rem', margin: 0, lineHeight: 1.5 }}>
                                Direct HTTP calls are sent to each API endpoint with optional JWT Bearer tokens to verify status codes and schemas.
                            </p>
                        </div>

                        <div style={{
                            background: 'rgba(15, 23, 42, 0.65)',
                            padding: '18px 20px',
                            borderRadius: '16px',
                            border: '1px solid rgba(139, 92, 246, 0.25)',
                            display: 'flex',
                            flexDirection: 'column',
                            gap: '8px'
                        }}>
                            <strong style={{ color: '#ffffff', fontSize: '0.85rem', fontWeight: 700, display: 'block' }}>
                                3. Results & Reports
                            </strong>
                            <p style={{ color: '#94a3b8', fontSize: '0.8rem', margin: 0, lineHeight: 1.5 }}>
                                Provides response times in milliseconds, actual HTTP status codes, and formatted JSON response payload trees.
                            </p>
                        </div>
                    </div>
                </div>
            )}

            {/* SECTION 2: KPI Dashboard Cards */}
            {runs.length > 0 && (
                <section style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '24px', width: '100%' }}>
                    {/* Card 1: Endpoints */}
                    <div style={{
                        position: 'relative',
                        borderRadius: '20px',
                        background: 'linear-gradient(180deg, rgba(24, 18, 48, 0.95) 0%, rgba(14, 10, 31, 0.95) 100%)',
                        border: '1px solid rgba(139, 92, 246, 0.25)',
                        padding: '24px 26px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        minHeight: '140px',
                        boxShadow: '0 10px 30px rgba(0, 0, 0, 0.35)'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                            <span style={{ color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px' }}>
                                Discovered Endpoints
                            </span>
                            <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: 'rgba(6, 182, 212, 0.12)', border: '1px solid rgba(6, 182, 212, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#22d3ee', boxShadow: '0 0 12px rgba(6, 182, 212, 0.25)' }}>
                                <Server size={18} />
                            </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: '#ffffff', lineHeight: 1 }}>
                                {testCases.length}
                            </span>
                            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#22d3ee', background: 'rgba(6, 182, 212, 0.12)', border: '1px solid rgba(6, 182, 212, 0.3)', padding: '4px 12px', borderRadius: '9999px' }}>
                                Active Suite
                            </span>
                        </div>
                    </div>

                    {/* Card 2: Executions */}
                    <div style={{
                        position: 'relative',
                        borderRadius: '20px',
                        background: 'linear-gradient(180deg, rgba(24, 18, 48, 0.95) 0%, rgba(14, 10, 31, 0.95) 100%)',
                        border: '1px solid rgba(139, 92, 246, 0.25)',
                        padding: '24px 26px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        minHeight: '140px',
                        boxShadow: '0 10px 30px rgba(0, 0, 0, 0.35)'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                            <span style={{ color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px' }}>
                                Total Executions
                            </span>
                            <div style={{ width: '40px', height: '40px', borderRadius: '12px', background: 'rgba(168, 85, 247, 0.12)', border: '1px solid rgba(168, 85, 247, 0.3)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#c084fc', boxShadow: '0 0 12px rgba(168, 85, 247, 0.25)' }}>
                                <Clock size={18} />
                            </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: '#ffffff', lineHeight: 1 }}>
                                {runs.length}
                            </span>
                            <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#c084fc', background: 'rgba(168, 85, 247, 0.12)', border: '1px solid rgba(168, 85, 247, 0.3)', padding: '4px 12px', borderRadius: '9999px' }}>
                                Completed
                            </span>
                        </div>
                    </div>

                    {/* Card 3: Pass vs Fail */}
                    <div style={{
                        position: 'relative',
                        borderRadius: '20px',
                        background: 'linear-gradient(180deg, rgba(24, 18, 48, 0.95) 0%, rgba(14, 10, 31, 0.95) 100%)',
                        border: '1px solid rgba(139, 92, 246, 0.25)',
                        padding: '24px 26px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        minHeight: '140px',
                        boxShadow: '0 10px 30px rgba(0, 0, 0, 0.35)'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                            <span style={{ color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px' }}>
                                Pass vs Fail
                            </span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '0.75rem', fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                                <span style={{ color: '#34d399', background: 'rgba(6, 78, 59, 0.6)', border: '1px solid rgba(16, 185, 129, 0.4)', padding: '3px 8px', borderRadius: '6px' }}>{passedCount} ✓</span>
                                <span style={{ color: '#fb7185', background: 'rgba(136, 19, 55, 0.6)', border: '1px solid rgba(244, 63, 94, 0.4)', padding: '3px 8px', borderRadius: '6px' }}>{failedCount} ✗</span>
                            </div>
                        </div>
                        <div style={{ width: '100%', background: '#020617', borderRadius: '9999px', height: '12px', overflow: 'hidden', display: 'flex', border: '1px solid rgba(139, 92, 246, 0.2)' }}>
                            <div style={{ background: 'linear-gradient(90deg, #10b981, #06b6d4)', height: '100%', width: `${passRate || 0}%`, transition: 'all 0.5s' }} />
                            <div style={{ background: 'linear-gradient(90deg, #f43f5e, #ec4899)', height: '100%', width: `${100 - (passRate || 0)}%`, transition: 'all 0.5s' }} />
                        </div>
                    </div>

                    {/* Card 4: Suite Pass Rate */}
                    <div style={{
                        position: 'relative',
                        borderRadius: '20px',
                        background: 'linear-gradient(180deg, rgba(24, 18, 48, 0.95) 0%, rgba(14, 10, 31, 0.95) 100%)',
                        border: '1px solid rgba(139, 92, 246, 0.25)',
                        padding: '24px 26px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                        minHeight: '140px',
                        boxShadow: '0 10px 30px rgba(0, 0, 0, 0.35)'
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                            <span style={{ color: '#94a3b8', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px' }}>
                                Suite Pass Rate
                            </span>
                            <span style={{
                                fontSize: '0.75rem',
                                fontWeight: 700,
                                padding: '4px 12px',
                                borderRadius: '9999px',
                                background: passRate !== null && passRate >= 80 ? 'rgba(6, 78, 59, 0.6)' : 'rgba(136, 19, 55, 0.6)',
                                color: passRate !== null && passRate >= 80 ? '#34d399' : '#fb7185',
                                border: passRate !== null && passRate >= 80 ? '1px solid rgba(16, 185, 129, 0.4)' : '1px solid rgba(244, 63, 94, 0.4)'
                            }}>
                                {passRate !== null && passRate >= 80 ? 'Healthy' : 'Needs Attention'}
                            </span>
                        </div>
                        <div style={{ fontSize: '2.2rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: passRate !== null && passRate >= 80 ? '#34d399' : '#fb7185', lineHeight: 1 }}>
                            {passRate !== null ? `${passRate}%` : '—'}
                        </div>
                    </div>
                </section>
            )}

            {/* SECTION 3: Configured Test Cases & Search Filter Toolbar */}
            <section style={{ display: 'flex', flexDirection: 'column', gap: '24px', width: '100%' }}>
                {/* Filter & Search Toolbar */}
                <div style={{ display: 'flex', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: '16px', width: '100%', flexWrap: 'wrap' }}>
                    <div style={{ position: 'relative', flex: 1, minWidth: '280px', display: 'flex', alignItems: 'center' }}>
                        <Search size={18} style={{ position: 'absolute', left: '16px', color: '#94a3b8', pointerEvents: 'none' }} />
                        <input
                            type="text"
                            placeholder="Filter endpoints by title or URL..."
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            style={{
                                width: '100%',
                                background: 'rgba(2, 6, 23, 0.75)',
                                border: '1px solid rgba(139, 92, 246, 0.3)',
                                borderRadius: '16px',
                                padding: '12px 18px 12px 48px',
                                color: '#ffffff',
                                fontSize: '0.85rem',
                                outline: 'none',
                                boxShadow: 'inset 0 2px 4px rgba(0, 0, 0, 0.4)'
                            }}
                        />
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(2, 6, 23, 0.75)', padding: '6px', borderRadius: '16px', border: '1px solid rgba(139, 92, 246, 0.3)' }}>
                        {['ALL', 'GET', 'POST', 'PUT', 'DELETE'].map(m => (
                            <button
                                key={m}
                                onClick={() => setSelectedMethod(m)}
                                style={{
                                    padding: '8px 18px',
                                    borderRadius: '12px',
                                    fontSize: '0.78rem',
                                    fontWeight: 700,
                                    border: 'none',
                                    cursor: 'pointer',
                                    transition: 'all 0.2s',
                                    background: selectedMethod === m ? 'linear-gradient(90deg, #7c3aed, #4f46e5)' : 'transparent',
                                    color: selectedMethod === m ? '#ffffff' : '#94a3b8',
                                    boxShadow: selectedMethod === m ? '0 0 14px rgba(124, 58, 237, 0.4)' : 'none'
                                }}
                            >
                                {m}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Test Cases List */}
                <div className="flex flex-col gap-4">
                    <div className="flex items-center justify-between">
                        <h3 className="text-white text-base font-bold tracking-tight flex items-center gap-2.5">
                            <span>Configured Test Cases</span>
                            <span className="text-xs font-mono text-cyan-400 bg-cyan-950/50 border border-cyan-500/30 px-2.5 py-0.5 rounded-full">
                                {filteredCases.length}
                            </span>
                        </h3>
                    </div>

                    {loadingCases ? (
                        <div className="text-center py-16 bg-slate-950/40 rounded-3xl border border-violet-500/20 backdrop-blur-md">
                            <RefreshCw size={26} className="animate-spin text-cyan-400 mx-auto mb-3" />
                            <p className="text-zinc-400 text-xs font-medium">Loading API test cases...</p>
                        </div>
                    ) : filteredCases.length === 0 ? (
                        <div className="text-center py-16 bg-slate-950/40 rounded-3xl border border-violet-500/20 border-dashed backdrop-blur-md">
                            <Zap size={36} className="text-zinc-500 mx-auto mb-3" />
                            <p className="text-white text-sm font-bold">No API Test Cases Found</p>
                            <p className="text-zinc-400 text-xs mt-1.5 max-w-sm mx-auto leading-relaxed">
                                {testCases.length === 0 
                                    ? 'Click "Generate & Run" to create tests for discovered endpoints.' 
                                    : 'No endpoints matched your search or HTTP method filter.'}
                            </p>
                        </div>
                    ) : (
                        <div className="flex flex-col gap-4">
                            {filteredCases.map(tc => (
                                <TestCaseCard key={tc.id} tc={tc} appId={appId} />
                            ))}
                        </div>
                    )}
                </div>
            </section>

            {/* SECTION 4: Execution History Log */}
            {recentRuns.length > 0 && (
                <section className="pt-8 border-t border-violet-500/20 flex flex-col gap-5">
                    <div className="flex items-center justify-between">
                        <h3 className="text-white text-base font-bold tracking-tight">
                            Execution History Log
                        </h3>
                        <span className="text-xs text-zinc-400 font-mono">Showing recent {recentRuns.length} runs</span>
                    </div>

                    <div className="flex flex-col gap-3">
                        {recentRuns.map(run => (
                            <RunRow key={run.id} run={run} />
                        ))}
                    </div>
                </section>
            )}
        </div>
    );
}