# Jarvis Voice Assistant

## Overview

Jarvis is a Python-based voice assistant that can recognize voice commands, respond with speech, open websites, search information, play media, launch applications, and support both English and Hindi languages.

## Features

* Voice Command Recognition
* Text-to-Speech Responses
* Hindi & English Language Support
* Wikipedia Search Integration
* Open Websites (YouTube, Google, GitHub, etc.)
* Play Music and Videos
* Launch & Close Applications
* GUI Interface with Animated Avatar
* Wake Word Detection ("Hello Jarvis")

## Technologies Used

* Python
* SpeechRecognition
* pyttsx3
* Wikipedia API
* Vosk Speech Recognition
* SoundDevice
* Tkinter GUI
* LangDetect

## Installation

1. Clone the repository:

```bash
git clone https://github.com/yourusername/jarvis-voice-assistant.git
```

2. Install dependencies:

```bash
pip install SpeechRecognition pyttsx3 wikipedia langdetect pywhatkit vosk sounddevice
```

3. Download the Vosk speech model and place it in:

```bash
models/vosk-model-small-en-us-0.15
```

4. Run the project:

```bash
python jarvis.py
```

## Usage

* Say "Hello Jarvis" to activate.
* Ask for the current time.
* Open websites like YouTube or Google.
* Search information about people or topics.
* Play music and videos.
* Launch supported applications.

## Project Structure

```
jarvis.py
models/
README.md
```

## Future Improvements

* Weather Information
* AI Chat Integration
* WhatsApp Messaging
* Smart Home Control
* Custom GUI Themes

## Author

Ayaan Ali
