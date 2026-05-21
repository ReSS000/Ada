import sys
import os
import psutil
import pyautogui
import subprocess
import sounddevice as sd
import numpy as np
import io
import wave
import speech_recognition as sr
from fuzzywuzzy import fuzz
from PIL import ImageGrab
from dotenv import load_dotenv
from google import genai
from google.genai import types

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QTextEdit, QLineEdit, QPushButton, QLabel)
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QFont, QTextCursor

# .env dosyasından API anahtarını yükle
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if not api_key or api_key == "buraya_aldigin_api_anahtarini_yapistir":
    print("HATA: Lütfen .env dosyasina GEMINI_API_KEY degerini girin.")
    exit(1)

# Gemini Client'ı başlat
try:
    client = genai.Client(api_key=api_key)
except Exception as e:
    print(f"API başlatılamadı: {e}")
    exit(1)
MODEL_ID = "gemini-flash-lite-latest"  # Lite sürümünün limiti günde 1500 istek.

# ==========================================
# ABBY'NİN YETENEKLERİ (TOOLS)
# ==========================================

def get_system_status() -> str:
    """Returns detailed hardware and system status including CPU, RAM, Disk, GPU, and Battery."""
    # CPU
    cpu_name = "Bilinmiyor"
    try:
        cpu_name = subprocess.check_output(['wmic', 'cpu', 'get', 'name'], text=True).split('\n')[1].strip()
    except Exception:
        import platform
        cpu_name = platform.processor()
        
    cpu_usage = psutil.cpu_percent(interval=1)
    cpu_freq = psutil.cpu_freq()
    freq_str = f"{cpu_freq.current:.0f}MHz" if cpu_freq else "Bilinmiyor"
    
    # RAM
    ram = psutil.virtual_memory()
    ram_usage = ram.percent
    ram_total = f"{ram.total / (1024**3):.1f}GB"
    ram_used = f"{ram.used / (1024**3):.1f}GB"
    
    # DISK (C:)
    disk = psutil.disk_usage('C:\\')
    disk_total = f"{disk.total / (1024**3):.1f}GB"
    disk_free = f"{disk.free / (1024**3):.1f}GB"
    
    # BATTERY
    battery = psutil.sensors_battery()
    bat_str = f"%{battery.percent} ({'Şarj oluyor' if battery.power_plugged else 'Pilde'})" if battery else "Masaüstü/Bilinmiyor"
    
    # GPU
    gpu_info = "GPU: Bilgi alınamadı."
    try:
        smi_output = subprocess.check_output(
            ['nvidia-smi', '--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total', '--format=csv,noheader'], 
            text=True
        ).strip()
        # Çıktı örneği: NVIDIA GeForce RTX 2050, 45, 10 %, 1500 MiB, 4096 MiB
        gpu_info = f"GPU: {smi_output}"
    except Exception:
        gpu_info = "GPU: NVIDIA sürücüleri veya nvidia-smi bulunamadı."

    return f"DETAYLI DONANIM RAPORU:\n- CPU: {cpu_name} - %{cpu_usage} (Frekans: {freq_str})\n- RAM: %{ram_usage} ({ram_used} / {ram_total})\n- Disk (C:): Boş {disk_free} / Toplam {disk_total}\n- {gpu_info}\n- Pil: {bat_str}"

def list_running_apps() -> str:
    """Returns a list of currently running major applications."""
    apps = []
    for proc in psutil.process_iter(['name', 'memory_percent']):
        try:
            if proc.info['memory_percent'] is not None and proc.info['memory_percent'] > 0.5:
                apps.append(proc.info['name'])
        except:
            pass
    return f"En çok RAM tüketen açık uygulamalar: {', '.join(list(set(apps)))}"

def close_application(app_name: str) -> str:
    """Closes a running application forcefully by its name."""
    log_tool_action(f"close_application('{app_name}')")
    killed = False
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and app_name.lower() in proc.info['name'].lower():
                proc.kill()
                killed = True
        except:
            pass
    if killed:
        return f"{app_name} başarıyla kapatıldı."
    else:
        return f"{app_name} bulunamadı veya kapatılamadı."

