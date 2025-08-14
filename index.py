# main.py
# ICD-10 Live Search - Kivy (RecycleView, auto theme detection, copy)
# Install: kivy, requests
# Build: buildozer android debug deploy run
 
import threading
import requests
from kivy.app import App
from kivy.metrics import dp
from kivy.clock import mainthread
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.label import Label
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.button import Button
from kivy.core.clipboard import Clipboard
from kivy.properties import StringProperty, BooleanProperty, ListProperty
from kivy.lang import Builder

API_URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"

KV = '''
<SelectableLabel@BoxLayout>:
    code: ''
    desc: ''
    orientation: 'vertical'
    size_hint_y: None
    height: dp(64)
    padding: dp(8)
    canvas.before:
        Color:
            rgba: root.bg_color
        Rectangle:
            pos: self.pos
            size: self.size
    Label:
        text: root.code
        size_hint_y: None
        height: self.texture_size[1]
        halign: 'left'
        valign: 'middle'
        text_size: self.width - dp(16), None
        bold: True
        color: root.text_color
    Label:
        text: root.desc
        size_hint_y: None
        height: self.texture_size[1]
        halign: 'left'
        valign: 'top'
        text_size: self.width - dp(16), None
        color: root.muted_color

<RootWidget>:
    orientation: 'vertical'
    padding: dp(8)
    spacing: dp(8)

    BoxLayout:
        size_hint_y: None
        height: dp(48)
        spacing: dp(8)
        TextInput:
            id: search_input
            hint_text: "Type diagnosis or code… e.g. fever, diabetes, I10"
            multiline: False
            on_text: root.on_text_change(self.text)
            foreground_color: root.text_color
            background_color: root.input_bg
            cursor_color: root.text_color
        ToggleButton:
            id: theme_toggle
            size_hint_x: None
            width: dp(110)
            text: 'Dark' if root.dark_theme else 'Light'
            on_state:
                root.toggle_theme(self.state == 'down')

    Label:
        id: status_lbl
        text: root.status_text
        size_hint_y: None
        height: dp(22)
        color: root.muted_color

    ScrollView:
        id: scroll
        do_scroll_x: False
        GridLayout:
            id: results_container
            cols: 1
            size_hint_y: None
            height: self.minimum_height
            row_default_height: dp(64)
            row_force_default: False
            spacing: dp(6)
            padding: dp(2)

    BoxLayout:
        size_hint_y: None
        height: dp(48)
        Button:
            text: "Copy Selected"
            on_release: root.copy_selected()
            background_color: root.button_bg
            color: root.button_text
'''

