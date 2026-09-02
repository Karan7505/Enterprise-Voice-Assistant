import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";

function MemorySidebar({
  memories,
  isOpen,
  toggleSidebar,
  onClearMemories,
  isClearDisabled = false,
}) {
  const [filter, setFilter] = useState("");
  const [copyState, setCopyState] = useState({ key: null, status: "idle" });
  const copyTimerRef = useRef(null);

  useEffect(() => () => clearTimeout(copyTimerRef.current), []);

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

  const copyToClipboard = async (key, value) => {
    clearTimeout(copyTimerRef.current);
    try {
      if (!navigator.clipboard) {
        throw new Error("Clipboard API unavailable");
      }
      await navigator.clipboard.writeText(`${key}: ${value}`);
      setCopyState({ key, status: "copied" });
    } catch (error) {
      console.error("Clipboard copy failed:", error);
      setCopyState({ key, status: "error" });
    }
    copyTimerRef.current = setTimeout(
      () => setCopyState({ key: null, status: "idle" }),
      2000,
    );
  };

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
            <div>
              <span className="sidebar-eyebrow">Personal context</span>
              <h2 id="memory-drawer-title">Memory</h2>
            </div>
            <span className="memory-badge" aria-label={`${memoryKeys.length} saved memories`}>
              {memoryKeys.length}
            </span>
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
            filteredKeys.map((key) => {
              const isCopied = copyState.key === key && copyState.status === "copied";
              const hasCopyError = copyState.key === key && copyState.status === "error";

              return (
                <div key={key} className="memory-card">
                  <div className="memory-card-header">
                    <span className="memory-key">{key}</span>
                    <button
                      type="button"
                      className="copy-btn"
                      onClick={() => copyToClipboard(key, memories[key])}
                      title={isCopied ? "Copied" : hasCopyError ? "Copy failed" : "Copy memory"}
                      aria-label={isCopied ? `${key} copied` : hasCopyError ? `Could not copy ${key}` : `Copy ${key}`}
                      tabIndex={isOpen ? 0 : -1}
                    >
                      <Icon name={isCopied ? "check" : hasCopyError ? "alert" : "copy"} size={15} />
                    </button>
                  </div>
                  <div className="memory-value">{String(memories[key])}</div>
                </div>
              );
            })
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
