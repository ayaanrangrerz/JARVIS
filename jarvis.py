import os
import datetime
import webbrowser
import sys
import traceback
import threading
import time

# Voice-only mode: require these packages
try:
    import speech_recognition as sr
except ImportError:
    print("Missing dependency: SpeechRecognition. Install with: pip install SpeechRecognition")
    sys.exit(1)

try:
    import pyttsx3
except ImportError:
    print("Missing dependency: pyttsx3. Install with: pip install pyttsx3")
    sys.exit(1)

try:
    import wikipedia
    HAS_WIKIPEDIA = True
except Exception:
    wikipedia = None
    HAS_WIKIPEDIA = False

# Language mode: 'en' or 'hi' (default)
LANGUAGE = 'hi'
# Current detected language (updates per utterance)
CURRENT_LANG = LANGUAGE
# Optional forced microphone device index; set to an int to override auto-selection
# Set to None to auto-select the best available input device.
FORCE_INPUT_DEVICE = None

# If default LANGUAGE is Hindi, try to set wikipedia language to Hindi initially
if LANGUAGE == 'hi' and HAS_WIKIPEDIA:
    try:
        wikipedia.set_lang('hi')
    except Exception:
        pass

from langdetect import detect

try:
    import pywhatkit
    HAS_PYWHATKIT = True
except Exception:
    pywhatkit = None
    HAS_PYWHATKIT = False

# Vosk offline ASR setup
from vosk import Model, KaldiRecognizer
import sounddevice as sd
import json
import subprocess
import shlex


def get_current_input_device():
    dev = sd.default.device
    try:
        pair = tuple(dev)
        if len(pair) > 0:
            return pair[0]
    except Exception:
        pass
    return dev


def set_input_device(index):
    try:
        sd.default.device = index
        print(f"Using input device {index}")
        return True
    except Exception as e:
        print(f"Invalid input device {index}: {e}")
        return False


def select_input_device_by_rms(sample_seconds=0.5):
    """Select the best input device, preferring real microphones over loopback devices."""
    if FORCE_INPUT_DEVICE is not None:
        if set_input_device(FORCE_INPUT_DEVICE):
            return FORCE_INPUT_DEVICE
        print(f"Forced device {FORCE_INPUT_DEVICE} not available, scanning available devices...")

    try:
        devices = sd.query_devices()
        mic_candidates = []
        fallback_candidates = []
        for i, d in enumerate(devices):
            if d.get('max_input_channels', 0) <= 0:
                continue
            name = (d.get('name') or '').lower()
            if any(x in name for x in ('sound mapper', 'speaker', 'stereo', 'mix', 'output', 'loopback', 'playback')):
                continue
            if any(x in name for x in ('microphone', 'mic', 'input', 'usb', 'array')):
                mic_candidates.append((i, d.get('name')))
            else:
                fallback_candidates.append((i, d.get('name')))

        def test_device(index):
            try:
                samplerate = int(sd.query_devices(index).get('default_samplerate', 16000))
                print(f"Testing device {index} with samplerate {samplerate}")
                recording = sd.rec(int(sample_seconds * samplerate), samplerate=samplerate, channels=1, dtype='int16', device=index)
                sd.wait()
                import numpy as _np
                arr = recording.flatten().astype(_np.int32)
                rms = float((_np.square(arr.astype(_np.float64)).mean())**0.5)
                return rms
            except Exception as e:
                print(f"Test failed for device {index}: {e}")
                return None

        best_device = None
        best_rms = -1.0
        for i, name in mic_candidates:
            rms = test_device(i)
            if rms is not None and rms > best_rms:
                best_device = (i, name, rms)
                best_rms = rms
        if best_device:
            i, name, rms = best_device
            print(f"Selected mic device {i}: {name} (rms={rms:.2f})")
            return i

        for i, name in fallback_candidates:
            rms = test_device(i)
            if rms is not None and rms > best_rms:
                best_device = (i, name, rms)
                best_rms = rms
        if best_device:
            i, name, rms = best_device
            print(f"Selected fallback device {i}: {name} (rms={rms:.2f})")
            return i

    except Exception as e:
        print('select_input_device_by_rms error:', e)
    return None

# Try to auto-select best input device at startup by brief scan
select_input_device_by_rms()

# GUI imports
try:
    import tkinter as tk
    from tkinter import font
    HAS_GUI = True
