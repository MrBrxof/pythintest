import sys
import json
import os
import uuid
import webbrowser
import urllib.request
import ssl
import telebot
import random
import requests
import time
import concurrent.futures
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QPushButton, QLabel, QStackedWidget, QSpacerItem, 
                             QSizePolicy, QHBoxLayout, QStyle, QMessageBox, QFrame,
                             QGraphicsBlurEffect)
from PyQt6.QtCore import Qt, QPoint, QSize, QThread, pyqtSignal, QTimer, QRectF, QPropertyAnimation, QRect, QEasingCurve
from PyQt6.QtGui import (QFont, QCursor, QIcon, QPainter, QColor, QPen, 
                         QPixmap, QPainterPath)

try:
    import socks
except ImportError:
    print("\n" + "!"*60)
    print("❌ КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ: Не установлена библиотека PySocks!")
    print("pip install PySocks -i https://pypi.tuna.tsinghua.edu.cn/simple")
    print("!"*60 + "\n")

# Отключаем строгую проверку SSL-сертификатов
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

CACHE_DIR = "Cache"
os.makedirs(CACHE_DIR, exist_ok=True)
CONFIG_FILE = os.path.join(CACHE_DIR, "brxof_vpn_config.json")
BOT_TOKEN = "8864809709:AAGQyPLYBR5VNy_spw_NpKV71wYDWjb7iqo"

# Увеличиваем таймауты для API телеграма, чтобы файлы успевали скачиваться
telebot.apihelper.READ_TIMEOUT = 10
telebot.apihelper.CONNECT_TIMEOUT = 10

def get_icon(filename, url):
    filepath = os.path.join(CACHE_DIR, filename)
    if not os.path.exists(filepath):
        try:
            urllib.request.urlretrieve(url, filepath)
        except Exception as e:
            print(f"Ошибка загрузки {filename}: {e}")
    return filepath

# Загружаем все необходимые иконки
TG_ICON_PATH = get_icon("telegram.png", "https://img.icons8.com/color/48/telegram-app--v1.png")
HOME_ICON_PATH = get_icon("home.png", "https://img.icons8.com/ios-filled/48/ffffff/home.png")
WALLET_ICON_PATH = get_icon("wallet.png", "https://img.icons8.com/ios-filled/48/ffffff/wallet.png")
SETTINGS_ICON_PATH = get_icon("settings.png", "https://img.icons8.com/ios-filled/48/ffffff/settings.png")
LIGHTNING_ICON_PATH = get_icon("lightning.png", "https://img.icons8.com/ios-filled/100/ffffff/lightning-bolt.png")

def get_white_system_icon(style, standard_pixmap):
    icon = style.standardIcon(standard_pixmap)
    pixmap = icon.pixmap(16, 16)
    painter = QPainter(pixmap)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), QColor("white"))
    painter.end()
    return QIcon(pixmap)

class LoadingButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._is_loading = False
        self._angle = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.rotate)
        self._original_text = text
        self._original_icon = QIcon()

    def start_loading(self):
        self._is_loading = True
        self._original_icon = self.icon()
        self.setIcon(QIcon())
        self.setText("")
        self.timer.start(25)
        self.setEnabled(False)

    def stop_loading(self, new_text=None):
        self._is_loading = False
        self.timer.stop()
        self.setText(new_text if new_text else self._original_text)
        if not new_text:
            self.setIcon(self._original_icon)
        self.setEnabled(True)

    def rotate(self):
        self._angle = (self._angle + 10) % 360
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._is_loading:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(QColor(255, 255, 255))
            pen.setWidth(3)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            size = min(self.width(), self.height()) - 20
            rect = QRectF((self.width() - size) / 2, (self.height() - size) / 2, size, size)
            painter.drawArc(rect, -self._angle * 16, 120 * 16)

