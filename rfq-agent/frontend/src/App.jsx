import { Routes, Route, Link } from 'react-router-dom';
import { Activity } from 'lucide-react';
import Dashboard from './pages/Dashboard';
import NewRFQ from './pages/NewRFQ';
import RFQDetail from './pages/RFQDetail';

function App() {
  return (
    <div className="app-container">
      <nav className="navbar">
        <Link to="/" className="navbar-brand">
          <Activity color="var(--accent-blue)" size={24} />
          RFQ Feasibility Agent
        </Link>
      </nav>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/new" element={<NewRFQ />} />
          <Route path="/rfq/:id" element={<RFQDetail />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