except:
    HAS_GUI = False

MODEL_PATH = "models/vosk-model-small-en-us-0.15"
VOSK_MODEL = None

def get_vosk_model():
    global VOSK_MODEL
    if VOSK_MODEL is None:
        if not os.path.isdir(MODEL_PATH):
            return None
        try:
            VOSK_MODEL = Model(MODEL_PATH)
        except Exception as e:
            print(f"Failed to load Vosk model: {e}")
            VOSK_MODEL = None
    return VOSK_MODEL

# Text-to-Speech Engine (required)
engine = pyttsx3.init()
engine.setProperty('rate', 150)

# On Windows, set to use the default speaker
try:
    if sys.platform == 'win32':
        engine.setProperty('volume', 1.0)
except:
    pass

# Global GUI flag
gui_window = None
speaking_flag = False
opened_procs = {}
last_opened = None

def create_gui():
    """Create a simple GUI window with Jarvis avatar"""
    global gui_window
    if not HAS_GUI:
        return None
    
    try:
        root = tk.Tk()
        root.title("Jarvis Assistant")
        root.geometry("400x500")
        root.configure(bg='#0a0e27')
        
        # Title
        title_font = font.Font(family="Helvetica", size=16, weight="bold")
        title_label = tk.Label(root, text="JARVIS", font=title_font, bg='#0a0e27', fg='#00ff00')
        title_label.pack(pady=10)
        
        # Avatar area (animated circle)
        canvas = tk.Canvas(root, width=300, height=300, bg='#0a0e27', highlightthickness=0)
        canvas.pack(pady=20)
        
        # Draw avatar circle
        avatar_id = canvas.create_oval(75, 75, 225, 225, fill='#1a1f3a', outline='#00ff00', width=3)
        
        # Text display area
        text_frame = tk.Frame(root, bg='#0a0e27')
        text_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)
        
        text_display = tk.Label(
            text_frame,
            text="Ready to assist...",
            bg='#0a0e27',
            fg='#00ff00',
            font=("Courier", 10),
            wraplength=350,
            justify=tk.CENTER
        )
        text_display.pack()
        
        root.after(100, root.lift)
        
        return {
            'root': root,
            'canvas': canvas,
            'avatar_id': avatar_id,
            'text_display': text_display
        }
    except Exception as e:
        print(f"GUI creation failed: {e}")
        return None


def open_url(url):
    """Open a URL reliably across platforms."""
    try:
        if sys.platform == 'win32':
            # os.startfile is the most direct way on Windows
            try:
                os.startfile(url)
                return True
            except Exception:
                # Fallback to PowerShell Start-Process
                try:
                    subprocess.run(["powershell", "-Command", f"Start-Process \"{url}\""], check=True)
                    return True
                except Exception:
                    return False
        else:
            return webbrowser.open(url, new=2)
    except Exception:
        try:
            return webbrowser.open(url, new=2)
        except Exception:
            return False

def update_gui_text(gui, text):
    """Update GUI with text"""
    if gui and 'text_display' in gui:
        try:
            gui['text_display'].config(text=text)
            gui['root'].update()
        except:
            pass

def animate_speaking(gui):
    """Animate avatar while speaking"""
    if not gui:
        return
    
    try:
        canvas = gui['canvas']
        avatar_id = gui['avatar_id']
        for i in range(5):
            if not speaking_flag:
                break
            canvas.itemconfig(avatar_id, fill='#00ff00')
            gui['root'].update()
            time.sleep(0.15)
            canvas.itemconfig(avatar_id, fill='#1a1f3a')
            gui['root'].update()
            time.sleep(0.15)
    except:
        pass

def speak(text, gui=None):
    """Speak text and show on GUI"""
    global speaking_flag
    speaking_flag = True
    
    print("Jarvis:", text)
    update_gui_text(gui, f"Jarvis: {text}")
    
    # Try Windows PowerShell TTS first (most reliable)
    if sys.platform == 'win32':
        try:
            animate_speaking(gui)
            # Use PowerShell for reliable Windows TTS
            ps_cmd = f'''Add-Type -AssemblyName System.Speech; $speak = New-Object System.Speech.Synthesis.SpeechSynthesizer; $speak.Volume = 100; $speak.Rate = -2; $speak.Speak('{text.replace("'", "''")}')'''
            os.system(f'powershell.exe -Command "{ps_cmd}"')
            speaking_flag = False
            return
        except Exception as e:
            print(f"PowerShell TTS Error: {e}")
    
    # Fallback to pyttsx3
    if engine:
        try:
            animate_speaking(gui)
            engine.say(text)
            engine.runAndWait()
        except Exception as e:
            print(f"pyttsx3 TTS Error: {e}")
    
    speaking_flag = False
    update_gui_text(gui, "Listening...")

