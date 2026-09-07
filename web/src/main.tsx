import { Component, StrictMode } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import './styles.css';

class WorkspaceBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('Workspace rendering failed', error.message, info.componentStack); }
  render() {
    if (this.state.failed) return <main style={{padding:48,fontFamily:'system-ui'}} role="alert"><h1>The workspace could not be displayed</h1><p>Reload to open a fresh workspace. Your original analysis file has not been changed.</p><button onClick={() => window.location.reload()}>Reload workspace</button></main>;
    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(<StrictMode><WorkspaceBoundary><App /></WorkspaceBoundary></StrictMode>);
