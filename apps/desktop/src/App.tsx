import { useEffect, useState } from "react";
import { AlertTriangle, Loader2, RefreshCw } from "lucide-react";
import { useApp } from "./shared/context/AppContext";
import { rpc } from "./shared/lib/api";
import { installGlobalErrorHandlers } from "./shared/lib/errorMonitor";
import type { PhotoRecord } from "./shared/types/memoframe";
import ErrorBoundary from "./shared/ui/ErrorBoundary";
import NavRail from "./shared/ui/NavRail";
import OnboardingFlow from "./shared/ui/OnboardingFlow";
import ToastContainer from "./shared/ui/ToastContainer";
import ModelDownloadScreen from "./shared/ui/ModelDownloadScreen";
import GalleryView from "./features/gallery/GalleryView";
import PeopleView from "./features/people/PeopleView";
import DuplicatesView from "./features/duplicates/DuplicatesView";
import BurstsView from "./features/bursts/BurstsView";
import TimelineView from "./features/timeline/TimelineView";
import AnalyticsView from "./features/analytics/AnalyticsView";
import SettingsView from "./features/settings/SettingsView";
import LightboxModal from "./features/lightbox/LightboxModal";
import CommandPalette from "./shared/ui/CommandPalette";
import ExportPhotosModal from "./shared/ui/ExportPhotosModal";
import ScanProgressModal from "./shared/ui/ScanProgressModal";

function WorkspaceShell() {
  const { activeView, connected, backendError, initBackend, lightboxPhoto, setLightboxPhoto } =
    useApp();

  const renderView = () => {
    switch (activeView) {
      case "people":
        return <PeopleView />;
      case "duplicates":
        return <DuplicatesView />;
      case "bursts":
        return <BurstsView />;
      case "timeline":
        return <TimelineView />;
      case "analytics":
        return <AnalyticsView />;
      case "settings":
        return <SettingsView />;
      case "photos":
      default:
        return <GalleryView />;
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-app text-primary animate-fade-in">
      <NavRail />

      <div className="flex-1 min-w-0 flex flex-col h-screen overflow-hidden">
        {!connected && backendError && (
          <div className="px-4 py-2 bg-danger-bg border-b border-danger/50 text-xs text-primary flex items-center justify-between gap-3 shrink-0">
            <span className="inline-flex items-center gap-2 min-w-0">
              <AlertTriangle className="w-3.5 h-3.5 text-danger shrink-0" strokeWidth={1.7} />
              <span className="truncate">{backendError}</span>
            </span>
            <button
              type="button"
              onClick={initBackend}
              className="btn-danger h-6 px-2 text-xs shrink-0"
            >
              <RefreshCw className="w-3 h-3" strokeWidth={1.6} />
              <span>Retry</span>
            </button>
          </div>
        )}

        <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
          <ErrorBoundary key={activeView} sectionName={activeView.toUpperCase()}>
            {renderView()}
          </ErrorBoundary>
        </main>
      </div>

      {lightboxPhoto && (
        <ErrorBoundary sectionName="Lightbox" onReset={() => setLightboxPhoto(null)}>
          <LightboxModal
            key={lightboxPhoto.id}
            photo={lightboxPhoto}
            onClose={() => setLightboxPhoto(null)}
          />
        </ErrorBoundary>
      )}

      <ExportPhotosModal />
      <CommandPalette />
      <ScanProgressModal />
      <ToastContainer />
    </div>
  );
}

export default function App() {
  const {
    connected,
    backendError,
    initReady,
    inOnboarding,
    completeOnboarding,
    modelGateOpen,
    completeModelGate,
    lightboxPhoto,
    setLightboxPhoto,
    setLightboxList,
  } = useApp();

  const lightboxParam = new URLSearchParams(window.location.search).get("lightbox");
  const lightboxPhotoId = lightboxParam ? Number(lightboxParam) : null;
  const [checkingModels, setCheckingModels] = useState(true);
  const [modelsReady, setModelsReady] = useState(true);

  useEffect(() => installGlobalErrorHandlers(), []);

  useEffect(() => {
    if (!connected || !lightboxPhotoId) return;
    try {
      const raw = localStorage.getItem("memoframe_lightbox_ids");
      if (raw) {
        const ids = JSON.parse(raw) as number[];
        if (Array.isArray(ids) && ids.length > 0) {
          setLightboxList(ids.map(id => ({ id })));
        }
      }
    } catch {
      /* ignore */
    }
    rpc<{ photo: PhotoRecord }>("photos.detail", { image_id: lightboxPhotoId })
      .then(res => {
        if (res?.photo) setLightboxPhoto(res.photo);
      })
      .catch(() => {});
  }, [connected, lightboxPhotoId, setLightboxList, setLightboxPhoto]);

  useEffect(() => {
    if (!connected || lightboxPhotoId) return;

    let mounted = true;
    rpc<{ ready: boolean }>("models.status")
      .then(res => {
        if (!mounted) return;
        setModelsReady(Boolean(res && res.ready));
      })
      .catch(() => {
        if (!mounted) return;
        setModelsReady(true);
      })
      .finally(() => {
        if (mounted) setCheckingModels(false);
      });

    return () => {
      mounted = false;
    };
  }, [connected, lightboxPhotoId]);

  if (lightboxPhotoId) {
    return (
      <div className="h-screen w-screen bg-app text-primary overflow-hidden">
        {lightboxPhoto ? (
          <ErrorBoundary sectionName="Lightbox" onReset={() => window.close()}>
            <LightboxModal
              key={lightboxPhoto.id}
              photo={lightboxPhoto}
              onClose={() => window.close()}
            />
          </ErrorBoundary>
        ) : (
          <div className="h-full w-full flex items-center justify-center text-xs text-secondary">
            Loading photo...
          </div>
        )}
        <ToastContainer />
      </div>
    );
  }

  // Calm startup splash while connecting and verifying initial workspace/model state
  // (prevents WorkspaceShell from flashing before Onboarding or ModelDownloadScreen)
  if (!initReady || (connected && checkingModels && !backendError)) {
    return (
      <div className="h-screen w-screen bg-app text-primary flex flex-col items-center justify-center gap-3 select-none">
        <img src="./logo.svg" alt="MemoFrame" className="w-11 h-11 object-contain animate-pulse" />
        <div className="flex items-center gap-2 text-xs text-secondary font-mono">
          <Loader2 className="w-3.5 h-3.5 animate-spin text-accent-secondary" />
          <span>Starting MemoFrame Studio...</span>
        </div>
      </div>
    );
  }

  // First-time sequential onboarding wizard (Intro -> Model Setup Loop -> First Folder Scan)
  if (connected && inOnboarding) {
    return (
      <>
        <OnboardingFlow onComplete={() => void completeOnboarding()} />
        <ToastContainer />
      </>
    );
  }

  // Blocking pre-scan or missing-model recovery loop (cannot be bypassed until models verify)
  if (connected && (modelGateOpen || !modelsReady)) {
    return (
      <>
        <ModelDownloadScreen
          onComplete={() => {
            setModelsReady(true);
            void completeModelGate();
          }}
        />
        <ToastContainer />
      </>
    );
  }

  return <WorkspaceShell />;
}
