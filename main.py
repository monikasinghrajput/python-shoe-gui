#!/usr/bin/env python3
"""
Bee-Tek Card Shoe Monitor
A Kivy GUI application for monitoring card-dealing shoe and sending card data via HTTP POST.
"""

# Standard library imports
import json          # For reading/writing JSON config files
import logging       # For console logging and debugging
import os            # For file operations
import re            # For regex pattern matching (card parsing)
import sys           # For PyInstaller resource path detection
import threading     # For background serial port monitoring
import time          # For delays and timing
from collections import deque  # For history buffer
from dataclasses import dataclass, asdict  # For clean config data structure
from datetime import datetime  # For timestamps
from typing import Callable, Optional  # For type hints

# Third-party imports
import requests      # For HTTP POST requests
import serial        # For serial port communication (pyserial)

# Kivy imports - GUI framework
from kivy.app import App  # Base application class
from kivy.clock import Clock  # For thread-safe UI updates
from kivy.core.window import Window  # For window size control
from kivy.uix.boxlayout import BoxLayout  # Layout manager
from kivy.uix.gridlayout import GridLayout  # Grid layout for symbols
from kivy.uix.button import Button  # Button widget
from kivy.uix.label import Label  # Text display widget
from kivy.uix.scrollview import ScrollView  # Scrollable container
from kivy.uix.textinput import TextInput  # Text input fields
from kivy.uix.image import Image  # For image display
from kivy.graphics import Color, Ellipse, Rectangle, RoundedRectangle, Line  # For drawing and background
from kivy.effects.scroll import ScrollEffect

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================
# Set up logging to display timestamps and log levels in the console
logging.basicConfig(
    level=logging.INFO,  # Show INFO, WARNING, and ERROR messages
    format='%(asctime)s [%(levelname)s] %(message)s',  # Format: time [LEVEL] message
    datefmt='%H:%M:%S'  # Time format: hours:minutes:seconds
)
logger = logging.getLogger(__name__)  # Create logger for this module

# ============================================================================
# CONSTANTS AND CONFIGURATION
# ============================================================================
SERIAL_PORT = '/dev/ttyUSB0'  # Linux USB serial device for Bee-Tek shoe
SERIAL_BAUDRATE = 9600         # Communication speed (bits per second)
SERIAL_TIMEOUT = 2              # Seconds to wait for serial data
RETRY_DELAY = 2.5               # Seconds to wait before reconnecting after error
HTTP_TIMEOUT = 3                # Seconds to wait for HTTP response