def take_command(gui=None):
    """Record audio and convert to text. Uses Google SR for Hindi, Vosk for English."""
    samplerate = 16000
    global CURRENT_LANG

    # Hindi mode: use speech_recognition with Google API (language hi-IN)
    if 'sr' in globals() and sr is not None:
        recognizer = sr.Recognizer()
        update_gui_text(gui, "Sunn raha hoon...")
        # Speak prompt in current language
        if CURRENT_LANG == 'hi':
            speak("Sunn raha hoon", gui)
        else:
            speak("Listening", gui)
        try:
            duration = 5
            input_device = get_current_input_device()
            print(f"take_command listening on device {input_device}")
            recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16', device=input_device)
            sd.wait()
            audio_data = sr.AudioData(recording.tobytes(), samplerate, 2)
            # Try Hindi first
            text_hi = ''
            text_en = ''
            try:
                text_hi = recognizer.recognize_google(audio_data, language='hi-IN')
            except Exception:
                text_hi = ''
            try:
                text_en = recognizer.recognize_google(audio_data, language='en-US')
            except Exception:
                text_en = ''

            chosen = ''
            chosen_lang = ''
            if text_hi and text_en:
                # choose longer result
                chosen = text_hi if len(text_hi) >= len(text_en) else text_en
            elif text_hi:
                chosen = text_hi
            elif text_en:
                chosen = text_en

            if chosen:
                chosen = chosen.lower()
                # detect language
                try:
                    lang = detect(chosen)
                    if lang.startswith('hi'):
                        CURRENT_LANG = 'hi'
                    else:
                        CURRENT_LANG = 'en'
                except Exception:
                    # fallback: if we used hi recognition prefer hi
                    if text_hi:
                        CURRENT_LANG = 'hi'
                    else:
                        CURRENT_LANG = 'en'

                print("You said:", chosen)
                update_gui_text(gui, f"You said: {chosen}")
                return chosen
            else:
                # No recognition
                if CURRENT_LANG == 'hi':
                    speak("Samajh nahi aaya, kripya phir se bolen.", gui)
                else:
                    speak("I didn't catch that. Please repeat.", gui)
                return ""
        except Exception as e:
            speak("Microphone error.", gui)
            traceback.print_exc()
            return ""

    # Default / English: use Vosk model
    if not os.path.isdir(MODEL_PATH):
        speak("Speech model not found. Please download the model.", gui)
        return ""

    model = Model(MODEL_PATH)
    rec = KaldiRecognizer(model, samplerate)

    update_gui_text(gui, "Listening...")
    speak("Listening", gui)
    try:
        duration = 5  # seconds to listen per attempt
        recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16')
        sd.wait()
        data = recording.tobytes()
        if rec.AcceptWaveform(data):
            res = rec.Result()
        else:
            res = rec.FinalResult()
        res_json = json.loads(res)
        text = res_json.get('text', '')
        if text:
            print("You said:", text)
            update_gui_text(gui, f"You said: {text}")
            return text.lower()
        else:
            # Hindi message if CURRENT_LANG=='hi'
            if CURRENT_LANG == 'hi':
                speak("Samajh nahi aaya, kripya phir se bolen.", gui)
            else:
                speak("I didn't catch that. Please repeat.", gui)
            return ""
    except Exception as e:
        speak("Microphone or audio device error.", gui)
        traceback.print_exc()
        return ""

