/**
 * Web Audio API Notification Chime Generator & Autoplay Unlocker.
 * Synthesizes a clean, pleasant notification chime in browser without external audio files.
 * Automatically unlocks AudioContext on first user gesture.
 */

let sharedAudioCtx: AudioContext | null = null;

const getAudioContext = (): AudioContext | null => {
  if (typeof window === 'undefined') return null;
  const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
  if (!AudioCtx) return null;

  if (!sharedAudioCtx || sharedAudioCtx.state === 'closed') {
    sharedAudioCtx = new AudioCtx();
  }
  return sharedAudioCtx;
};

/**
 * Attaches a one-time global user interaction listener to unlock AudioContext
 * so modern browsers allow notification chimes to play asynchronously.
 */
export const initAudioUnlock = () => {
  const unlock = () => {
    const ctx = getAudioContext();
    if (ctx && ctx.state === 'suspended') {
      ctx.resume().then(() => {
        console.log('[Audio] Notification audio context unlocked successfully.');
      }).catch(err => console.warn('[Audio] Unlock failed:', err));
    }
  };

  if (typeof window !== 'undefined') {
    window.addEventListener('click', unlock, { once: true });
    window.addEventListener('keydown', unlock, { once: true });
    window.addEventListener('touchstart', unlock, { once: true });
  }
};

/**
 * Plays a synthesized audio chime when a notification arrives.
 */
export const playNotificationSound = (level: string = 'info') => {
  try {
    const ctx = getAudioContext();
    if (!ctx) return;

    if (ctx.state === 'suspended') {
      ctx.resume();
    }

    const now = ctx.currentTime;
    const isError = level === 'error';
    const isWarning = level === 'warning';

    // Frequencies: High harmonic chime for success/info, lower alert tone for error
    const freq1 = isError ? 440 : (isWarning ? 523.25 : 587.33); // A4 / C5 / D5
    const freq2 = isError ? 349.23 : (isWarning ? 659.25 : 880);   // F4 / E5 / A5

    // Tone 1
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(freq1, now);
    gain1.gain.setValueAtTime(0.25, now);
    gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.3);

    osc1.connect(gain1);
    gain1.connect(ctx.destination);

    // Tone 2 (Harmonic secondary chime)
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(freq2, now + 0.08);
    gain2.gain.setValueAtTime(0.25, now + 0.08);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 0.5);

    osc2.connect(gain2);
    gain2.connect(ctx.destination);

    osc1.start(now);
    osc1.stop(now + 0.3);

    osc2.start(now + 0.08);
    osc2.stop(now + 0.5);
  } catch (err) {
    console.warn("Notification audio play failed:", err);
  }
};
