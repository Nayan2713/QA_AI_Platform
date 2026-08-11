import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Zap, Play, RefreshCw, CheckCircle, XCircle, Clock, ChevronDown, ChevronRight, Trash2 } from 'lucide-react';
import { getAPITestCases, getAPITestRuns, generateAndRunAPITests, runSingleAPITest, deleteAPITestCase } from '../lib/api';
import { APITestCase, APITestRun } from '../lib/types';

interface Props {
    appId: number;
}

const METHOD_COLORS: Record<string, string> = {
    GET: 'text-green-400 bg-green-900/30 border-green-700',
    POST: 'text-blue-400 bg-blue-900/30 border-blue-700',
    PUT: 'text-yellow-400 bg-yellow-900/30 border-yellow-700',
    PATCH: 'text-orange-400 bg-orange-900/30 border-orange-700',
    DELETE: 'text-red-400 bg-red-900/30 border-red-700',
};

function MethodBadge({ method }: { method: string }) {
    const cls = METHOD_COLORS[method] || 'text-zinc-400 bg-zinc-800 border-zinc-600';
    return (
        <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded border ${cls}`}>
            {method}
        </span>
    );
}

function StatusCodeBadge({ code }: { code: number | null }) {
    if (code === null) return <span className="text-zinc-500 text-xs">—</span>;
    const color = code < 300 ? 'text-green-400' : code < 400 ? 'text-yellow-400' : 'text-red-400';
    return <span className={`text-xs font-mono font-bold ${color}`}>{code}</span>;
}

function RunRow({ run }: { run: APITestRun }) {
    const [open, setOpen] = useState(false);
    return (
        <div className={`rounded-lg border ${run.passed ? 'border-zinc-700 bg-zinc-800/50' : 'border-red-800 bg-red-950/20'}`}>
            <div
                className="flex items-center justify-between px-4 py-3 cursor-pointer"
                onClick={() => setOpen(!open)}
            >
                <div className="flex items-center gap-3">
                    {run.passed
                        ? <CheckCircle size={14} className="text-green-400 shrink-0" />
                        : <XCircle size={14} className="text-red-400 shrink-0" />}
                    <StatusCodeBadge code={run.actual_status_code} />
                    {run.response_time_ms !== null && (
                        <span className="flex items-center gap-1 text-zinc-500 text-xs">
                            <Clock size={11} /> {run.response_time_ms.toFixed(0)}ms
                        </span>
                    )}
                    {!run.passed && run.failure_reason && (
                        <span className="text-red-300 text-xs truncate max-w-xs">{run.failure_reason}</span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-zinc-600 text-xs">{new Date(run.created_at).toLocaleTimeString()}</span>
                    {open ? <ChevronDown size={13} className="text-zinc-500" /> : <ChevronRight size={13} className="text-zinc-500" />}
                </div>
            </div>
            {open && (
                <div className="px-4 pb-4 border-t border-zinc-700 mt-1 pt-3">
                    {run.error && <p className="text-red-300 text-xs mb-2 font-mono">{run.error}</p>}
                    {run.failure_reason && !run.error && (
                        <p className="text-red-300 text-xs mb-2">{run.failure_reason}</p>
                    )}
                    {run.response_body && (
                        <>
                            <p className="text-zinc-500 text-xs mb-1">Response body (first 2 KB)</p>
                            <pre className="text-xs text-zinc-300 bg-zinc-900 rounded p-3 overflow-auto max-h-40 font-mono">
                                {(() => {
                                    try { return JSON.stringify(JSON.parse(run.response_body), null, 2); }
                                    catch { return run.response_body; }
                                })()}
                            </pre>
                        </>
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
        <div className="bg-zinc-800 rounded-xl border border-zinc-700 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3">
                <div
                    className="flex items-center gap-3 flex-1 cursor-pointer min-w-0"
                    onClick={() => setOpen(!open)}
                >
                    <MethodBadge method={tc.method} />
                    <div className="min-w-0">
                        <p className="text-zinc-200 text-sm font-medium truncate">{tc.title}</p>
                        <p className="text-zinc-500 text-xs font-mono truncate">{tc.url}</p>
                    </div>
                    {tc.ai_generated && (
                        <span className="text-xs text-purple-400 bg-purple-900/30 border border-purple-700 px-2 py-0.5 rounded shrink-0">AI</span>
                    )}
                    {tc.auth_required && (
                        <span className="text-xs text-yellow-400 bg-yellow-900/30 border border-yellow-700 px-2 py-0.5 rounded shrink-0">Auth</span>
                    )}
                </div>
                <div className="flex items-center gap-2 ml-3">
                    <button
                        onClick={() => runMutation.mutate()}
                        disabled={runMutation.isPending}
                        className="flex items-center gap-1 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
                    >
                        <Play size={11} className={runMutation.isPending ? 'animate-pulse' : ''} />
                        {runMutation.isPending ? 'Running…' : 'Run'}
                    </button>
                    <button
                        onClick={() => deleteMutation.mutate()}
                        disabled={deleteMutation.isPending}
                        className="text-zinc-500 hover:text-red-400 transition-colors p-1"
                        title="Delete"
                    >
                        <Trash2 size={13} />
                    </button>
                </div>
            </div>

            {open && (
                <div className="px-4 pb-4 border-t border-zinc-700 pt-3 space-y-3 text-xs">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <p className="text-zinc-500 mb-1">Expected status</p>
                            <StatusCodeBadge code={tc.expected_status} />
                        </div>
                        {tc.expected_body_contains.length > 0 && (
                            <div>
                                <p className="text-zinc-500 mb-1">Assert keys in response</p>
                                <div className="flex flex-wrap gap-1">
                                    {tc.expected_body_contains.map(k => (
                                        <span key={k} className="bg-zinc-700 text-zinc-300 px-2 py-0.5 rounded font-mono">{k}</span>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                    {Object.keys(tc.body).length > 0 && (
                        <div>
                            <p className="text-zinc-500 mb-1">Request body</p>
                            <pre className="bg-zinc-900 rounded p-2 text-zinc-300 overflow-auto font-mono">
                                {JSON.stringify(tc.body, null, 2)}
                            </pre>
                        </div>
                    )}
                    {runMutation.data && (
                        <div className="mt-2">
                            <p className="text-zinc-500 mb-1">Latest result</p>
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

    const recentRuns = runs.slice(0, 20);
    const passRate = runs.length > 0
        ? Math.round((runs.filter(r => r.passed).length / runs.length) * 100)
        : null;

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Zap size={18} className="text-blue-400" />
                    <h2 className="text-white font-semibold text-lg">API Testing</h2>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => runAllMutation.mutate()}
                        disabled={runAllMutation.isPending || testCases.length === 0}
                        className="flex items-center gap-2 bg-zinc-700 hover:bg-zinc-600 disabled:opacity-40 text-white text-sm px-4 py-2 rounded-lg transition-colors"
                    >
                        <Play size={13} />
                        Run All
                    </button>
                    <button
                        onClick={() => generateMutation.mutate()}
                        disabled={generateMutation.isPending}
                        className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors"
                    >
                        <RefreshCw size={13} className={generateMutation.isPending ? 'animate-spin' : ''} />
                        {generateMutation.isPending ? 'Generating…' : 'Generate & Run'}
                    </button>
                </div>
            </div>

            {/* Summary */}
            {runs.length > 0 && (
                <div className="grid grid-cols-3 gap-4">
                    <div className="bg-zinc-800 rounded-xl p-4 border border-zinc-700">
                        <p className="text-zinc-400 text-xs mb-1">Test Cases</p>
                        <p className="text-white text-2xl font-bold">{testCases.length}</p>
                    </div>
                    <div className="bg-zinc-800 rounded-xl p-4 border border-zinc-700">
                        <p className="text-zinc-400 text-xs mb-1">Total Runs</p>
                        <p className="text-white text-2xl font-bold">{runs.length}</p>
                    </div>
                    <div className="bg-zinc-800 rounded-xl p-4 border border-zinc-700">
                        <p className="text-zinc-400 text-xs mb-1">Pass Rate</p>
                        <p className={`text-2xl font-bold ${passRate !== null && passRate >= 80 ? 'text-green-400' : 'text-red-400'}`}>
                            {passRate !== null ? `${passRate}%` : '—'}
                        </p>
                    </div>
                </div>
            )}

            {/* Test Cases */}
            <div>
                <h3 className="text-zinc-300 text-sm font-medium mb-3">
                    Test Cases ({testCases.length})
                </h3>
                {loadingCases ? (
                    <p className="text-zinc-500 text-sm">Loading…</p>
                ) : testCases.length === 0 ? (
                    <div className="text-center py-10 bg-zinc-800/50 rounded-xl border border-zinc-700 border-dashed">
                        <Zap size={24} className="text-zinc-600 mx-auto mb-2" />
                        <p className="text-zinc-400 text-sm">No API test cases yet.</p>
                        <p className="text-zinc-600 text-xs mt-1">Click "Generate & Run" to create tests from your discovered endpoints.</p>
                    </div>
                ) : (
                    <div className="space-y-3">
                        {testCases.map(tc => (
                            <TestCaseCard key={tc.id} tc={tc} appId={appId} />
                        ))}
                    </div>
                )}
            </div>

            {/* Recent Runs */}
            {recentRuns.length > 0 && (
                <div>
                    <h3 className="text-zinc-300 text-sm font-medium mb-3">Recent Runs</h3>
                    <div className="space-y-2">
                        {recentRuns.map(run => (
                            <RunRow key={run.id} run={run} />
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}