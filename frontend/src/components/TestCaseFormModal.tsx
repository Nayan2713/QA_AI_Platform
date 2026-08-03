import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import { TestCase, TestStep } from '../lib/types';
import api from '../lib/api';

interface TestCaseFormModalProps {
  appId: number;
  testCase?: TestCase | null; // If null, we are creating
  onClose: () => void;
  onSuccess: () => void;
}

const ACTION_OPTIONS = [
  'navigate', 'fill', 'click', 'wait', 'assert', 'hover', 'scroll', 'select', 'screenshot'
] as const;

export const TestCaseFormModal: React.FC<TestCaseFormModalProps> = ({ appId, testCase, onClose, onSuccess }) => {
  const [title, setTitle] = useState(testCase?.title || '');
  const [category, setCategory] = useState(testCase?.category || 'Generic');
  const [expectedResult, setExpectedResult] = useState(testCase?.expected_result || '');
  const [steps, setSteps] = useState<TestStep[]>(testCase?.steps && testCase.steps.length > 0 ? testCase.steps : [{ action: 'navigate', selector: '', target: '', value: '' }]);
  
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState('');
  const [modelChoice, setModelChoice] = useState('auto');
  const [aiGenerated, setAiGenerated] = useState(testCase?.ai_generated || false);
  const [generatedModel, setGeneratedModel] = useState<string | null>(testCase?.model_used || null);

  const isEdit = !!testCase;

  const handleAddStep = () => {
    setSteps([...steps, { action: 'click', selector: '', target: '', value: '' }]);
  };

  const handleRemoveStep = (index: number) => {
    setSteps(steps.filter((_, i) => i !== index));
  };

  const handleStepChange = (index: number, field: keyof TestStep, value: string) => {
    const newSteps = [...steps];
    newSteps[index] = { ...newSteps[index], [field]: value };
    setSteps(newSteps);
  };

  const handleGenerateAI = async () => {
    if (!title.trim()) {
      setError('Please enter a Title first so the AI knows what test case to generate.');
      return;
    }
    
    setGenerating(true);
    setError('');
    
    try {
      const res = await api.post('test-cases/generate_single/', {
        app_id: appId,
        title: title,
        model_choice: modelChoice
      });
      
      const generated = res.data;
      if (generated.category) setCategory(generated.category);
      if (generated.expected_result) setExpectedResult(generated.expected_result);
      if (generated.steps && generated.steps.length > 0) setSteps(generated.steps);
      setAiGenerated(true);
      setGeneratedModel(generated.model_used || modelChoice);
    } catch (err: any) {
      console.error(err);
      setError('Failed to generate test case via AI. Ensure the backend LLM service is running.');
    } finally {
      setGenerating(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!title.trim() || !expectedResult.trim() || steps.length === 0) {
      setError('Title, expected result, and at least one step are required.');
      return;
    }

    setSaving(true);
    try {
      const payload = {
        app: appId,
        title,
        category,
        expected_result: expectedResult,
        steps: steps,
        ai_generated: aiGenerated,
        generation_context: { model_used: generatedModel || (aiGenerated ? modelChoice : 'Manual') },
      };

      if (isEdit) {
        await api.patch(`test-cases/${testCase.id}/`, payload);
      } else {
        await api.post('test-cases/', payload);
      }
      onSuccess();
    } catch (err: any) {
      console.error(err);
      const responseData = err.response?.data?.data || err.response?.data;
      if (responseData && typeof responseData === 'object') {
        const errors = Object.entries(responseData).map(([k, v]) => {
          if (Array.isArray(v)) {
            return `${k}: ${v.join(', ')}`;
          }
          return `${k}: ${v}`;
        });
        setError(`Validation Error: ${errors.join(' | ')}`);
      } else {
        setError(`Failed to ${isEdit ? 'update' : 'create'} test case.`);
      }
    } finally {
      setSaving(false);
    }
  };

  return createPortal(
    <div className="modal-overlay" style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      backgroundColor: 'rgba(7, 5, 18, 0.75)',
      backdropFilter: 'blur(12px)',
      WebkitBackdropFilter: 'blur(12px)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      paddingTop: '60px', paddingBottom: '40px', zIndex: 10000, overflowY: 'auto'
    }}>
      <div className="modal-content glass-card" style={{
        width: '90%', maxWidth: '800px', maxHeight: '85vh',
        overflowY: 'auto', padding: '24px'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0 }}>{isEdit ? '✏️ Edit Test Case' : '➕ Create Manual Test Case'}</h3>
          <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', fontSize: '1.2rem' }}>✕</button>
        </div>

        {error && <div className="error-alert" style={{ marginBottom: '16px' }}>{error}</div>}

        <form onSubmit={handleSubmit}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-end' }}>
              <div style={{ flex: 2 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '6px' }}>Title</label>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input 
                    type="text" 
                    value={title} 
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="e.g., Verify Login Flow"
                    style={{
                      flex: 1, padding: '10px', backgroundColor: 'rgba(15, 23, 42, 0.5)',
                      border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '6px', color: '#f8fafc'
                    }}
                    required
                  />
                  <select
                    value={modelChoice}
                    onChange={(e) => setModelChoice(e.target.value)}
                    style={{
                      backgroundColor: 'rgba(15, 23, 42, 0.8)',
                      color: '#cbd5e1',
                      border: '1px solid rgba(255, 255, 255, 0.1)',
                      padding: '10px 8px',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      outline: 'none',
                    }}
                  >
                    <option value="auto">Auto-Select LLM</option>
                    <option value="ollama_qwen">Ollama / Qwen (Local)</option>
                    <option value="ollama_groq">Ollama / Groq (Local)</option>
                    <option value="openai">ChatGPT / OpenAI (Cloud)</option>
                  </select>
                  <button 
                    type="button" 
                    onClick={handleGenerateAI}
                    disabled={generating}
                    style={{
                      backgroundColor: 'rgba(139, 92, 246, 0.15)',
                      color: '#a78bfa',
                      border: '1px solid rgba(139, 92, 246, 0.3)',
                      padding: '10px 14px',
                      borderRadius: '6px',
                      cursor: generating ? 'not-allowed' : 'pointer',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      whiteSpace: 'nowrap',
                      opacity: generating ? 0.7 : 1
                    }}
                  >
                    {generating ? '⏳ Generating...' : '✨ Auto-Fill with AI'}
                  </button>
                </div>
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '6px' }}>Category</label>
                <select 
                  value={category} 
                  onChange={(e) => setCategory(e.target.value as any)}
                  style={{
                    width: '100%', padding: '10px', backgroundColor: 'rgba(15, 23, 42, 0.5)',
                    border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '6px', color: '#f8fafc'
                  }}
                >
                  <option value="Generic">Generic</option>
                  <option value="Industry Flow">Industry Flow</option>
                  <option value="Access Control">Access Control</option>
                </select>
              </div>
            </div>

            <div>
              <label style={{ display: 'block', fontSize: '0.85rem', color: '#94a3b8', marginBottom: '6px' }}>Expected Result</label>
              <textarea 
                value={expectedResult} 
                onChange={(e) => setExpectedResult(e.target.value)}
                placeholder="What should happen if the test passes?"
                style={{
                  width: '100%', padding: '10px', backgroundColor: 'rgba(15, 23, 42, 0.5)',
                  border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '6px', color: '#f8fafc',
                  minHeight: '80px', resize: 'vertical'
                }}
                required
              />
            </div>

            <div style={{ marginTop: '10px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <label style={{ display: 'block', fontSize: '0.9rem', color: '#cbd5e1', fontWeight: 600 }}>Steps</label>
                <button type="button" onClick={handleAddStep} style={{
                  backgroundColor: 'rgba(59, 130, 246, 0.2)', color: '#60a5fa', border: '1px solid rgba(59, 130, 246, 0.3)',
                  padding: '4px 10px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem'
                }}>+ Add Step</button>
              </div>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                {steps.map((step, index) => (
                  <div key={index} style={{ 
                    display: 'flex', gap: '10px', alignItems: 'center', padding: '10px', 
                    backgroundColor: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.05)', borderRadius: '6px' 
                  }}>
                    <div style={{ width: '30px', textAlign: 'center', color: '#64748b', fontSize: '0.8rem' }}>{index + 1}</div>
                    
                    <select 
                      value={step.action} 
                      onChange={(e) => handleStepChange(index, 'action', e.target.value as any)}
                      style={{
                        width: '120px', padding: '8px', backgroundColor: 'rgba(15, 23, 42, 0.8)',
                        border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '4px', color: '#f8fafc', fontSize: '0.85rem'
                      }}
                    >
                      {ACTION_OPTIONS.map(opt => <option key={opt} value={opt}>{opt.toUpperCase()}</option>)}
                    </select>

                    {/* Selector Input (Visible for most actions except navigate, wait) */}
                    {['fill', 'click', 'assert', 'hover', 'scroll', 'select'].includes(step.action) && (
                      <input 
                        type="text" 
                        value={step.selector || ''} 
                        onChange={(e) => handleStepChange(index, 'selector', e.target.value)}
                        placeholder="Selector (e.g. #login-btn)"
                        style={{
                          flex: 1, padding: '8px', backgroundColor: 'rgba(15, 23, 42, 0.5)',
                          border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '4px', color: '#f8fafc', fontSize: '0.85rem'
                        }}
                      />
                    )}

                    {/* Target Input (Only for navigate) */}
                    {['navigate'].includes(step.action) && (
                      <input 
                        type="text" 
                        value={step.target || ''} 
                        onChange={(e) => handleStepChange(index, 'target', e.target.value)}
                        placeholder="Target URL (e.g. /login)"
                        style={{
                          flex: 2, padding: '8px', backgroundColor: 'rgba(15, 23, 42, 0.5)',
                          border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '4px', color: '#f8fafc', fontSize: '0.85rem'
                        }}
                      />
                    )}

                    {/* Value Input (For fill, wait, assert, select, etc) */}
                    {['fill', 'wait', 'assert', 'select', 'scroll', 'screenshot'].includes(step.action) && (
                      <input 
                        type="text" 
                        value={step.value || ''} 
                        onChange={(e) => handleStepChange(index, 'value', e.target.value)}
                        placeholder={step.action === 'wait' ? 'Wait ms (e.g. 1000)' : 'Value'}
                        style={{
                          flex: 1, padding: '8px', backgroundColor: 'rgba(15, 23, 42, 0.5)',
                          border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '4px', color: '#f8fafc', fontSize: '0.85rem'
                        }}
                      />
                    )}

                    <button type="button" onClick={() => handleRemoveStep(index)} disabled={steps.length <= 1} style={{
                      backgroundColor: 'transparent', color: steps.length <= 1 ? '#475569' : '#ef4444', 
                      border: 'none', cursor: steps.length <= 1 ? 'not-allowed' : 'pointer', fontSize: '1.2rem', padding: '0 5px'
                    }}>✕</button>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '20px' }}>
              <button type="button" onClick={onClose} style={{
                padding: '10px 16px', backgroundColor: 'transparent', color: '#cbd5e1', 
                border: '1px solid rgba(255,255,255,0.2)', borderRadius: '6px', cursor: 'pointer'
              }}>Cancel</button>
              <button type="submit" disabled={saving} style={{
                padding: '10px 16px', backgroundColor: '#3b82f6', color: 'white', 
                border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600, opacity: saving ? 0.7 : 1
              }}>
                {saving ? 'Saving...' : (isEdit ? 'Save Changes' : 'Create Test Case')}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>,
    document.body
  );
};
