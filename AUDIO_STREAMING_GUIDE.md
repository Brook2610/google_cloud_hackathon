# Seamless Browser Audio Streaming Guide

A comprehensive guide on implementing smooth, stutter-free real-time audio playback in web applications. This technique is essential for voice assistants, real-time transcription, and any application streaming audio chunks from a server.

## Table of Contents

1. [The Problem](#the-problem)
2. [The Solution: Audio Scheduling](#the-solution-audio-scheduling)
3. [Implementation Details](#implementation-details)
4. [Code Examples](#code-examples)
5. [Common Pitfalls](#common-pitfalls)
6. [Best Practices](#best-practices)

---

## The Problem

When streaming audio from a server (like Gemini Live API, OpenAI Realtime, etc.), you receive audio in **chunks**. The naive approach is to play each chunk sequentially:

```javascript
// ❌ BAD: Causes choppy audio
async function playAudio(chunk) {
    const source = audioContext.createBufferSource();
    source.buffer = chunk;
    source.connect(audioContext.destination);
    source.onended = () => playNextChunk(); // Wait for this to finish
    source.start();
}
```

**Why this fails:**
- There's a tiny gap between when one chunk ends and the next starts
- JavaScript event callbacks have latency
- The `onended` event fires, then you process the next chunk, then you start it - all adding milliseconds of silence
- Result: **choppy, stuttering audio**

---

## The Solution: Audio Scheduling

The Web Audio API allows you to **schedule audio to play at a specific time in the future**. Instead of waiting for each chunk to finish, you schedule the next chunk to start exactly when the previous one ends.

```javascript
// ✅ GOOD: Seamless audio
let nextPlayTime = 0;

async function playAudioChunk(chunk) {
    const currentTime = audioContext.currentTime;
    
    // If we've fallen behind, catch up with a small buffer
    if (nextPlayTime <= currentTime) {
        nextPlayTime = currentTime + 0.02; // 20ms buffer
    }
    
    const source = audioContext.createBufferSource();
    source.buffer = chunk;
    source.connect(audioContext.destination);
    source.start(nextPlayTime); // Schedule for exact time
    
    // Next chunk plays right after this one
    nextPlayTime += chunk.duration;
}
```

**Why this works:**
- Audio is scheduled ahead of time with sample-accurate precision
- No gaps between chunks - they're mathematically adjacent
- The browser's audio subsystem handles the timing, not JavaScript

---

## Implementation Details

### 1. Separate Audio Contexts

Use separate `AudioContext` instances for recording and playback to avoid interference:

```javascript
let recordingContext = null;  // For microphone input
let playbackContext = null;   // For audio output

async function initPlaybackContext() {
    if (!playbackContext || playbackContext.state === 'closed') {
        playbackContext = new AudioContext({ sampleRate: 24000 }); // Match your audio rate
    }
    if (playbackContext.state === 'suspended') {
        await playbackContext.resume();
    }
}
```

### 2. Converting PCM to AudioBuffer

Server audio (like from Gemini) is typically raw PCM. Convert it to Web Audio format:

```javascript
function pcmToAudioBuffer(pcmBytes, sampleRate) {
    // PCM 16-bit signed integers
    const int16View = new Int16Array(pcmBytes.buffer);
    
    // Web Audio uses Float32 (-1.0 to 1.0)
    const float32Array = new Float32Array(int16View.length);
    for (let i = 0; i < int16View.length; i++) {
        float32Array[i] = int16View[i] / 32768; // Normalize to -1 to 1
    }
    
    // Create AudioBuffer
    const audioBuffer = audioContext.createBuffer(1, float32Array.length, sampleRate);
    audioBuffer.getChannelData(0).set(float32Array);
    
    return audioBuffer;
}
```

### 3. Handling Base64 Audio from WebSocket

If your server sends base64-encoded audio (common with JSON messages):

```javascript
function base64ToPcmBytes(base64Data) {
    const binaryString = atob(base64Data);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }
    return bytes;
}
```

### 4. Tracking Scheduled Sources (for Interrupts)

When the user interrupts, you need to stop all playing audio:

```javascript
let scheduledSources = [];

function playAudioChunk(audioBuffer) {
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    
    const startTime = nextPlayTime;
    source.start(startTime);
    
    // Track for cleanup
    scheduledSources.push({ source, endTime: startTime + audioBuffer.duration });
    
    nextPlayTime = startTime + audioBuffer.duration;
    
    // Remove from tracking when done
    source.onended = () => {
        scheduledSources = scheduledSources.filter(s => s.source !== source);
    };
}

function clearAllAudio() {
    scheduledSources.forEach(({ source }) => {
        try { source.stop(); } catch (e) {}
    });
    scheduledSources = [];
    nextPlayTime = 0;
}
```

---

## Code Examples

### Complete Playback Module

```javascript
class SeamlessAudioPlayer {
    constructor(sampleRate = 24000) {
        this.sampleRate = sampleRate;
        this.context = null;
        this.nextPlayTime = 0;
        this.scheduledSources = [];
        this.isPlaying = false;
    }

    async init() {
        if (!this.context || this.context.state === 'closed') {
            this.context = new AudioContext({ sampleRate: this.sampleRate });
        }
        if (this.context.state === 'suspended') {
            await this.context.resume();
        }
    }

    async playChunk(base64Data) {
        await this.init();

        // Decode base64 to bytes
        const binaryString = atob(base64Data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
            bytes[i] = binaryString.charCodeAt(i);
        }

        // Convert PCM 16-bit to Float32
        const int16View = new Int16Array(bytes.buffer);
        const float32Array = new Float32Array(int16View.length);
        for (let i = 0; i < int16View.length; i++) {
            float32Array[i] = int16View[i] / 32768;
        }

        // Create audio buffer
        const audioBuffer = this.context.createBuffer(1, float32Array.length, this.sampleRate);
        audioBuffer.getChannelData(0).set(float32Array);

        // Schedule playback
        const currentTime = this.context.currentTime;
        if (this.nextPlayTime <= currentTime) {
            this.nextPlayTime = currentTime + 0.02; // 20ms buffer
        }

        const source = this.context.createBufferSource();
        source.buffer = audioBuffer;
        source.connect(this.context.destination);
        source.start(this.nextPlayTime);

        this.scheduledSources.push({ source, endTime: this.nextPlayTime + audioBuffer.duration });
        this.nextPlayTime += audioBuffer.duration;
        this.isPlaying = true;

        source.onended = () => {
            this.scheduledSources = this.scheduledSources.filter(s => s.source !== source);
            if (this.scheduledSources.length === 0) {
                this.isPlaying = false;
            }
        };
    }

    stop() {
        this.scheduledSources.forEach(({ source }) => {
            try { source.stop(); } catch (e) {}
        });
        this.scheduledSources = [];
        this.nextPlayTime = 0;
        this.isPlaying = false;
    }

    async close() {
        this.stop();
        if (this.context) {
            await this.context.close();
            this.context = null;
        }
    }
}

// Usage:
const player = new SeamlessAudioPlayer(24000);

ws.onmessage = async (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'audio') {
        await player.playChunk(msg.data);
    } else if (msg.type === 'interrupted') {
        player.stop();
    }
};
```

### Recording Module (Microphone to Server)

```javascript
class AudioRecorder {
    constructor(sampleRate = 16000) {
        this.sampleRate = sampleRate;
        this.context = null;
        this.processor = null;
        this.stream = null;
        this.onAudioData = null; // Callback for audio chunks
    }

    async start() {
        this.stream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: this.sampleRate,
                channelCount: 1,
                echoCancellation: true,
                noiseSuppression: true,
            }
        });

        this.context = new AudioContext({ sampleRate: this.sampleRate });
        const source = this.context.createMediaStreamSource(this.stream);

        // Use smaller buffer for lower latency
        this.processor = this.context.createScriptProcessor(2048, 1, 1);
        
        this.processor.onaudioprocess = (e) => {
            if (!this.onAudioData) return;

            const inputData = e.inputBuffer.getChannelData(0);
            
            // Convert Float32 to Int16 PCM
            const int16Array = new Int16Array(inputData.length);
            for (let i = 0; i < inputData.length; i++) {
                const s = Math.max(-1, Math.min(1, inputData[i]));
                int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }

            this.onAudioData(int16Array.buffer);
        };

        source.connect(this.processor);
        this.processor.connect(this.context.destination);
    }

    stop() {
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }
        if (this.stream) {
            this.stream.getTracks().forEach(track => track.stop());
            this.stream = null;
        }
        if (this.context) {
            this.context.close();
            this.context = null;
        }
    }
}

// Usage:
const recorder = new AudioRecorder(16000);
recorder.onAudioData = (buffer) => {
    ws.send(buffer); // Send binary PCM to server
};
await recorder.start();
```

---

## Common Pitfalls

### 1. AudioContext Autoplay Policy

Browsers block audio until user interaction:

```javascript
// ❌ BAD: May be blocked
const ctx = new AudioContext(); // Might be suspended

// ✅ GOOD: Resume on user interaction
button.addEventListener('click', async () => {
    await audioContext.resume();
    startStreaming();
});
```

### 2. Sample Rate Mismatch

Ensure your AudioContext sample rate matches the incoming audio:

```javascript
// If server sends 24kHz audio
const playbackContext = new AudioContext({ sampleRate: 24000 });

// If server sends 16kHz audio  
const playbackContext = new AudioContext({ sampleRate: 16000 });
```

### 3. Buffer Underrun

If chunks arrive too slowly, you'll hear gaps. Add a small buffer:

```javascript
if (nextPlayTime <= currentTime) {
    nextPlayTime = currentTime + 0.02; // 20ms safety buffer
}
```

### 4. Memory Leaks

Always clean up sources and track them:

```javascript
source.onended = () => {
    scheduledSources = scheduledSources.filter(s => s.source !== source);
};
```

### 5. Sharing AudioContext

Don't share context between recording and playback:

```javascript
// ❌ BAD: Can cause feedback issues
const sharedContext = new AudioContext();

// ✅ GOOD: Separate contexts
const recordingContext = new AudioContext({ sampleRate: 16000 });
const playbackContext = new AudioContext({ sampleRate: 24000 });
```

---

## Best Practices

### 1. Buffer Size for Recording

- **2048**: Lower latency, good for real-time
- **4096**: More stable, slightly higher latency
- **1024**: Minimum, may cause issues on slow devices

### 2. Scheduling Buffer

The "catch-up" buffer should be small but not zero:

```javascript
// Too small: Risk of gaps if JS is slow
nextPlayTime = currentTime + 0.01; // 10ms - risky

// Good balance
nextPlayTime = currentTime + 0.02; // 20ms - recommended

// Too large: Noticeable latency
nextPlayTime = currentTime + 0.1; // 100ms - too much
```

### 3. Handle Interruptions Gracefully

When user speaks (interrupts AI), stop all scheduled audio immediately:

```javascript
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    if (msg.type === 'interrupted') {
        player.stop(); // Clear all scheduled audio
    }
};
```

### 4. Visualizer Sync

Tie visualizer state to actual playback:

```javascript
source.onended = () => {
    if (scheduledSources.length === 0) {
        setVisualizerActive(false);
    }
};
```

### 5. Error Handling

Wrap audio operations in try-catch:

```javascript
try {
    source.stop();
} catch (e) {
    // Source might have already ended
}
```

---

## Server-Side Considerations

### FastAPI WebSocket Example

When sending audio from server:

```python
import base64

# Send audio as base64 JSON
await websocket.send_json({
    "type": "audio",
    "data": base64.b64encode(audio_bytes).decode("utf-8")
})

# Or send raw binary (more efficient, but need different handling)
await websocket.send_bytes(audio_bytes)
```

### Gemini Live API Integration

```python
async for response in turn:
    sc = getattr(response, "server_content", None)
    model_turn = getattr(sc, "model_turn", None)
    if model_turn:
        for part in getattr(model_turn, "parts", []) or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                # Send to browser
                await websocket.send_json({
                    "type": "audio",
                    "data": base64.b64encode(inline.data).decode("utf-8")
                })
```

---

## Summary

| Technique | Purpose |
|-----------|---------|
| **Audio Scheduling** | Eliminate gaps between chunks |
| **Separate Contexts** | Prevent recording/playback interference |
| **Source Tracking** | Enable clean interruption handling |
| **Small Buffer** | Balance latency vs. stability |
| **PCM Conversion** | Properly handle server audio format |

The key insight is: **never wait for audio to finish - schedule it ahead of time**.

---

## References

- [Web Audio API - MDN](https://developer.mozilla.org/en-US/docs/Web/API/Web_Audio_API)
- [AudioBufferSourceNode.start()](https://developer.mozilla.org/en-US/docs/Web/API/AudioBufferSourceNode/start)
- [AudioContext.currentTime](https://developer.mozilla.org/en-US/docs/Web/API/BaseAudioContext/currentTime)
