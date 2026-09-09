import { useEffect, useState } from "react";
import Icon from "./Icon";

// Human-readable labels: favorite_color -> "Favorite Color"
const formatMemoryLabel = (key) => {
  const words = String(key || "")
    .toLowerCase()
    .replace(/[_\-.]+/g, " ")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!words.length) return String(key || "");
  return words
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
};

// Normalize short structured values ("blue", "yes", "python") to Title Case.
// Longer values (sentences, addresses) are left untouched.
const formatMemoryValue = (value) => {
  const raw = String(value ?? "").trim();
  if (!raw) return raw;
  const words = raw.split(/\s+/);
  if (raw.length > 24 || words.length > 3) return raw;
  if (/\d/.test(raw)) return raw;
  if (!/^[a-z0-9][a-z0-9 _-]*$/i.test(raw)) return raw;
  return raw.replace(/[a-z0-9]+/gi, (w) => w.charAt(0).toUpperCase() + w.slice(1));
};

function MemorySidebar({
  memories,
  isOpen,
  toggleSidebar,
  onClearMemories,
  isClearDisabled = false,
}) {
  const [filter, setFilter] = useState("");

  useEffect(() => {
    if (!isOpen) return undefined;

    const handleEscape = (event) => {
      if (event.key === "Escape") toggleSidebar();
    };

    window.addEventListener("keydown", handleEscape);
    return () => window.removeEventListener("keydown", handleEscape);
  }, [isOpen, toggleSidebar]);

  const memoryKeys = Object.keys(memories || {});
  const filteredKeys = memoryKeys.filter((key) =>
    key.toLowerCase().includes(filter.toLowerCase()) ||
    String(memories[key]).toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <>
      {isOpen && (
        <button
          type="button"
          className="memory-backdrop"
          onClick={toggleSidebar}
          aria-label="Close memory drawer"
        />
      )}

      <aside
        className={`memory-sidebar ${isOpen ? "open" : "closed"}`}
        role="dialog"
        aria-modal={isOpen ? "true" : undefined}
        aria-labelledby="memory-drawer-title"
        aria-hidden={!isOpen}
      >
        <div className="sidebar-header">
          <div className="sidebar-title">
            <Icon name="memory" size={20} />
            <h2 id="memory-drawer-title">Memory</h2>
          </div>
          <button
            type="button"
            className="toggle-btn"
            onClick={toggleSidebar}
            title="Close memory drawer"
            aria-label="Close memory drawer"
            tabIndex={isOpen ? 0 : -1}
          >
            <Icon name="close" size={20} />
          </button>
        </div>

        <div className="sidebar-search">
          <Icon name="search" size={17} />
          <input
            type="search"
            placeholder="Search saved details"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Search memories"
            tabIndex={isOpen ? 0 : -1}
          />
        </div>

        <div className="memories-container">
          {memoryKeys.length === 0 ? (
            <div className="empty-memories">
              <div className="empty-icon" aria-hidden="true">
                <Icon name="memory" size={28} />
              </div>
              <p>No saved details yet</p>
              <span>Share a preference or detail and it can appear here.</span>
            </div>
          ) : filteredKeys.length === 0 ? (
            <div className="empty-memories">
              <p>No matching memories</p>
              <span>Try a different search.</span>
            </div>
          ) : (
            filteredKeys.map((key) => (
              <div key={key} className="memory-card">
                <div className="memory-card-header">
                  <span className="memory-key">{formatMemoryLabel(key)}</span>
                </div>
                <div className="memory-value">{formatMemoryValue(memories[key])}</div>
              </div>
            ))
          )}
        </div>

        <div className="sidebar-footer">
          <button
            type="button"
            className="clear-session-btn"
            onClick={onClearMemories}
            disabled={isClearDisabled}
            title="Delete saved memories while keeping this conversation"
            tabIndex={isOpen ? 0 : -1}
          >
            <Icon name="trash" size={16} />
            Reset memory
          </button>
        </div>
      </aside>
    </>
  );
}

export default MemorySidebar;
