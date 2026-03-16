import { Routes, Route, Link, useLocation } from 'react-router-dom';
import {
  LayoutDashboard, PlusCircle, Settings, Activity,
  Zap, ChevronRight, HelpCircle
} from 'lucide-react';
import Dashboard from './pages/Dashboard';
import NewRFQ from './pages/NewRFQ';
import RFQDetail from './pages/RFQDetail';
import PipelineActivity from './pages/PipelineActivity';

function SidebarItem({ to, icon, label, badge }) {
  const location = useLocation();
  const active = location.pathname === to || (to !== '/' && location.pathname.startsWith(to));
  return (
    <Link to={to} className={`sidebar-item ${active ? 'active' : ''}`}>
      <span className="sidebar-item-icon">{icon}</span>
      <span className="sidebar-item-label">{label}</span>
      {badge != null && <span className="sidebar-item-badge">{badge}</span>}
      {active && <ChevronRight size={12} className="sidebar-item-arrow" />}
    </Link>
  );
}

function App() {
  return (
    <div className="app-layout">
      {/* ── Sidebar ── */}
      <aside className="app-sidebar">
        <div className="sidebar-header">
          <Link to="/" className="sidebar-brand">
            <span className="sidebar-logo">
              <Zap size={14} />
            </span>
            <div className="sidebar-brand-text">
              <span className="sidebar-brand-name">RFQ Agent</span>
              <span className="sidebar-brand-sub">AI · Manufacturing</span>
            </div>
          </Link>
        </div>

        <nav className="sidebar-nav">
          <div className="sidebar-section">
            <div className="sidebar-section-label">Workspace</div>
            <SidebarItem to="/" icon={<LayoutDashboard size={15} />} label="Dashboard" />
            <SidebarItem to="/new" icon={<PlusCircle size={15} />} label="New RFQ" />
          </div>

          <div className="sidebar-section">
            <div className="sidebar-section-label">Monitoring</div>
            <SidebarItem to="/activity" icon={<Activity size={15} />} label="Pipeline Activity" />
          </div>
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-system-status">
            <div className="status-pulse" />
            <div className="sidebar-status-text">
              <span className="sidebar-status-label">AI Engine</span>
              <span className="sidebar-status-value">Online</span>
            </div>
          </div>
          <div className="sidebar-footer-actions">
            <button className="sidebar-icon-btn" title="Help"><HelpCircle size={15} /></button>
            <button className="sidebar-icon-btn" title="Settings"><Settings size={15} /></button>
          </div>
        </div>
      </aside>

      {/* ── Main body ── */}
      <div className="app-body">
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/new" element={<NewRFQ />} />
            <Route path="/rfq/:id" element={<RFQDetail />} />
            <Route path="/activity" element={<PipelineActivity />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}

export default App;
