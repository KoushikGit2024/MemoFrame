import { useEffect, useState } from 'react';
import { DownloadCloud, AlertTriangle, RefreshCw, CheckCircle2 } from 'lucide-react';
import { rpc } from '../lib/api';
import { onBackendEvent } from '../lib/api';

interface ModelStatusResponse {
  ready: boolean;
  missing: string[];
  models: Record<string, { name: string; filename: string; present: boolean; size_bytes: number }>;
}

interface ModelProgressEvent {
  model: string;
  name: string;
  downloaded: number;
  total: number;
  percent: number;
  stage: string;
}

interface ModelDownloadScreenProps {
  onComplete: () => void;
}

export default function ModelDownloadScreen({ onComplete }: ModelDownloadScreenProps) {
  const [modelName, setModelName] = useState<string>('Face Recognition Models');
  const [percent, setPercent] = useState<number>(0);
  const [downloadedBytes, setDownloadedBytes] = useState<number>(0);
  const [totalBytes, setTotalBytes] = useState<number>(0);
  const [statusText, setStatusText] = useState<string>('Preparing models...');
  const [error, setError] = useState<string | null>(null);
  const [isDone, setIsDone] = useState<boolean>(false);

  const formatSize = (bytes: number): string => {
    if (!bytes || bytes <= 0) return '0 MB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
  };

  const startDownload = async () => {
    setError(null);
    setStatusText('Checking model files...');
    try {
      const res = await rpc<ModelStatusResponse>('models.status');
      if (res.ready) {
        setIsDone(true);
        setTimeout(onComplete, 600);
        return;
      }
      setStatusText('Downloading AI models...');
      await rpc('models.download');
    } catch (err: any) {
      setError(err?.message || 'Failed to start model download.');
    }
  };

  useEffect(() => {
    const unsub = onBackendEvent((payload) => {
      if (payload.event === 'models.progress') {
        const data = payload.data as unknown as ModelProgressEvent;
        if (data.name) setModelName(data.name);
        setPercent(data.percent || 0);
        setDownloadedBytes(data.downloaded || 0);
        setTotalBytes(data.total || 0);
        if (data.stage === 'downloading') {
          setStatusText(`Downloading ${data.name}...`);
        } else if (data.stage === 'ready' || data.stage === 'done') {
          setStatusText(`Verifying ${data.name}...`);
        }
      } else if (payload.event === 'models.ready') {
        setPercent(100);
        setStatusText('All models ready!');
        setIsDone(true);
        setTimeout(onComplete, 700);
      } else if (payload.event === 'models.error') {
        const msg = (payload.data as any)?.message || 'An error occurred during download.';
        setError(msg);
      }
    });

    startDownload();
    return () => unsub();
  }, []);

  return (
    <div className="flex h-screen w-screen items-center justify-center bg-app text-primary select-none p-6">
      <div className="w-full max-w-md bg-card border border-subtle rounded-md p-6 shadow-2xl flex flex-col items-center text-center">
        <div className="w-12 h-12 rounded-full bg-elevated border border-hairline flex items-center justify-center mb-4 text-accent">
          {isDone ? (
            <CheckCircle2 className="w-6 h-6 text-emerald-400 animate-pulse" />
          ) : error ? (
            <AlertTriangle className="w-6 h-6 text-danger" />
          ) : (
            <DownloadCloud className="w-6 h-6 animate-bounce" />
          )}
        </div>

        <h2 className="text-base font-semibold text-primary mb-1">
          {isDone ? 'Models Ready' : error ? 'Download Error' : 'Downloading AI Models'}
        </h2>
        <p className="text-xs text-secondary mb-5 max-w-xs">
          {isDone
            ? 'Facial detection and clustering components are configured and ready.'
            : error
            ? error
            : 'MemoFrame requires local onnx models for private on-device face recognition.'}
        </p>

        {!error && (
          <div className="w-full space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-primary truncate max-w-[200px]">{modelName}</span>
              <span className="font-mono text-secondary tabular-nums">
                {totalBytes > 0 ? `${formatSize(downloadedBytes)} / ${formatSize(totalBytes)}` : ''} ({percent}%)
              </span>
            </div>

            <div className="w-full h-2 bg-input rounded-full overflow-hidden border border-subtle">
              <div
                className={`h-full transition-all duration-200 ${isDone ? 'bg-emerald-400' : 'bg-accent'}`}
                style={{ width: `${Math.max(3, percent)}%` }}
              />
            </div>

            <div className="text-[11px] text-tertiary text-left pt-1">
              {statusText}
            </div>
          </div>
        )}

        {error && (
          <button
            type="button"
            onClick={startDownload}
            className="mt-2 h-8 px-4 inline-flex items-center gap-1.5 rounded-xs bg-accent text-accent-text text-xs font-medium hover:bg-accent-hover transition-colors"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>Retry Download</span>
          </button>
        )}
      </div>
    </div>
  );
}
