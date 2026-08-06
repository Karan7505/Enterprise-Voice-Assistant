import { useEffect, useRef } from "react";

function AudioVisualizer({ isPlaying, isListening }) {
  const canvasRef = useRef(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    let animationFrameId;

    let step = 0;
    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const isActive = isPlaying || isListening;
      const barCount = 32;
      const barWidth = 4;
      const barGap = 6;
      const startX = (canvas.width - (barCount * (barWidth + barGap))) / 2;

      step += isActive ? 0.15 : 0.03;

      for (let i = 0; i < barCount; i++) {
        let height = 6;
        if (isActive) {
          height = Math.sin(step + i * 0.4) * 18 + Math.cos(step * 1.2 + i * 0.2) * 12 + 22;
          height = Math.max(6, Math.min(height, 54));
        }

        const x = startX + i * (barWidth + barGap);
        const y = (canvas.height - height) / 2;

        const gradient = ctx.createLinearGradient(0, y, 0, y + height);
        if (isListening) {
          gradient.addColorStop(0, "#ef4444");
          gradient.addColorStop(1, "#f97316");
        } else if (isPlaying) {
          gradient.addColorStop(0, "#3b82f6");
          gradient.addColorStop(1, "#8b5cf6");
        } else {
          gradient.addColorStop(0, "#475569");
          gradient.addColorStop(1, "#334155");
        }

        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.roundRect(x, y, barWidth, height, 3);
        ctx.fill();
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [isPlaying, isListening]);

  return (
    <div className="audio-visualizer-container">
      <div className="visualizer-status">
        {isListening ? (
          <span className="status-badge listening">
            <span className="dot pulse"></span> Listening...
          </span>
        ) : isPlaying ? (
          <span className="status-badge speaking">
            <span className="dot wave"></span> Speaking...
          </span>
        ) : (
          <span className="status-badge idle">
            <span className="dot"></span> Idle
          </span>
        )}
      </div>
      <canvas
        ref={canvasRef}
        width={360}
        height={60}
        className="visualizer-canvas"
      />
    </div>
  );
}

export default AudioVisualizer;