def open_application(app_name: str) -> str:
    """Opens a Windows application by its executable name or path (e.g. 'taskmgr', 'calc', 'notepad')."""
    try:
        subprocess.Popen(app_name, shell=True)
        return f"{app_name} başarıyla açıldı."
    except Exception as e:
        return f"{app_name} açılamadı. Hata: {str(e)}"

def list_directory(path: str) -> str:
    """Lists files and folders in a given directory path. Use this to explore the file system."""
    try:
        if path.lower() in ["desktop", "masaüstü"]:
            path = os.path.join(os.path.expanduser("~"), "Desktop")
        items = os.listdir(path)
        return f"{path} klasörünün içeriği:\n" + "\n".join(items)
    except Exception as e:
        return f"Klasör okunamadı. Hata: {str(e)}"

def search_file(filename: str, root_dir: str = "") -> str:
    """Searches for a file by its name. root_dir defaults to user's Desktop if empty. Returns absolute paths."""
    if not root_dir:
        root_dir = os.path.join(os.path.expanduser("~"), "Desktop")
    found_paths = []
    try:
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if filename.lower() in file.lower():
                    found_paths.append(os.path.join(root, file))
        if found_paths:
            return f"Bulunan dosyalar:\n" + "\n".join(found_paths[:5])
        return f"'{filename}' adlı dosya {root_dir} içinde bulunamadı."
    except Exception as e:
        return f"Arama sırasında hata: {str(e)}"

def open_file_or_path(path: str) -> str:
    """Opens any file, executable or folder given its absolute path. Very powerful tool for full access."""
    log_tool_action(f"open_file_or_path('{path}')")
    try:
        os.startfile(path)
        return f"{path} başarıyla açıldı."
    except Exception as e:
        return f"{path} açılamadı. Dosya yolunun tam ve doğru olduğundan emin ol. Hata: {str(e)}"

def delete_file_or_directory(path: str) -> str:
    """Deletes a file or directory permanently. Be extremely careful, this is irreversible."""
    log_tool_action(f"delete_file_or_directory('{path}')")
    try:
        import os
        import shutil
        if os.path.isfile(path):
            os.remove(path)
            return f"DOSYA SİLİNDİ: {path}"
        elif os.path.isdir(path):
            shutil.rmtree(path)
            return f"KLASÖR VE İÇİNDEKİ HER ŞEY SİLİNDİ: {path}"
        else:
            return f"Silinecek dosya veya klasör bulunamadı: {path}"
    except Exception as e:
        return f"Silme işlemi başarısız: {str(e)}"

def move_file_or_directory(source_path: str, destination_path: str) -> str:
    """Moves a file or directory from source to destination. Can also be used to rename files."""
    log_tool_action(f"move_file_or_directory('{source_path}', '{destination_path}')")
    try:
        import shutil
        import os
        if not os.path.exists(source_path):
            return f"Kaynak bulunamadı: {source_path}"
        shutil.move(source_path, destination_path)
        return f"BAŞARIYLA TAŞINDI: {source_path} -> {destination_path}"
    except Exception as e:
        return f"Taşıma başarısız: {str(e)}"
def media_control(action: str) -> str:
    """Controls media playback. valid actions: 'playpause', 'nexttrack', 'prevtrack', 'volumeup', 'volumedown', 'volumemute'"""
    valid_actions = ['playpause', 'nexttrack', 'prevtrack', 'volumeup', 'volumedown', 'volumemute']
    if action in valid_actions:
        pyautogui.press(action)
        return f"Medya komutu çalıştırıldı: {action}"
    return f"Geçersiz komut: {action}"

def keyboard_type(text: str) -> str:
    """Types text safely via keyboard. Replaces Turkish chars with English to prevent errors."""
    log_tool_action(f"keyboard_type('{text}')")
    trans = str.maketrans("şğçöüıŞĞÇÖÜİ", "sgcouiSGCOUI")
    safe_text = text.translate(trans)
    pyautogui.write(safe_text, interval=0.01)
    return f"Klavyeden '{safe_text}' yazıldı."