def run_jarvis(gui=None):
    """Main JARVIS logic with smart command handling"""
    command = take_command(gui)

    if not command:
        return

    # Greeting
    if any(word in command for word in ["hello", "hi", "hey", "namaste"]):
        if CURRENT_LANG == 'hi':
            speak("Namaste Ayaan, main aapki kaise madad karoon?", gui)
        else:
            speak("Hello Ayaan, how can I help you?", gui)

    # Time
    elif any(word in command for word in ["time", "what time", "current time"]):
        current_time = datetime.datetime.now().strftime("%I:%M %p")
        if CURRENT_LANG == 'hi':
            speak(f"Vartmaan samay hai {current_time}", gui)
        else:
            speak(f"The current time is {current_time}", gui)

    # Open website/app - smart parsing
    elif "open" in command:
        # Extract what to open: "open youtube" -> "youtube"
        parts = command.split("open")
        if len(parts) > 1:
            to_open = parts[1].strip().lower()
            
            # Map common app/site names
            url_map = {
                "youtube": "https://www.youtube.com",
                "google": "https://www.google.com",
                "facebook": "https://www.facebook.com",
                "twitter": "https://www.twitter.com",
                "instagram": "https://www.instagram.com",
                "whatsapp": "https://www.whatsapp.com",
                "gmail": "https://www.gmail.com",
                "github": "https://www.github.com",
                "linkedin": "https://www.linkedin.com",
                "reddit": "https://www.reddit.com",
                "wikipedia": "https://www.wikipedia.org",
                "amazon": "https://www.amazon.com",
                "ebay": "https://www.ebay.com",
                "netflix": "https://www.netflix.com",
            }
            
            # Check if it's a known site
            if to_open in url_map:
                url = url_map[to_open]
                if CURRENT_LANG == 'hi':
                    speak(f"{to_open} khol raha hoon", gui)
                else:
                    speak(f"Opening {to_open}", gui)
                try:
                    ok = open_url(url)
                    if not ok:
                        speak(f"I couldn't open {to_open}.", gui)
                except Exception:
                    speak(f"I couldn't open {to_open}.", gui)
            else:
                # Try as generic URL or search
                if "." in to_open or to_open.startswith("http"):
                    url = to_open if to_open.startswith("http") else f"https://{to_open}"
                    speak(f"Opening {to_open}", gui)
                    try:
                        ok = open_url(url)
                        last_opened = 'browser'
                        if not ok:
                            speak(f"I couldn't open {to_open}.", gui)
                    except Exception:
                        speak(f"I couldn't open {to_open}.", gui)
                else:
                    # Search for it
                    if CURRENT_LANG == 'hi':
                        speak(f"{to_open} ki khoj kar raha hoon", gui)
                    else:
                        speak(f"Searching for {to_open}", gui)
                    search_url = f"https://www.google.com/search?q={to_open.replace(' ', '+')}"
                    try:
                        ok = open_url(search_url)
                        last_opened = 'browser'
                        if not ok:
                            speak(f"I couldn't search for {to_open}.", gui)
                    except Exception:
                        speak(f"I couldn't search for {to_open}.", gui)

    # Search/Tell about person or thing
    elif any(word in command for word in ["who is", "what is", "tell me about", "search", "find"]):
        # Extract the query
        query = command
        for keyword in ["who is", "what is", "tell me about", "search", "find"]:
            if keyword in command:
                query = command.split(keyword)[1].strip()
                break
        
        if CURRENT_LANG == 'hi':
            speak(f"{query} ki khoj kar raha hoon", gui)
        else:
            speak(f"Searching for {query}", gui)
        
        # Try Wikipedia first
        if HAS_WIKIPEDIA:
            try:
                try:
                    if CURRENT_LANG == 'hi':
                        wikipedia.set_lang('hi')
                    else:
                        wikipedia.set_lang('en')
                except Exception:
                    pass
                info = wikipedia.summary(query, sentences=3)
                speak(info, gui)
            except:
                # If Wikipedia fails, do a Google search
                if CURRENT_LANG == 'hi':
                    speak(f"Main Google par {query} khoj raha hoon", gui)
                else:
                    speak(f"Let me search Google for {query}", gui)
                search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                try:
                    webbrowser.open(search_url)
                except Exception:
                    speak(f"I couldn't find information about {query}.", gui)
        else:
            # No Wikipedia, use Google search
            if CURRENT_LANG == 'hi':
                speak(f"Main Google par {query} khoj raha hoon", gui)
            else:
                speak(f"Let me search Google for {query}", gui)
            search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
            try:
                webbrowser.open(search_url)
            except Exception:
                speak(f"I couldn't find information about {query}.", gui)

    # Play music/video
    elif any(word in command for word in ["play", "music", "song", "video"]):
        # Extract what to play
        parts = command.split("play")
        if len(parts) > 1:
            to_play = parts[1].strip().lower()
            if CURRENT_LANG == 'hi':
                speak(f"{to_play} YouTube par chala raha hoon", gui)
            else:
                speak(f"Playing {to_play} on YouTube", gui)
            search_url = f"https://www.youtube.com/results?search_query={to_play.replace(' ', '+')}"
            try:
                ok = open_url(search_url)
                last_opened = 'browser'
                if not ok:
                    speak(f"I couldn't play {to_play}.", gui)
            except Exception:
                speak(f"I couldn't play {to_play}.", gui)

    # Launch or close specific apps
    elif any(word in command for word in ["launch", "start app", "open app", "run app"]):
        # Example: "launch notepad" or "open app calculator"
        parts = command.replace('launch', '').replace('start app','').replace('open app','').replace('run app','').strip()
        if parts:
            launch_target(parts, gui)

    elif any(word in command for word in ["close", "kill", "terminate", "stop app"]):
        # Example: "close notepad" or "close browser"
        parts = command
        for k in ['close','kill','terminate','stop app']:
            parts = parts.replace(k, '')
        target = parts.strip()
        if target:
            close_target(target, gui)

    # Exit/Stop
    elif any(word in command for word in ["stop", "exit", "quit", "bye", "goodbye"]):
        if CURRENT_LANG == 'hi':
            speak("Alvida! Aapse baat karke accha laga.", gui)
        else:
            speak("Goodbye! It was nice talking to you.", gui)
        if gui:
            gui['root'].after(1000, gui['root'].quit)
        else:
            sys.exit(0)

    # If no keyword matched, try to be helpful
    else:
        if CURRENT_LANG == 'hi':
            speak("Maaf kijiye, main samajh nahi paaya. Kaho: open YouTube, who is Einstein, play music, ya stop.", gui)
        else:
            speak("Sorry, I didn't understand. Try saying: open YouTube, who is Einstein, play music, or stop.", gui)

    return command


