import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Eye, RefreshCw, CheckCircle, XCircle, AlertCircle, Trash2 } from 'lucide-react';
import { getVisualBaselines, getVisualDiffs, runVisualRegression, resetVisualBaseline } from '../lib/api';
import { VisualBaseline, VisualDiff } from '../lib/types';

interface Props {
    appId: number;
    latestTestRunId?: number;
}

const MEDIA_URL = (import.meta as any).env.VITE_MEDIA_URL || '/media/';

function statusBadge(status: VisualDiff['status']) {
    if (status === 'PASSED') return (
        <span className="flex items-center gap-1 text-green-400 text-xs font-semibold">
            <CheckCircle size={13} /> Passed
        </span>
    );
    if (status === 'FAILED') return (
        <span className="flex items-center gap-1 text-red-400 text-xs font-semibold">
            <XCircle size={13} /> Failed
        </span>
    );
    return (
        <span className="flex items-center gap-1 text-yellow-400 text-xs font-semibold">
            <AlertCircle size={13} /> No Baseline
        </span>
    );
}

export default function VisualRegression({ appId, latestTestRunId }: Props) {
    const qc = useQueryClient();
    const [selectedDiffRunId, setSelectedDiffRunId] = useState<number | undefined>(latestTestRunId);
    const [expandedDiff, setExpandedDiff] = useState<number | null>(null);

    const { data: baselines = [], isLoading: loadingBaselines } = useQuery({
        queryKey: ['visual-baselines', appId],
        queryFn: () => getVisualBaselines(appId),
    });

    const { data: diffs = [], isLoading: loadingDiffs } = useQuery({
        queryKey: ['visual-diffs', selectedDiffRunId],
        queryFn: () => selectedDiffRunId ? getVisualDiffs(selectedDiffRunId) : Promise.resolve([]),
        enabled: !!selectedDiffRunId,
    });

    const runMutation = useMutation({
        mutationFn: () => runVisualRegression(appId, selectedDiffRunId),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['visual-diffs'] });
        },
    });

    const resetMutation = useMutation({
        mutationFn: (baselineId: number) => resetVisualBaseline(baselineId),
        onSuccess: () => {
            qc.invalidateQueries({ queryKey: ['visual-baselines', appId] });
        },
    });

    const failedDiffs = diffs.filter(d => d.status === 'FAILED');
    const passedDiffs = diffs.filter(d => d.status === 'PASSED');

    return (
        <div className="space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Eye size={18} className="text-purple-400" />
                    <h2 className="text-white font-semibold text-lg">Visual Regression</h2>
                </div>
                <button
                    onClick={() => runMutation.mutate()}
                    disabled={runMutation.isPending}
                    className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg transition-colors"
                >
                    <RefreshCw size={14} className={runMutation.isPending ? 'animate-spin' : ''} />
                    {runMutation.isPending ? 'Checking…' : 'Run Visual Check'}
                </button>
            </div>

            {/* Error banner */}
            {runMutation.isError && (
                <div className="bg-red-950/40 border border-red-800 rounded-xl p-4 flex items-center justify-between text-red-300 text-sm">
                    <div className="flex items-center gap-2">
                        <AlertCircle size={16} className="text-red-400 shrink-0" />
                        <span>
                            {(runMutation.error as any)?.response?.data?.error ||
                             (runMutation.error as any)?.response?.data?.detail ||
                             'Failed to run visual check. Please ensure a test run exists.'}
                        </span>
                    </div>
                    <button
                        onClick={() => runMutation.reset()}
                        className="text-xs text-red-400 hover:text-red-300 underline ml-4"
                    >
                        Dismiss
                    </button>
                </div>
            )}

            {/* Summary cards */}
            {diffs.length > 0 && (
                <div className="grid grid-cols-3 gap-4">
                    <div className="bg-zinc-800 rounded-xl p-4 border border-zinc-700">
                        <p className="text-zinc-400 text-xs mb-1">Steps Checked</p>
                        <p className="text-white text-2xl font-bold">{diffs.length}</p>
                    </div>
                    <div className="bg-zinc-800 rounded-xl p-4 border border-zinc-700">
                        <p className="text-green-400 text-xs mb-1">Passed</p>
                        <p className="text-white text-2xl font-bold">{passedDiffs.length}</p>
                    </div>
                    <div className="bg-zinc-800 rounded-xl p-4 border border-zinc-700">
                        <p className="text-red-400 text-xs mb-1">Regressions</p>
                        <p className="text-white text-2xl font-bold">{failedDiffs.length}</p>
                    </div>
                </div>
            )}

            {/* Diff results */}
            {loadingDiffs ? (
                <p className="text-zinc-500 text-sm">Loading diffs…</p>
            ) : diffs.length > 0 ? (
                <div className="space-y-3">
                    <h3 className="text-zinc-300 text-sm font-medium">Step Results</h3>
                    {diffs.map(diff => (
                        <div
                            key={diff.id}
                            className={`rounded-xl border p-4 transition-colors cursor-pointer
                ${diff.status === 'FAILED' ? 'border-red-700 bg-red-950/20' :
                                    diff.status === 'PASSED' ? 'border-zinc-700 bg-zinc-800' :
                                        'border-yellow-700 bg-yellow-950/20'}`}
                            onClick={() => setExpandedDiff(expandedDiff === diff.id ? null : diff.id)}
                        >
                            <div className="flex items-center justify-between">
                                <div className="flex items-center gap-3">
                                    {statusBadge(diff.status)}
                                    <span className="text-zinc-300 text-sm">Step {diff.step_number}</span>
                                    {diff.status === 'FAILED' && (
                                        <span className="text-red-300 text-xs bg-red-900/40 px-2 py-0.5 rounded">
                                            {diff.diff_percentage.toFixed(1)}% changed
                                        </span>
                                    )}
                                </div>
                                <span className="text-zinc-600 text-xs">{new Date(diff.created_at).toLocaleTimeString()}</span>
                            </div>

                            {/* Expanded diff image */}
                            {expandedDiff === diff.id && diff.diff_screenshot_path && (
                                <div className="mt-4">
                                    <p className="text-zinc-400 text-xs mb-2">Pixel diff (white = changed pixels)</p>
                                    <img
                                        src={`${MEDIA_URL}${diff.diff_screenshot_path}`}
                                        alt="Visual diff"
                                        className="rounded-lg border border-zinc-600 max-w-full"
                                    />
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            ) : selectedDiffRunId ? (
                <p className="text-zinc-500 text-sm">No visual diff data yet. Click "Run Visual Check" to compare screenshots.</p>
            ) : (
                <p className="text-zinc-500 text-sm">Select a test run above to view visual diffs.</p>
            )}

            {/* Baselines */}
            <div>
                <h3 className="text-zinc-300 text-sm font-medium mb-3">
                    Stored Baselines ({baselines.length})
                </h3>
                {loadingBaselines ? (
                    <p className="text-zinc-500 text-sm">Loading…</p>
                ) : baselines.length === 0 ? (
                    <p className="text-zinc-500 text-sm">No baselines yet. Run a test to create the first baseline.</p>
                ) : (
                    <div className="space-y-2">
                        {baselines.map((b: VisualBaseline) => (
                            <div key={b.id} className="flex items-center justify-between bg-zinc-800 rounded-lg px-4 py-3 border border-zinc-700">
                                <div>
                                    <p className="text-zinc-200 text-sm">Page {b.page} · Step {b.step_number}</p>
                                    <p className="text-zinc-500 text-xs">{b.width}×{b.height} · Updated {new Date(b.updated_at).toLocaleDateString()}</p>
                                </div>
                                <button
                                    onClick={() => resetMutation.mutate(b.id)}
                                    disabled={resetMutation.isPending}
                                    title="Reset baseline"
                                    className="text-zinc-500 hover:text-red-400 transition-colors p-1"
                                >
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}