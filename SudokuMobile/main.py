import os
import json
import random
import time
import threading
import webbrowser

from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.utils import get_color_from_hex
from kivy.properties import StringProperty, NumericProperty, ListProperty

# --- Константы ---
LEVELS = ["Легкий", "Средний", "Сложный", "Эксперт"]
PRICE_1 = 30
PRICE_3 = 75
REWARD_WIN = 50
REWARD_LOSS = 5
START_HINTS = 3
START_COINS = 0

SAVE_FILE = "sudoku_save.json"
STATS_FILE = "sudoku_stats.json"

# Для Android путь для сохранений — во внутреннюю память приложения
if platform_name := __import__('kivy.utils').utils.platform:
    if platform_name == 'android':
        from android.storage import app_storage_path
        SAVE_FILE = os.path.join(app_storage_path(), SAVE_FILE)
        STATS_FILE = os.path.join(app_storage_path(), STATS_FILE)

# Цвета (Kivy по умолчанию RGBA 0-1, конвертируем hex)
def c(hex_str):
    return get_color_from_hex(hex_str)

BG = c('#2c3e50')
PANEL = c('#34495e')
ACCENT = c('#f1c40f')
CYAN = c('#4ecdc4')
RED = c('#e74c3c')
GREEN = c('#27ae60')
CELL_BG = c('#ecf0f1')
CELL_FIXED = c('#e74c3c')
CELL_USER = c('#27ae60')
ROWCOL_BG = c('#d8e6ee')
BLOCK_BG = c('#c8dce8')
SELECT_BG = c('#f5e6a8')
DARK = c('#1a252f')


