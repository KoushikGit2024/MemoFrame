import { useEffect, useState } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";
import { useApp } from "./context/AppContext";
import { rpc } from "./lib/api";
import type { PhotoRecord } from "./types/memoframe";
import NavRail from "./components/NavRail";
import ToastContainer from "./components/ToastContainer";
import ModelDownloadScreen from "./components/ModelDownloadScreen";
import GalleryView from "./views/GalleryView";
import PeopleView from "./views/PeopleView";
import DuplicatesView from "./views/DuplicatesView";
import BurstsView from "./views/BurstsView";
import TimelineView from "./views/TimelineView";
import SettingsView from "./views/SettingsView";
import LightboxModal from "./modals/LightboxModal";
import ScanProgressModal from "./modals/ScanProgressModal";

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
      case "settings":
        return <SettingsView />;
      case "photos":
      default:
        return <GalleryView />;
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-app text-primary">
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

        <main className="flex-1 min-h-0 flex flex-col overflow-hidden">{renderView()}</main>
      </div>

      {lightboxPhoto && (
        <LightboxModal
          key={lightboxPhoto.id}
          photo={lightboxPhoto}
          onClose={() => setLightboxPhoto(null)}
        />
      )}

      <ScanProgressModal />
      <ToastContainer />
    </div>
  );
}

export default function App() {
  const { connected, lightboxPhoto, setLightboxPhoto, setLightboxList } = useApp();
  const lightboxParam = new URLSearchParams(window.location.search).get("lightbox");
  const lightboxPhotoId = lightboxParam ? Number(lightboxParam) : null;

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

  if (lightboxPhotoId) {
    return (
      <div className="h-screen w-screen bg-app text-primary overflow-hidden">
        {lightboxPhoto ? (
          <LightboxModal
            key={lightboxPhoto.id}
            photo={lightboxPhoto}
            onClose={() => window.close()}
          />
        ) : (
          <div className="h-full w-full flex items-center justify-center text-xs text-secondary">
            Loading photo...
          </div>
        )}
        <ToastContainer />
      </div>
    );
  }
  const [checkingModels, setCheckingModels] = useState(true);
  const [modelsReady, setModelsReady] = useState(false);

  useEffect(() => {
    if (!connected) return;

    let mounted = true;
    rpc<{ ready: boolean }>("models.status")
      .then(res => {
        if (!mounted) return;
        if (res && res.ready) {
          setModelsReady(true);
        } else {
          setModelsReady(false);
        }
      })
      .catch(() => {
        if (!mounted) return;
        // If models.status fails or is not supported, fall back to letting the app load
        setModelsReady(true);
      })
      .finally(() => {
        if (mounted) setCheckingModels(false);
      });

    return () => {
      mounted = false;
    };
  }, [connected]);

  // If connected and models are not ready, show model download screen with real-time progress
  if (connected && !checkingModels && !modelsReady) {
    return <ModelDownloadScreen onComplete={() => setModelsReady(true)} />;
  }

  return <WorkspaceShell />;
}