# --- ПОТОК ДЛЯ РАБОТЫ TELEGRAM БОТА ---
class BotAuthThread(QThread):
    auth_success = pyqtSignal(dict)
    auth_error = pyqtSignal(str)
    url_ready = pyqtSignal(str)

    def __init__(self, token):
        super().__init__()
        self.bot_token = token
        self.bot = telebot.TeleBot(token)
        self.auth_id = str(uuid.uuid4()).replace('-', '') 
        self.running = True
        self.is_url_emitted = False

        @self.bot.message_handler(commands=['start'])
        def handle_start(message):
            if not self.running: 
                return
            
            parts = message.text.split()
            if len(parts) > 1 and parts[1] == self.auth_id:
                user_id = message.from_user.id
                user_data = {
                    "name": message.from_user.first_name or "User",
                    "username": message.from_user.username or "",
                    "id": user_id,
                    "avatar_path": ""
                }
                
                # Защищенный блок скачивания аватарки с ретраями
                for attempt in range(3):
                    try:
                        photos = self.bot.get_user_profile_photos(user_id)
                        if photos.total_count > 0:
                            file_id = photos.photos[0][-1].file_id 
                            file_info = self.bot.get_file(file_id)
                            downloaded_file = self.bot.download_file(file_info.file_path)
                            
                            avatar_path = os.path.join(CACHE_DIR, f"avatar_{user_id}.jpg")
                            with open(avatar_path, 'wb') as new_file:
                                new_file.write(downloaded_file)
                            user_data["avatar_path"] = avatar_path
                        break # Если всё ок, выходим из цикла попыток
                    except Exception:
                        if attempt == 2:
                            print("⚠️ Аватарка пропущена (прокси сбрасывает загрузку файла).")
                        time.sleep(1)

                # Отправка сообщения с ретраями
                for attempt in range(3):
                    try:
                        self.bot.reply_to(message, "✅ Авторизация успешна! Можете вернуться в приложение.")
                        break
                    except Exception:
                        if attempt == 2:
                            print("⚠️ Не удалось отправить сообщение в Telegram, но авторизация засчитана.")
                        time.sleep(1)
                
                self.auth_success.emit(user_data)
                self.stop()
            else:
                try:
                    self.bot.reply_to(message, "⚠️ Неверная или устаревшая ссылка авторизации.")
                except:
                    pass

    def fetch_proxies(self):
        print("⏳ Загрузка баз SOCKS и HTTP прокси с GitHub...")
        proxies = []
        sources = {
            "socks5": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
            "socks4": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
            "http": "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt"
        }
        
        for protocol, url in sources.items():
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    text = response.read().decode('utf-8')
                    lines = [line.strip() for line in text.split('\n') if line.strip() and ":" in line]
                    proxies.extend([f"{protocol}://{line}" for line in lines])
            except Exception as e:
                print(f"⚠️ Ошибка загрузки {protocol}: {e}")
                
        random.shuffle(proxies)
        proxies = list(dict.fromkeys(proxies))
        proxies.sort(key=lambda x: 0 if x.startswith("socks") else 1) 
        return proxies

    def get_working_proxy(self, proxies):
        print("⏳ Ищем стабильный прокси...")
        batch_size = 30 
        
        def test_proxy(p):
            try:
                res = requests.get(f"https://api.telegram.org/bot{self.bot_token}/getMe", 
                                   proxies={"https": p, "http": p}, timeout=3.5)
                if res.status_code == 200:
                    return p
            except:
                pass
            return None

        for i in range(0, min(900, len(proxies)), batch_size):
            if not self.running: return None
            
            batch = proxies[i:i+batch_size]
            with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
                futures = [executor.submit(test_proxy, p) for p in batch]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result:
                        proxies.remove(result) 
                        return result 
        return None

    def run(self):
        try:
            proxies = self.fetch_proxies()
            working_proxy = None
            
            while self.running:
                if not working_proxy:
                    if proxies:
                        working_proxy = self.get_working_proxy(proxies)
                    
                    if working_proxy:
                        print(f"✅ УСТАНОВЛЕН ПРОКСИ: {working_proxy}")
                        telebot.apihelper.proxy = {'https': working_proxy}
                    else:
                        print("\n🔴 ОШИБКА: Доступные прокси закончились.\n")
                        self.auth_error.emit("Не удалось связаться с Telegram. Включите свой VPN.")
                        return

                try:
                    bot_info = self.bot.get_me()
                    
                    if not self.is_url_emitted:
                        url = f"https://t.me/{bot_info.username}?start={self.auth_id}"
                        print("\n" + "="*40)
                        print("🟢 Бот успешно запущен локально!")
                        print(f"🔗 Ссылка для входа: {url}")
                        print("="*40 + "\n")
                        self.url_ready.emit(url)
                        self.is_url_emitted = True
                    
                    self.bot.remove_webhook()
                    self.bot.polling(none_stop=False, timeout=5)
                    
                except telebot.apihelper.ApiTelegramException as e:
                    if "Conflict" in str(e):
                        print("\n🔴 ОШИБКА: Бот уже запущен в другом месте.\n")
                        self.auth_error.emit("Бот уже запущен. Закройте его копию и повторите.")
                        break
                    else:
                        working_proxy = None 
                except Exception:
                    working_proxy = None 
                    self.sleep(1)
                    
        except Exception as e:
            self.auth_error.emit(f"Произошла ошибка ядра: {e}")

    def stop(self):
        self.running = False
        self.bot.stop_polling()
        self.quit()

class CustomTitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(15, 0, 0, 0) 
        self.layout.setSpacing(0) 
        self.setFixedHeight(30) 
        self.initial_pos = None

        self.title = QLabel("Brxof VPN")
        self.title.setFont(QFont("Segoe UI", 9)) 
        self.title.setStyleSheet("color: #bbbbbb;") 

        self.btn_min = QPushButton() 
        white_min_icon = get_white_system_icon(self.style(), QStyle.StandardPixmap.SP_TitleBarMinButton)
        self.btn_min.setIcon(white_min_icon)
        self.btn_min.setFixedSize(45, 30)
        self.btn_min.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_min.setStyleSheet("""
            QPushButton { background-color: transparent; border: none; }
            QPushButton:hover { background-color: #333333; }
            QPushButton:pressed { background-color: #444444; }
        """)
        self.btn_min.clicked.connect(self.parent.showMinimized)

        self.btn_close = QPushButton() 
        white_close_icon = get_white_system_icon(self.style(), QStyle.StandardPixmap.SP_TitleBarCloseButton)
        self.btn_close.setIcon(white_close_icon)
        self.btn_close.setFixedSize(45, 30)
        self.btn_close.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.btn_close.setStyleSheet("""
            QPushButton { 
                background-color: transparent; border: none; 
                border-top-right-radius: 12px; 
            }
            QPushButton:hover { background-color: #e81123; }
            QPushButton:pressed { background-color: #f1707a; }
        """)
        self.btn_close.clicked.connect(self.parent.close)

        self.layout.addWidget(self.title)
        self.layout.addStretch() 
        self.layout.addWidget(self.btn_min)
        self.layout.addWidget(self.btn_close)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.initial_pos = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.initial_pos is not None:
            delta = event.position().toPoint() - self.initial_pos
            self.parent.move(self.parent.x() + delta.x(), self.parent.y() + delta.y())

    def mouseReleaseEvent(self, event):
        self.initial_pos = None