def launch_target(name, gui=None):
    """Launch an application by name (limited mapping)"""
    nm = name.lower()
    app_map = {
        'notepad': 'notepad.exe',
        'calculator': 'calc.exe',
        'cmd': 'cmd.exe',
        'vscode': r'C:\\Users\\ayaan\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe',
        'chrome': r'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
        'firefox': r'C:\\Program Files\\Mozilla Firefox\\firefox.exe',
    }
    if nm in app_map:
        exe = app_map[nm]
        try:
            proc = subprocess.Popen([exe])
            opened_procs[nm] = proc
            if CURRENT_LANG == 'hi':
                speak(f"{nm} shuru kar diya", gui)
            else:
                speak(f"Launched {nm}", gui)
        except Exception as e:
            if CURRENT_LANG == 'hi':
                speak(f"{nm} shuru nahi kar paaya: {e}", gui)
            else:
                speak(f"Couldn't launch {nm}: {e}", gui)
    else:
        # Fallback: try opening as URL or search
        if "." in nm or nm.startswith('http'):
            url = nm if nm.startswith('http') else f"https://{nm}"
            webbrowser.open(url)
            if CURRENT_LANG == 'hi':
                speak(f"{nm} khol diya", gui)
            else:
                speak(f"Opened {nm}", gui)
        else:
            # search
            webbrowser.open(f"https://www.google.com/search?q={nm.replace(' ','+')}")
            if CURRENT_LANG == 'hi':
                speak(f"{nm} ki khoj kar raha hoon", gui)
            else:
                speak(f"Searching for {nm}", gui)


