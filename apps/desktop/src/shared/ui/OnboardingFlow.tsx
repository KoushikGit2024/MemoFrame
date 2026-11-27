import { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  DownloadCloud,
  FolderSearch,
  HardDrive,
  Layers,
  Loader2,
  Pause,
  Play,
  RefreshCw,
  ScanFace,
  ShieldCheck,
  X,
} from "lucide-react";
import { useApp } from "../context/AppContext";
import { onBackendEvent, rpc } from "../lib/api";

type Step = "intro" | "models" | "scan";

interface ModelItemStatus {
  name: string;
  filename: string;
  present: boolean;
  size_bytes: number;
}

interface ModelStatusResponse {
  ready: boolean;
  missing: string[];
  models: Record<string, ModelItemStatus>;
}

interface ModelProgressEvent {
  model: string;
  name: string;
  downloaded: number;
  total: number;
  percent: number;
  stage: string;
}

interface OnboardingFlowProps {
  onComplete: () => void;
}

const PILLARS = [
  {
    icon: ScanFace,
    title: "Private Face Studio",
    desc: "Detect, cluster, and name people locally with YuNet and SFace ONNX models.",
    accent: "text-violet border-violet/40 bg-violet-bg",
  },
  {
    icon: Layers,
    title: "Smart Duplicates & Bursts",
    desc: "Spot near-duplicates, burst sequences, and chronological events automatically.",
    accent: "text-amber border-amber/40 bg-amber-bg",
  },
  {
    icon: ShieldCheck,
    title: "100% Offline & Non-Destructive",
    desc: "Original photos are never modified, moved, or uploaded. All data stays on your PC.",
    accent: "text-success border-success/40 bg-success-bg",
  },
];

