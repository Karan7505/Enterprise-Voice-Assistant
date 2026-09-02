const paths = {
  memory: <><path d="M9 4.5a2.5 2.5 0 0 1 5 0v.3a3 3 0 0 1 3.5 4.6 3.2 3.2 0 0 1-.2 5.5A3 3 0 0 1 14 19.2v.3a2.5 2.5 0 0 1-5 0v-.3a3 3 0 0 1-3.3-4.3 3.2 3.2 0 0 1-.2-5.5A3 3 0 0 1 9 4.8z"/><path d="M9 5v14M14 8.5a3 3 0 0 0 3.5.9M14 15.5a3 3 0 0 1 3.3-.6M9 9a3 3 0 0 1-3.5.4M9 15a3 3 0 0 0-3.3-.1"/></>,
  trash: <><path d="M4 7h16M9 3h6l1 4H8zM7 7l1 14h8l1-14M10 11v6M14 11v6"/></>,
  close: <><path d="m6 6 12 12M18 6 6 18"/></>,
  copy: <><rect x="8" y="8" width="11" height="11" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></>,
  check: <path d="m5 12 4 4L19 6"/>,
  alert: <><path d="M12 9v4M12 17h.01"/><path d="M10.3 3.7 2.6 17a2 2 0 0 0 1.7 3h15.4a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0Z"/></>,
  volume: <><path d="M11 5 6 9H3v6h3l5 4zM15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12"/></>,
  mic: <><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6"/></>,
  stop: <rect x="6" y="6" width="12" height="12" rx="2"/>,
  send: <><path d="m22 2-7 20-4-9-9-4zM22 2 11 13"/></>,
  play: <path d="m8 5 11 7-11 7z"/>,
  pause: <><path d="M9 5v14M15 5v14"/></>,
  search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
};

function Icon({ name, size = 18, className = "" }) {
  return (
    <svg
      aria-hidden="true"
      className={`line-icon ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

export default Icon;