def keyboard_press(keys: str) -> str:
    """Presses a key or combination of keys. For combinations, separate with comma (e.g., 'alt,tab', 'ctrl,c', 'enter', 'win,d')."""
    key_list = [k.strip() for k in keys.split(',')]
    try:
        pyautogui.hotkey(*key_list)
        return f"Tuşlara basıldı: {keys}"
    except Exception as e:
        return f"Tuş basma hatası: {str(e)}"

def mouse_move_and_click(x: int = -1, y: int = -1, click: str = "left") -> str:
    """Moves mouse to (x,y) and clicks. If x,y are -1, clicks current position. click options: 'left', 'right', 'double'."""
    try:
        if x != -1 and y != -1:
            pyautogui.moveTo(x, y, duration=0.2)
        if click == "left":
            pyautogui.click()
        elif click == "right":
            pyautogui.rightClick()
        elif click == "double":
            pyautogui.doubleClick()
        return f"Mouse {click} tıklaması yapıldı (x:{x}, y:{y})."
    except Exception as e:
        return f"Mouse hatası: {str(e)}"

def bring_window_to_front(window_title: str) -> str:
    """Brings a specific application window to the foreground AND maximizes it. Use this instead of alt-tabbing."""
    log_tool_action(f"bring_window_to_front('{window_title}')")
    import pygetwindow as gw
    import ctypes
    import pyautogui
    try:
        windows = gw.getWindowsWithTitle(window_title)
        if not windows:
            return f"'{window_title}' adında pencere bulunamadı."
        
        for win in windows:
            # Sadece görünür ve boyutu olan pencereleri al (arkaplan işlemleri değil)
            if win.title and win.width > 0 and getattr(win, '_hWnd', None):
                # Focus çalma kısıtlamasını (Focus Steal Prevention) aşmak için Alt tuşu hilesi
                pyautogui.keyDown('alt')
                pyautogui.keyUp('alt')
                
                # SW_MAXIMIZE = 3 (Pencereyi tam ekran yap)
                ctypes.windll.user32.ShowWindow(win._hWnd, 3)
                
                # Pencereyi en öne getir
                ctypes.windll.user32.SetForegroundWindow(win._hWnd)
                return f"'{win.title}' penceresi öne getirildi ve tam ekran (maximize) yapıldı."
                
        return "Öne getirilecek görünür bir pencere bulunamadı."
    except Exception as e:
        return f"Hata: {str(e)}"

def take_screenshot_and_analyze(prompt: str) -> str:
    """Takes a screenshot of the current screen and analyzes it with Gemini based on prompt."""
    image = ImageGrab.grab()
    try:
        response = client.models.generate_content(
            model=MODEL_ID,
            contents=[image, prompt]
        )
        return f"Ekran analizi sonucu: {response.text}"
    except Exception as e:
        return f"Ekran okuma hatası: {str(e)}"

def log_tool_action(action: str):
    try:
        import os, datetime
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abby_latest_log.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] [SİSTEM - TOOL] {action}\n")
    except:
        pass
def search_on_web(query: str) -> str:
    """Searches the web seamlessly without relying on keyboard macros. ALWAYS USE THIS FOR WEB SEARCHES!"""
    log_tool_action(f"search_on_web('{query}')")
    import webbrowser
    import urllib.parse
    try:
        url = "https://www.google.com/search?q=" + urllib.parse.quote(query)
        webbrowser.open(url)
        return f"Tarayıcıda '{query}' kelimesi aratıldı."
    except Exception as e:
        return f"Arama hatası: {str(e)}"

def remember_rule(rule: str) -> str:
    """Saves a successful action, user preference, or learned rule to long-term memory."""
    log_tool_action(f"remember_rule('{rule}')")
    try:
        import os
        mem_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.txt")
        with open(mem_path, "a", encoding="utf-8") as f:
            f.write(f"- {rule}\n")
        return f"Bu bilgi kalıcı hafızaya kaydedildi: {rule}"
    except Exception as e:
        return f"Hafıza kaydı başarısız: {str(e)}"