# Helper function to get resource path (works with PyInstaller)
def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller."""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# Card parsing regex patterns
# Pattern 1: Successful card read - [Game]<Card:4S>, [Manual Burn Cards]<Card:H3>, etc.
# Format: " [Operation]<Card:RS> " with spaces before/after
# Group 1: Rank (2-9, T, J, Q, K, A, or 10)
# Group 2: Suit (C, D, H, S)
CARD_PATTERN = re.compile(r' \[(?:Game|Manual Burn Cards)\]<Card:([2-9TJQKA]|10)([CDHS])> ', re.IGNORECASE)

# Pattern 2: Failed/incomplete card read - " [Game]<Game> " or " [Manual Burn Cards]<Game> "
# This appears when the shoe couldn't read the card properly
FAILED_READ_PATTERN = re.compile(r' \[(?:Game|Manual Burn Cards)\]<Game> ', re.IGNORECASE)

# Pattern 3: Hardware alarm messages - " [Game]<Alarm:E3 Card Not Read> ", " [GameAlarm]<Alarm:...> "
# Matches [Game], [GameAlarm], and [Manual Burn Cards] with spaces
ALARM_PATTERN = re.compile(r' \[(?:Game(?:Alarm)?|Manual Burn Cards)\]<Alarm:([^>]+)> ', re.IGNORECASE)

# Pattern 4: Warning codes - <W0x01>, <W0x02>, etc.
# Hex warning codes from the shoe hardware
WARNING_PATTERN = re.compile(r'<(W0x[0-9A-Fa-f]+)>', re.IGNORECASE)



# ============================================================================
# DATA MODELS
# ============================================================================
@dataclass
class Config:
    """Configuration data model for server connection settings.
    
    Uses @dataclass decorator for automatic __init__, __repr__, etc.
    Fields are loaded from shoe.json and can be edited in the UI.
    """
    ip: str = "192.168.1.140"  # Server IP address
    port: int = 9000            # Server port number
    url: str = "api/holdem/beetek/card"  # URL endpoint path (without leading /)


# ============================================================================
# CONFIGURATION FILE MANAGEMENT
# ============================================================================
def load_config(filepath: str = 'shoe.json') -> Config:
    """Load configuration from JSON file or create default if not found.
    
    Args:
        filepath: Path to the JSON config file
        
    Returns:
        Config object with loaded or default values
    """
    try:
        # Check if config file exists
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                data = json.load(f)  # Parse JSON into dictionary
                logger.info(f"Loaded config from {filepath}")
                # **data unpacks dictionary into Config constructor arguments
                return Config(**data)
    except Exception as e:
        logger.warning(f"Failed to load config: {e}")
    
    # If file doesn't exist or failed to load, create default config
    config = Config()  # Uses default values from dataclass
    save_config(config, filepath)  # Save it to disk
    return config


def save_config(config: Config, filepath: str = 'shoe.json') -> bool:
    """Save configuration to JSON file atomically (safely).
    
    Uses atomic write pattern: write to temp file, then rename.
    This prevents corruption if the process is interrupted mid-write.
    
    Args:
        config: Config object to save
        filepath: Destination file path
        
    Returns:
        True if successful, False otherwise
    """
    try:
        temp_path = filepath + '.tmp'  # Create temporary file first
        with open(temp_path, 'w') as f:
            # asdict() converts dataclass to dictionary for JSON serialization
            json.dump(asdict(config), f, indent=2)  # Pretty-print with 2-space indent
        # os.replace() is atomic - either fully succeeds or fully fails
        os.replace(temp_path, filepath)
        logger.info(f"Saved config to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


# ============================================================================
# CARD PARSING
# ============================================================================
def parse_cards_from_buffer(text: str) -> list:
    """Extract card codes from text buffer using regex pattern.
    
    Parses strings like: [Game]<Card:4S>, [Manual Burn Cards]<Card:H3>, etc.
    
    Args:
        text: Raw text buffer from serial port
        
    Returns:
        List of card codes like ['S4', 'HT', 'CK'] (suit-rank format for server)
    """
    cards = []
    # finditer() returns all regex matches in the text
    for match in CARD_PATTERN.finditer(text):
        rank = match.group(1).upper()  # Group 1: rank (2-9, T, J, Q, K, A, or 10)
        suit = match.group(2).upper()  # Group 2: suit (C, D, H, S)
        
        # Normalize '10' to 'T' for consistency (10H -> TH)
        if rank == '10':
            rank = 'T'
            
        card = f"{suit}{rank}"  # Format: suit + rank (e.g., "S4", "TH", "CK")
        cards.append(card)
    return cards


# ============================================================================
# HTTP CLIENT
# ============================================================================
def send_card_http(ip: str, port: int, url: str, card: str) -> bool:
    """Send card data to server via HTTP POST request.
    
    Args:
        ip: Server IP address
        port: Server port number
        url: URL path (e.g., 'sendCard')
        card: Card code (e.g., '4S', 'TH')
        
    Returns:
        True if server responded with 2xx status code, False otherwise
    """
    try:
        # Build URL ensuring single slash between port and path
        url_path = url.lstrip('/')  # Remove leading slash if present
        full_url = f"http://{ip}:{port}/{url_path}"  # e.g., http://192.168.1.140:9000/sendCard
        
        # Prepare JSON payload
        payload = {
            "card": card,  # Card code like "4S"
            "timestamp": datetime.now().astimezone().isoformat()  # ISO format with timezone
        }
        
        # Send POST request with JSON body
        response = requests.post(
            full_url,
            json=payload,  # Automatically serializes dict to JSON
            headers={"Content-Type": "application/json"},
            timeout=HTTP_TIMEOUT  # Fail if server doesn't respond within 3 seconds
        )
        
        # Check if response status code is 2xx (success)
        success = 200 <= response.status_code < 300
        if success:
            logger.info(f"✅ Sent {card} -> {response.status_code}")
        else:
            logger.warning(f"❌ Failed {card} -> {response.status_code}")
        return success
        
    except Exception as e:
        # Catch network errors, timeouts, etc.
        logger.error(f"❌ HTTP error for {card}: {e}")
        return False


class SerialMonitor(threading.Thread):
    """Background thread for monitoring serial port."""
    
    def __init__(
        self,
        port: str,
        baudrate: int,
        timeout: float,
        config: Config,
        on_connected: Callable,
        on_disconnected: Callable,
        on_card: Callable[[str, bool], None],  # card, success (card can be empty for failed reads)
        on_error: Callable[[str], None]
    ):
        super().__init__(daemon=True)
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.config = config
        self.on_connected = on_connected
        self.on_disconnected = on_disconnected
        self.on_card = on_card
        self.on_error = on_error
        self._stop_event = threading.Event()
        self.ser: Optional[serial.Serial] = None
        
    def stop(self):
        """Signal thread to stop."""
        self._stop_event.set()
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except:
                pass
    
    def run(self):
        """Main monitoring loop with auto-reconnect."""
        text_buffer = ""
        
        while not self._stop_event.is_set():
            # Try to open serial port
            if not self.ser or not self.ser.is_open:
                try:
                    self.ser = serial.Serial(
                        self.port,
                        baudrate=self.baudrate,
                        timeout=self.timeout
                    )
                    logger.info(f"✅ Opened {self.port} @ {self.baudrate}")
                    Clock.schedule_once(lambda dt: self.on_connected(), 0)
                    text_buffer = ""  # Reset buffer on new connection
                    
                except serial.SerialException as e:
                    error_msg = str(e)
                    if "Permission denied" in error_msg:
                        msg = "Permission denied. Run: sudo usermod -a -G dialout $USER"
                    elif "No such file" in error_msg:
                        msg = f"Device not found: {self.port}"
                    else:
                        msg = f"Serial error: {error_msg}"
                    
                    logger.error(f"❌ {msg}")
                    Clock.schedule_once(lambda dt: self.on_error(msg), 0)
                    time.sleep(RETRY_DELAY)
                    continue
                    
                except Exception as e:
                    logger.error(f"❌ Unexpected error: {e}")
                    Clock.schedule_once(lambda dt: self.on_error(str(e)), 0)
                    time.sleep(RETRY_DELAY)
                    continue
            
            # Read from serial port
            try:
                if self.ser.in_waiting > 0:
                    chunk = self.ser.read(self.ser.in_waiting)
                    # Decode with error handling
                    text_chunk = chunk.decode('ascii', errors='ignore')
                    text_buffer += text_chunk
                    
                    # PRIORITY 1: Check for hardware alarm messages (highest priority)
                    alarm_matches = ALARM_PATTERN.findall(text_buffer)
                    if alarm_matches:
                        for alarm_msg in alarm_matches:
                            logger.error(f"🚨 ALARM: {alarm_msg}")
                            # Notify UI about the alarm
                            Clock.schedule_once(
                                lambda dt, msg=alarm_msg: self.on_error(f"ALARM: {msg}"),
                                0
                            )
                            # Special handling for card read failures in alarms
                            if "card not read" in alarm_msg.lower() or "e3" in alarm_msg.lower():
                                Clock.schedule_once(
                                    lambda dt, msg=alarm_msg: self.on_card(f"FAIL: {msg}", False),
                                    0
                                )
                        # Remove alarm patterns from buffer
                        text_buffer = ALARM_PATTERN.sub('', text_buffer)
                    
                    # PRIORITY 2: Check for warning codes
                    warning_matches = WARNING_PATTERN.findall(text_buffer)
                    if warning_matches:
                        for warning_code in warning_matches:
                            logger.warning(f"⚠️  WARNING: {warning_code}")
                            # Notify UI about the warning
                            Clock.schedule_once(
                                lambda dt, code=warning_code: self.on_error(f"Warning: {code}"),
                                0
                            )
                        # Remove warning patterns from buffer
                        text_buffer = WARNING_PATTERN.sub('', text_buffer)
                    
                    # PRIORITY 3: Check for failed card reads (generic failure)
                    failed_reads = FAILED_READ_PATTERN.findall(text_buffer)
                    if failed_reads:
                        # Card failed to read - show warning for each failed attempt
                        for _ in failed_reads:
                            logger.warning("⚠️  Card read FAILED (shoe couldn't read card)")
                            # Notify UI with failure message
                            Clock.schedule_once(
                                lambda dt: self.on_card("FAIL: Unreadable", False),
                                0
                            )
                        # Remove failed read markers from buffer
                        text_buffer = FAILED_READ_PATTERN.sub('', text_buffer)
                    
                    # Parse successful card reads
                    cards = parse_cards_from_buffer(text_buffer)
                    
                    if cards:
                        # Keep only tail after last match to preserve partial fragments
                        last_match = list(CARD_PATTERN.finditer(text_buffer))[-1]
                        text_buffer = text_buffer[last_match.end():]
                        
                        # Process each successfully read card
                        for card in cards:
                            logger.info(f"📤 Parsed card: {card}")
                            success = send_card_http(
                                self.config.ip,
                                self.config.port,
                                self.config.url,
                                card
                            )
                            # Notify UI with card code - always True because read succeeded
                            Clock.schedule_once(
                                lambda dt, c=card: self.on_card(c, True),
                                0
                            )
                    
                    # Limit buffer size
                    if len(text_buffer) > 2000:
                        text_buffer = text_buffer[-1000:]
                
                time.sleep(0.05)  # Small delay to prevent tight loop
                
            except serial.SerialException as e:
                logger.error(f"❌ Read error: {e}")
                Clock.schedule_once(lambda dt: self.on_disconnected(), 0)
                if self.ser:
                    try:
                        self.ser.close()
                    except:
                        pass
                    self.ser = None
                time.sleep(RETRY_DELAY)
                
            except Exception as e:
                logger.error(f"❌ Unexpected read error: {e}")
                time.sleep(0.1)
        
        # Cleanup
        if self.ser:
            try:
                self.ser.close()
                logger.info("Serial port closed")
            except:
                pass



class StatusIndicator(BoxLayout):
    """Visual connection status indicator with colored dot."""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint = (None, None)
        self.size = (300, 30)
        self.spacing = 5
        
        # Colored dot canvas
        self.dot_widget = BoxLayout(size_hint=(None, None), size=(20, 20))
        with self.dot_widget.canvas:
            self.dot_color = Color(1, 0, 0, 1)  # Red initially
            self.dot = Ellipse(pos=self.dot_widget.pos, size=self.dot_widget.size)
        
        self.dot_widget.bind(pos=self._update_dot, size=self._update_dot)
        
        # Status label
        self.label = Label(
            text='Disconnected',
            size_hint=(None, None),
            size=(270, 30),
            font_size='14sp',
            halign='left',
            valign='middle',
            color=(0.1, 0.1, 0.1, 1)
        )
        self.label.bind(size=self.label.setter('text_size'))
        
        self.add_widget(self.dot_widget)
        self.add_widget(self.label)
    
    def _update_dot(self, *args):
        """Update dot position."""
        self.dot.pos = self.dot_widget.pos
        self.dot.size = self.dot_widget.size
    
    def set_connected(self, connected: bool, message: str = ""):
        """Update status indicator."""
        if connected:
            self.dot_color.rgba = (0, 0.8, 0, 1)  # Green
            self.label.text = f"Connected ({SERIAL_PORT} @{SERIAL_BAUDRATE})"
        else:
            self.dot_color.rgba = (1, 0, 0, 1)  # Red
            self.label.text = message or "Disconnected"



class ShoeMonitorApp(App):
    """Main Kivy application."""
    
    title = ''  # Set title to blank (removes window title)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.app_config = load_config()
        self.monitor: Optional[SerialMonitor] = None
        self.is_monitoring = False
        self.history = deque()  # Unlimited history for long gaming sessions
        
    def build(self):
        """Build the UI."""
        Window.size = (1000, 700)
        Window.clearcolor = (0.86, 0.86, 0.88, 1)  # More greyish background
        
        Window.set_title('')  # Remove window title
        # Root layout with modern styling
        root = BoxLayout(orientation='vertical', padding=15, spacing=12)
        
        # Blue background row with bee icon (responsive)
        bee_container = BoxLayout(
            orientation='vertical',
            size_hint=(1, None),
            height=70,
            padding=10
        )
        # Add dark blue background - RGB(18, 44, 72)
        with bee_container.canvas.before:
            self.bee_bg_color = Color(18/255, 44/255, 72/255, 1)  # Dark blue matching Save button
            self.bee_bg_rect = Rectangle(pos=bee_container.pos, size=bee_container.size)
        
        # Update background when container resizes (responsive)
        def _update_bee_bg(*args):
            self.bee_bg_rect.pos = bee_container.pos
            self.bee_bg_rect.size = bee_container.size
        bee_container.bind(pos=_update_bee_bg, size=_update_bee_bg)
        
        # Bee icon centered
        bee_icon = Image(
            source=resource_path('bee.png'),
            size_hint=(None, None),
            size=(50, 50),
            pos_hint={'center_x': 0.5, 'center_y': 0.5}
        )
        bee_container.add_widget(bee_icon)
        
        # Header: "Bee-Tek Shoe Reader" centered at top with modern styling
        header = Label(
            text='Bee-Tek Shoe Reader',
            size_hint=(1, None),
            height=45,
            font_size='26sp',
            bold=True,
            halign='center',
            valign='middle',
            color=(0.15, 0.25, 0.4, 1)  # Dark blue color
        )
        header.bind(size=header.setter('text_size'))
        
        # Row 1: Configuration inputs with rounded corners
        config_box = BoxLayout(orientation='horizontal', size_hint=(1, None), height=60, spacing=10)
        
        self.ip_input = TextInput(
            text=self.app_config.ip,
            hint_text='IP Address',
            multiline=False,
            font_size='16sp',
            padding=[14, 18, 14, 18],  # left, top, right, bottom - 4px more total
            size_hint=(0.75, 1),  # Reduced width to 75%
            background_color=(1, 1, 1, 1),
            foreground_color=(0.1, 0.1, 0.1, 1),
            cursor_color=(0.2, 0.5, 0.82, 1),
            cursor_width=2,
            selection_color=(0.2, 0.5, 0.82, 0.3)
        )
        self.port_input = TextInput(
            text=str(self.app_config.port),
            hint_text='Port',
            multiline=False,
            input_filter='int',
            font_size='16sp',
            padding=[14, 18, 14, 18],  # left, top, right, bottom - 4px more total
            size_hint=(0.45, 1),  # Reduced width to 45%
            background_color=(1, 1, 1, 1),
            foreground_color=(0.1, 0.1, 0.1, 1),
            cursor_color=(0.2, 0.5, 0.82, 1),
            cursor_width=2,
            selection_color=(0.2, 0.5, 0.82, 0.3)
        )
        self.url_input = TextInput(
            text=self.app_config.url,
            hint_text='URL Path',
            multiline=False,
            font_size='16sp',
            padding=[14, 18, 14, 18],  # left, top, right, bottom - 4px more total
            size_hint=(0.95, 1),  # Reduced width to 95%
            background_color=(1, 1, 1, 1),
            foreground_color=(0.1, 0.1, 0.1, 1),
            cursor_color=(0.2, 0.5, 0.82, 1),
            cursor_width=2,
            selection_color=(0.2, 0.5, 0.82, 0.3)
        )
        
        config_box.add_widget(Label(
            text='IP:', 
            size_hint=(None, 1), 
            width=35, 
            font_size='14sp',
            bold=True,
            color=(0.25, 0.25, 0.25, 1)
        ))
        config_box.add_widget(self.ip_input)
        config_box.add_widget(Label(
            text='Port:', 
            size_hint=(None, 1), 
            width=45, 
            font_size='14sp',
            bold=True,
            color=(0.25, 0.25, 0.25, 1)
        ))
        config_box.add_widget(self.port_input)
        config_box.add_widget(Label(
            text='URL:', 
            size_hint=(None, 1), 
            width=45, 
            font_size='14sp',
            bold=True,
            color=(0.25, 0.25, 0.25, 1)
        ))
        config_box.add_widget(self.url_input)
        
        # Add Save button and status indicator to config row
        self.save_btn = Button(
            text='Save',
            font_size='15sp',
            size_hint=(None, 1),
            width=100,
            background_color=(18/255, 44/255, 72/255, 1),  # Dark blue RGB(18,44,72)
            background_normal='',  # Disable default background (prevents hover)
            background_down='',    # Disable press background (prevents hover)
            color=(1, 1, 1, 1),
            bold=True
        )
        self.save_btn.bind(on_press=self.save_configuration)
        config_box.add_widget(self.save_btn)
        
        self.status_indicator = StatusIndicator()
        config_box.add_widget(self.status_indicator)
        
        # Control buttons moved to bottom right (created later after history)
        
        # Row 3: History container (grid of symbols) with modern styling
        history_label = Label(
            text='Card History',
            size_hint=(1, None),
            height=42,
            font_size='20sp',
            bold=True,
            halign='center',
            valign='middle',
            color=(0.2, 0.2, 0.2, 1)
        )
        history_label.bind(size=history_label.setter('text_size'))
        
        # Container wrapper with thin border and shadow
        history_container_wrapper = BoxLayout(orientation='vertical', size_hint=(1, 1), padding=8)
        with history_container_wrapper.canvas.before:
            # Shadow effect
            Color(0, 0, 0, 0.15)
            self.history_shadow = Rectangle(pos=(history_container_wrapper.x + 3, history_container_wrapper.y - 3), size=history_container_wrapper.size)
            # Border
            Color(0.7, 0.7, 0.75, 1)
            self.history_border = Line(rectangle=(history_container_wrapper.x, history_container_wrapper.y, history_container_wrapper.width, history_container_wrapper.height), width=0.6)
        def _update_history_border(*args):
            self.history_border.rectangle = (history_container_wrapper.x, history_container_wrapper.y, history_container_wrapper.width, history_container_wrapper.height)
            self.history_shadow.pos = (history_container_wrapper.x + 3, history_container_wrapper.y - 3)
            self.history_shadow.size = history_container_wrapper.size
        history_container_wrapper.bind(pos=_update_history_border, size=_update_history_border)
        
        # Grid layout for symbols - fills row-wise, wraps to next row
        # Dynamically calculate columns based on window width
        self.history_container = GridLayout(
            cols=self._calculate_grid_cols(),
            size_hint=(1, None),
            spacing=8,
            padding=12
        )
        # Auto-adjust height based on content
        self.history_container.bind(minimum_height=self.history_container.setter('height'))
        # Update columns when window resizes
        Window.bind(width=self._on_window_resize)
        
        # ScrollView with visible scrollbars
        self.history_scroll = ScrollView(size_hint=(1, 1), bar_width=12, bar_color=(0.4, 0.45, 0.5, 0.95), bar_inactive_color=(0.6, 0.65, 0.7, 0.7), effect_cls=ScrollEffect)
        self.history_scroll.add_widget(self.history_container)
        history_container_wrapper.add_widget(self.history_scroll)
        
        # Row 2: Control buttons at bottom right
        control_box = BoxLayout(orientation='horizontal', size_hint=(1, None), height=60, spacing=10)
        control_box.add_widget(BoxLayout())  # Spacer to push buttons to right
        
        self.start_stop_btn = Button(
            text='Start',
            font_size='15sp',
            background_color=(0.18, 0.62, 0.28, 1),
            color=(1, 1, 1, 1),
            size_hint=(None, 1),
            width=130,
            bold=True
        )
        self.start_stop_btn.bind(on_press=self.toggle_monitoring)
        
        self.clear_btn = Button(
            text='Clear History',
            font_size='15sp',
            background_color=(0.82, 0.45, 0.18, 1),
            color=(1, 1, 1, 1),
            size_hint=(None, 1),
            width=150,
            bold=True
        )
        self.clear_btn.bind(on_press=self.clear_history)
        
        control_box.add_widget(self.start_stop_btn)
        control_box.add_widget(self.clear_btn)
        
        # Add all to root
        root.add_widget(bee_container)
        root.add_widget(header)
        root.add_widget(config_box)
        root.add_widget(history_label)
        root.add_widget(history_container_wrapper)
        root.add_widget(control_box)
        
        return root
    
    def _calculate_grid_cols(self):
        """Calculate number of grid columns based on window width."""
        # Each symbol is ~60px wide + 8px spacing = 68px per item
        # Leave ~40px padding on sides
        available_width = Window.width - 40
        cols = max(10, int(available_width / 68))  # Minimum 10 columns
        return cols
    
    def _on_window_resize(self, instance, width):
        """Update grid columns when window is resized."""
        if hasattr(self, 'history_container'):
            self.history_container.cols = self._calculate_grid_cols()
    
    def toggle_monitoring(self, instance):
        """Start or stop serial monitoring."""
        if not self.is_monitoring:
            # Validate inputs
            ip = self.ip_input.text.strip()
            port_text = self.port_input.text.strip()
            url = self.url_input.text.strip()
            
            if not ip or not port_text or not url:
                logger.error("All fields must be filled")
                return
            
            try:
                port = int(port_text)
                if not (1 <= port <= 65535):
                    raise ValueError("Port out of range")
            except ValueError:
                logger.error("Invalid port number")
                return
            
            # Update config
            self.app_config.ip = ip
            self.app_config.port = port
            self.app_config.url = url
            
            # Start monitoring
            self.is_monitoring = True
            self.start_stop_btn.text = 'Stop'
            self.start_stop_btn.background_color = (0.82, 0.18, 0.18, 1)  # Rich red
            
            # Disable inputs
            self.ip_input.disabled = True
            self.port_input.disabled = True
            self.url_input.disabled = True
            self.save_btn.disabled = True
            
            # Start monitor thread
            self.monitor = SerialMonitor(
                port=SERIAL_PORT,
                baudrate=SERIAL_BAUDRATE,
                timeout=SERIAL_TIMEOUT,
                config=self.app_config,
                on_connected=self.on_connected,
                on_disconnected=self.on_disconnected,
                on_card=self.on_card_received,
                on_error=self.on_error
            )
            self.monitor.start()
            logger.info("Started monitoring")
            
        else:
            # Stop monitoring
            self.is_monitoring = False
            self.start_stop_btn.text = 'Start'
            self.start_stop_btn.background_color = (0.18, 0.62, 0.28, 1)  # Rich green
            
            if self.monitor:
                self.monitor.stop()
                self.monitor = None
            
            # Re-enable inputs
            self.ip_input.disabled = False
            self.port_input.disabled = False
            self.url_input.disabled = False
            self.save_btn.disabled = False
            
            self.status_indicator.set_connected(False, "Stopped")
            logger.info("Stopped monitoring")
    
    def save_configuration(self, instance):
        """Save current configuration to file."""
        ip = self.ip_input.text.strip()
        port_text = self.port_input.text.strip()
        url = self.url_input.text.strip()
        
        if not ip or not port_text or not url:
            logger.error("All fields must be filled")
            return
        
        try:
            port = int(port_text)
            if not (1 <= port <= 65535):
                raise ValueError("Port out of range")
        except ValueError:
            logger.error("Invalid port number")
            return
        
        self.app_config.ip = ip
        self.app_config.port = port
        self.app_config.url = url
        
        if save_config(self.app_config):
            logger.info("✅ Configuration saved")
    
    def clear_history(self, instance):
        """Clear history display."""
        self.history.clear()
        self.history_container.clear_widgets()
        logger.info("History cleared")
    
    def on_connected(self):
        """Called when serial port connects."""
        self.status_indicator.set_connected(True)
    
    def on_disconnected(self):
        """Called when serial port disconnects."""
        self.status_indicator.set_connected(False, "Disconnected (retrying...)")
    
    def on_error(self, message: str):
        """Called on error."""
        self.status_indicator.set_connected(False, f"Error: {message[:30]}")
    
    def on_card_received(self, card: str, success: bool):
        """Called when card event occurs (successful read or failed read).
        
        Args:
            card: Card code (e.g., '4S', 'KH'), or failure message (e.g., 'FAIL: E3 Card Not Read')
            success: True if card was successfully read, False if failed
        """
        # Determine symbol and color based on card status
        if card.startswith("FAIL:"):
            # Explicit failure with reason (e.g., "FAIL: E3 Card Not Read", "FAIL: Unreadable")
            symbol = '[FAIL]'      # Show failure indicator
            color = (1, 0, 0, 1)   # Red
        elif card and success:
            # Valid card successfully read (e.g., '4S', 'KH')
            symbol = '[OK]'        # Card successfully read
            color = (0.18, 0.62, 0.28, 1)  # Same green as Start button
        else:
            # Empty string or other generic failure
            symbol = '[X]'         # Card read failed
            color = (1, 0, 0, 1)   # Red
        
        # Add to history (only store what we need)
        entry = {
            'symbol': symbol,
            'color': color
        }
        self.history.append(entry)
        
        # Update UI
        self.render_history()
    
    def render_history(self):
        """Render history entries as a grid of symbols (no timestamp, no card value).
        
        Symbols fill row-wise (left to right), then wrap to next row.
        Each symbol is just a colored checkmark or X.
        """
        self.history_container.clear_widgets()
        
        # Add each symbol as a simple label in the grid
        for entry in self.history:
            # Create a single label for the symbol
            symbol_label = Label(
                text=entry['symbol'],
                size_hint=(None, None),  # Fixed size
                size=(60, 40),           # 60x40 pixels per symbol (wider for [OK] text)
                font_size='16sp',        # Smaller font for bracketed text
                bold=True,
                color=entry['color'],
                halign='center',
                valign='middle'
            )
            # Enable text alignment
            symbol_label.bind(size=symbol_label.setter('text_size'))
            
            # Add directly to grid (it handles row wrapping automatically)
            self.history_container.add_widget(symbol_label)
        
        # Auto-scroll to TOP to show newest symbols (scroll_y=1 is top, 0 is bottom)
        Clock.schedule_once(lambda dt: setattr(self.history_scroll, 'scroll_y', 1), 0.1)


if __name__ == '__main__':
    ShoeMonitorApp().run()
