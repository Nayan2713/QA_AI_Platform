import React, { useState, useRef } from 'react';
import { createPortal } from 'react-dom';
import api from '../lib/api';

interface BulkUploadModalProps {
  appId: number;
  onClose: () => void;
  onSuccess: () => void;
}

interface ParsedTestCase {
  title: string;
  category: string;
  expected_result: string;
  steps: any[];
  ai_generated?: boolean;
  selected?: boolean;
}

export const BulkUploadModal: React.FC<BulkUploadModalProps> = ({ appId, onClose, onSuccess }) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [modelChoice, setModelChoice] = useState('auto');
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const [successMsg, setSuccessMsg] = useState('');

  // Preview data
  const [columns, setColumns] = useState<string[]>([]);
  const [formatType, setFormatType] = useState<string>('');
  const [parsedCases, setParsedCases] = useState<ParsedTestCase[]>([]);
  const [hasPreviewed, setHasPreviewed] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = (file: File) => {
    const ext = file.name.toLowerCase().split('.').pop();
    if (!['csv', 'xlsx', 'xls', 'pdf'].includes(ext || '')) {
      setError('Unsupported file type. Please select a .csv, .xlsx, .xls, or .pdf file.');
      setSelectedFile(null);
      return;
    }
    setError('');
    setSelectedFile(file);
    setHasPreviewed(false);
    setParsedCases([]);
    setColumns([]);
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  };

  const handlePreview = async () => {
    if (!selectedFile) {
      setError('Please select a file to upload first.');
      return;
    }

    setLoading(true);
    setError('');
    const formData = new FormData();
    formData.append('app_id', String(appId));
    formData.append('file', selectedFile);
    formData.append('model_choice', modelChoice);
    formData.append('preview', 'true');

    try {
      const res = await api.post('test-cases/bulk_upload/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      const data = res.data;
      setColumns(data.columns || []);
      setFormatType(data.format_type || '');
      const casesWithSelect = (data.test_cases || []).map((tc: any) => ({
        ...tc,
        selected: true
      }));
      setParsedCases(casesWithSelect);
      setHasPreviewed(true);

      if (casesWithSelect.length === 0) {
        setError('No test cases could be parsed from the file.');
      }
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.error || 'Failed to parse file. Please check file format.');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleSelectAll = (checked: boolean) => {
    setParsedCases(parsedCases.map(c => ({ ...c, selected: checked })));
  };

  const handleToggleSelectCase = (index: number) => {
    setParsedCases(parsedCases.map((c, i) => i === index ? { ...c, selected: !c.selected } : c));
  };

  const handleCommitImport = async () => {
    const selectedCases = parsedCases.filter(c => c.selected);
    if (selectedCases.length === 0) {
      setError('Please select at least one test case to import.');
      return;
    }

    setImporting(true);
    setError('');
    try {
      const res = await api.post('test-cases/bulk_upload/', {
        app_id: appId,
        test_cases: selectedCases
      });

      setSuccessMsg(`Successfully imported ${res.data.created_count || selectedCases.length} test cases!`);
      setTimeout(() => {
        onSuccess();
        onClose();
      }, 1200);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.error || 'Failed to import test cases.');
    } finally {
      setImporting(false);
    }
  };

  const handleDirectImport = async () => {
    if (!selectedFile) return;
    setLoading(true);
    setError('');
    const formData = new FormData();
    formData.append('app_id', String(appId));
    formData.append('file', selectedFile);
    formData.append('model_choice', modelChoice);
    formData.append('preview', 'false');

    try {
      const res = await api.post('test-cases/bulk_upload/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setSuccessMsg(`Successfully imported ${res.data.created_count} test cases!`);
      setTimeout(() => {
        onSuccess();
        onClose();
      }, 1200);
    } catch (err: any) {
      console.error(err);
      setError(err.response?.data?.error || 'Failed to import test cases.');
    } finally {
      setLoading(false);
    }
  };

  const selectedCount = parsedCases.filter(c => c.selected).length;

  return createPortal(
    <div className="modal-backdrop" style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      backgroundColor: 'rgba(5, 5, 12, 0.82)',
      backdropFilter: 'blur(8px)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: '20px'
    }}>
      <div className="glass-card animate-slide-up" style={{
        width: '100%',
        maxWidth: '820px',
        maxHeight: '90vh',
        overflowY: 'auto',
        borderRadius: '16px',
        padding: '28px',
        boxShadow: '0 20px 50px rgba(0, 0, 0, 0.6)',
        border: '1px solid rgba(255, 255, 255, 0.12)',
        backgroundColor: '#0f172a'
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 700, color: '#f8fafc', display: 'flex', alignItems: 'center', gap: '8px' }}>
              📁 Bulk Upload Test Cases
            </h3>
            <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: '#94a3b8' }}>
              Upload CSV, Excel, or PDF files. Column headers and steps will be automatically mapped.
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              fontSize: '1.4rem',
              cursor: 'pointer',
              padding: '4px 8px'
            }}
          >
            ✕
          </button>
        </div>

        {error && (
          <div style={{
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            color: '#fca5a5',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            padding: '10px 14px',
            borderRadius: '8px',
            marginBottom: '16px',
            fontSize: '0.85rem'
          }}>
            ⚠️ {error}
          </div>
        )}

        {successMsg && (
          <div style={{
            backgroundColor: 'rgba(16, 185, 129, 0.15)',
            color: '#6ee7b7',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            padding: '10px 14px',
            borderRadius: '8px',
            marginBottom: '16px',
            fontSize: '0.85rem'
          }}>
            ✅ {successMsg}
          </div>
        )}

        {/* Drop zone & Config */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '16px', marginBottom: '20px' }}>
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: `2px dashed ${isDragOver ? '#3b82f6' : selectedFile ? '#10b981' : 'rgba(255, 255, 255, 0.2)'}`,
              borderRadius: '12px',
              padding: '32px 20px',
              textAlign: 'center',
              backgroundColor: isDragOver ? 'rgba(59, 130, 246, 0.08)' : selectedFile ? 'rgba(16, 185, 129, 0.05)' : 'rgba(15, 23, 42, 0.6)',
              cursor: 'pointer',
              transition: 'all 0.2s'
            }}
          >
            <input
              type="file"
              ref={fileInputRef}
              onChange={(e) => e.target.files?.[0] && handleFileSelect(e.target.files[0])}
              accept=".csv,.xlsx,.xls,.pdf"
              style={{ display: 'none' }}
            />
            {selectedFile ? (
              <div>
                <div style={{ fontSize: '2rem', marginBottom: '8px' }}>
                  {selectedFile.name.endsWith('.pdf') ? '📄' : selectedFile.name.endsWith('.csv') ? '📊' : '📈'}
                </div>
                <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '1rem' }}>
                  {selectedFile.name}
                </div>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '4px' }}>
                  {(selectedFile.size / 1024).toFixed(1)} KB • Click or drag to change file
                </div>
              </div>
            ) : (
              <div>
                <div style={{ fontSize: '2.2rem', marginBottom: '8px' }}>📤</div>
                <div style={{ fontWeight: 600, color: '#f8fafc', fontSize: '0.95rem' }}>
                  Drag & Drop your CSV, Excel, or PDF file here
                </div>
                <div style={{ fontSize: '0.8rem', color: '#94a3b8', marginTop: '4px' }}>
                  Supports .csv, .xlsx, .xls, .pdf files with columns like Title, Steps, Expected Result
                </div>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <label style={{ fontSize: '0.85rem', color: '#94a3b8', fontWeight: 600, whiteSpace: 'nowrap' }}>
              AI Router Model:
            </label>
            <select
              value={modelChoice}
              onChange={(e) => setModelChoice(e.target.value)}
              style={{
                flex: 1,
                backgroundColor: 'rgba(15, 23, 42, 0.8)',
                color: '#ffffff',
                border: '1px solid rgba(255, 255, 255, 0.15)',
                padding: '8px 12px',
                borderRadius: '8px',
                fontSize: '0.85rem',
                outline: 'none'
              }}
            >
              <option value="auto">Auto-Select LLM Router</option>
              <option value="ollama_qwen">Ollama / Qwen (Local)</option>
              <option value="ollama_groq">Ollama / Groq (Local)</option>
              <option value="openai">ChatGPT / OpenAI (Cloud)</option>
            </select>

            <button
              type="button"
              onClick={handlePreview}
              disabled={!selectedFile || loading}
              style={{
                backgroundColor: 'rgba(59, 130, 246, 0.2)',
                color: '#60a5fa',
                border: '1px solid rgba(59, 130, 246, 0.4)',
                padding: '8px 16px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.85rem'
              }}
            >
              {loading ? 'Analyzing File...' : '🔍 Preview & Inspect'}
            </button>
          </div>
        </div>

        {/* Column Badges & Preview Table */}
        {hasPreviewed && (
          <div style={{ marginTop: '20px', borderTop: '1px solid rgba(255, 255, 255, 0.1)', paddingTop: '16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
                <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>DETECTED COLUMNS:</span>
                {columns.map(col => (
                  <span key={col} style={{
                    fontSize: '0.75rem',
                    padding: '2px 8px',
                    borderRadius: '12px',
                    backgroundColor: 'rgba(99, 102, 241, 0.2)',
                    color: '#a5b4fc',
                    border: '1px solid rgba(99, 102, 241, 0.3)'
                  }}>
                    {col}
                  </span>
                ))}
              </div>
              <div style={{ fontSize: '0.82rem', color: '#94a3b8' }}>
                Found <strong style={{ color: '#f8fafc' }}>{parsedCases.length}</strong> test scenarios
              </div>
            </div>

            {/* Table */}
            <div style={{
              maxHeight: '280px',
              overflowY: 'auto',
              borderRadius: '8px',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              marginBottom: '20px'
            }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem', textAlign: 'left' }}>
                <thead style={{ backgroundColor: 'rgba(30, 41, 59, 0.9)', position: 'sticky', top: 0, zIndex: 2 }}>
                  <tr>
                    <th style={{ padding: '10px 12px', width: '36px' }}>
                      <input
                        type="checkbox"
                        checked={parsedCases.length > 0 && selectedCount === parsedCases.length}
                        onChange={(e) => handleToggleSelectAll(e.target.checked)}
                      />
                    </th>
                    <th style={{ padding: '10px 12px', color: '#cbd5e1' }}>Title</th>
                    <th style={{ padding: '10px 12px', color: '#cbd5e1', width: '110px' }}>Category</th>
                    <th style={{ padding: '10px 12px', color: '#cbd5e1', width: '90px' }}>Steps</th>
                    <th style={{ padding: '10px 12px', color: '#cbd5e1' }}>Expected Result</th>
                  </tr>
                </thead>
                <tbody>
                  {parsedCases.map((tc, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.05)', backgroundColor: tc.selected ? 'rgba(59, 130, 246, 0.05)' : 'transparent' }}>
                      <td style={{ padding: '10px 12px' }}>
                        <input
                          type="checkbox"
                          checked={!!tc.selected}
                          onChange={() => handleToggleSelectCase(i)}
                        />
                      </td>
                      <td style={{ padding: '10px 12px', fontWeight: 600, color: '#f8fafc' }}>{tc.title}</td>
                      <td style={{ padding: '10px 12px' }}>
                        <span style={{
                          fontSize: '0.7rem',
                          padding: '2px 6px',
                          borderRadius: '4px',
                          backgroundColor: 'rgba(59, 130, 246, 0.15)',
                          color: '#93c5fd'
                        }}>
                          {tc.category}
                        </span>
                      </td>
                      <td style={{ padding: '10px 12px', color: '#cbd5e1' }}>
                        {tc.steps?.length || 0} step(s)
                      </td>
                      <td style={{ padding: '10px 12px', color: '#94a3b8' }}>
                        {tc.expected_result}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '10px' }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              backgroundColor: 'rgba(255, 255, 255, 0.05)',
              color: '#cbd5e1',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              padding: '9px 18px',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.85rem'
            }}
          >
            Cancel
          </button>

          {hasPreviewed ? (
            <button
              type="button"
              onClick={handleCommitImport}
              disabled={importing || selectedCount === 0}
              style={{
                backgroundColor: '#3b82f6',
                color: '#ffffff',
                border: 'none',
                padding: '9px 20px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              {importing ? (
                <>
                  <div className="spinner-small"></div>
                  <span>Importing...</span>
                </>
              ) : (
                `📥 Import Selected (${selectedCount})`
              )}
            </button>
          ) : (
            <button
              type="button"
              onClick={handleDirectImport}
              disabled={!selectedFile || loading}
              style={{
                backgroundColor: '#3b82f6',
                color: '#ffffff',
                border: 'none',
                padding: '9px 20px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.85rem',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              {loading ? (
                <>
                  <div className="spinner-small"></div>
                  <span>Uploading...</span>
                </>
              ) : (
                '🚀 Direct Import'
              )}
            </button>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
};
