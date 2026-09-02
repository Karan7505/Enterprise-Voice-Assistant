import { useEffect, useRef } from "react";

const clampLevel = (level) =>
  Math.min(1, Math.max(0, Number(level) || 0));

const moveAudioParam = (param, value, context, timeConstant) => {
  const now = context.currentTime;
  if (typeof param.cancelAndHoldAtTime === "function") {
    param.cancelAndHoldAtTime(now);
  } else {
    const currentValue = param.value;
    param.cancelScheduledValues(now);
    param.setValueAtTime(currentValue, now);
  }
  param.setTargetAtTime(value, now, timeConstant);
};

const rampAudioParamToZero = (param, context, duration = 0.035) => {
  const now = context.currentTime;
  if (typeof param.cancelAndHoldAtTime === "function") {
    param.cancelAndHoldAtTime(now);
  } else {
    const currentValue = param.value;
    param.cancelScheduledValues(now);
    param.setValueAtTime(currentValue, now);
  }
  param.linearRampToValueAtTime(0, now + duration);
};

const createAirNoiseBuffer = (context) => {
  const frameCount = Math.floor(context.sampleRate * 8);
  const buffer = context.createBuffer(1, frameCount, context.sampleRate);
  const samples = buffer.getChannelData(0);
  const components = Array.from({ length: 24 }, () => ({
    // Integer cycle counts make this synthetic texture periodic at the loop
    // boundary, avoiding a click when the BufferSource repeats.
    cycles: Math.floor(2_400 + Math.random() * 13_600),
    amplitude: 0.2 + Math.random() * 0.8,
    phase: Math.random() * Math.PI * 2,
  }));
  const normalizer = components.reduce(
    (total, component) => total + component.amplitude,
    0,
  );

  for (let index = 0; index < frameCount; index += 1) {
    const cyclePosition = index / frameCount;
    const texture = components.reduce(
      (total, component) =>
        total +
        component.amplitude *
          Math.sin(Math.PI * 2 * component.cycles * cyclePosition + component.phase),
      0,
    );
    samples[index] = texture / normalizer;
  }

  return buffer;
};