def get_active_window() -> str:
    """Returns the title of the currently focused window on the screen."""
    log_tool_action("get_active_window()")
    try:
        import pygetwindow as gw
        active = gw.getActiveWindow()
        if active:
            return f"Şu an ekrandaki aktif pencere: '{active.title}'"
        return "Aktif pencere bulunamadı veya okunamadı."
    except Exception as e:
        return f"Aktif pencere alınamadı: {str(e)}"

def run_terminal_command(command: str) -> str:
    """Executes a Windows CMD/PowerShell command. Used for tasks requiring advanced access. Extremely powerful. Asks for user confirmation."""
    log_tool_action(f"run_terminal_command('{command}')")
    
    # Güvenlik Koruması: Kara liste
    dangerous_keywords = ['format ', 'diskpart', 'del ', 'rmdir ', 'rd ', 'shutdown', 'bootrec', 'reg delete']
    cmd_lower = command.lower()
    for kw in dangerous_keywords:
        if kw in cmd_lower:
            return f"KRİTİK GÜVENLİK ENGELİ: '{kw}' içeren komutlar çok tehlikeli olduğu için engellendi. Bu işlemi yapamazsın."
            
    # Kullanıcı Onayı (Blocking MessageBox)
    import ctypes
    # 1 = MB_OKCANCEL, 48 = MB_ICONEXCLAMATION -> 1 | 48 = 49
    # Returns 1 for OK, 2 for Cancel
    msg = f"Abby arka planda şu terminal komutunu çalıştırmak istiyor:\n\n{command}\n\nİzin veriyor musun?"
    result = ctypes.windll.user32.MessageBoxW(0, msg, "Güvenlik Onayı Gerekli", 49)
    
    if result != 1:
        return "İPTAL EDİLDİ: Kullanıcı bu komutun çalışmasına izin vermedi."
        
    # Onaylandı, çalıştır
    import subprocess
    try:
        output = subprocess.check_output(command, shell=True, text=True, stderr=subprocess.STDOUT, timeout=30)
        return f"Komut başarıyla çalıştı. Çıktı:\n{output}"
    except subprocess.TimeoutExpired:
        return "Komut zaman aşımına uğradı."
    except subprocess.CalledProcessError as e:
        return f"Komut hata ile sonuçlandı. Çıktı:\n{e.output}"
    except Exception as e:
        return f"Beklenmeyen hata: {str(e)}"

def get_spotify_song() -> str:
    """Returns the title of the currently playing song on Spotify by analyzing background window titles."""
    log_tool_action("get_spotify_song()")
    try:
        import pygetwindow as gw
        import ctypes
        import psutil
        
        for w in gw.getAllWindows():
            if w.title and w.title not in ['Default IME', 'MSCTFIME UI', 'Program Manager']:
                pid = ctypes.c_ulong()
                ctypes.windll.user32.GetWindowThreadProcessId(w._hWnd, ctypes.byref(pid))
                try:
                    p = psutil.Process(pid.value)
                    if p.name().lower() == 'spotify.exe':
                        if w.title == 'Spotify Premium' or w.title == 'Spotify Free' or w.title == 'Spotify':
                            return "Spotify açık ama şu an bir şarkı çalmıyor (Durdurulmuş)."
                        return f"Şu an Spotify'da çalan parça: {w.title}"
                except Exception:
                    pass
        return "Spotify açık değil veya çalan şarkı bulunamadı."
    except Exception as e:
        return f"Spotify kontrolü başarısız: {str(e)}"
abby_tools = [get_system_status, list_running_apps, open_application, close_application, media_control, keyboard_type, keyboard_press, mouse_move_and_click, bring_window_to_front, take_screenshot_and_analyze, list_directory, search_file, open_file_or_path, delete_file_or_directory, search_on_web, remember_rule, get_active_window, move_file_or_directory, run_terminal_command, get_spotify_song]

