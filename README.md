# Jarvis Voice Assistant

A Python desktop voice assistant with speech recognition, spoken responses, and commands for common desktop actions and information lookup.

## Features
- Speech input and text-to-speech output
- English and Hindi language support as configured by the app
- Wikipedia lookup and commands to open websites or play media
- Tkinter interface

## Setup
Requires Python, a working microphone, speakers, and the packages imported by `jarvis.py`. Install the listed libraries:

```bash
python -m pip install SpeechRecognition pyttsx3 wikipedia langdetect pywhatkit vosk sounddevice
python jarvis.py
```

Some voice-recognition features may require an additional Vosk model. Check the model path expected by the script and configure it locally before using those features.

## Notes
Microphone, internet, and operating-system permissions affect available commands. Review commands before use; this is an educational personal-assistant demo.