def close_target(name, gui=None):
    nm = name.lower()
    # If we have a launched process tracked, terminate it
    if nm in opened_procs:
        proc = opened_procs.pop(nm)
        try:
            proc.terminate()
            if CURRENT_LANG == 'hi':
                speak(f"{nm} band kar diya", gui)
            else:
                speak(f"Closed {nm}", gui)
        except Exception:
            if CURRENT_LANG == 'hi':
                speak(f"{nm} bandh nahi kar paya", gui)
            else:
                speak(f"Couldn't close {nm}", gui)
        return

    # If user asked to close browser or youtube, attempt to kill common browser processes
    if 'browser' in nm or 'chrome' in nm or 'youtube' in nm or 'edge' in nm or 'firefox' in nm:
        procs = ['chrome.exe','msedge.exe','firefox.exe']
        for p in procs:
            try:
                subprocess.run(['taskkill','/IM',p,'/F'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
        if CURRENT_LANG == 'hi':
            speak("Browser band kar diya", gui)
        else:
            speak("Closed browser windows", gui)
        return

    speak(f"I don't know how to close {name}", gui)


def is_wake_phrase(text):
    text = (text or '').lower()
    if not text:
        return False
    keywords = ['jarvis', 'hello', 'hi']
    if any(word in text for word in keywords):
        return True
    # fuzzy fallback for common misrecognitions
    fuzzy = ['hell', 'jarv', 'hello of', 'hello died', 'jarvish']
    return any(word in text for word in fuzzy)


def wait_for_wake(gui=None):
    """Passive wait for wake words; returns when wake word heard."""
    # Use default LANGUAGE preference for idle prompts
    if LANGUAGE == 'hi':
        speak("Jab aap tayaar ho to 'Hello Jarvis' kaho.", gui)
    else:
        speak("Say 'Hello Jarvis' to wake me.", gui)

    model = get_vosk_model()
    if model is None:
        speak("Speech model not found. Please download the Vosk model.", gui)
        return

    samplerate = 16000
    wake_grammar = '["hello jarvis", "jarvis", "hello", "hi jarvis", "hi", "hey jarvis", "hey"]'

    while True:
        text = ''
        data = b''
        try:
            rec = KaldiRecognizer(model, samplerate, wake_grammar)
            duration = 3
            input_device = get_current_input_device()
            print(f"wait_for_wake listening on device {input_device}")
            recording = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1, dtype='int16', device=input_device)
            sd.wait()
            data = recording.tobytes()
            if rec.AcceptWaveform(data):
                res = rec.Result()
            else:
                res = rec.FinalResult()
            res_json = json.loads(res)
            text = res_json.get('text', '').lower().strip()
            if not text:
                partial_json = json.loads(rec.PartialResult())
                text = partial_json.get('partial', '').lower().strip()
            print(f"[wake] Vosk result: {res} -> '{text}'")
        except Exception as e:
            print('[wake] Vosk error:', e)
            text = ''
            data = b''

        # If Vosk produced nothing, try Google SR as a fallback (if available)
        if not text and 'sr' in globals() and sr is not None and data:
            try:
                recognizer = sr.Recognizer()
                audio_data = sr.AudioData(data, samplerate, 2)
                try:
                    text = recognizer.recognize_google(audio_data, language='en-US').lower()
                except Exception:
                    try:
                        text = recognizer.recognize_google(audio_data, language='hi-IN').lower()
                    except Exception:
                        text = ''
                if text:
                    print(f"[wake] SR fallback -> '{text}'")
            except Exception as e:
                print('[wake] SR fallback error:', e)

        if is_wake_phrase(text):
            if LANGUAGE == 'hi':
                speak('Haan?', gui)
            else:
                speak('Yes?', gui)
            return

def main():
    """Main loop with GUI or console mode."""
    global gui_window
    gui_window = create_gui() if HAS_GUI else None

    def voice_loop(gui=None):
        try:
            while True:
                wait_for_wake(gui)
                if gui:
                    if CURRENT_LANG == 'hi':
                        speak('Main sun raha hoon. Koi hukm bataiye.', gui)
                    else:
                        speak('I am listening. Tell me a command.', gui)
                else:
                    if CURRENT_LANG == 'hi':
                        speak('Main sun raha hoon. Koi hukm bataiye.')
                    else:
                        speak('I am listening. Tell me a command.')

                while True:
                    cmd = run_jarvis(gui)
                    if not cmd:
                        continue
                    if any(k in cmd for k in ['sleep', 'stop listening', 'go to sleep']):
                        if CURRENT_LANG == 'hi':
                            speak("Sone ja raha hoon. Jarvis ko jagane ke liye 'Hello Jarvis' kaho.", gui)
                        else:
                            speak('Going to sleep. Say Hello Jarvis to wake me.', gui)
                        break
                    time.sleep(0.5)
        except KeyboardInterrupt:
            if CURRENT_LANG == 'hi':
                speak("Band kar raha hoon. Alvida!", gui)
            else:
                speak("Shutting down. Goodbye!", gui)
            sys.exit(0)

    if gui_window:
        thread = threading.Thread(target=voice_loop, args=(gui_window,), daemon=True)
        thread.start()
        gui_window['root'].mainloop()
    else:
        voice_loop()

if __name__ == '__main__':
    main()
    