function formatMB(bytes: number): string {
  if (!bytes || bytes <= 0) return "0.0 MB";
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function OnboardingFlow({ onComplete }: OnboardingFlowProps) {
  const { scan, scanLogs, startScanFolder, togglePauseScan, cancelScan, hasIndexedPhotos } =
    useApp();

  const [step, setStep] = useState<Step>("intro");
  const [modelsMap, setModelsMap] = useState<Record<string, ModelItemStatus>>({});
  const [activeModel, setActiveModel] = useState("Checking models...");
  const [modelPercent, setModelPercent] = useState(0);
  const [downloadedBytes, setDownloadedBytes] = useState(0);
  const [totalBytes, setTotalBytes] = useState(0);
  const [modelError, setModelError] = useState<string | null>(null);
  const [modelsVerified, setModelsVerified] = useState(false);
  const [downloading, setDownloading] = useState(false);

  const advanceTimerRef = useRef<number | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);
  const scanStartedHereRef = useRef(false);

  useEffect(() => {
    return () => {
      if (advanceTimerRef.current !== null) window.clearTimeout(advanceTimerRef.current);
    };
  }, []);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [scanLogs]);

  // Complete onboarding automatically once first scan finishes with indexed photos
  useEffect(() => {
    if (step === "scan" && scanStartedHereRef.current && !scan.running && hasIndexedPhotos) {
      advanceTimerRef.current = window.setTimeout(onComplete, 500);
    }
  }, [step, scan.running, hasIndexedPhotos, onComplete]);

  const checkAndDownloadModels = async () => {
    setModelError(null);
    setDownloading(true);
    setActiveModel("Verifying local ONNX models...");
    try {
      const st = await rpc<ModelStatusResponse>("models.status");
      if (st?.models) setModelsMap(st.models);
      if (st?.ready) {
        setModelsVerified(true);
        setDownloading(false);
        setModelPercent(100);
        setActiveModel("All AI models verified");
        advanceTimerRef.current = window.setTimeout(() => setStep("scan"), 550);
        return;
      }
      setActiveModel("Starting secure model download...");
      const dl = await rpc<{ ready?: boolean; started?: boolean; downloading?: boolean }>(
        "models.download"
      );
      if (dl?.ready) {
        setModelsVerified(true);
        setDownloading(false);
        setModelPercent(100);
        advanceTimerRef.current = window.setTimeout(() => setStep("scan"), 550);
      }
    } catch (err) {
      setDownloading(false);
      setModelError(
        err instanceof Error ? err.message : "Failed to verify or download required AI models."
      );
    }
  };

  useEffect(() => {
    if (step !== "models") return;

    const unsub = onBackendEvent(payload => {
      if (payload.event === "models.progress") {
        const d = payload.data as unknown as ModelProgressEvent;
        if (d.name) setActiveModel(d.name);
        setModelPercent(d.percent || 0);
        setDownloadedBytes(d.downloaded || 0);
        setTotalBytes(d.total || 0);
        if (d.stage === "done" || d.stage === "ready") {
          setModelsMap(prev =>
            prev[d.model] ? { ...prev, [d.model]: { ...prev[d.model], present: true } } : prev
          );
        }
      } else if (payload.event === "models.ready") {
        setModelsVerified(true);
        setDownloading(false);
        setModelPercent(100);
        setActiveModel("All AI models verified");
        setModelError(null);
        advanceTimerRef.current = window.setTimeout(() => setStep("scan"), 600);
      } else if (payload.event === "models.error") {
        setDownloading(false);
        setModelsVerified(false);
        setModelError(
          String(
            (payload.data as Record<string, unknown>)?.message ||
              "Model download interrupted. Retry to continue."
          )
        );
      }
    });

    void checkAndDownloadModels();
    return () => unsub();
  }, [step]);

  const handleFirstScan = async () => {
    scanStartedHereRef.current = true;
    await startScanFolder();
  };

  const stepIndex = step === "intro" ? 1 : step === "models" ? 2 : 3;

  return (
    <div className="h-screen w-screen bg-app text-primary flex items-center justify-center p-6 overflow-auto select-none">
      <div className="w-full max-w-2xl bg-card border border-hairline rounded-sm p-6 flex flex-col gap-5 animate-modal-in">
        {/* Stepper Header */}
        <div className="flex items-center justify-between gap-3 border-b border-subtle pb-3.5">
          <div className="flex items-center gap-2.5">
            <img src="./logo.svg" alt="MemoFrame" className="w-7 h-7 object-contain shrink-0" />
            <div>
              <div className="text-xs font-bold tracking-[0.12em] text-primary leading-none">
                MEMOFRAME
              </div>
              <div className="text-[11px] text-secondary mt-0.5">First-Time Studio Setup</div>
            </div>
          </div>

          <div className="flex items-center gap-2 font-mono text-[11px]">
            {[
              [1, "Intro"],
              [2, "AI Models"],
              [3, "First Scan"],
            ].map(([num, label]) => {
              const n = Number(num);
              const done = stepIndex > n || (n === 2 && modelsVerified);
              const active = stepIndex === n;
              return (
                <span
                  key={n}
                  className={`px-2 py-0.5 rounded-xs border ${
                    active
                      ? "bg-accent-secondary-light border-accent-secondary/60 text-accent-secondary font-semibold"
                      : done
                        ? "bg-success-bg border-success/50 text-success"
                        : "bg-input border-subtle text-secondary"
                  }`}
                >
                  {n}. {label}
                </span>
              );
            })}
          </div>
        </div>

        {/* STEP 1: Brand Intro */}
        {step === "intro" && (
          <div className="flex flex-col gap-5 animate-fade-in">
            <div className="flex flex-col gap-1.5">
              <h1 className="text-xl font-semibold text-primary tracking-tight">
                Welcome to MemoFrame Photo &amp; Face Studio
              </h1>
              <p className="text-xs text-secondary leading-relaxed max-w-xl">
                Before browsing your library, MemoFrame will verify its offline AI models and index
                your first photo folder. This takes about a minute on first launch.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
              {PILLARS.map(({ icon: Icon, title, desc, accent }, idx) => (
                <div
                  key={title}
                  style={{ animationDelay: `${idx * 70}ms` }}
                  className="bg-input border border-subtle rounded-xs p-3.5 flex flex-col gap-2 animate-intro-up"
                >
                  <div className={`w-8 h-8 rounded-xs border flex items-center justify-center ${accent}`}>
                    <Icon className="w-4 h-4" strokeWidth={1.7} />
                  </div>
                  <div className="text-xs font-semibold text-primary">{title}</div>
                  <p className="text-[11.5px] text-secondary leading-relaxed">{desc}</p>
                </div>
              ))}
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-subtle">
              <span className="text-[11px] text-secondary font-mono">
                Step 1 of 3 · Strictly offline after model verification
              </span>
              <button
                type="button"
                onClick={() => setStep("models")}
                className="btn-primary h-9 px-4 text-xs"
              >
                <span>Begin Setup</span>
                <ArrowRight className="w-3.5 h-3.5" strokeWidth={1.8} />
              </button>
            </div>
          </div>
        )}

        {/* STEP 2: Sequential Model Setup (Blocking Retry Loop on Failure) */}
        {step === "models" && (
          <div className="flex flex-col gap-4 animate-fade-in">
            <div className="flex items-start gap-3">
              <div
                className={`w-10 h-10 rounded-xs border flex items-center justify-center shrink-0 ${
                  modelsVerified
                    ? "bg-success-bg border-success/50 text-success"
                    : modelError
                      ? "bg-danger-bg border-danger/50 text-danger"
                      : "bg-accent-secondary-light border-accent-secondary/50 text-accent-secondary"
                }`}
              >
                {modelsVerified ? (
                  <CheckCircle2 className="w-5 h-5" strokeWidth={1.7} />
                ) : modelError ? (
                  <AlertTriangle className="w-5 h-5" strokeWidth={1.7} />
                ) : (
                  <DownloadCloud className="w-5 h-5 animate-pulse" strokeWidth={1.7} />
                )}
              </div>
              <div className="min-w-0 flex-1">
                <h2 className="text-sm font-semibold text-primary">
                  {modelsVerified
                    ? "AI Models Verified"
                    : modelError
                      ? "Model Setup Requires Retry"
                      : "Preparing Offline AI Models"}
                </h2>
                <p className="text-xs text-secondary mt-0.5">
                  {modelError
                    ? "All required ONNX models must be downloaded and verified before scanning photos."
                    : "Downloading SHA-256 verified face detection, recognition, and scene models."}
                </p>
              </div>
            </div>

            {/* Per-model verification list */}
            {Object.keys(modelsMap).length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {Object.entries(modelsMap).map(([key, item]) => (
                  <div
                    key={key}
                    className="px-3 py-2 bg-input border border-subtle rounded-xs flex items-center justify-between gap-2 text-xs"
                  >
                    <span className="truncate text-primary">{item.name}</span>
                    <span
                      className={`font-mono text-[10.5px] shrink-0 ${
                        item.present ? "text-success" : "text-secondary"
                      }`}
                    >
                      {item.present ? "Verified" : "Pending"}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {!modelError ? (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-primary font-medium truncate">{activeModel}</span>
                  <span className="font-mono text-secondary tabular-nums">
                    {totalBytes > 0 ? `${formatMB(downloadedBytes)} / ${formatMB(totalBytes)} ` : ""}
                    ({modelPercent}%)
                  </span>
                </div>
                <div className="w-full h-2 bg-input border border-subtle rounded-xs overflow-hidden">
                  <div
                    className={`h-full transition-all duration-200 ${
                      modelsVerified ? "bg-success" : "bg-accent-secondary"
                    }`}
                    style={{ width: `${Math.max(4, modelPercent)}%` }}
                  />
                </div>
              </div>
            ) : (
              <div className="p-3 bg-danger-bg border border-danger/50 rounded-xs flex flex-col gap-2.5">
                <div className="text-xs text-primary break-words">{modelError}</div>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] text-secondary">
                    Check your internet connection and retry—setup will continue once all models verify.
                  </span>
                  <button
                    type="button"
                    disabled={downloading}
                    onClick={() => void checkAndDownloadModels()}
                    className="btn-primary h-8 px-3 text-xs shrink-0"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${downloading ? "animate-spin" : ""}`} />
                    <span>Retry Download</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        )}

        {/* STEP 3: Forced First Folder Scan */}
        {step === "scan" && (
          <div className="flex flex-col gap-4 animate-fade-in">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-xs border border-accent-secondary/50 bg-accent-secondary-light text-accent-secondary flex items-center justify-center shrink-0">
                {scan.running ? (
                  <Loader2 className="w-5 h-5 animate-spin" strokeWidth={1.7} />
                ) : (
                  <HardDrive className="w-5 h-5" strokeWidth={1.7} />
                )}
              </div>
              <div>
                <h2 className="text-sm font-semibold text-primary">
                  {scan.running ? "Indexing Your First Photo Folder..." : "Scan Your First Photo Folder"}
                </h2>
                <p className="text-xs text-secondary mt-0.5">
                  Select a folder of photos to unlock People, Timeline, Duplicates, and Bursts. Your
                  original files are read-only and never altered.
                </p>
              </div>
            </div>

            {scan.running ? (
              <div className="flex flex-col gap-2.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-primary truncate">{scan.label}</span>
                  <span className="font-mono text-accent-secondary tabular-nums">{scan.percent}%</span>
                </div>
                <div className="w-full h-2 bg-input border border-subtle rounded-xs overflow-hidden">
                  <div
                    className={`h-full transition-all duration-200 ${
                      scan.paused ? "bg-amber" : "bg-accent-secondary"
                    }`}
                    style={{ width: `${Math.max(3, scan.percent)}%` }}
                  />
                </div>
                <div className="bg-input border border-subtle rounded-xs p-2.5 h-32 overflow-y-auto font-mono text-[11px] text-secondary flex flex-col gap-0.5">
                  {scanLogs.length === 0 ? (
                    <span className="opacity-60">Initializing worker pool...</span>
                  ) : (
                    scanLogs.slice(-40).map((line, i) => (
                      <div key={i} className={line.startsWith("[ERROR]") ? "text-danger" : ""}>
                        {line}
                      </div>
                    ))
                  )}
                  <div ref={logEndRef} />
                </div>
                <div className="flex items-center justify-end gap-2">
                  <button
                    type="button"
                    onClick={togglePauseScan}
                    className={`${scan.paused ? "btn-warning" : "btn-neutral"} h-8 px-3 text-xs`}
                  >
                    {scan.paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
                    <span>{scan.paused ? "Resume" : "Pause"}</span>
                  </button>
                  <button type="button" onClick={cancelScan} className="btn-danger h-8 px-3 text-xs">
                    <X className="w-3.5 h-3.5" />
                    <span>Cancel</span>
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3 pt-2 border-t border-subtle flex-wrap">
                <span className="text-[11px] text-secondary">
                  {hasIndexedPhotos
                    ? "Photos indexed! Ready to enter your workspace."
                    : "Library sections remain locked until at least one folder is scanned."}
                </span>
                <div className="flex items-center gap-2">
                  {hasIndexedPhotos && (
                    <button type="button" onClick={onComplete} className="btn-success h-9 px-4 text-xs">
                      <span>Open Workspace</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                  <button
                    type="button"
                    onClick={() => void handleFirstScan()}
                    className="btn-primary h-9 px-4 text-xs"
                  >
                    <FolderSearch className="w-4 h-4" strokeWidth={1.7} />
                    <span>Choose Photo Folder...</span>
                  </button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