function useOrbAmbientSound({
  isVisible,
  isAmbientIdle,
  isListening,
  isPlaying,
  isThinking,
}) {
  const graphRef = useRef(null);
  const stateRef = useRef({
    isVisible,
    isAmbientIdle,
    isListening,
    isPlaying,
    isThinking,
  });
  const unlockedRef = useRef(false);
  const ensureGraphRef = useRef(null);
  const syncGraphRef = useRef(null);
  const suspendTimerRef = useRef(null);
  const audibleTimerRef = useRef(null);
  const audibleReadyRef = useRef(false);
  const wasAudibleRef = useRef(false);

  useEffect(() => {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return undefined;

    let disposed = false;

    const canPlayAmbient = () => {
      const state = stateRef.current;
      return (
        state.isVisible &&
        state.isAmbientIdle &&
        !state.isListening &&
        !state.isPlaying &&
        !state.isThinking &&
        document.visibilityState === "visible"
      );
    };

    const clearSuspendTimer = () => {
      if (suspendTimerRef.current !== null) {
        window.clearTimeout(suspendTimerRef.current);
        suspendTimerRef.current = null;
      }
    };

    const clearAudibleTimer = () => {
      if (audibleTimerRef.current !== null) {
        window.clearTimeout(audibleTimerRef.current);
        audibleTimerRef.current = null;
      }
    };

    const disposeGraph = (graph) => {
      if (!graph) return;
      graph.context.onstatechange = null;
      graph.sources.forEach((source) => {
        try { source.stop(); } catch { /* already stopped */ }
      });
      graph.nodes.forEach((node) => {
        try { node.disconnect(); } catch { /* already disconnected */ }
      });
      if (graph.context.state !== "closed") {
        graph.context.close().catch(() => {});
      }
    };

    const recoverClosedGraph = (graph) => {
      if (!graph || disposed) return;
      clearSuspendTimer();
      clearAudibleTimer();
      audibleReadyRef.current = false;
      wasAudibleRef.current = false;
      if (graphRef.current === graph) {
        graphRef.current = null;
      }
      disposeGraph(graph);
      unlockedRef.current = false;
      addUnlockListeners();
    };

    const syncGraph = async () => {
      const graph = graphRef.current;
      if (!graph || disposed) return;

      if (graph.context.state === "closed") {
        recoverClosedGraph(graph);
        return;
      }

      const shouldBeAudible = canPlayAmbient();

      if (!shouldBeAudible) {
        clearSuspendTimer();
        clearAudibleTimer();
        audibleReadyRef.current = false;
        wasAudibleRef.current = false;
        rampAudioParamToZero(graph.masterGain.gain, graph.context, 0.015);
        if (graph.context.state === "running") {
          suspendTimerRef.current = window.setTimeout(() => {
            suspendTimerRef.current = null;
            if (
              !disposed &&
              graphRef.current === graph &&
              !canPlayAmbient() &&
              graph.context.state === "running"
            ) {
              graph.context.suspend().catch(() => {});
            }
          }, 220);
        }
        return;
      }

      clearSuspendTimer();
      if (!audibleReadyRef.current) {
        if (audibleTimerRef.current === null) {
          audibleTimerRef.current = window.setTimeout(() => {
            audibleTimerRef.current = null;
            if (
              !disposed &&
              canPlayAmbient()
            ) {
              audibleReadyRef.current = true;
              void syncGraph();
            }
          }, 300);
        }
        return;
      }

      if (graph.context.state !== "running") {
        try {
          await graph.context.resume();
        } catch {
          unlockedRef.current = false;
          addUnlockListeners();
          return;
        }
      }

      if (
        disposed ||
        !canPlayAmbient() ||
        graph.context.state !== "running"
      ) {
        return;
      }

      const targetGain = 0.028;
      const filterFrequency = 950;
      const gainTimeConstant = !wasAudibleRef.current
        ? 1.6
        : 0.25;

      moveAudioParam(
        graph.masterGain.gain,
        targetGain,
        graph.context,
        gainTimeConstant,
      );
      moveAudioParam(
        graph.filter.frequency,
        filterFrequency,
        graph.context,
        0.14,
      );
      moveAudioParam(
        graph.upperOscillator.detune,
        0,
        graph.context,
        0.18,
      );
      moveAudioParam(
        graph.airFilter.frequency,
        1150,
        graph.context,
        0.4,
      );
      moveAudioParam(
        graph.breathOscillator.frequency,
        0.075,
        graph.context,
        0.35,
      );
      moveAudioParam(
        graph.breathDepth.gain,
        0.08,
        graph.context,
        0.25,
      );
      moveAudioParam(
        graph.driftOscillator.frequency,
        0.021,
        graph.context,
        0.4,
      );
      moveAudioParam(
        graph.airOscillator.frequency,
        0.041,
        graph.context,
        0.45,
      );
      moveAudioParam(
        graph.airDepth.gain,
        0.06,
        graph.context,
        0.35,
      );
      wasAudibleRef.current = true;
    };

    const ensureGraph = async () => {
      if (disposed) return;
      if (graphRef.current?.context.state === "closed") {
        const closedGraph = graphRef.current;
        recoverClosedGraph(closedGraph);
      }
      if (graphRef.current) {
        try {
          if (graphRef.current.context.state !== "running") {
            await graphRef.current.context.resume();
          }
          await syncGraph();
          return graphRef.current?.context.state === "running";
        } catch {
          unlockedRef.current = false;
          addUnlockListeners();
          return false;
        }
      }

      let context = null;
      let sources = [];
      let nodes = [];
      try {
        try {
          context = new AudioContext({ latencyHint: "playback" });
        } catch {
          context = new AudioContext();
        }
        const masterGain = context.createGain();
        const energyGain = context.createGain();
        const filter = context.createBiquadFilter();
        const airFilter = context.createBiquadFilter();
        const airGain = context.createGain();
        const baseOscillator = context.createOscillator();
        const baseGain = context.createGain();
        const upperOscillator = context.createOscillator();
        const upperGain = context.createGain();
        const shimmerOscillator = context.createOscillator();
        const shimmerGain = context.createGain();
        const airSource = context.createBufferSource();
        const breathOscillator = context.createOscillator();
        const breathDepth = context.createGain();
        const driftOscillator = context.createOscillator();
        const driftDepth = context.createGain();
        const shimmerDriftDepth = context.createGain();
        const filterOscillator = context.createOscillator();
        const filterDepth = context.createGain();
        const airOscillator = context.createOscillator();
        const airDepth = context.createGain();
        const airFilterDepth = context.createGain();

        masterGain.gain.value = 0;
        energyGain.gain.value = 0.92;
        filter.type = "lowpass";
        filter.frequency.value = 950;
        filter.Q.value = 0.55;
        airFilter.type = "bandpass";
        airFilter.frequency.value = 1150;
        airFilter.Q.value = 0.65;
        airGain.gain.value = 0.2;

        baseOscillator.type = "sine";
        baseOscillator.frequency.value = 220;
        baseGain.gain.value = 0.42;

        upperOscillator.type = "sine";
        upperOscillator.frequency.value = 326.7;
        upperGain.gain.value = 0.13;

        shimmerOscillator.type = "sine";
        shimmerOscillator.frequency.value = 659.3;
        shimmerGain.gain.value = 0.035;

        airSource.buffer = createAirNoiseBuffer(context);
        airSource.loop = true;

        breathOscillator.type = "sine";
        breathOscillator.frequency.value = 0.075;
        breathDepth.gain.value = 0.08;

        driftOscillator.type = "sine";
        driftOscillator.frequency.value = 0.021;
        driftDepth.gain.value = 5.5;
        shimmerDriftDepth.gain.value = -3.5;

        filterOscillator.type = "sine";
        filterOscillator.frequency.value = 0.016;
        filterDepth.gain.value = 180;

        airOscillator.type = "sine";
        airOscillator.frequency.value = 0.041;
        airDepth.gain.value = 0.06;
        airFilterDepth.gain.value = 150;

        baseOscillator.connect(baseGain).connect(filter);
        upperOscillator.connect(upperGain).connect(filter);
        shimmerOscillator.connect(shimmerGain).connect(filter);
        airSource.connect(airFilter).connect(airGain).connect(energyGain);
        filter.connect(energyGain).connect(masterGain).connect(context.destination);
        breathOscillator.connect(breathDepth).connect(energyGain.gain);
        driftOscillator.connect(driftDepth).connect(upperOscillator.detune);
        driftOscillator
          .connect(shimmerDriftDepth)
          .connect(shimmerOscillator.detune);
        filterOscillator.connect(filterDepth).connect(filter.frequency);
        airOscillator.connect(airDepth).connect(airGain.gain);
        airOscillator.connect(airFilterDepth).connect(airFilter.frequency);

        sources = [
          baseOscillator,
          upperOscillator,
          shimmerOscillator,
          airSource,
          breathOscillator,
          driftOscillator,
          filterOscillator,
          airOscillator,
        ];
        sources.forEach((source) => source.start());
        nodes = [
          baseOscillator,
          baseGain,
          upperOscillator,
          upperGain,
          shimmerOscillator,
          shimmerGain,
          airSource,
          airFilter,
          airGain,
          breathOscillator,
          breathDepth,
          driftOscillator,
          driftDepth,
          shimmerDriftDepth,
          filterOscillator,
          filterDepth,
          airOscillator,
          airDepth,
          airFilterDepth,
          filter,
          energyGain,
          masterGain,
        ];

        graphRef.current = {
          context,
          masterGain,
          filter,
          airFilter,
          upperOscillator,
          breathOscillator,
          breathDepth,
          driftOscillator,
          airOscillator,
          airDepth,
          sources,
          nodes,
        };
        const graph = graphRef.current;
        context.onstatechange = () => {
          if (
            context.state === "closed" &&
            graphRef.current === graph
          ) {
            recoverClosedGraph(graph);
          }
        };

        if (context.state !== "running") {
          await context.resume();
        }
        await syncGraph();
        return context.state === "running";
      } catch {
        if (graphRef.current?.context === context) {
          graphRef.current = null;
        }
        if (context) {
          context.onstatechange = null;
        }
        sources.forEach((source) => {
          try { source.stop(); } catch { /* never started or already stopped */ }
        });
        nodes.forEach((node) => {
          try { node.disconnect(); } catch { /* already disconnected */ }
        });
        if (context && context.state !== "closed") {
          context.close().catch(() => {});
        }
        return false;
      }
    };

    const removeUnlockListeners = () => {
      document.removeEventListener("pointerdown", unlockAmbientSound, true);
      document.removeEventListener("keydown", unlockAmbientSound, true);
    };

    const markAmbientUnlocked = (didUnlock) => {
      if (didUnlock && !disposed) {
        unlockedRef.current = true;
        removeUnlockListeners();
      }
      return didUnlock;
    };

    const attemptAmbientStart = async () =>
      markAmbientUnlocked(await ensureGraph());

    let unlockInFlight = false;
    const unlockAmbientSound = async (event) => {
      if (
        unlockedRef.current ||
        unlockInFlight ||
        disposed ||
        !event.isTrusted
      ) {
        return;
      }

      unlockInFlight = true;
      await attemptAmbientStart();
      unlockInFlight = false;
    };

    const addUnlockListeners = () => {
      removeUnlockListeners();
      document.addEventListener("pointerdown", unlockAmbientSound, {
        capture: true,
        passive: true,
      });
      document.addEventListener("keydown", unlockAmbientSound, true);
    };

    const handleVisibilityChange = () => {
      void syncGraph();
    };

    const handlePageHide = () => {
      clearSuspendTimer();
      clearAudibleTimer();
      audibleReadyRef.current = false;
      wasAudibleRef.current = false;
      const graph = graphRef.current;
      if (!graph) return;
      graph.masterGain.gain.cancelScheduledValues(graph.context.currentTime);
      graph.masterGain.gain.setValueAtTime(0, graph.context.currentTime);
      if (graph.context.state === "running") {
        graph.context.suspend().catch(() => {});
      }
    };

    const handlePageShow = () => {
      void syncGraph();
    };

    ensureGraphRef.current = ensureGraph;
    syncGraphRef.current = syncGraph;
    addUnlockListeners();
    document.addEventListener("visibilitychange", handleVisibilityChange);
    window.addEventListener("pagehide", handlePageHide);
    window.addEventListener("pageshow", handlePageShow);
    if (stateRef.current.isVisible && document.visibilityState === "visible") {
      void attemptAmbientStart();
    }

    return () => {
      disposed = true;
      clearSuspendTimer();
      clearAudibleTimer();
      removeUnlockListeners();
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      window.removeEventListener("pagehide", handlePageHide);
      window.removeEventListener("pageshow", handlePageShow);
      ensureGraphRef.current = null;
      syncGraphRef.current = null;
      unlockedRef.current = false;

      const graph = graphRef.current;
      graphRef.current = null;
      disposeGraph(graph);
    };
  }, []);

  useEffect(() => {
    stateRef.current = {
      isVisible,
      isAmbientIdle,
      isListening,
      isPlaying,
      isThinking,
    };

    if (!unlockedRef.current) return;
    if (graphRef.current) {
      void syncGraphRef.current?.();
    } else {
      void ensureGraphRef.current?.();
    }
  }, [isAmbientIdle, isListening, isPlaying, isThinking, isVisible]);
}

