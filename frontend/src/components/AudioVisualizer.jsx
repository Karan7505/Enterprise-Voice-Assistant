const clampLevel = (level) =>
  Math.min(1, Math.max(0, Number(level) || 0));

function AudioVisualizer({
  activity = "idle",
  isVisible = true,
  activityLevel = 0,
}) {
  const state = ["idle", "listening", "thinking", "speaking"].includes(activity)
    ? activity
    : "idle";
  const isListening = state === "listening";
  const isPlaying = state === "speaking";
  const isThinking = state === "thinking";
  const isAudioReactive = isListening || isPlaying;
  const reactiveLevel = isVisible && isAudioReactive
    ? clampLevel(activityLevel)
    : 0;
  const scaleStrength = isListening ? 0.18 : isPlaying ? 0.075 : 0;
  const brightnessBase = isListening ? 1.1 : isPlaying ? 1.04 : 1;
  const saturationBase = isListening ? 1.07 : isPlaying ? 1.03 : 1;
  const haloBase = isListening ? 0.16 : isPlaying ? 0.07 : 0;
  const reactiveStyle = {
    "--voice-reactive-scale": (1 + reactiveLevel * scaleStrength).toFixed(4),
    "--voice-reactive-brightness": (
      brightnessBase + reactiveLevel * 0.3
    ).toFixed(4),
    "--voice-reactive-saturation": (
      saturationBase + reactiveLevel * 0.17
    ).toFixed(4),
    "--voice-reactive-halo-opacity": (
      haloBase + reactiveLevel * 0.34
    ).toFixed(4),
    "--voice-reactive-halo-blur": `${24 + reactiveLevel * 64}px`,
    "--voice-reactive-halo-scale": (
      1 + reactiveLevel * (isListening ? 0.13 : 0.06)
    ).toFixed(4),
    "--voice-reactive-ring-scale": (
      1 + reactiveLevel * (isListening ? 0.1 : 0.05)
    ).toFixed(4),
    "--voice-reactive-inner-brightness": (
      1 + reactiveLevel * (isListening ? 0.52 : 0.28)
    ).toFixed(4),
    "--voice-reactive-halo-brightness": (
      1.06 + reactiveLevel * (isListening ? 0.54 : 0.3)
    ).toFixed(4),
    "--voice-reactive-gradient-x": `${50 + reactiveLevel * (isListening ? 16 : 9)}%`,
    "--voice-reactive-gradient-y": `${50 - reactiveLevel * (isListening ? 11 : 6)}%`,
    "--voice-reactive-gradient-size": `${118 + reactiveLevel * (isListening ? 24 : 11)}%`,
    "--liquid-wave-opacity": (
      0.24 +
      (isListening ? reactiveLevel * 0.52 : isPlaying ? reactiveLevel * 0.38 : isThinking ? 0.2 : 0)
    ).toFixed(4),
    "--liquid-wave-scale": (
      1 +
      (isListening ? reactiveLevel * 0.13 : isPlaying ? reactiveLevel * 0.06 : isThinking ? 0.05 : 0)
    ).toFixed(4),
    "--liquid-wave-speed": isListening
      ? "3.8s"
      : isThinking
        ? "6.5s"
        : isPlaying
          ? "7.5s"
          : "12s",
    "--liquid-wave-shift": `${reactiveLevel * (isListening ? 14 : isPlaying ? 8 : 4)}%`,
  };

  return (
    <section
      className={`audio-visualizer-container orb-${state}`}
      role="status"
      aria-live="polite"
      aria-label={`Assistant is ${state}`}
    >
      <div className="orb-reactive-shell" style={reactiveStyle}>
        <div className="orb-stage" aria-hidden="true">
          <span className="orb-ring" />
          <div className="ai-orb">
            <span className="orb-liquid-wave orb-liquid-wave-back" />
            <span className="orb-liquid-wave orb-liquid-wave-front" />
          </div>
        </div>
      </div>
    </section>
  );
}

export default AudioVisualizer;