class SudokuBoard(GridLayout):
    """Игровое поле 9x9"""
    def __init__(self, game, **kwargs):
        super().__init__(**kwargs)
        self.game = game
        self.cols = 9
        self.rows = 9
        self.spacing = 0
        self.padding = 0
        self.cells = {}
        self._build()

    def _build(self):
        for r in range(9):
            for col in range(9):
                # Границы блоков 3x3
                border = [1, 1, 1, 1]
                if r % 3 == 0 and r != 0:
                    border[1] = 3
                if col % 3 == 0 and col != 0:
                    border[0] = 3
                btn = Button(
                    text='',
                    background_normal='',
                    background_color=CELL_BG,
                    color=c('#2c3e50'),
                    font_size='20sp',
                    bold=True,
                )
                btn.border = border
                btn.bind(on_release=lambda inst, rr=r, cc=col: self.game.select_cell(rr, cc))
                self.add_widget(btn)
                self.cells[(r, col)] = btn

    def refresh(self):
        """Обновить все клетки по данным игры"""
        for r in range(9):
            for col in range(9):
                btn = self.cells[(r, col)]
                val = self.game.board[r][col]
                if val != 0:
                    btn.text = str(val)
                    if self.game.initial_board[r][col] != 0:
                        btn.color = CELL_FIXED
                    else:
                        btn.color = CELL_USER
                else:
                    btn.text = ''
                btn.background_color = CELL_BG

    def highlight(self, row, col):
        """Подсветка строки/столбца/блока"""
        # Сброс
        for r in range(9):
            for cc in range(9):
                self.cells[(r, cc)].background_color = CELL_BG

        # Строка
        for cc in range(9):
            self.cells[(row, cc)].background_color = ROWCOL_BG
        # Столбец
        for r in range(9):
            self.cells[(r, col)].background_color = ROWCOL_BG
        # Блок
        br, bc = (row // 3) * 3, (col // 3) * 3
        for r in range(br, br + 3):
            for cc in range(bc, bc + 3):
                self.cells[(r, cc)].background_color = BLOCK_BG
        # Выбранная
        self.cells[(row, col)].background_color = SELECT_BG


class MenuScreen(Screen):
    def __init__(self, game, **kwargs):
        super().__init__(**kwargs)
        self.game = game
        self._build()

    def _build(self):
        layout = BoxLayout(orientation='vertical', padding=20, spacing=10)
        layout.add_widget(Label(text='СУДОКУ', font_size='42sp', bold=True,
                                color=ACCENT, size_hint_y=0.15))
        # Инфо по уровням
        info = BoxLayout(orientation='vertical', size_hint_y=0.25, spacing=2)
        for lvl in LEVELS:
            row = BoxLayout(size_hint_y=None, height=30)
            row.add_widget(Label(text=f'{lvl}:', bold=True, color=c('#ecf0f1'), size_hint_x=0.5))
            row.add_widget(Label(text=f'💡 {self.game.hints[lvl]}', color=CYAN, size_hint_x=0.25))
            row.add_widget(Label(text=f'🪙 {self.game.coins[lvl]}', color=ACCENT, size_hint_x=0.25))
            info.add_widget(row)
        layout.add_widget(info)

        # Кнопки
        for text, action in [
            ("НОВАЯ ИГРА", self.game.new_game_start),
            ("ПРОДОЛЖИТЬ" if self.game.has_save() else None, self.game.resume_game),
            ("УДАЛИТЬ СОХРАНЕНИЕ" if self.game.has_save() else None, self.game.delete_save_confirm),
            ("СЛОЖНОСТЬ", self.game.open_difficulty),
            ("🛒 МАГАЗИН", self.game.open_shop),
            ("СТАТИСТИКА", self.game.open_stats),
            ("ПРАВИЛА", self.game.open_rules),
        ]:
            if text:
                btn = Button(text=text, font_size='18sp', background_color=PANEL,
                             background_normal='', size_hint_y=None, height=55)
                btn.bind(on_release=lambda inst, a=action: a())
                layout.add_widget(btn)

        self.add_widget(layout)


class GameScreen(Screen):
    def __init__(self, game, **kwargs):
        super().__init__(**kwargs)
        self.game = game
        self._build()

    def _build(self):
        root = BoxLayout(orientation='vertical', padding=5, spacing=5)

        # Верхняя панель: время, ошибки, уровень, подсказки, монеты
        top = BoxLayout(size_hint_y=0.08, spacing=2)
        self.time_label = Label(text='00:00', font_size='14sp', color=CYAN)
        self.mistake_label = Label(text='0/3', font_size='14sp', color=RED)
        self.level_label = Label(text=self.game.current_level, font_size='14sp', color=ACCENT)
        self.hint_label = Label(text=f'💡 {self.game.hints[self.game.current_level]}',
                                font_size='14sp', color=CYAN)
        self.coin_label = Label(text=f'🪙 {self.game.coins[self.game.current_level]}',
                                font_size='14sp', color=ACCENT)
        for lbl in (self.time_label, self.mistake_label, self.level_label,
                    self.hint_label, self.coin_label):
            top.add_widget(lbl)
        root.add_widget(top)

        # Поле
        self.board = SudokuBoard(self.game, size_hint_y=0.55)
        root.add_widget(self.board)

        # Цифры 1-9
        nums = BoxLayout(size_hint_y=0.1, spacing=2)
        for i in range(1, 10):
            btn = Button(text=str(i), font_size='20sp', bold=True,
                         background_color=PANEL, background_normal='', color=ACCENT)
            btn.bind(on_release=lambda inst, n=i: self.game.place_number(n))
            nums.add_widget(btn)
        root.add_widget(nums)

        # Кнопки действий
        actions = BoxLayout(size_hint_y=0.1, spacing=5)
        for txt, col, act in [
            ("💡", c('#f39c12'), self.game.use_hint),
            ("🤖", c('#e67e22'), self.game.use_auto),
            ("🗑", c('#e74c3c'), self.game.clear_cell),
            ("МЕНЮ", c('#c0392b'), self.game.back_to_menu),
        ]:
            btn = Button(text=txt, font_size='16sp', bold=True,
                         background_color=col, background_normal='')
            btn.bind(on_release=lambda inst, a=act: a())
            actions.add_widget(btn)
        root.add_widget(actions)

        self.add_widget(root)


class SudokuApp(App):
    def build(self):
        self.title = "Судоку"
        self.board_widget = None
        self.game_screen = None
        self.board = [[0] * 9 for _ in range(9)]
        self.solution = [[0] * 9 for _ in range(9)]
        self.initial_board = [[0] * 9 for _ in range(9)]
        self.selected_row = None
        self.selected_col = None
        self.mistakes = 0
        self.current_level = "Легкий"
        self.start_time = None
        self.timer_running = False
        self.elapsed_seconds = 0

        self.hints = {lvl: START_HINTS for lvl in LEVELS}
        self.coins = {lvl: START_COINS for lvl in LEVELS}

        self.stats = self.load_stats()
        self.load_wallet()

        self.sm = ScreenManager()
        self.menu_screen = MenuScreen(game=self, name='menu')
        self.sm.add_widget(self.menu_screen)
        self.sm.current = 'menu'
        return self.sm

    # --- Сохранения и статистика ---
    def load_stats(self):
        default = {
            "wins": 0, "losses": 0,
            "best_times": {lvl: None for lvl in LEVELS},
            "hints": {lvl: START_HINTS for lvl in LEVELS},
            "coins": {lvl: START_COINS for lvl in LEVELS},
        }
        if os.path.exists(STATS_FILE):
            try:
                with open(STATS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for k, v in data.items():
                        if k in ("best_times", "hints", "coins"):
                            default[k].update(v)
                        else:
                            default[k] = v
                    return default
            except Exception:
                return default
        return default

    def save_stats(self):
        try:
            with open(STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("Ошибка сохранения статистики:", e)

    def load_wallet(self):
        for lvl in LEVELS:
            self.hints[lvl] = self.stats["hints"].get(lvl, START_HINTS)
            self.coins[lvl] = self.stats["coins"].get(lvl, START_COINS)

    def save_wallet(self):
        self.stats["hints"] = dict(self.hints)
        self.stats["coins"] = dict(self.coins)
        self.save_stats()

    def has_save(self):
        return os.path.exists(SAVE_FILE)

    def save_game(self):
        if self.start_time and self.timer_running:
            elapsed = self.elapsed_seconds + int(time.time() - self.start_time)
        else:
            elapsed = self.elapsed_seconds
        data = {
            "board": self.board, "solution": self.solution,
            "initial_board": self.initial_board, "mistakes": self.mistakes,
            "current_level": self.current_level, "elapsed_seconds": elapsed,
        }
        try:
            with open(SAVE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print("Ошибка сохранения:", e)

    def delete_save_confirm(self):
        self.confirm('Удаление', 'Точно удалить сохранение?', self._do_delete)

    def _do_delete(self):
        if os.path.exists(SAVE_FILE):
            os.remove(SAVE_FILE)
        self.refresh_menu()

    def resume_game(self):
        if not self.has_save():
            self.info('Сохранение', 'Сохранённой игры нет.')
            return
        try:
            with open(SAVE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            self.info('Ошибка', f'Не удалось загрузить сохранение:\n{e}')
            return
        self.board = data["board"]
        self.solution = data["solution"]
        self.initial_board = data["initial_board"]
        self.mistakes = data["mistakes"]
        self.current_level = data["current_level"]
        self.elapsed_seconds = data.get("elapsed_seconds", 0)
        self.open_game(from_save=True)

    # --- Меню / навигация ---
    def refresh_menu(self):
        self.sm.clear_widgets()
        self.menu_screen = MenuScreen(game=self, name='menu')
        self.sm.add_widget(self.menu_screen)
        self.sm.current = 'menu'

    def new_game_start(self):
        self.mistakes = 0
        self.elapsed_seconds = 0
        self.selected_row = None
        self.selected_col = None
        self.start_time = None
        self.timer_running = False
        self.generate_board()
        self.open_game(from_save=False)

    def open_game(self, from_save=False):
        self.sm.clear_widgets()
        self.game_screen = GameScreen(game=self, name='game')
        self.sm.add_widget(self.game_screen)
        self.sm.current = 'game'
        self.board_widget = self.game_screen.board
        self.board_widget.refresh()
        if from_save:
            self.restore_timer()
        else:
            self.start_timer()
            self.save_game()

    def back_to_menu(self):
        self.save_game()
        self.stop_timer()
        self.refresh_menu()

    def open_difficulty(self):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        for name in LEVELS:
            btn = Button(text=f"{name}   💡{self.hints[name]}  🪙{self.coins[name]}",
                         size_hint_y=None, height=50, background_color=PANEL,
                         background_normal='')
            btn.bind(on_release=lambda inst, n=name: self._set_level(n, popup))
            content.add_widget(btn)
        popup = Popup(title='Выбери уровень', content=content, size_hint=(0.9, 0.7))
        popup.open()

    def _set_level(self, level, popup):
        self.current_level = level
        popup.dismiss()
        self.refresh_menu()

    # --- Магазин ---
    def open_shop(self):
        content = BoxLayout(orientation='vertical', padding=10, spacing=5)
        scroll = ScrollView()
        inner = BoxLayout(orientation='vertical', size_hint_y=None, spacing=5)
        inner.bind(minimum_height=inner.setter('height'))

        for lvl in LEVELS:
            block = BoxLayout(orientation='vertical', size_hint_y=None, height=110, spacing=3)
            header = BoxLayout(size_hint_y=None, height=30)
            header.add_widget(Label(text=lvl, bold=True, color=CYAN, size_hint_x=0.4))
            header.add_widget(Label(text=f'💡{self.hints[lvl]} 🪙{self.coins[lvl]}',
                                    color=ACCENT, size_hint_x=0.6))
            block.add_widget(header)
            btns = BoxLayout(size_hint_y=None, height=50, spacing=5)
            b1 = Button(text=f'+1 ({PRICE_1}🪙)', background_color=GREEN, background_normal='')
            b1.bind(on_release=lambda inst, l=lvl: self.buy_hint(l, 1, shop_popup))
            b2 = Button(text=f'+3 ({PRICE_3}🪙)', background_color=c('#16a085'), background_normal='')
            b2.bind(on_release=lambda inst, l=lvl: self.buy_hint(l, 3, shop_popup))
            btns.add_widget(b1); btns.add_widget(b2)
            block.add_widget(btns)
            inner.add_widget(block)

        scroll.add_widget(inner)
        content.add_widget(scroll)
        shop_popup = Popup(title='🛒 Магазин подсказок', content=content, size_hint=(0.95, 0.9))
        shop_popup.open()

    def buy_hint(self, level, amount, shop_popup):
        price = PRICE_1 if amount == 1 else PRICE_3
        if self.coins[level] < price:
            self.info('Не хватает монет',
                      f'Для «{level}» нужно {price} 🪙, а у тебя {self.coins[level]} 🪙.\n'
                      'Выигрывай игры, чтобы заработать монеты!')
            return
        self.coins[level] -= price
        self.hints[level] += amount
        self.save_wallet()
        shop_popup.dismiss()
        self.info('Покупка успешна!',
                  f'+{amount} 💡 для «{level}».\nОсталось: {self.coins[level]} 🪙')

    # --- Статистика ---
    def open_stats(self):
        content = BoxLayout(orientation='vertical', padding=10, spacing=5)
        content.add_widget(Label(text=f"🏆 Побед: {self.stats['wins']}", color=GREEN, bold=True))
        content.add_widget(Label(text=f"💀 Проигрышей: {self.stats['losses']}", color=RED, bold=True))
        content.add_widget(Label(text=f"🎮 Всего: {self.stats['wins'] + self.stats['losses']}"))
        content.add_widget(Label(text='--- ПО УРОВНЯМ ---', color=CYAN))
        for lvl in LEVELS:
            best = self.stats['best_times'].get(lvl)
            best_text = self.fmt_time(best) if best is not None else '—'
            content.add_widget(Label(text=f"{lvl}: {best_text}  💡{self.hints[lvl]}  🪙{self.coins[lvl]}"))

        btn_reset = Button(text='СБРОСИТЬ', size_hint_y=None, height=50,
                           background_color=RED, background_normal='')
        btn_reset.bind(on_release=lambda inst: self.reset_stats_confirm(popup))
        content.add_widget(btn_reset)
        popup = Popup(title='📊 Статистика', content=content, size_hint=(0.9, 0.8))
        popup.open()

    def reset_stats_confirm(self, parent_popup):
        self.confirm('Сброс', 'Сбросить статистику, монеты и подсказки?',
                     lambda: self._do_reset(parent_popup))

    def _do_reset(self, parent_popup):
        self.stats = {
            "wins": 0, "losses": 0,
            "best_times": {lvl: None for lvl in LEVELS},
            "hints": {lvl: START_HINTS for lvl in LEVELS},
            "coins": {lvl: START_COINS for lvl in LEVELS},
        }
        self.hints = {lvl: START_HINTS for lvl in LEVELS}
        self.coins = {lvl: START_COINS for lvl in LEVELS}
        self.save_stats()
        if parent_popup: parent_popup.dismiss()
        self.refresh_menu()

    # --- Правила ---
    def open_rules(self):
        text = (
            "Цель — заполнить все клетки цифрами 1-9.\n"
            "В каждой строке, столбце и блоке 3x3 цифры не повторяются.\n\n"
            "🔴 Красные — даны изначально\n"
            "🟢 Зелёные — твои\n\n"
            "💡 Подсказка — ставит верную цифру в выбранную клетку (тратит 1💡)\n"
            "🤖 Авто — ставит случайную верную цифру (тратит 1💡)\n"
            "🗑 Очистить — убирает твою цифру\n\n"
            "⚠️ 3 ошибки — проигрыш!\n\n"
            f"💡 Подсказки: у каждого уровня свой запас.\n"
            f"🪙 Монеты: победа +{REWARD_WIN}, проигрыш +{REWARD_LOSS}.\n"
            f"Магазин: {PRICE_1}🪙 за 1, {PRICE_3}🪙 за 3.\n"
        )
        content = BoxLayout(orientation='vertical', padding=10)
        scroll = ScrollView()
        lbl = Label(text=text, size_hint_y=None, halign='left', valign='top')
        lbl.bind(width=lambda inst, w: setattr(inst, 'text_size', (w, None)))
        lbl.bind(texture_size=lambda inst, ts: setattr(inst, 'height', ts[1]))
        scroll.add_widget(lbl)
        content.add_widget(scroll)
        Popup(title='📖 Правила', content=content, size_hint=(0.95, 0.85)).open()

    # --- Диалоги ---
    def info(self, title, msg):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        content.add_widget(Label(text=msg, halign='center'))
        btn = Button(text='OK', size_hint_y=None, height=50,
                     background_color=PANEL, background_normal='')
        p = Popup(title=title, content=content, size_hint=(0.85, 0.4))
        btn.bind(on_release=lambda inst: p.dismiss())
        content.add_widget(btn)
        p.open()

    def confirm(self, title, msg, on_yes):
        content = BoxLayout(orientation='vertical', padding=10, spacing=10)
        content.add_widget(Label(text=msg, halign='center'))
        btns = BoxLayout(size_hint_y=None, height=50, spacing=10)
        by = Button(text='ДА', background_color=GREEN, background_normal='')
        bn = Button(text='НЕТ', background_color=RED, background_normal='')
        btns.add_widget(by); btns.add_widget(bn)
        content.add_widget(btns)
        p = Popup(title=title, content=content, size_hint=(0.85, 0.4))
        by.bind(on_release=lambda inst: (p.dismiss(), on_yes()))
        bn.bind(on_release=lambda inst: p.dismiss())
        p.open()

    # --- Игровая логика ---
    def generate_board(self):
        empty_counts = {"Легкий": 35, "Средний": 45, "Сложный": 55, "Эксперт": 65}
        empty = empty_counts.get(self.current_level, 45)
        base = [[0] * 9 for _ in range(9)]
        for b in range(0, 9, 3):
            nums = list(range(1, 10))
            random.shuffle(nums)
            for i in range(3):
                for j in range(3):
                    base[b + i][b + j] = nums[i * 3 + j]
        self._solve(base)
        self.solution = [row[:] for row in base]
        cells = [(i, j) for i in range(9) for j in range(9)]
        random.shuffle(cells)
        for idx in range(empty):
            i, j = cells[idx]
            base[i][j] = 0
        self.board = [row[:] for row in base]
        self.initial_board = [row[:] for row in base]

    def _solve(self, board):
        for i in range(9):
            for j in range(9):
                if board[i][j] == 0:
                    for num in range(1, 10):
                        if self._is_valid(board, i, j, num):
                            board[i][j] = num
                            if self._solve(board):
                                return True
                            board[i][j] = 0
                    return False
        return True

    def _is_valid(self, board, row, col, num):
        if num in board[row]: return False
        if num in [board[i][col] for i in range(9)]: return False
        br, bc = (row // 3) * 3, (col // 3) * 3
        for i in range(br, br + 3):
            for j in range(bc, bc + 3):
                if board[i][j] == num: return False
        return True

    def select_cell(self, row, col):
        if self.initial_board[row][col] != 0:
            self.selected_row = self.selected_col = None
            self.board_widget.refresh()
            return
        self.selected_row, self.selected_col = row, col
        self.board_widget.highlight(row, col)
        # Восстанавливаем цифры после сброса фона
        self.board_widget.refresh()
        self.board_widget.highlight(row, col)

    def place_number(self, num):
        if self.selected_row is None:
            self.info('Внимание', 'Сначала выбери клетку!')
            return
        r, col = self.selected_row, self.selected_col
        if self.initial_board[r][col] != 0:
            self.info('Ошибка', 'Эту клетку нельзя менять!')
            return
        if not self.timer_running:
            self.start_timer()
        if num != self.solution[r][col]:
            self.mistakes += 1
            self.game_screen.mistake_label.text = f'{self.mistakes}/3'
            self.board[r][col] = num
            self.board_widget.refresh()
            self.board_widget.cells[(r, col)].background_color = RED
            if self.mistakes >= 3:
                self.register_loss()
                if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
                self.stop_timer()
                self.show_loss()
            else:
                self.save_game()
            return
        self.board[r][col] = num
        self.board_widget.refresh()
        self.select_cell(r, col)
        self.save_game()
        if self.check_win():
            self.stop_timer()
            total = self.elapsed_seconds
            self.register_win(total)
            if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
            self.show_win(total)

    def clear_cell(self):
        if self.selected_row is None: return
        r, col = self.selected_row, self.selected_col
        if self.initial_board[r][col] != 0:
            self.info('Ошибка', 'Нельзя очистить изначальную клетку!')
            return
        if self.board[r][col] != 0:
            self.board[r][col] = 0
            self.board_widget.refresh()
            self.select_cell(r, col)
            self.save_game()

    def use_hint(self):
        if self.selected_row is None:
            self.info('Подсказка', 'Сначала выбери клетку!')
            return
        r, col = self.selected_row, self.selected_col
        if self.initial_board[r][col] != 0:
            self.info('Подсказка', 'Эта клетка изначальная!')
            return
        if self.board[r][col] != 0:
            self.info('Подсказка', 'Клетка уже заполнена!')
            return
        if self.hints[self.current_level] <= 0:
            self.info('Нет подсказок',
                      f'Закончились подсказки для «{self.current_level}».\nКупи в магазине!')
            return
        correct = self.solution[r][col]
        def do():
            self.hints[self.current_level] -= 1
            self.save_wallet()
            self.board[r][col] = correct
            self.board_widget.refresh()
            self.select_cell(r, col)
            self.update_top_labels()
            self.save_game()
            if self.check_win():
                self.stop_timer()
                total = self.elapsed_seconds
                self.register_win(total)
                if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
                self.show_win(total)
        self.confirm('Подсказка',
                     f'В клетку поставить {correct}?\nПотратится 1 💡 подсказка.',
                     do)

    def use_auto(self):
        empty = [(i, j) for i in range(9) for j in range(9)
                 if self.board[i][j] == 0 and self.initial_board[i][j] == 0]
        if not empty:
            self.info('АВТО', 'Нет пустых клеток!')
            return
        if self.hints[self.current_level] <= 0:
            self.info('Нет подсказок',
                      f'Закончились подсказки для «{self.current_level}».\nКупи в магазине!')
            return
        r, col = random.choice(empty)
        correct = self.solution[r][col]
        self.hints[self.current_level] -= 1
        self.save_wallet()
        self.board[r][col] = correct
        self.selected_row, self.selected_col = r, col
        self.board_widget.refresh()
        self.select_cell(r, col)
        self.update_top_labels()
        self.save_game()
        if self.check_win():
            self.stop_timer()
            total = self.elapsed_seconds
            self.register_win(total)
            if os.path.exists(SAVE_FILE): os.remove(SAVE_FILE)
            self.show_win(total)

    def update_top_labels(self):
        if self.game_screen:
            self.game_screen.hint_label.text = f'💡 {self.hints[self.current_level]}'
            self.game_screen.coin_label.text = f'🪙 {self.coins[self.current_level]}'

    def check_win(self):
        for i in range(9):
            for j in range(9):
                if self.board[i][j] != self.solution[i][j]:
                    return False
        return True

    def register_win(self, seconds):
        self.stats["wins"] += 1
        lvl = self.current_level
        best = self.stats["best_times"].get(lvl)
        if best is None or seconds < best:
            self.stats["best_times"][lvl] = seconds
        self.coins[lvl] += REWARD_WIN
        self.save_wallet()

    def register_loss(self):
        self.stats["losses"] += 1
        lvl = self.current_level
        self.coins[lvl] += REWARD_LOSS
        self.save_wallet()

    def show_win(self, seconds):
        best = self.stats["best_times"].get(self.current_level)
        record = best is not None and best == seconds
        msg = (f'Время: {self.fmt_time(seconds)}\n'
               f'🪙 +{REWARD_WIN} монет\n')
        if record:
            msg += '⭐ НОВЫЙ РЕКОРД! ⭐\n'
        self.confirm('🏆 Победа!', msg, self.new_game_start)

    def show_loss(self):
        self.confirm('💀 Игра окончена',
                     f'3 ошибки!\n🪙 +{REWARD_LOSS} монет',
                     self.new_game_start)

    # --- Таймер ---
    def start_timer(self):
        self.start_time = time.time()
        self.timer_running = True
        self._tick_timer()

    def _tick_timer(self):
        if self.timer_running and self.game_screen:
            total = self.elapsed_seconds + int(time.time() - self.start_time)
            self.game_screen.time_label.text = self.fmt_time(total)
            Clock.schedule_once(lambda dt: self._tick_timer(), 1)

    def stop_timer(self):
        if self.start_time and self.timer_running:
            self.elapsed_seconds += int(time.time() - self.start_time)
            self.start_time = None
        self.timer_running = False

    def restore_timer(self):
        if self.game_screen:
            self.game_screen.time_label.text = self.fmt_time(self.elapsed_seconds)
        self.start_timer()

    def fmt_time(self, seconds):
        return f"{seconds // 60:02d}:{seconds % 60:02d}"


if __name__ == '__main__':
    SudokuApp().run()