function AudioVisualizer({
  isPlaying,
  isListening,
  isThinking,
  isVisible = true,
  isAmbientIdle = false,
  voiceLevel = 0,
}) {
  const state = isListening
    ? "listening"
    : isPlaying
      ? "speaking"
      : isThinking
        ? "thinking"
        : "idle";
  const reactiveLevel = isListening && isVisible
    ? clampLevel(voiceLevel)
    : 0;
  useOrbAmbientSound({
    isVisible,
    isAmbientIdle,
    isListening,
    isPlaying,
    isThinking,
  });
  const reactiveStyle = {
    "--voice-reactive-scale": (1 + reactiveLevel * 0.09).toFixed(4),
    "--voice-reactive-brightness": (
      (isListening ? 1.07 : 1) + reactiveLevel * 0.24
    ).toFixed(4),
    "--voice-reactive-saturation": (
      (isListening ? 1.03 : 1) + reactiveLevel * 0.14
    ).toFixed(4),
    "--voice-reactive-halo-opacity": (
      (isListening ? 0.08 : 0) + reactiveLevel * 0.34
    ).toFixed(4),
    "--voice-reactive-halo-blur": `${24 + reactiveLevel * 60}px`,
    "--voice-reactive-halo-scale": (
      1 + reactiveLevel * 0.065
    ).toFixed(4),
    "--voice-reactive-ring-scale": (
      1 + reactiveLevel * 0.06
    ).toFixed(4),
    "--voice-reactive-inner-brightness": (
      1 + reactiveLevel * 0.34
    ).toFixed(4),
    "--voice-reactive-halo-brightness": (
      1.08 + reactiveLevel * 0.35
    ).toFixed(4),
    "--voice-reactive-gradient-x": `${50 + reactiveLevel * 10}%`,
    "--voice-reactive-gradient-y": `${50 - reactiveLevel * 7}%`,
    "--voice-reactive-gradient-size": `${118 + reactiveLevel * 14}%`,
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
          <div className="ai-orb" />
        </div>
      </div>
    </section>
  );
}

export default AudioVisualizer;