class BrxofVPN(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setFixedSize(360, 640)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.auth_thread = None
        self.current_auth_action = None
        
        self.main_widget = QWidget()
        self.setCentralWidget(self.main_widget)
        self.main_layout = QVBoxLayout(self.main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.main_widget.setStyleSheet("""
            QWidget#MainWidget {
                background-color: #0a0a0a;
                border-radius: 12px; 
                border: 1px solid #1f1f1f;
            }
            QWidget {
                background-color: transparent;
                color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QLabel { background-color: transparent; }
        """)
        self.main_widget.setObjectName("MainWidget")

        self.title_bar = CustomTitleBar(self)
        self.main_layout.addWidget(self.title_bar)

        self.stacked_widget = QStackedWidget()
        self.main_layout.addWidget(self.stacked_widget)

        self.login_screen = QWidget()
        self.main_screen = QWidget()
        
        self.setup_login_screen()
        self.setup_tab_settings() 
        self.setup_main_screen()

        self.stacked_widget.addWidget(self.login_screen)
        self.stacked_widget.addWidget(self.main_screen)

        self.auth_data = self.check_auth()
        if self.auth_data.get("logged_in", False):
            self.update_profile_ui(self.auth_data)
            self.stacked_widget.setCurrentWidget(self.main_screen)
        else:
            self.stacked_widget.setCurrentWidget(self.login_screen)

    def check_auth(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as file:
                    return json.load(file)
            except Exception:
                return {"logged_in": False}
        return {"logged_in": False}

    def save_auth(self, status, data=None):
        auth_data = {"logged_in": status}
        if data:
            auth_data.update(data)
        with open(CONFIG_FILE, 'w') as file:
            json.dump(auth_data, file)
        return auth_data

    def setup_login_screen(self):
        layout = QVBoxLayout(self.login_screen)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(30, 0, 30, 30) 

        title_label = QLabel("Brxof VPN")
        title_label.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        subtitle_label = QLabel("Для использования требуется\nпривязать аккаунт")
        subtitle_label.setFont(QFont("Arial", 12))
        subtitle_label.setStyleSheet("color: #aaaaaa;")
        subtitle_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))

        self.tg_button = LoadingButton(" Войти через Telegram") 
        self.tg_button.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.tg_button.setFixedHeight(50)
        
        if os.path.exists(TG_ICON_PATH):
            self.tg_button.setIcon(QIcon(TG_ICON_PATH))
            self.tg_button.setIconSize(QSize(24, 24)) 
        
        self.tg_button.setStyleSheet("""
            QPushButton {
                background-color: #2AABEE; color: white;
                border-radius: 12px; font-size: 15px; font-weight: bold;
                padding-left: 15px; padding-right: 15px;
            }
            QPushButton:hover { background-color: #229ED9; }
            QPushButton:pressed { background-color: #1c88ba; padding-top: 3px; padding-left: 3px; }
            QPushButton:disabled { background-color: #333333; color: transparent; }
        """)
        self.tg_button.clicked.connect(self.action_open_browser)
        layout.addWidget(self.tg_button)

        self.copy_btn = LoadingButton(" Скопировать ссылку Telegram")
        self.copy_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.copy_btn.setFixedHeight(40)
        self.copy_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent; color: #2AABEE;
                border: 2px solid #2AABEE; border-radius: 12px;
                font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #112233; }
            QPushButton:pressed { background-color: #1a3344; padding-top: 3px; padding-left: 3px; }
            QPushButton:disabled { color: transparent; border-color: #555555; }
        """)
        self.copy_btn.clicked.connect(self.action_copy_link)
        layout.addWidget(self.copy_btn)

        layout.addItem(QSpacerItem(20, 60, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def setup_main_screen(self):
        self.content_wrapper = QWidget(self.main_screen)
        self.content_wrapper.setGeometry(0, 0, 360, 610) 
        wrapper_layout = QVBoxLayout(self.content_wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.setSpacing(0)

        self.tabs_widget = QStackedWidget()
        
        self.tab_home = QWidget()
        self.tab_balance = QWidget()

        self.setup_tab_home()
        self.setup_tab_balance()

        self.tabs_widget.addWidget(self.tab_home)
        self.tabs_widget.addWidget(self.tab_balance)
        self.tabs_widget.addWidget(self.tab_settings)

        self.bottom_nav = QFrame()
        self.bottom_nav.setFixedHeight(60)
        self.bottom_nav.setStyleSheet("""
            QFrame {
                background-color: #0f0f0f; border-top: 1px solid #1f1f1f;
                border-bottom-left-radius: 12px; border-bottom-right-radius: 12px;
            }
        """)
        nav_layout = QHBoxLayout(self.bottom_nav)
        nav_layout.setContentsMargins(20, 5, 20, 5)
        nav_layout.setSpacing(15)

        self.btn_nav_home = QPushButton()
        if os.path.exists(HOME_ICON_PATH): self.btn_nav_home.setIcon(QIcon(HOME_ICON_PATH))
        
        self.btn_nav_balance = QPushButton()
        if os.path.exists(WALLET_ICON_PATH): self.btn_nav_balance.setIcon(QIcon(WALLET_ICON_PATH))
        
        self.btn_nav_settings = QPushButton()
        if os.path.exists(SETTINGS_ICON_PATH): self.btn_nav_settings.setIcon(QIcon(SETTINGS_ICON_PATH))

        nav_btns = [self.btn_nav_home, self.btn_nav_balance, self.btn_nav_settings]
        for idx, btn in enumerate(nav_btns):
            btn.setCheckable(True)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setIconSize(QSize(28, 28))
            btn.setStyleSheet("""
                QPushButton { background-color: transparent; border: none; border-radius: 12px; padding: 5px; }
                QPushButton:hover { background-color: #1a1a1a; }
                QPushButton:checked { background-color: #1f3a55; }
                QPushButton:pressed { background-color: #1a2a3a; padding-top: 8px; padding-left: 8px; }
            """)
            btn.clicked.connect(lambda checked, i=idx: self.switch_tab(i))
            nav_layout.addWidget(btn)

        self.btn_nav_home.setChecked(True)

        wrapper_layout.addWidget(self.tabs_widget)
        wrapper_layout.addWidget(self.bottom_nav)

        self.blur_effect = QGraphicsBlurEffect()
        self.blur_effect.setBlurRadius(0)
        self.content_wrapper.setGraphicsEffect(self.blur_effect)

        self.payment_overlay = QWidget(self.main_screen)
        self.payment_overlay.setGeometry(0, 0, 360, 610)
        self.payment_overlay.setStyleSheet("background-color: rgba(0, 0, 0, 150);")
        self.payment_overlay.hide()
        self.payment_overlay.mousePressEvent = self.close_payment_drawer

        self.payment_drawer = QFrame(self.payment_overlay)
        self.drawer_height = 250
        self.payment_drawer.setGeometry(0, 610, 360, self.drawer_height) 
        self.payment_drawer.setStyleSheet("""
            QFrame { background-color: #151515; border-top-left-radius: 20px; border-top-right-radius: 20px; border: 1px solid #2a2a2a; }
        """)
        
        drawer_layout = QVBoxLayout(self.payment_drawer)
        drawer_layout.setContentsMargins(20, 20, 20, 30)
        drawer_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        drawer_title = QLabel("Выберите способ оплаты")
        drawer_title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        drawer_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        stars_btn = QPushButton("Пополнить через Telegram Stars")
        stars_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        stars_btn.setFixedHeight(50)
        stars_btn.setStyleSheet("""
            QPushButton { background-color: #2AABEE; color: white; border-radius: 12px; font-size: 15px; font-weight: bold; }
            QPushButton:hover { background-color: #229ED9; }
            QPushButton:pressed { background-color: #1c88ba; padding-top: 3px; padding-left: 3px; }
        """)
        stars_btn.clicked.connect(lambda: QMessageBox.information(self, "В разработке", "Оплата через Telegram Stars скоро будет добавлена!"))

        drawer_layout.addWidget(drawer_title)
        drawer_layout.addSpacing(20)
        drawer_layout.addWidget(stars_btn)
        
        self.drawer_anim = QPropertyAnimation(self.payment_drawer, b"geometry")
        self.drawer_anim.setDuration(300)
        self.drawer_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def switch_tab(self, index):
        btns = [self.btn_nav_home, self.btn_nav_balance, self.btn_nav_settings]
        for i, btn in enumerate(btns):
            btn.setChecked(i == index)
        self.tabs_widget.setCurrentIndex(index)

    def setup_tab_home(self):
        layout = QVBoxLayout(self.tab_home)
        layout.setContentsMargins(20, 20, 20, 20)
        
        self.profile_frame = QFrame()
        self.profile_frame.setFixedHeight(65)
        self.profile_frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.profile_frame.setStyleSheet("""
            QFrame { background-color: #131313; border: 1px solid #222222; border-radius: 15px; }
        """)
        
        profile_layout = QHBoxLayout(self.profile_frame)
        profile_layout.setContentsMargins(10, 0, 15, 0)

        self.avatar_label = QLabel("?")
        self.avatar_label.setFixedSize(40, 40)
        self.avatar_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar_label.setStyleSheet("QLabel { background-color: #2AABEE; color: white; border-radius: 20px; font-size: 18px; font-weight: bold; border: none; }")

        name_container = QVBoxLayout()
        name_container.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        name_container.setSpacing(0)
        
        self.profile_name = QLabel("Имя")
        self.profile_name.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.profile_name.setStyleSheet("border: none; padding: 0px; margin: 0px;")
        
        self.profile_username = QLabel("@username")
        self.profile_username.setFont(QFont("Segoe UI", 9))
        self.profile_username.setStyleSheet("color: #888888; border: none; padding: 0px; margin: 0px;")

        name_container.addWidget(self.profile_name)
        name_container.addWidget(self.profile_username)

        profile_layout.addWidget(self.avatar_label)
        profile_layout.addSpacing(10)
        profile_layout.addLayout(name_container)

        top_h_layout = QHBoxLayout()
        top_h_layout.addWidget(self.profile_frame, alignment=Qt.AlignmentFlag.AlignLeft)
        top_h_layout.addStretch()

        self.connect_btn = QPushButton()
        self.connect_btn.setFixedSize(110, 110)
        self.connect_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        
        if os.path.exists(LIGHTNING_ICON_PATH):
            self.connect_btn.setIcon(QIcon(LIGHTNING_ICON_PATH))
            self.connect_btn.setIconSize(QSize(50, 50))
            
        self.connect_btn.setStyleSheet("""
            QPushButton { background-color: #1a1a1a; border: 4px solid #2AABEE; border-radius: 55px; }
            QPushButton:hover { background-color: #262626; border: 4px solid #3bc0ff; }
            QPushButton:pressed { background-color: #111111; padding-top: 6px; padding-left: 6px; }
        """)

        layout.addLayout(top_h_layout)
        layout.addItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        layout.addWidget(self.connect_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addItem(QSpacerItem(20, 60, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

    def setup_tab_balance(self):
        layout = QVBoxLayout(self.tab_balance)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        balance_title = QLabel("Ваш баланс")
        balance_title.setStyleSheet("color: #888888; font-size: 14px; margin: 0px;")
        balance_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.balance_amount = QLabel("50 ₽")
        self.balance_amount.setFont(QFont("Segoe UI", 36, QFont.Weight.Bold))
        self.balance_amount.setStyleSheet("margin: 0px; padding: 0px;")
        self.balance_amount.setAlignment(Qt.AlignmentFlag.AlignCenter)

        topup_btn = QPushButton("Пополнить")
        topup_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        topup_btn.setFixedSize(140, 40)
        topup_btn.setStyleSheet("""
            QPushButton { background-color: #2AABEE; color: white; border-radius: 12px; font-size: 14px; font-weight: bold; }
            QPushButton:hover { background-color: #229ED9; }
            QPushButton:pressed { background-color: #1c88ba; padding-top: 2px; padding-left: 2px; }
        """)
        topup_btn.clicked.connect(self.open_payment_drawer)

        layout.addWidget(balance_title)
        layout.addWidget(self.balance_amount)
        layout.addSpacing(10)
        layout.addWidget(topup_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(30)

        plan_title = QLabel("Ваш тариф: Бесплатный")
        plan_title.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(plan_title)
        layout.addSpacing(10)

        deluxe_card = QFrame()
        deluxe_card.setStyleSheet("QFrame { background-color: #262210; border: 1px solid #7A6510; border-radius: 12px; padding: 10px; }")
        dlx_layout = QHBoxLayout(deluxe_card)
        dlx_title = QLabel("👑 Deluxe")
        dlx_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #FFD700; border: none;")
        dlx_price = QLabel("50 ₽ / мес")
        dlx_price.setStyleSheet("color: #aaaaaa; border: none;")
        dlx_layout.addWidget(dlx_title)
        dlx_layout.addStretch()
        dlx_layout.addWidget(dlx_price)
        layout.addWidget(deluxe_card)

        premium_card = QFrame()
        premium_card.setStyleSheet("QFrame { background-color: #1e1329; border: 1px solid #5C209A; border-radius: 12px; padding: 10px; }")
        prm_layout = QHBoxLayout(premium_card)
        prm_title = QLabel("💎 Premium")
        prm_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #B824FF; border: none;")
        prm_price = QLabel("199 ₽ / мес")
        prm_price.setStyleSheet("color: #aaaaaa; border: none;")
        prm_layout.addWidget(prm_title)
        prm_layout.addStretch()
        prm_layout.addWidget(prm_price)
        layout.addWidget(premium_card)
        
        layout.addStretch()

    def setup_tab_settings(self):
        self.tab_settings = QWidget()
        layout = QVBoxLayout(self.tab_settings)
        layout.setContentsMargins(20, 30, 20, 20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        title = QLabel("Настройки")
        title.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        layout.addWidget(title)
        layout.addSpacing(20)

        self.admin_btn = QPushButton("Админ панель")
        self.admin_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.admin_btn.setFixedHeight(45)
        self.admin_btn.setStyleSheet("""
            QPushButton { background-color: #ff9800; color: white; border-radius: 12px; font-size: 14px; font-weight: bold; }
            QPushButton:hover { background-color: #e68a00; }
            QPushButton:pressed { background-color: #cc7a00; padding-top: 2px; padding-left: 2px; }
        """)
        self.admin_btn.hide() 
        layout.addWidget(self.admin_btn)
        
        layout.addSpacing(10)

        logout_btn = QPushButton("Отвязать аккаунт Telegram")
        logout_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        logout_btn.setFixedHeight(45)
        logout_btn.setStyleSheet("""
            QPushButton { background-color: rgba(255, 68, 68, 0.1); color: #ff4444; border: 1px solid #ff4444; border-radius: 12px; font-size: 14px; font-weight: bold; }
            QPushButton:hover { background-color: rgba(255, 68, 68, 0.2); }
            QPushButton:pressed { background-color: rgba(200, 50, 50, 0.2); padding-top: 2px; padding-left: 2px; }
        """)
        logout_btn.clicked.connect(self.logout)
        
        layout.addWidget(logout_btn)
        layout.addStretch()

    def open_payment_drawer(self):
        self.payment_overlay.show()
        self.blur_effect.setBlurRadius(10) 
        
        self.drawer_anim.setStartValue(QRect(0, 610, 360, self.drawer_height))
        self.drawer_anim.setEndValue(QRect(0, 610 - self.drawer_height, 360, self.drawer_height))
        self.drawer_anim.start()

    def close_payment_drawer(self, event=None):
        if event and event.pos().y() > (610 - self.drawer_height):
            return 
            
        self.blur_effect.setBlurRadius(0) 
        
        self.drawer_anim.setStartValue(QRect(0, 610 - self.drawer_height, 360, self.drawer_height))
        self.drawer_anim.setEndValue(QRect(0, 610, 360, self.drawer_height))
        
        self.drawer_anim.finished.connect(self.hide_overlay)
        self.drawer_anim.start()

    def hide_overlay(self):
        self.payment_overlay.hide()
        self.drawer_anim.finished.disconnect(self.hide_overlay)

    def update_profile_ui(self, data):
        name = data.get("name", "User")
        username = data.get("username", "")
        avatar_path = data.get("avatar_path", "")
        
        self.profile_name.setText(name)
        if username:
            formatted_user = f"@{username}" if not username.startswith("@") else username
            self.profile_username.setText(formatted_user)
            if formatted_user.lower() == "@brxofi":
                self.admin_btn.show()
            else:
                self.admin_btn.hide()
        else:
            self.profile_username.setText("Без юзернейма")
            self.admin_btn.hide()
            
        if avatar_path and os.path.exists(avatar_path):
            pixmap = QPixmap(avatar_path)
            pixmap = pixmap.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            
            target = QPixmap(40, 40)
            target.fill(Qt.GlobalColor.transparent)
            
            painter = QPainter(target)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addEllipse(0, 0, 40, 40)
            painter.setClipPath(path)
            
            x_offset = (40 - pixmap.width()) // 2
            y_offset = (40 - pixmap.height()) // 2
            painter.drawPixmap(x_offset, y_offset, pixmap)
            painter.end()
            
            self.avatar_label.setPixmap(target)
            self.avatar_label.setText("") 
            self.avatar_label.setStyleSheet("background-color: transparent; border: none;")
        else:
            if name:
                self.avatar_label.setPixmap(QPixmap()) 
                self.avatar_label.setText(name[0].upper())
                self.avatar_label.setStyleSheet("""
                    QLabel { background-color: #2AABEE; color: white; border-radius: 20px; font-size: 18px; font-weight: bold; border: none; }
                """)

    def action_open_browser(self):
        self.current_auth_action = "open"
        self.tg_button.start_loading()
        self.copy_btn.setEnabled(False)
        self.start_bot()

    def action_copy_link(self):
        self.current_auth_action = "copy"
        self.copy_btn.start_loading()
        self.tg_button.setEnabled(False)
        self.start_bot()

    def start_bot(self):
        if self.auth_thread and self.auth_thread.isRunning() and hasattr(self, 'current_auth_url'):
            self.process_auth_action(self.current_auth_url)
            return

        self.auth_thread = BotAuthThread(BOT_TOKEN)
        self.auth_thread.url_ready.connect(self.on_url_ready)
        self.auth_thread.auth_success.connect(self.on_auth_success)
        self.auth_thread.auth_error.connect(self.on_auth_error)
        self.auth_thread.start()

    def on_url_ready(self, url):
        self.current_auth_url = url
        self.process_auth_action(url)
        
        if self.current_auth_action == "copy":
            self.copy_btn.stop_loading(" Скопировано!")
            self.tg_button.setEnabled(True)
        else:
            self.tg_button.stop_loading()
            self.copy_btn.setEnabled(True)

    def process_auth_action(self, url):
        if self.current_auth_action == "open":
            webbrowser.open(url)
        elif self.current_auth_action == "copy":
            QApplication.clipboard().setText(url)

    def on_auth_success(self, user_data):
        self.tg_button.stop_loading()
        self.copy_btn.stop_loading()
        
        auth_data = self.save_auth(True, user_data)
        self.update_profile_ui(auth_data)
        
        self.switch_tab(0)
        self.stacked_widget.setCurrentWidget(self.main_screen)

    def on_auth_error(self, error_text):
        self.tg_button.stop_loading()
        self.copy_btn.stop_loading()
        
        msg = QMessageBox(self)
        msg.setWindowTitle("Ошибка")
        msg.setText(error_text)
        msg.setStyleSheet("background-color: #222222; color: white;")
        msg.exec()

    def logout(self):
        if self.auth_thread and self.auth_thread.isRunning():
            self.auth_thread.stop()
            
        avatar_path = self.auth_data.get("avatar_path", "") if hasattr(self, 'auth_data') else ""
        if avatar_path and os.path.exists(avatar_path):
            try:
                os.remove(avatar_path)
            except:
                pass

        self.save_auth(False)
        self.tg_button.stop_loading()
        self.copy_btn.stop_loading()
        self.copy_btn.setText(" Скопировать ссылку Telegram")
        self.stacked_widget.setCurrentWidget(self.login_screen)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Segoe UI", 10))
    window = BrxofVPN()
    window.show()
    sys.exit(app.exec())