class RootWidget(BoxLayout):
    status_text = StringProperty("")
    dark_theme = BooleanProperty(True)
    selected_text = StringProperty("")
    # theme colors (will be set by apply_theme)
    bg = ListProperty([0.06, 0.09, 0.16, 1])          # page bg
    input_bg = ListProperty([0.117, 0.160, 0.227, 1]) # input bg
    card_bg = ListProperty([0.07, 0.07, 0.07, 1])     # item bg
    text_color = ListProperty([1, 1, 1, 1])
    muted_color = ListProperty([0.58, 0.64, 0.72, 1])
    button_bg = ListProperty([0.09, 0.11, 0.13, 1])
    button_text = ListProperty([1,1,1,1])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        # load kv
        Builder.load_string(KV)
        # attempt to detect system theme on Android
        self.detect_system_theme()
        # apply theme colors to properties
        self.apply_theme(self.dark_theme)

        # small debounce state
        self._debounce_ev = None

    def detect_system_theme(self):
        # Try Android UiModeManager via pyjnius
        try:
            from jnius import autoclass
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            Context = autoclass('android.content.Context')
            activity = PythonActivity.mActivity
            ui_mode_service = activity.getSystemService(Context.UI_MODE_SERVICE)
            # UI_MODE_NIGHT_YES = 0x20 (bitmask) — use getNightMode if available
            try:
                UiModeManager = autoclass('android.app.UiModeManager')
                # getNightMode exists API 29+; else fallback to configuration
                night = ui_mode_service.getNightMode()
                # constants: MODE_NIGHT_YES == 2
                self.dark_theme = (night == 2)
            except Exception:
                # fallback: configuration.uiMode & UI_MODE_NIGHT_MASK
                Configuration = autoclass('android.content.res.Configuration')
                cfg = activity.getResources().getConfiguration()
                mask = cfg.uiMode & Configuration.UI_MODE_NIGHT_MASK
                # UI_MODE_NIGHT_YES == 0x20
                self.dark_theme = (mask == Configuration.UI_MODE_NIGHT_YES)
        except Exception:
            # Not Android or pyjnius not available -> keep default
            pass

    def apply_theme(self, dark: bool):
        if dark:
            self.bg = [0.06, 0.09, 0.16, 1]
            self.input_bg = [0.117, 0.160, 0.227, 1]
            self.card_bg = [0.12, 0.12, 0.12, 1]
            self.text_color = [1,1,1,1]
            self.muted_color = [0.58, 0.64, 0.72, 1]
            self.button_bg = [0.2, 0.3, 0.65, 1]
            self.button_text = [1,1,1,1]
        else:
            self.bg = [1,1,1,1]
            self.input_bg = [0.95,0.95,0.95,1]
            self.card_bg = [0.98,0.98,0.98,1]
            self.text_color = [0.06,0.09,0.16,1]
            self.muted_color = [0.35,0.35,0.35,1]
            self.button_bg = [0.12,0.5,0.9,1]
            self.button_text = [1,1,1,1]
        # apply background to root window
        try:
            from kivy.core.window import Window
            Window.clearcolor = self.bg
        except Exception:
            pass

    def toggle_theme(self, dark_on: bool):
        self.dark_theme = dark_on
        self.apply_theme(self.dark_theme)
        # update toggle button label text
        tb = self.ids.get('theme_toggle', None)
        if tb:
            tb.text = 'Dark' if dark_on else 'Light'

    def on_text_change(self, text):
        # debounce: schedule search after 0.3s
        if self._debounce_ev:
            self._debounce_ev.cancel()
        q = text.strip()
        if not q:
            self.clear_results()
            self.status_text = ""
            return
        from kivy.clock import Clock
        self._debounce_ev = Clock.schedule_once(lambda dt: self._search(q), 0.30)

    def _search(self, query):
        threading.Thread(target=self._fetch, args=(query,), daemon=True).start()

    def _fetch(self, query):
        self.status_text = "Searching..."
        self.clear_results()
        try:
            params = {'sf':'code,name','terms':query,'maxList':30}
            r = requests.get(API_URL, params=params, timeout=6)
            r.raise_for_status()
            data = r.json()
            rows = data[3] if len(data) > 3 else []
            self.render_results(rows, query)
        except Exception as e:
            self.status_text = f"Error: {e}"

    @mainthread
    def render_results(self, rows, query):
        container = self.ids.results_container
        container.clear_widgets()
        if not rows:
            self.status_text = "No results found."
            return
        for code, name in rows:
            # create the selectable label widget via Builder rule
            w = Builder.template('SelectableLabel', code=code, desc=name)
            # set theme colors on widget
            w.bg_color = self.card_bg
            w.text_color = self.text_color
            w.muted_color = self.muted_color
            # bind touch to select
            def _on_touch(instance, touch, txt=f"{code} - {name}"):
                if instance.collide_point(*touch.pos):
                    self.selected_text = txt
                    self.status_text = f"Selected: {txt}"
            w.bind(on_touch_down=_on_touch)
            container.add_widget(w)
        self.status_text = f"Found {len(rows)} results for '{query}' (tap to select)"

    def clear_results(self):
        try:
            self.ids.results_container.clear_widgets()
        except Exception:
            pass
        self.selected_text = ""

    def copy_selected(self):
        if self.selected_text:
            try:
                Clipboard.copy(self.selected_text)
                self.status_text = f"Copied: {self.selected_text}"
            except Exception as e:
                self.status_text = f"Copy failed: {e}"
        else:
            self.status_text = "Select an item first."

class ICD10App(App):
    def build(self):
        root = RootWidget()
        return root

if __name__ == '__main__':
    ICD10App().run()
