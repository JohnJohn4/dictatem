# Idea: Global Local Dictation Tool

**The Goal:**
I want to build a lightweight, invisible background app for Windows 11 that provides system-wide voice dictation. It needs to run completely offline and be faster than real-time.

**Hardware & Context:**
- OS: Windows 11
- CPU: AMD Ryzen 7 7800X3D
- GPU: NVIDIA RTX 4080 SUPER (16GB VRAM)
- RAM: 32GB
- The tool must heavily leverage this GPU to make transcription instantaneous. 

**Desired User Experience:**
1. I press a global hotkey (e.g., F12).
2. The app starts recording my microphone (maybe shows a tiny status indicator).
3. I speak freely.
4. I press the global hotkey again to stop.
5. The audio is instantly transcribed and automatically pasted into whatever window/application I currently have focused (Telegram, VS Code, Browser, etc.).

**Basic Questions I know need resolving (Help me figure these out):**
- What programming language is best for this so it runs invisibly with minimal overhead?
- Which specific Whisper implementation should we use to maximize the 4080 Super?
- How do we securely capture global hotkeys and handle the clipboard/pasting mechanics?