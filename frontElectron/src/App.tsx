import { AlertTriangle, RefreshCw } from 'lucide-react';
import { AppProvider, useApp } from './context/AppContext';
import NavRail from './components/NavRail';
import StatusBar from './components/StatusBar';
import ToastContainer from './components/ToastContainer';
import GalleryView from './views/GalleryView';
import PeopleView from './views/PeopleView';
import DuplicatesView from './views/DuplicatesView';
import BurstsView from './views/BurstsView';
import TimelineView from './views/TimelineView';
import SettingsView from './views/SettingsView';
import LightboxModal from './modals/LightboxModal';

function WorkspaceShell() {
  const { activeView, connected, backendError, initBackend, lightboxPhoto, setLightboxPhoto } = useApp();

  const renderView = () => {
    switch (activeView) {
      case 'people': return <PeopleView />;
      case 'duplicates': return <DuplicatesView />;
      case 'bursts': return <BurstsView />;
      case 'timeline': return <TimelineView />;
      case 'settings': return <SettingsView />;
      case 'photos':
      default: return <GalleryView />;
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-app text-primary">
      <NavRail />

      <div className="flex-1 min-w-0 flex flex-col h-screen overflow-hidden">
        {!connected && backendError && (
          <div className="px-4 py-2 bg-danger-bg border-b border-danger text-xs text-primary flex items-center justify-between gap-3 shrink-0">
            <span className="inline-flex items-center gap-2 min-w-0">
              <AlertTriangle className="w-3.5 h-3.5 text-danger shrink-0" strokeWidth={1.7} />
              <span className="truncate">{backendError}</span>
            </span>
            <button
              type="button"
              onClick={initBackend}
              className="h-6 px-2 inline-flex items-center gap-1 rounded-xs border border-danger text-xs text-danger hover:bg-danger hover:text-white shrink-0"
            >
              <RefreshCw className="w-3 h-3" strokeWidth={1.6} />
              <span>Retry</span>
            </button>
          </div>
        )}

        <main className="flex-1 min-h-0 flex flex-col overflow-hidden">
          {renderView()}
        </main>

        <StatusBar />
      </div>

      {lightboxPhoto && (
        <LightboxModal
          key={lightboxPhoto.id}
          photo={lightboxPhoto}
          onClose={() => setLightboxPhoto(null)}
        />
      )}

      <ToastContainer />
    </div>
  );
}

export default function App() {
  return (
    <AppProvider>
      <WorkspaceShell />
    </AppProvider>
  );
}