try:
    memory_content = ""
    mem_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.txt")
    if os.path.exists(mem_path):
        with open(mem_path, "r", encoding="utf-8") as f:
            memory_content = f.read()

    rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rule.md")
    if os.path.exists(rules_path):
        with open(rules_path, "r", encoding="utf-8") as f:
            base_instruction = f.read()
    else:
        # Yedek varsayılan kural
        base_instruction = "Senin adın Abby. Zeki ve yardımsever bir asistansın."
    
    if memory_content.strip():
        base_instruction += f"\n\nGEÇMİŞTEN ÖĞRENDİKLERİN (BUNLARA KESİNLİKLE UY):\n{memory_content}"

    chat = client.chats.create(
        model=MODEL_ID,
        config=types.GenerateContentConfig(
            system_instruction=base_instruction,
            temperature=0.4,
            tools=abby_tools,
        )
    )
except Exception as e:
    print(f"Chat başlatılamadı: {e}")
    exit(1)

# ==========================================
# GUI THREADING
# ==========================================

class ApiWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    status_update = pyqtSignal(str)

    def __init__(self, user_text):
        super().__init__()
        self.user_text = user_text

    def run(self):
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = chat.send_message(self.user_text)
                self.finished.emit(response.text)
                return
            except Exception as e:
                error_msg = str(e)
                if "429" in error_msg:
                    if attempt < max_retries - 1:
                        self.status_update.emit(f"Google API tıkandı amk, {15 * (attempt+1)} sn bekle tekrar deniyorum...")
                        time.sleep(15 * (attempt+1))
                        continue
                    else:
                        self.error.emit("API limitlerini s*ktin attın moruq. Dakikalık kota doldu, 30 saniye bi nefes al amk.")
                        return
                else:
                    self.error.emit(error_msg)
                    return

import threading
def speak_text(text: str):
    """Background thread to read text out loud."""
    try:
        import re
        # Markdown işaretlerini ve emojileri olabildiğince temizle
        clean_text = re.sub(r'\*\*(.*?)\*\*', r'\1', text) # Kalın
        clean_text = re.sub(r'\*(.*?)\*', r'\1', clean_text) # İtalik
        clean_text = re.sub(r'#+\s*', '', clean_text) # Başlık
        clean_text = clean_text.replace('\n', ' ') # Satır atlamaları
        clean_text = re.sub(r'http\S+', '', clean_text) # Linkleri okuma
        clean_text = re.sub(r'[{}[\]()]', '', clean_text) # Parantezler
        clean_text = clean_text.replace('`', '')
        
        # Eğer temizlenmiş metin çok boşsa okuma
        if not clean_text.strip(): return
        import os
        import tempfile
        from playsound import playsound
        import asyncio
        import edge_tts
        
        # Noktalama işaretlerindeki duraksamayı yok etmek için işaretleri temizle
        clean_text = re.sub(r'[.?!,;:]', ' ', clean_text)
        # Birden fazla boşluğu teke indir
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        # Create a temporary file
        fd, temp_path = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        
        # Eğer arka planda müzik/video çalıyorsa durdur
        was_playing = False
        try:
            from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
            async def _check_and_pause():
                sessions = await MediaManager.request_async()
                current_session = sessions.get_current_session()
                if current_session:
                    info = current_session.get_playback_info()
                    if info.playback_status == 4: # 4 = Playing
                        await current_session.try_pause_async()
                        return True
                return False
            was_playing = asyncio.run(_check_and_pause())
        except Exception:
            pass

        # Alternatif, daha umursamaz/sıkkın bir ses tonu denemesi:
        # Perdeyi iyice düşürdük (-40Hz) ve biraz hızlandırdık (+15%)
        async def _generate():
            comm = edge_tts.Communicate(clean_text, "tr-TR-EmelNeural", rate="+5%", pitch="-20Hz")
            await comm.save(temp_path)
            
        asyncio.run(_generate())
        playsound(temp_path)
        
        # Eğer konuşmadan önce bir şey çalıyorsa tekrar başlat
        if was_playing:
            try:
                from winrt.windows.media.control import GlobalSystemMediaTransportControlsSessionManager as MediaManager
                async def _resume():
                    sessions = await MediaManager.request_async()
                    current_session = sessions.get_current_session()
                    if current_session:
                        await current_session.try_play_async()
                asyncio.run(_resume())
            except Exception:
                pass
                
        # Oynatıldıktan sonra dosyayı sil
        try:
            os.remove(temp_path)
        except:
            pass
    except Exception as e:
        print("Sesli okuma hatası:", e)

