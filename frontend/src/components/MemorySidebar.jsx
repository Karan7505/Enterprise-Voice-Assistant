import { useState } from "react";

function MemorySidebar({ memories, isOpen, toggleSidebar, onClearSession }) {
  const [filter, setFilter] = useState("");
  const [copiedKey, setCopiedKey] = useState(null);

  const memoryKeys = Object.keys(memories || {});
  const filteredKeys = memoryKeys.filter((key) =>
    key.toLowerCase().includes(filter.toLowerCase()) ||
    String(memories[key]).toLowerCase().includes(filter.toLowerCase())
  );

  const copyToClipboard = (key, value) => {
    navigator.clipboard.writeText(`${key}: ${value}`);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  return (
    <aside className={`memory-sidebar ${isOpen ? "open" : "closed"}`}>
      <div className="sidebar-header">
        <div className="sidebar-title">
          <svg className="icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/>
          </svg>
          <h2>Extracted Memories</h2>
          <span className="memory-badge">{memoryKeys.length}</span>
        </div>
        <button className="toggle-btn" onClick={toggleSidebar} title="Close Sidebar">
          ✕
        </button>
      </div>

      <div className="sidebar-search">
        <input
          type="text"
          placeholder="Filter memories..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
      </div>

      <div className="memories-container">
        {memoryKeys.length === 0 ? (
          <div className="empty-memories">
            <div className="empty-icon">🧠</div>
            <p>No long-term facts extracted yet.</p>
            <span>Mention facts like your name, role, or preferences in chat!</span>
          </div>
        ) : filteredKeys.length === 0 ? (
          <div className="empty-memories">
            <p>No matching memories found.</p>
          </div>
        ) : (
          filteredKeys.map((key) => (
            <div key={key} className="memory-card">
              <div className="memory-card-header">
                <span className="memory-key">{key}</span>
                <button
                  className="copy-btn"
                  onClick={() => copyToClipboard(key, memories[key])}
                  title="Copy memory"
                >
                  {copiedKey === key ? "✓" : "📋"}
                </button>
              </div>
              <div className="memory-value">{String(memories[key])}</div>
            </div>
          ))
        )}
      </div>

      <div className="sidebar-footer">
        <button className="clear-session-btn" onClick={onClearSession}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 6h18M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
          </svg>
          Reset Session & Memories
        </button>
      </div>
    </aside>
  );
}

export default MemorySidebar;