def async_speak(text: str):
    threading.Thread(target=speak_text, args=(text,), daemon=True).start()

# ==========================================
# VOICE WAKE WORD & SPEECH-TO-TEXT SYSTEM
# ==========================================

class VoiceWakeWordListener(QThread):
    """Continuously listens for wake words ('Abby', 'Hey Abby', etc.) and triggers voice input using sounddevice."""
    wake_word_detected = pyqtSignal(str)  # Emits the full transcribed text
    listening = pyqtSignal(bool)  # Status update
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.sample_rate = 16000
        self.channels = 1
        
    def record_audio(self, duration):
        """Record audio for specified duration using sounddevice."""
        recording = sd.rec(int(duration * self.sample_rate), 
                          samplerate=self.sample_rate, 
                          channels=self.channels,
                          dtype='int16')
        sd.wait()
        return recording
    
    def transcribe_audio(self, audio_data):
        """Transcribe audio using Google Speech Recognition API (free web API)."""
        try:
            # Convert numpy array to WAV format in memory
            audio_bytes = io.BytesIO()
            with wave.open(audio_bytes, 'wb') as wav_file:
                wav_file.setnchannels(self.channels)
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(audio_data.tobytes())
            
            audio_bytes.seek(0)
            
            # Use speech_recognition with the audio data
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = 300  # Daha düşük threshold
            recognizer.dynamic_energy_threshold = True
            
            with sr.AudioFile(audio_bytes) as source:
                audio = recognizer.record(source)
            
            # Transcribe using Google's free web API
            text = recognizer.recognize_google(audio, language="tr-TR")
            return text
                
        except sr.UnknownValueError:
            # Ses anlaşılamadı - sessizlik veya gürültü
            return None
        except sr.RequestError as e:
            print(f"[VOICE] API Hatası: {e}")
            return None
        except Exception as e:
            print(f"[VOICE] Transcription error: {type(e).__name__}: {e}")
            return None
    
    def run(self):
        try:
            print("[VOICE] Wake word listener başladı. 'Abby' veya 'Hey Abby' dediğinde dinlemeyi başlayacağım...")
            
            wake_words = ["abby", "hey abby", "ey abby", "ebi", "ebbiy", "abi", "hey ebi", "ebiğ", "ebbiğ", ]
            listening_timeout = 5  # Dinlemek için 5 saniye bekle
            
            while self.running:
                try:
                    # Wake word'ü dinle (kısa kayıt)
                    audio_data = self.record_audio(1)
                    
                    # Transcribe et
                    wake_text = self.transcribe_audio(audio_data)
                    
                    if wake_text:
                        wake_text = wake_text.lower()
                        print(f"[VOICE] Algılanan metin: '{wake_text}'")
                        
                        # Fuzzy matching ile wake word'ü algıla
                        is_wake_word = any(fuzz.ratio(wake_text, ww) > 60 for ww in wake_words)
                        
                        if is_wake_word:
                            print("[VOICE] WAKE WORD ALGILANDI! Dinlemeye başlıyorum...")
                            self.listening.emit(True)
                            
                            # Pencereyi öne getir (tam ekran yapma)
                            try:
                                import pygetwindow as gw
                                import ctypes
                                windows = gw.getWindowsWithTitle("Abby")
                                if windows:
                                    for win in windows:
                                        if win.title and win.width > 0 and getattr(win, '_hWnd', None):
                                            pyautogui.keyDown('alt')
                                            pyautogui.keyUp('alt')
                                            # SW_RESTORE = 9 (pencereyi normal boyuta getir)
                                            ctypes.windll.user32.ShowWindow(win._hWnd, 9)
                                            ctypes.windll.user32.SetForegroundWindow(win._hWnd)
                                            break
                            except Exception as e:
                                print(f"[VOICE] Pencere öne getirme hatası: {e}")
                            
                            # Şimdi tam komutu dinle (5 saniye)
                            audio_data = self.record_audio(listening_timeout)
                            
                            # Komutu transcribe et
                            command_text = self.transcribe_audio(audio_data)
                            
                            if command_text:
                                print(f"[VOICE] Komut alındı: '{command_text}'")
                                self.listening.emit(False)
                                self.wake_word_detected.emit(command_text)
                            else:
                                self.listening.emit(False)
                                print("[VOICE] Komut anlaşılamadı.")
                        
                except Exception as e:
                    print(f"[VOICE] Dinleme hatası: {e}")
                    continue
                    
        except Exception as e:
            print(f"[VOICE] Sistem hatası: {e}")
    
    def stop(self):
        self.running = False


class AbbyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Abby")
        self.setGeometry(200, 200, 600, 750)
        
        # Dark Theme Palette
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1e1e1e;
            }
            QTextEdit {
                background-color: #252526;
                color: #d4d4d4;
                border: 1px solid #3c3c3c;
                border-radius: 5px;
                padding: 10px;
                font-family: 'Segoe UI', Consolas;
                font-size: 14px;
            }
            QLineEdit {
                background-color: #3c3c3c;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 5px;
                padding: 8px;
                font-family: 'Segoe UI';
                font-size: 14px;
            }
            QPushButton {
                background-color: #0e639c;
                color: white;
                border: none;
                border-radius: 5px;
                padding: 10px 20px;
                font-weight: bold;
                font-family: 'Segoe UI';
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #1177bb;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #aaaaaa;
            }
            QLabel {
                color: #888888;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
        """)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        layout.addWidget(self.chat_display)

        # Status Label
        self.status_label = QLabel("Sistemlerim devrede, patron. Beklemedeyim...")
        layout.addWidget(self.status_label)

        # Input Layout
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Abby'ye komut ver...")
        self.input_field.returnPressed.connect(self.send_message)
        layout.addWidget(self.input_field)

        self.send_button = QPushButton("Gönder")
        self.send_button.clicked.connect(self.send_message)
        layout.addWidget(self.send_button)

        # Voice Input Button
        self.voice_button = QPushButton("🎤 Sesle Komut Ver")
        self.voice_button.clicked.connect(self.toggle_voice_input)
        layout.addWidget(self.voice_button)

        # Yeni oturum başladığında log dosyasına ayraç koy
        try:
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abby_latest_log.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write("\n" + "="*50 + "\n=== YENİ OTURUM BAŞLADI ===\n" + "="*50 + "\n")
        except Exception:
            pass

        self.append_message("Abby", "Sistemlerim devrede, patron. Arayüz başlatıldı. Nasıl yardımcı olabilirim?", "#00ff00")
        
        # Voice wake word listener'ı başlat
        self.voice_listener = None
        self.start_voice_listener()

    def append_message(self, sender, text, color="#ffffff"):
        import re
        
        html_text = text
        # Basit Markdown -> HTML çevirici
        html_text = html_text.replace('\n* ', '\n• ')
        html_text = html_text.replace('\n- ', '\n• ')
        if html_text.startswith('* '): html_text = '• ' + html_text[2:]
        if html_text.startswith('- '): html_text = '• ' + html_text[2:]
        
        # Kalın (Bold)
        html_text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html_text)
        # İtalik
        html_text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', html_text)
        
        # Satır atlamaları
        html_text = html_text.replace('\n', '<br>')

        html = f"<b><span style='color:{color}'>{sender}:</span></b> {html_text}<br><br>"
        self.chat_display.moveCursor(QTextCursor.MoveOperation.End)
        self.chat_display.insertHtml(html)
        self.chat_display.moveCursor(QTextCursor.MoveOperation.End)
        
        # Dosyaya log kaydetme
        try:
            import os
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "abby_latest_log.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                import datetime
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{timestamp}] {sender}: {text}\n")
        except Exception:
            pass

    def send_message(self):
        user_text = self.input_field.text().strip()
        if not user_text:
            return

        self.append_message("Sen", user_text, "#00aaff")
        self.input_field.clear()
        
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        self.voice_button.setEnabled(False)
        self.status_label.setText("Abby ekranı izliyor ve düşünüyor...")

        self.worker = ApiWorker(user_text)
        self.worker.finished.connect(self.on_api_response)
        self.worker.error.connect(self.on_api_error)
        self.worker.status_update.connect(self.on_status_update)
        self.worker.start()

    def on_status_update(self, text):
        self.status_label.setText(text)

    def on_api_response(self, response_text):
        # [KAPAT] komutunu kontrol et
        should_close = "[KAPAT]" in response_text
        
        # Ekrandan [KAPAT] komutunu kaldır
        display_text = response_text.replace("[KAPAT]", "").strip()
        
        self.append_message("Abby", display_text, "#00ff00")
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONASTERISK)
        except:
            pass
            
        # SESLİ OKUMA
        async_speak(display_text)
        
        self.reset_input_state()
        
        # Kapatma komutu varsa programı kapat
        if should_close:
            print("[SİSTEM] Kapatma komutu alındı. Konuşma bitince kapanıyor...")
            # Konuşma bitmesini bekle (2 saniye) ve GUI thread'den kapat
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(2000, QApplication.instance().quit)

    def on_api_error(self, error_text):
        self.append_message("Sistem Hatası", f"API Hatası: {error_text}", "#ff5555")
        self.reset_input_state()
        
    def start_voice_listener(self):
        """Başlat voice wake word listener'ı."""
        try:
            self.voice_listener = VoiceWakeWordListener()
            self.voice_listener.wake_word_detected.connect(self.on_voice_command)
            self.voice_listener.listening.connect(self.on_voice_listening)
            self.voice_listener.start()
            self.append_message("Sistem", "🎤 Sesli komut dinlemeye başladı. 'Abby' veya 'Hey Abby' deyin!", "#ffaa00")
        except Exception as e:
            self.append_message("Sistem Hatası", f"Voice sistemi başlatılamadı: {e}", "#ff5555")
    
    def toggle_voice_input(self):
        """Manuel sesli komut girişi."""
        if not self.voice_listener or not self.voice_listener.isRunning():
            self.start_voice_listener()
        else:
            self.voice_listener.stop()
            self.voice_listener.wait()
            self.voice_listener = None
            self.append_message("Sistem", "🎤 Sesli komut dinlemesi durduruldu.", "#ffaa00")
    
    def on_voice_listening(self, is_listening):
        """Voice listener'ın dinleme durumu değiştiğinde."""
        if is_listening:
            self.status_label.setText("🎤 Dinliyorum, konuşun lütfen...")
            self.append_message("Sistem", "🎤 Dinliyorum... Komutunuzu söyleyin!", "#ffaa00")
        else:
            self.status_label.setText("Beklemedeyim...")
    
    def on_voice_command(self, command_text):
        """Wake word algılandı ve komut transcribe edildi."""
        self.append_message("Sen (Sesle)", command_text, "#00aaff")
        self.input_field.clear()
        
        self.input_field.setEnabled(False)
        self.send_button.setEnabled(False)
        self.voice_button.setEnabled(False)
        self.status_label.setText("Abby ekranı izliyor ve düşünüyor...")

        self.worker = ApiWorker(command_text)
        self.worker.finished.connect(self.on_api_response)
        self.worker.error.connect(self.on_api_error)
        self.worker.status_update.connect(self.on_status_update)
        self.worker.start()
    
    def reset_input_state(self):
        self.input_field.setEnabled(True)
        self.send_button.setEnabled(True)
        try:
            if self.voice_button:
                self.voice_button.setEnabled(True)
        except:
            pass
        self.input_field.setFocus()
        self.status_label.setText("Beklemedeyim...")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AbbyWindow()
    
    def on_app_quit():
        if window.voice_listener:
            window.voice_listener.stop()
            window.voice_listener.wait()
    
    app.aboutToQuit.connect(on_app_quit)
    window.show()
    sys.exit(app.exec())
