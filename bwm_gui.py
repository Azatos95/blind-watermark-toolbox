# -*- coding: utf-8 -*-
"""
盲水印工具箱 v0.3 —— blind_watermark 的独立 exe 图形界面

算法核心来自 guofei9987 的开源项目 blind_watermark (MIT License):
  https://github.com/guofei9987/blind_watermark
  原作者: 郭飞 (guofei9987@foxmail.com), Copyright (c) 2019 郭飞
本 GUI / 打包工程为二次开发, 同样以 MIT 协议开源, 详见 LICENSE。

v0.3 变更:
- 历史密码记忆: 记录用过的密码组合, 提取时自动填入(可用 ▾ 切换历史)
- 深色界面: 主背景 #121416 / 面板 #1A1D20 / 细框线 #303438 / 强调色 #D6B046
- 顶部警戒线式状态装饰栏: 运行正常灰绿 #7E9B84, 出错变红 #C0453F
- 字体使用思源黑体(Noto Sans SC) Bold / Medium, 全部控件直角
"""
import json
import os
import queue
import subprocess
import sys
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import blind_watermark
try:
    blind_watermark.bw_notes.close()
except Exception:
    pass

from blind_watermark import WaterMark

from bwm_theme import History, appdata_dir, detected_fonts

APP_NAME = '盲水印工具箱'
APP_VER = '0.3'
BWM_VER = getattr(blind_watermark, '__version__', '?')

# ---------------- 配色(深色 · 直角 · 低饱和) ----------------
BG = '#121416'          # 主背景
PANEL = '#1A1D20'       # 卡片 / 内嵌面板
PANEL_HI = '#20242A'    # 面板上的输入类控件
LINE = '#303438'        # 细框线 / 分割线
LINE_SOFT = '#24282B'   # 卡片内部弱分割
ACCENT = '#D6B046'      # 强调色
ACCENT_DK = '#B8952F'
ACCENT_SOFT = '#2A2517'  # 强调色淡背景
FG = '#E6E8EA'
FG_DIM = '#9AA0A6'
FG_MUTE = '#6B7076'
OK_GREEN = '#7E9B84'    # 运行正常的灰绿
ERR_RED = '#C0453F'     # 出错的红
DISABLED_BG = '#202327'
DISABLED_FG = '#5A5F65'

PIC_TYPES = [('图片文件', '*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp'), ('所有文件', '*.*')]
LOSS_LESS = ('.png', '.bmp', '.tif', '.tiff')


# ---------------- Unicode 路径补丁 ----------------
def imread_unicode(filename=None, flags=1, path=None, **kw):
    import cv2
    import numpy as np
    p = filename if filename is not None else path
    if p is None:
        return None
    try:
        data = np.fromfile(p, dtype=np.uint8)
    except OSError:
        return None
    if data.size == 0:
        return None
    return cv2.imdecode(data, flags)


def imwrite_unicode(filename=None, img=None, params=None, path=None, **kw):
    import cv2
    p = filename if filename is not None else path
    if p is None or img is None:
        return False
    ext = os.path.splitext(p)[1] or '.png'
    ok, buf = cv2.imencode(ext, img, params) if params else cv2.imencode(ext, img)
    if not ok:
        return False
    try:
        os.makedirs(os.path.dirname(os.path.abspath(p)), exist_ok=True)
        buf.tofile(p)
        return True
    except OSError:
        return False


def patch_cv2_unicode():
    import cv2
    cv2.imread = imread_unicode
    cv2.imwrite = imwrite_unicode


patch_cv2_unicode()


# ---------------- 拖拽支持 ----------------
def load_dnd():
    try:
        import tkinterdnd2
        return tkinterdnd2.TkinterDnD.Tk, tkinterdnd2.DND_FILES, True
    except Exception:
        return tk.Tk, None, False


DND_TK, DND_FILES, DND_OK = load_dnd()


def parse_drop(raw):
    """解析拖拽返回的文件列表(兼容 {含空格路径} 与 Tcl 列表)"""
    out = []
    if raw.startswith('{'):
        depth, cur = 0, ''
        for ch in raw:
            if ch == '{':
                depth += 1
                if depth == 1:
                    cur = ''
                    continue
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    out.append(cur)
                    continue
            if depth >= 1:
                cur += ch
        return out
    return [p for p in raw.split() if p]


# ---------------- 路径工具 ----------------
def get_desktop():
    for cand in (os.path.join(os.path.expanduser('~'), 'Desktop'),
                 os.path.join(os.path.expanduser('~'), '桌面')):
        if os.path.isdir(cand):
            return cand
    return os.path.expanduser('~')


OUT_DIR = os.path.join(get_desktop(), '盲水印输出')


def _writable(d):
    """真正试写一次, 判断目录可写(有些机器桌面是只读的/被安全软件锁的)"""
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, '.bwm_write_test')
        with open(probe, 'w'):
            pass
        os.remove(probe)
        return True
    except OSError:
        return False


def pick_out_dir():
    """选一个真正可写的默认输出目录, 逐个回退, 保证一定能存下结果"""
    for cand in (os.path.join(get_desktop(), '盲水印输出'),
                 os.path.join(os.path.expanduser('~'), 'Documents', '盲水印输出'),
                 os.path.join(os.path.expanduser('~'), '盲水印输出'),
                 os.path.join(appdata_dir(), '盲水印输出')):
        if _writable(cand):
            return cand
    return os.getcwd()


def ensure_outdir():
    global OUT_DIR
    if not _writable(OUT_DIR):
        OUT_DIR = pick_out_dir()
    return OUT_DIR


def default_out(src, suffix, force_lossless=True):
    """由源文件推导输出路径, 统一放到默认输出目录"""
    ensure_outdir()
    if src:
        stem = os.path.splitext(os.path.basename(src))[0] or '结果'
    else:
        stem = '结果'
    ext = os.path.splitext(src)[1].lower() if src else '.png'
    if force_lossless and ext not in LOSS_LESS:
        ext = '.png'
    if not ext:
        ext = '.png'
    return os.path.join(OUT_DIR, '%s%s%s' % (stem, suffix, ext))


def sidecar_path(img_path):
    return os.path.splitext(img_path)[0] + '.bwm.json'


def write_sidecar(img_path, payload):
    try:
        d = os.path.dirname(os.path.abspath(img_path))
        if d:
            os.makedirs(d, exist_ok=True)
        with open(sidecar_path(img_path), 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def read_sidecar(img_path):
    p = sidecar_path(img_path)
    if not os.path.isfile(p):
        return None
    try:
        # utf-8-sig: 兼容带 BOM 的 json(手工编辑/第三方工具写入时会带)
        with open(p, encoding='utf-8-sig') as f:
            return json.load(f)
    except Exception:
        return None


def open_folder(path):
    """打开文件夹/定位文件。会被后台线程调用, 必须永不阻塞、永不抛异常。"""
    if not path:
        return False
    path = os.path.abspath(path)
    target = path if os.path.isdir(path) else os.path.dirname(path)
    if not os.path.isdir(target):
        return False
    try:
        if os.path.isfile(path):
            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)], close_fds=True)
        else:
            subprocess.Popen(['explorer', os.path.normpath(target)], close_fds=True)
        return True
    except Exception:
        pass

    def _sf(p):
        try:
            os.startfile(p)
        except Exception:
            pass

    th = threading.Thread(target=_sf, args=(target,), daemon=True)
    th.start()
    th.join(2.0)
    return True


HISTORY = History()


# ---------------- 直角 UI 组件 ----------------
class Panel(tk.Frame):
    """细框线直角面板(卡片)。外层画 1px 框线, 内层为面板底色。"""

    def __init__(self, master, title=None, pad=14, **kw):
        super().__init__(master, bg=LINE, bd=0, highlightthickness=0, **kw)
        self.inner = tk.Frame(self, bg=PANEL, bd=0, highlightthickness=0)
        self.inner.pack(fill='both', expand=True, padx=1, pady=1)
        self.inner.columnconfigure(0, weight=1)
        self._row = 0
        if title:
            tk.Label(self.inner, text=title, bg=PANEL, fg=FG_DIM,
                     font=(FONT_MED, 10), anchor='w').grid(
                row=self._row, column=0, sticky='w', padx=pad, pady=(pad - 4, 2))
            self._row += 1
            tk.Frame(self.inner, bg=LINE_SOFT, height=1).grid(
                row=self._row, column=0, sticky='ew', padx=pad, pady=(0, 8))
            self._row += 1


class DropZone(tk.Frame):
    """直角可拖入区域, 显示当前文件"""

    def __init__(self, master, text='把图片拖到这里, 或点击选择', on_pick=None, height=96):
        super().__init__(master, bg=PANEL_HI, bd=0, highlightthickness=1,
                         highlightbackground=LINE, highlightcolor=LINE, cursor='hand2')
        self.on_pick = on_pick
        self._default = text
        self.columnconfigure(0, weight=1)
        self.configure(height=height)
        self.grid_propagate(False)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self.hint = tk.Label(self, text=text, bg=PANEL_HI, fg=ACCENT,
                             font=(FONT_MED, 10))
        self.hint.grid(row=1, column=0)
        self.file_lbl = tk.Label(self, text='尚未选择文件', bg=PANEL_HI, fg=FG_MUTE,
                                 font=(FONT_REG, 9), wraplength=520, justify='center')
        self.file_lbl.grid(row=2, column=0, sticky='n', pady=(2, 0))
        for w in (self, self.hint, self.file_lbl):
            w.bind('<Button-1>', self._pick)

    def _pick(self, _e=None):
        if self.on_pick:
            self.on_pick()

    def set_file(self, path):
        if path:
            self.configure(highlightbackground=OK_GREEN, highlightcolor=OK_GREEN)
            self.hint.configure(text='✓ ' + os.path.basename(path), fg=FG)
            self.file_lbl.configure(text='点击或拖入可更换', fg=FG_MUTE)
        else:
            self.configure(highlightbackground=LINE, highlightcolor=LINE)
            self.hint.configure(text=self._default, fg=ACCENT)
            self.file_lbl.configure(text='尚未选择文件', fg=FG_MUTE)


def label(parent, text, bg=PANEL, fg=FG_DIM, font=None, **kw):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=font or (FONT_REG, 9),
                    anchor='w', **kw)


def entry(parent, var, width=None, bg=PANEL_HI):
    e = tk.Entry(parent, textvariable=var, bg=bg, fg=FG, insertbackground=ACCENT,
                 disabledbackground=DISABLED_BG, disabledforeground=DISABLED_FG,
                 relief='flat', bd=0, highlightthickness=1,
                 highlightbackground=LINE, highlightcolor=ACCENT,
                 font=(FONT_REG, 10), width=width or 14)
    return e


def _pwd_menu_button(parent, on_pick, tip='历史'):
    """▾ 历史密码按钮"""
    b = tk.Menubutton(parent, text='▾', bg=PANEL_HI, fg=FG_DIM, activebackground=ACCENT_SOFT,
                      activeforeground=ACCENT, relief='flat', bd=0, highlightthickness=1,
                      highlightbackground=LINE, font=(FONT_MED, 10), width=2, cursor='hand2')
    m = tk.Menu(b, tearoff=0, bg=PANEL, fg=FG, activebackground=ACCENT_SOFT,
                activeforeground=ACCENT, bd=1, relief='flat',
                font=(FONT_REG, 9), activeborderwidth=0)
    b.configure(menu=m)
    b._menu = m
    b._fill = lambda items, empty='(暂无历史)': _fill_menu(m, items, empty, on_pick)
    return b


def _fill_menu(menu, items, empty, on_pick):
    menu.delete(0, 'end')
    if not items:
        menu.add_command(label=empty, state='disabled')
        return
    for it in items:
        menu.add_command(label=it, command=lambda v=it: on_pick(v))


class PwdRow:
    """密码行: 标签 + 输入框 + 历史下拉(或搜索按钮)"""

    def __init__(self, parent, row, text, var, pad=14, hint=None, on_history=None):
        self.var = var
        label(parent, text, fg=FG_DIM).grid(row=row, column=0, sticky='w',
                                            padx=(pad, 6), pady=5)
        box = tk.Frame(parent, bg=PANEL)
        box.grid(row=row, column=1, columnspan=2, sticky='w', padx=0, pady=5)
        self.entry = entry(box, var, width=14)
        self.entry.pack(side='left')
        if on_history:
            self.mb = _pwd_menu_button(box, on_history)
            self.mb.pack(side='left', padx=(4, 0))
            self.refresh_history = self.mb._fill
        if hint:
            label(box, hint, fg=FG_MUTE, font=(FONT_REG, 8)).pack(side='left', padx=(8, 0))


class PathRow:
    """路径行: 标签 + 只读感输入框 + 浏览/打开"""

    def __init__(self, parent, row, text, var, on_browse, on_open=None, pad=14):
        label(parent, text, fg=FG_DIM).grid(row=row, column=0, sticky='w',
                                            padx=(pad, 6), pady=5)
        self.entry = entry(parent, var, width=40)
        self.entry.grid(row=row, column=1, sticky='ew', padx=(0, 6), pady=5)
        parent.columnconfigure(1, weight=1)
        box = tk.Frame(parent, bg=PANEL)
        box.grid(row=row, column=2, sticky='e', padx=(0, pad))
        btn(box, '浏览', on_browse, kind='ghost').pack(side='left')
        if on_open:
            btn(box, '打开', on_open, kind='ghost').pack(side='left', padx=(6, 0))


def btn(parent, text, command, kind='ghost', width=None):
    """直角按钮: primary=强调色实底, ghost=细框线描边, danger=红描边"""
    if kind == 'primary':
        b = tk.Button(parent, text=text, command=command, bg=ACCENT, fg='#141414',
                      activebackground=ACCENT_DK, activeforeground='#141414',
                      disabledforeground='#6a6250', relief='flat', bd=0,
                      highlightthickness=0, font=(FONT_BOLD, 10), cursor='hand2',
                      padx=20, pady=8)
        if width:
            b.configure(width=width)
        return b
    b = tk.Button(parent, text=text, command=command, bg=PANEL, fg=FG_DIM,
                  activebackground=ACCENT_SOFT, activeforeground=ACCENT,
                  disabledforeground=DISABLED_FG, relief='flat', bd=0,
                  highlightthickness=1, highlightbackground=LINE, highlightcolor=ACCENT,
                  font=(FONT_REG, 9), cursor='hand2', padx=12, pady=6)
    if width:
        b.configure(width=width)
    return b


class Toggle(tk.Button):
    """直角切换按钮(替代深色下发暗的单选圆圈), 选中用强调色描边+文字"""

    def __init__(self, master, text, command=None, **kw):
        super().__init__(master, text=text, command=self._click, bg=PANEL, fg=FG_DIM,
                         activebackground=ACCENT_SOFT, activeforeground=ACCENT,
                         relief='flat', bd=0, highlightthickness=1,
                         highlightbackground=LINE, highlightcolor=ACCENT,
                         font=(FONT_MED, 9), cursor='hand2', padx=14, pady=6, **kw)
        self._cmd = command
        self._on = False

    def _click(self):
        if self._cmd:
            self._cmd()
        return 'break'

    def set_on(self, on):
        self._on = bool(on)
        if self._on:
            self.configure(bg=ACCENT_SOFT, fg=ACCENT, highlightbackground=ACCENT)
        else:
            self.configure(bg=PANEL, fg=FG_DIM, highlightbackground=LINE)


# 字体族(在 App 初始化时按本机可用情况填充)
FONT_BOLD = 'TkDefaultFont'
FONT_MED = 'TkDefaultFont'
FONT_REG = 'TkDefaultFont'
FONT_MONO = 'Consolas'


# ---------------- 主窗口 ----------------
class App(DND_TK):
    def __init__(self):
        super().__init__()
        global FONT_BOLD, FONT_MED, FONT_REG, FONT_MONO
        self._init_fonts()
        FONT_BOLD = self.F['bold']
        FONT_MED = self.F['medium']
        FONT_REG = self.F['regular']
        FONT_MONO = self.F['mono']

        self.title('%s v%s' % (APP_NAME, APP_VER))
        self.configure(bg=BG)
        self.minsize(760, 620)
        self._center(940, 760)

        self._setup_style()
        self.logq = queue.Queue()
        self.doneq = queue.Queue()
        self.busy = False
        self.drop_targets = []
        self.active_drop = None
        self._last_dir = get_desktop()
        self._stripe_phase = 0

        self._build_stripe()
        self._build_header()
        self._build_tabs()
        self._build_statusbar()
        self._build_log()
        self._setup_dnd()

        self._drain_job = None
        self.after(120, self._drain_log)
        self.log('就绪 · blind_watermark %s · Python %s' %
                 (BWM_VER, sys.version.split()[0]))
        self.log('字体: %s / %s' % (self.F['bold'], self.F['medium']))
        self.log('配置与历史密码: %s' % appdata_dir())
        self.log('输出目录: %s' % ensure_outdir())
        if not DND_OK:
            self.log('提示: 未装 tkinterdnd2, 拖拽不可用, 请点「浏览」选择图片。')
        last = HISTORY.last_pair()
        if last:
            self.log('已记住上次的密码: A=%s B=%s (提取时会自动填入)' % (last[0], last[1]))
        self.set_state('ok')

    # ---- 字体 ----
    def _init_fonts(self):
        self.F = detected_fonts(self)
        import tkinter.font as tkfont
        try:
            for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont'):
                tkfont.nametofont(name).configure(family=self.F['regular'], size=9)
        except Exception:
            pass

    def f(self, weight='regular', size=9):
        fam = self.F.get(weight, self.F['regular'])
        return (fam, size, 'bold') if weight == 'bold' and 'Bold' not in fam else (fam, size)

    # ---- 窗口 ----
    def _center(self, w, h):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        self.geometry('%dx%d+%d+%d' % (w, h, x, y))

    # ---- 警戒线装饰(顶部斜纹) ----
    def _build_stripe(self):
        self.stripe = tk.Canvas(self, height=4, bg=BG, highlightthickness=0, bd=0)
        self.stripe.pack(fill='x', side='top')
        self.stripe.bind('<Configure>', lambda e: self._draw_stripe())
        # 警戒线下方再压一条强调色细线, 强化"状态条"的装饰感
        self.stripe_rule = tk.Frame(self, bg=ACCENT, height=1)
        self.stripe_rule.pack(fill='x', side='top')

    def _draw_stripe(self):
        c = self.stripe
        c.delete('all')
        w, h = c.winfo_width(), 4
        if w < 4:
            w = self.winfo_width() or 800
        color = self._state_color or OK_GREEN
        step = 8
        for x in range(-h, w + step, step):
            c.create_line(x, h, x + h, 0, fill=color, width=2)

    def set_state(self, state):
        """state: ok(灰绿) / err(红) / busy(强调)"""
        if state == 'err':
            self._state_color = ERR_RED
            self._state_text = '异常'
        elif state == 'busy':
            self._state_color = ACCENT
            self._state_text = '处理中'
        else:
            self._state_color = OK_GREEN
            self._state_text = '正常'
        self._draw_stripe()
        if hasattr(self, 'state_lbl'):
            col = {'ok': OK_GREEN, 'err': ERR_RED, 'busy': ACCENT}[state]
            self.state_lbl.configure(text='● ' + self._state_text, fg=col)

    _state_color = None
    _state_text = '正常'

    # ---- 样式 ----
    def _setup_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use('clam')
        except tk.TclError:
            pass
        st.configure('TFrame', background=BG)
        st.configure('TLabel', background=BG, foreground=FG)
        st.configure('TCheckbutton', background=PANEL, foreground=FG,
                     focuscolor=PANEL)
        st.map('TCheckbutton', background=[('active', PANEL)])

        # 标签页: 直角, 选中项用强调色下划线感(用背景区分)
        st.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(0, 6, 0, 0))
        st.configure('TNotebook.Tab', padding=(20, 9), borderwidth=0,
                     background=BG, foreground=FG_MUTE, font=(self.F['medium'], 10))
        st.map('TNotebook.Tab',
               background=[('selected', PANEL), ('active', PANEL_HI)],
               foreground=[('selected', ACCENT), ('active', FG)])
        st.layout('TNotebook', [('Notebook.client', {'sticky': 'nswe'})])

        # 进度条
        st.configure('Thin.Horizontal.TProgressbar', background=ACCENT,
                     troughcolor=PANEL, bordercolor=LINE, lightcolor=ACCENT,
                     darkcolor=ACCENT, borderwidth=0, thickness=3)

        # 滚动条: 极细直角(clam 默认带立体箭头, 这里去掉)
        st.layout('Vertical.TScrollbar', [
            ('Vertical.Scrollbar.trough', {'sticky': 'ns', 'children': [
                ('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'}),
            ]}),
        ])
        st.configure('Vertical.TScrollbar', background=LINE, troughcolor='#0D0F11',
                     bordercolor='#0D0F11', lightcolor=LINE, darkcolor=LINE,
                     arrowcolor=LINE, borderwidth=0, relief='flat', width=6)
        st.map('Vertical.TScrollbar', background=[('active', ACCENT)])

    # ---- 顶部 ----
    def _build_header(self):
        hd = tk.Frame(self, bg=BG)
        hd.pack(fill='x', padx=18, pady=(8, 2))
        hd.columnconfigure(1, weight=1)
        tk.Label(hd, text=APP_NAME, bg=BG, fg=FG,
                 font=(self.F['bold'], 16)).grid(row=0, column=0, sticky='w')
        tk.Label(hd, text='v%s' % APP_VER, bg=BG, fg=ACCENT,
                 font=(self.F['medium'], 10)).grid(row=0, column=1, sticky='w', padx=(8, 0))
        tk.Label(hd, text='图片里藏一段看不见的信息 · 截图 / 裁剪 / 旋转后依然能取回',
                 bg=BG, fg=FG_MUTE, font=(self.F['regular'], 9)).grid(
            row=1, column=0, columnspan=3, sticky='w', pady=(2, 0))
        self.dnd_badge = tk.Label(hd, text='拖拽已就绪' if DND_OK else '拖拽不可用',
                                  bg=BG, fg=OK_GREEN if DND_OK else ERR_RED,
                                  font=(self.F['medium'], 9))
        self.dnd_badge.grid(row=0, column=2, rowspan=2, sticky='e')
        tk.Frame(self, bg=LINE, height=1).pack(fill='x', padx=18, pady=(8, 0))

    # ---- 标签页 ----
    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True, padx=18, pady=(10, 0))
        self.tab_text = TextTab(self.nb, self)
        self.tab_img = ImageTab(self.nb, self)
        self.tab_ext = ExtractTab(self.nb, self)
        self.nb.add(self.tab_text, text='嵌入文字水印')
        self.nb.add(self.tab_img, text='嵌入图片水印')
        self.nb.add(self.tab_ext, text='提取水印')
        self.nb.bind('<<NotebookTabChanged>>', lambda e: self._sync_drop())

    # ---- 底部状态条 ----
    def _build_statusbar(self):
        tk.Frame(self, bg=LINE, height=1).pack(fill='x', padx=18, pady=(8, 0))
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill='x', padx=18, pady=(6, 2))
        self.state_lbl = tk.Label(bar, text='● 正常', bg=BG, fg=OK_GREEN,
                                  font=(self.F['medium'], 9))
        self.state_lbl.pack(side='left')
        self.status = tk.Label(bar, text='就绪', bg=BG, fg=FG_MUTE,
                               font=(self.F['regular'], 9), anchor='w')
        self.status.pack(side='left', padx=(10, 0))
        self.bar = ttk.Progressbar(bar, mode='indeterminate', length=120,
                                   style='Thin.Horizontal.TProgressbar')
        self.log_btn = btn(bar, '收起日志', self._toggle_log, kind='ghost')
        self.log_btn.pack(side='right')
        btn(bar, '打开输出目录', lambda: open_folder(ensure_outdir()),
            kind='ghost').pack(side='right', padx=(0, 6))

    def _build_log(self):
        self.logbox = tk.Frame(self, bg=BG)
        self.logbox.pack(fill='x', padx=18, pady=(4, 12))
        wrap = tk.Frame(self.logbox, bg=LINE)
        wrap.pack(fill='both', expand=True)
        inner = tk.Frame(wrap, bg='#0D0F11')
        inner.pack(fill='both', expand=True, padx=1, pady=1)
        self.log_text = tk.Text(inner, height=5, wrap='word', bg='#0D0F11', fg='#B9C0C6',
                                insertbackground=ACCENT, bd=0, relief='flat',
                                highlightthickness=0, padx=10, pady=8,
                                font=(self.F['mono'], 9), state='disabled')
        sb = ttk.Scrollbar(inner, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.log_text.tag_configure('ok', foreground=OK_GREEN)
        self.log_text.tag_configure('err', foreground=ERR_RED)
        self.log_text.tag_configure('info', foreground=ACCENT)

    def _toggle_log(self):
        if self.logbox.winfo_ismapped():
            self.logbox.pack_forget()
            self.log_btn.configure(text='展开日志')
        else:
            self.logbox.pack(fill='x', padx=18, pady=(4, 12))
            self.log_btn.configure(text='收起日志')

    # ---- 拖拽 ----
    def _setup_dnd(self):
        if not DND_OK:
            return
        try:
            self.drop_target_register(DND_FILES)
            self.drop_targets.append(self)
        except Exception:
            pass
        if hasattr(self, 'dnd_bind'):
            try:
                self.dnd_bind('<<Drop>>', self._on_drop)
            except Exception:
                pass
        self._sync_drop()

    def _sync_drop(self):
        try:
            cur = self.nb.index(self.nb.select())
        except Exception:
            cur = 0
        tab = (self.tab_text, self.tab_img, self.tab_ext)[cur]
        self.active_drop = tab.on_drop
        self._set_status('就绪 · %s' % tab.TITLE, FG_MUTE)

    def _on_drop(self, event):
        files = parse_drop(event.data)
        if not files or not self.active_drop:
            return
        self.active_drop(files[0])

    def dnd_self_check(self):
        if not DND_OK:
            return 'no-tkdnd'
        try:
            subs = self.dnd_bind('<<Drop>>') if hasattr(self, 'dnd_bind') else ''
            return 'targets=%d bind=%s' % (len(self.drop_targets), subs)
        except Exception as e:
            return 'bind-fail %s' % e

    # ---- 日志 / 状态 ----
    def log(self, msg, tag=None):
        self.logq.put((msg, tag))

    def _drain_log(self):
        try:
            while True:
                msg, tag = self.logq.get_nowait()
                self.log_text.configure(state='normal')
                self.log_text.insert('end', msg.rstrip() + '\n', tag or '')
                self.log_text.see('end')
                self.log_text.configure(state='disabled')
        except queue.Empty:
            pass
        try:
            while True:
                title, ok, msg = self.doneq.get_nowait()
                self.exit_busy(msg if (msg and len(str(msg)) < 60) else (title + '完成'), ok)
        except queue.Empty:
            pass
        try:
            self._drain_job = self.after(120, self._drain_log)
        except tk.TclError:
            self._drain_job = None      # 窗口已销毁

    def destroy(self):
        """取消挂起的定时器, 避免销毁后 Tk 继续回调报 invalid command name"""
        if getattr(self, '_drain_job', None):
            try:
                self.after_cancel(self._drain_job)
            except Exception:
                pass
            self._drain_job = None
        super().destroy()

    def _set_status(self, text, color=FG_MUTE):
        self.status.configure(text=text, fg=color)

    def enter_busy(self, text):
        self.busy = True
        self.set_state('busy')
        self._set_status(text, ACCENT)
        self.bar.pack(side='left', padx=10)
        self.bar.start(12)

    def exit_busy(self, text='就绪', ok=None):
        self.busy = False
        self.bar.stop()
        self.bar.pack_forget()
        if ok is None:
            self._set_status(text, FG_MUTE)
            self.set_state('ok')
        else:
            self._set_status(text, OK_GREEN if ok else ERR_RED)
            self.set_state('ok' if ok else 'err')

    def pick_open(self, var, save=False, defext='.png'):
        if save:
            p = filedialog.asksaveasfilename(initialdir=OUT_DIR,
                                             initialfile=os.path.basename(var.get() or ''),
                                             defaultextension=defext, filetypes=PIC_TYPES)
        else:
            p = filedialog.askopenfilename(initialdir=self._last_dir, filetypes=PIC_TYPES)
        if p:
            if not save:
                self._last_dir = os.path.dirname(p)
            var.set(p)
        return p

    def run_async(self, title, fn):
        if self.busy:
            messagebox.showinfo(APP_NAME, '正在处理, 请稍等…')
            return
        self.enter_busy(title)

        def work():
            try:
                ok, msg = fn()
            except Exception:
                ok, msg = False, '出错: %s' % traceback.format_exc().strip().splitlines()[-1]
                self.log(traceback.format_exc().strip(), 'err')
            self.doneq.put((title, bool(ok), msg))

        threading.Thread(target=work, daemon=True).start()


# ---------------- 通用标签页 ----------------
class BaseTab(tk.Frame):
    TITLE = ''

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.columnconfigure(0, weight=1)
        self._row = 0

    def on_drop(self, path):
        raise NotImplementedError

    def next_row(self):
        r = self._row
        self._row += 1
        return r


def make_panel(tab, title=None, pady=(0, 10)):
    p = Panel(tab, title=title)
    p.grid(row=tab.next_row(), column=0, sticky='ew', pady=pady)
    return p


def action_bar(tab, primary_text, primary_cmd, clear_cmd):
    bar = tk.Frame(tab, bg=BG)
    bar.grid(row=tab.next_row(), column=0, sticky='ew', pady=(2, 14))
    bar.columnconfigure(0, weight=1)
    go = btn(bar, primary_text, primary_cmd, kind='primary')
    go.grid(row=0, column=0, sticky='e')
    btn(bar, '清空', clear_cmd, kind='ghost').grid(row=0, column=1, padx=(8, 0))
    return go


# ---------------- ① 文字水印嵌入 ----------------
class TextTab(BaseTab):
    TITLE = '嵌入文字水印'

    def __init__(self, master, app):
        super().__init__(master, app)
        self.src = tk.StringVar()
        self.out = tk.StringVar()
        last = HISTORY.last_pair()
        self.pwd_img = tk.StringVar(value=last[0] if last else '123')
        self.pwd_wm = tk.StringVar(value=last[1] if last else '123')

        # 选图
        c1 = Panel(self)
        c1.grid(row=self.next_row(), column=0, sticky='ew', pady=(0, 10))
        self.drop = DropZone(c1.inner, '把【原图】拖到这里 · 或点击选择',
                             on_pick=self.pick_src)
        self.drop.grid(row=0, column=0, sticky='ew', padx=14, pady=14)
        c1.inner.columnconfigure(0, weight=1)

        # 文字 + 参数
        c2 = Panel(self, title='要藏进去的文字')
        c2.grid(row=self.next_row(), column=0, sticky='ew', pady=(0, 10))
        g = c2.inner
        g.columnconfigure(1, weight=1)
        r = c2._row
        tb = tk.Frame(g, bg=LINE)
        tb.grid(row=r, column=0, columnspan=3, sticky='ew', padx=14, pady=(0, 4))
        self.txt = tk.Text(tb, height=3, wrap='word', bg=PANEL_HI, fg=FG,
                           insertbackground=ACCENT, bd=0, relief='flat',
                           highlightthickness=1, highlightbackground=LINE,
                           highlightcolor=ACCENT, font=(app.F['regular'], 10), padx=8, pady=6)
        self.txt.pack(fill='both', expand=True, padx=1, pady=1)
        self.txt.insert('1.0', '版权所有 · 请勿外传')
        r += 1
        self.cap = label(g, '', fg=FG_MUTE, font=(app.F['regular'], 8))
        self.cap.grid(row=r, column=0, columnspan=3, sticky='w', padx=14, pady=(2, 6))
        self.txt.bind('<KeyRelease>', lambda e: self.update_cap())
        r += 1
        self.row_pi = PwdRow(g, r, '密码 A(图片)', self.pwd_img,
                             hint='嵌入与提取必须一致', on_history=lambda v: self.pwd_img.set(v))
        r += 1
        self.row_pw = PwdRow(g, r, '密码 B(水印)', self.pwd_wm,
                             hint='嵌入与提取必须一致', on_history=lambda v: self.pwd_wm.set(v))
        r += 1
        PathRow(g, r, '输出到', self.out, self.pick_out, self.open_out)
        self._refresh_hist_menus()

        self.go = action_bar(self, '开始嵌入文字水印', self.run, self.clear)
        self.update_cap()

    def _refresh_hist_menus(self):
        pairs = [p[0] for p in HISTORY.data['pairs']]
        imgs = list(dict.fromkeys(pairs or HISTORY.top_images()))
        wms = list(dict.fromkeys(pairs or HISTORY.top_wms()))
        self.row_pi.mb._fill(imgs, '暂无历史')
        self.row_pw.mb._fill(wms, '暂无历史')

    def pick_src(self):
        p = self.app.pick_open(self.src)
        if p:
            self.set_src(p)

    def set_src(self, path):
        self.src.set(path)
        self.drop.set_file(path)
        if not self.out.get() or self.out.get().startswith(OUT_DIR):
            self.out.set(default_out(path, '_文字水印'))
        self.update_cap()
        self.app.log('已载入原图: %s' % os.path.basename(path), 'info')

    def pick_out(self):
        p = self.app.pick_open(self.out, save=True)
        if p:
            self.out.set(p)

    def open_out(self):
        if not open_folder(self.out.get() or ensure_outdir()):
            messagebox.showinfo(APP_NAME, '输出目录: %s' % OUT_DIR)

    def on_drop(self, path):
        if os.path.isdir(path):
            return
        self.set_src(path)
        self.app._set_status('已载入原图, 填写文字后点「开始嵌入文字水印」', ACCENT)

    def update_cap(self):
        s = self.txt.get('1.0', 'end').strip()
        n = len(s.encode('utf-8')) * 8 if s else 0
        src = self.src.get()
        limit = '?'
        if src and os.path.isfile(src):
            try:
                import cv2
                im = imread_unicode(src, cv2.IMREAD_UNCHANGED)
                if im is not None:
                    limit = int((im.shape[0] // 8) * (im.shape[1] // 8))
            except Exception:
                pass
        over = limit != '?' and n >= limit
        self.cap.configure(text='占用 %d bit · 该图最多可放约 %s bit%s'
                                % (n, limit, ' · 已超容量!' if over else ''),
                           fg=ERR_RED if over else FG_MUTE)

    def clear(self):
        self.src.set('')
        self.drop.set_file(None)
        self.out.set('')
        self.update_cap()

    def run(self):
        src = self.src.get().strip()
        text = self.txt.get('1.0', 'end').strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror(APP_NAME, '请先拖入或选择原图')
            return
        if not text:
            messagebox.showerror(APP_NAME, '请输入要隐藏的文字')
            return
        try:
            pi, pw = int(self.pwd_img.get()), int(self.pwd_wm.get())
        except ValueError:
            messagebox.showerror(APP_NAME, '密码必须是整数(算法限制)')
            return
        out = self.out.get().strip() or default_out(src, '_文字水印')
        if os.path.splitext(out)[1].lower() not in LOSS_LESS:
            out = os.path.splitext(out)[0] + '.png'
        self.out.set(out)

        def job():
            bwm = WaterMark(password_img=pi, password_wm=pw)
            bwm.read_img(src)
            bwm.read_wm(text, mode='str')
            n = len(bwm.wm_bit)
            self.app.log('[文字水印] 原图: %s' % os.path.basename(src))
            self.app.log('[文字水印] 文字: %r  →  %d bit' % (text, n))
            bwm.embed(out)
            self.app.log('✓ 已生成: %s  (%.2f MB)' % (out, os.path.getsize(out) / 1048576), 'ok')
            HISTORY.remember(pi, pw, os.path.dirname(out))
            ok = write_sidecar(out, {
                'type': 'text', 'bwm_version': BWM_VER, 'wm_bit_len': n,
                'password_img': pi, 'password_wm': pw, 'payload': text,
                'created': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
            })
            self.app.log('✓ 密码已记住(%s/%s), 提取信息已随手保存: %s'
                         % (pi, pw, os.path.basename(sidecar_path(out)) if ok else '(失败)'), 'ok')
            open_folder(out)
            return True, '✓ 文字水印嵌入完成'

        self.app.run_async('正在嵌入文字水印…', job)


# ---------------- ② 图片水印嵌入 ----------------
class ImageTab(BaseTab):
    TITLE = '嵌入图片水印'

    def __init__(self, master, app):
        super().__init__(master, app)
        self.src = tk.StringVar()
        self.wm = tk.StringVar()
        self.out = tk.StringVar()
        last = HISTORY.last_pair()
        self.pwd_img = tk.StringVar(value=last[0] if last else '123')
        self.pwd_wm = tk.StringVar(value=last[1] if last else '123')

        c1 = Panel(self)
        c1.grid(row=self.next_row(), column=0, sticky='ew', pady=(0, 10))
        c1.inner.columnconfigure(0, weight=1)
        c1.inner.columnconfigure(1, weight=1)
        self.drop = DropZone(c1.inner, '拖入【原图】', on_pick=self.pick_src)
        self.drop.grid(row=0, column=0, sticky='nsew', padx=(14, 6), pady=14)
        self.drop_wm = DropZone(c1.inner, '拖入【水印图】', on_pick=self.pick_wm)
        self.drop_wm.grid(row=0, column=1, sticky='nsew', padx=(6, 14), pady=14)
        label(c1.inner, '提示: 水印图建议用黑白稿, 尺寸不要超过原图容量的 1/8',
              fg=FG_MUTE, font=(app.F['regular'], 8)).grid(
            row=1, column=0, columnspan=2, sticky='w', padx=14, pady=(0, 12))

        c2 = Panel(self, title='参数')
        c2.grid(row=self.next_row(), column=0, sticky='ew', pady=(0, 10))
        g, r = c2.inner, c2._row
        self.row_pi = PwdRow(g, r, '密码 A(图片)', self.pwd_img,
                             hint='嵌入与提取必须一致', on_history=lambda v: self.pwd_img.set(v))
        r += 1
        self.row_pw = PwdRow(g, r, '密码 B(水印)', self.pwd_wm,
                             hint='嵌入与提取必须一致', on_history=lambda v: self.pwd_wm.set(v))
        r += 1
        PathRow(g, r, '输出到', self.out, self.pick_out, self.open_out)
        pairs = [p[0] for p in HISTORY.data['pairs']]
        self.row_pi.mb._fill(list(dict.fromkeys(pairs or HISTORY.top_images())), '暂无历史')
        self.row_pw.mb._fill(list(dict.fromkeys(pairs or HISTORY.top_wms())), '暂无历史')

        self.go = action_bar(self, '开始嵌入图片水印', self.run, self.clear)

    def pick_src(self):
        p = self.app.pick_open(self.src)
        if p:
            self.set_src(p)

    def pick_wm(self):
        p = self.app.pick_open(self.wm)
        if p:
            self.set_wm(p)

    def set_src(self, path):
        self.src.set(path)
        self.drop.set_file(path)
        if not self.out.get() or self.out.get().startswith(OUT_DIR):
            self.out.set(default_out(path, '_图片水印'))

    def set_wm(self, path):
        self.wm.set(path)
        self.drop_wm.set_file(path)

    def pick_out(self):
        p = self.app.pick_open(self.out, save=True)
        if p:
            self.out.set(p)

    def open_out(self):
        if not open_folder(self.out.get() or ensure_outdir()):
            messagebox.showinfo(APP_NAME, '输出目录: %s' % OUT_DIR)

    def on_drop(self, path):
        if os.path.isdir(path):
            return
        if not (self.src.get() and os.path.isfile(self.src.get())):
            self.set_src(path)
            self.app._set_status('已载入原图, 请再拖入水印图', ACCENT)
        else:
            self.set_wm(path)
            self.app._set_status('已载入水印图, 可点「开始嵌入图片水印」', ACCENT)

    def clear(self):
        self.src.set('')
        self.wm.set('')
        self.out.set('')
        self.drop.set_file(None)
        self.drop_wm.set_file(None)

    def run(self):
        src, wm = self.src.get().strip(), self.wm.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror(APP_NAME, '请先拖入/选择原图')
            return
        if not wm or not os.path.isfile(wm):
            messagebox.showerror(APP_NAME, '请先拖入/选择水印图')
            return
        try:
            pi, pw = int(self.pwd_img.get()), int(self.pwd_wm.get())
        except ValueError:
            messagebox.showerror(APP_NAME, '密码必须是整数(算法限制)')
            return
        out = self.out.get().strip() or default_out(src, '_图片水印')
        if os.path.splitext(out)[1].lower() not in LOSS_LESS:
            out = os.path.splitext(out)[0] + '.png'
        self.out.set(out)

        def job():
            import cv2
            im = imread_unicode(wm, cv2.IMREAD_GRAYSCALE)
            if im is None:
                return False, '水印图读不出来, 请换一张'
            h, w = im.shape[:2]
            bwm = WaterMark(password_img=pi, password_wm=pw)
            bwm.read_img(src)
            bwm.read_wm(wm, mode='img')
            self.app.log('[图片水印] 原图: %s' % os.path.basename(src))
            self.app.log('[图片水印] 水印: %s (%dx%d = %d bit)'
                         % (os.path.basename(wm), w, h, w * h))
            try:
                bwm.embed(out)
            except AssertionError:
                return False, '水印太大, 超过这张原图的容量, 请换小一点的水印图'
            self.app.log('✓ 已生成: %s  (%.2f MB)' % (out, os.path.getsize(out) / 1048576), 'ok')
            HISTORY.remember(pi, pw, os.path.dirname(out))
            ok = write_sidecar(out, {
                'type': 'img', 'bwm_version': BWM_VER, 'wm_shape': [h, w],
                'password_img': pi, 'password_wm': pw,
                'created': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
            })
            self.app.log('✓ 密码已记住(%s/%s), 侧车文件: %s'
                         % (pi, pw, os.path.basename(sidecar_path(out)) if ok else '(失败)'), 'ok')
            open_folder(out)
            return True, '✓ 图片水印嵌入完成'

        self.app.run_async('正在嵌入图片水印…', job)


# ---------------- ③ 提取 ----------------
class ExtractTab(BaseTab):
    TITLE = '提取水印'

    def __init__(self, master, app):
        super().__init__(master, app)
        self.src = tk.StringVar()
        self.outdir = tk.StringVar(value=HISTORY.last_output_dir() or ensure_outdir())
        last = HISTORY.last_pair()
        self.pwd_img = tk.StringVar(value=last[0] if last else '123')
        self.pwd_wm = tk.StringVar(value=last[1] if last else '123')
        self.mode = tk.StringVar(value='text')
        self.length = tk.StringVar(value='')
        self.shape = tk.StringVar(value='')

        c1 = Panel(self)
        c1.grid(row=self.next_row(), column=0, sticky='ew', pady=(0, 10))
        c1.inner.columnconfigure(0, weight=1)
        self.drop = DropZone(c1.inner, '把【带水印的图片】拖到这里',
                             on_pick=self.pick_src, height=88)
        self.drop.grid(row=0, column=0, sticky='ew', padx=14, pady=14)
        self.auto_lbl = label(c1.inner,
                              '密码已按历史自动填入 · 若图片旁有同名 .bwm.json, 长度/尺寸也会自动填好',
                              fg=FG_MUTE, font=(app.F['regular'], 8))
        self.auto_lbl.grid(row=1, column=0, sticky='w', padx=14, pady=(0, 10))

        c2 = Panel(self, title='水印类型')
        c2.grid(row=self.next_row(), column=0, sticky='ew', pady=(0, 10))
        g, r = c2.inner, c2._row
        rb = tk.Frame(g, bg=PANEL)
        rb.grid(row=r, column=0, columnspan=3, sticky='w', padx=14, pady=(0, 4))
        self.tg_text = Toggle(rb, '文字水印 · 更抗攻击',
                              command=lambda: self._set_mode('text'))
        self.tg_text.pack(side='left', padx=(0, 8))
        self.tg_img = Toggle(rb, '图片水印', command=lambda: self._set_mode('img'))
        self.tg_img.pack(side='left')
        r += 1
        self.row_len = tk.Frame(g, bg=PANEL)
        self.row_len.grid(row=r, column=0, columnspan=3, sticky='w', padx=14, pady=5)
        label(self.row_len, '水印长度(bit)', fg=FG_DIM).pack(side='left')
        entry(self.row_len, self.length, width=8).pack(side='left', padx=(8, 8))
        label(self.row_len, '嵌入日志里会给出, 或看同名 .bwm.json', fg=FG_MUTE,
              font=(app.F['regular'], 8)).pack(side='left')
        r += 1
        self.row_shape = tk.Frame(g, bg=PANEL)
        self.row_shape.grid(row=r, column=0, columnspan=3, sticky='w', padx=14, pady=5)
        label(self.row_shape, '水印图尺寸 宽x高', fg=FG_DIM).pack(side='left')
        entry(self.row_shape, self.shape, width=10).pack(side='left', padx=(8, 8))
        label(self.row_shape, '例 100x100', fg=FG_MUTE,
              font=(app.F['regular'], 8)).pack(side='left')
        r += 1

        # 密码区: 一行显示"历史密码"快捷项, 干净且不啰嗦
        self.pwd_box = tk.Frame(g, bg=PANEL)
        self.pwd_box.grid(row=r, column=0, columnspan=3, sticky='w', padx=14, pady=5)
        label(self.pwd_box, '密码 A(图片)', fg=FG_DIM).pack(side='left')
        self.e_pi = entry(self.pwd_box, self.pwd_img, width=12)
        self.e_pi.pack(side='left', padx=(8, 0))
        self.mb_pi = _pwd_menu_button(self.pwd_box, lambda v: self.pwd_img.set(v))
        self.mb_pi.pack(side='left', padx=(4, 0))
        label(self.pwd_box, '密码 B(水印)', fg=FG_DIM).pack(side='left', padx=(20, 0))
        self.e_pw = entry(self.pwd_box, self.pwd_wm, width=12)
        self.e_pw.pack(side='left', padx=(8, 0))
        self.mb_pw = _pwd_menu_button(self.pwd_box, lambda v: self.pwd_wm.set(v))
        self.mb_pw.pack(side='left', padx=(4, 0))
        r += 1
        self.hist_box = tk.Frame(g, bg=PANEL)
        self.hist_box.grid(row=r, column=0, columnspan=3, sticky='w', padx=14, pady=(0, 2))
        r += 1
        PathRow(g, r, '结果存到', self.outdir, self.pick_outdir, self.open_out)
        self.refresh_history()
        self.sync_mode()

        self.go = action_bar(self, '开始提取水印', self.run, self.clear)

    # ---- 历史密码 ----
    def refresh_history(self):
        """把最近用过的密码对做成可点的小标签, 一键填入"""
        pairs = HISTORY.data['pairs'][:4]
        top_i = HISTORY.top_images(4)
        top_w = HISTORY.top_wms(4)
        for w in self.hist_box.winfo_children():
            w.destroy()
        if pairs:
            label(self.hist_box, '历史', fg=FG_MUTE, font=(FONT_REG, 8)).pack(side='left',
                                                                            padx=(0, 4))
        for pi, pw in pairs:
            cell = tk.Frame(self.hist_box, bg=ACCENT, bd=0)
            cell.pack(side='left', padx=(6, 0))
            b = tk.Label(cell, text='%s / %s' % (pi, pw), bg=PANEL_HI, fg=FG_DIM,
                         font=(FONT_MONO, 8), padx=9, pady=3, cursor='hand2')
            b.pack(padx=(2, 0))          # 左侧留出 2px 强调色竖条
            b.bind('<Button-1>', lambda e, a=pi, c=pw: self._use_pair(a, c))
            b.bind('<Enter>', lambda e, w=b: w.configure(fg=ACCENT, bg=PANEL))
            b.bind('<Leave>', lambda e, w=b: w.configure(fg=FG_DIM, bg=PANEL_HI))
        if not pairs:
            label(self.hist_box, '历史: 暂无(成功嵌入一次就会记住密码)', fg=FG_MUTE,
                  font=(FONT_REG, 8)).pack(side='left')
        self.mb_pi._fill(top_i, '暂无历史')
        self.mb_pw._fill(top_w, '暂无历史')

    def _use_pair(self, pi, pw):
        self.pwd_img.set(pi)
        self.pwd_wm.set(pw)
        self.app._set_status('已填入历史密码 A=%s B=%s' % (pi, pw), ACCENT)

    def _set_mode(self, m):
        self.mode.set(m)
        self.sync_mode()

    def sync_mode(self):
        is_text = self.mode.get() == 'text'
        if hasattr(self, 'tg_text'):
            self.tg_text.set_on(is_text)
            self.tg_img.set_on(not is_text)
        if is_text:
            self.row_len.grid()
            self.row_shape.grid_remove()
            if hasattr(self, 'go'):
                self.go.configure(text='开始提取文字水印')
        else:
            self.row_shape.grid()
            self.row_len.grid_remove()
            if hasattr(self, 'go'):
                self.go.configure(text='开始提取图片水印')

    def pick_src(self):
        p = self.app.pick_open(self.src)
        if p:
            self.set_src(p)

    def set_src(self, path):
        self.src.set(path)
        self.drop.set_file(path)
        sc = read_sidecar(path)
        if sc:
            if sc.get('password_img') is not None:
                self.pwd_img.set(str(sc['password_img']))
            if sc.get('password_wm') is not None:
                self.pwd_wm.set(str(sc['password_wm']))
            if sc.get('type') == 'img':
                self.mode.set('img')
                h, w = sc.get('wm_shape', [0, 0])
                self.shape.set('%dx%d' % (w, h))
            else:
                self.mode.set('text')
                self.length.set(str(sc.get('wm_bit_len', '')))
            self.sync_mode()
            self.auto_lbl.configure(
                text='✓ 已读取同名信息文件, 密码/长度自动填好, 直接点提取', fg=OK_GREEN)
            self.app.log('发现提取信息文件, 已自动回填参数: %s'
                         % os.path.basename(sidecar_path(path)), 'ok')
        else:
            self.auto_lbl.configure(
                text='密码已按历史自动填入 · 未找到 .bwm.json, 请手动填水印长度', fg=FG_MUTE)
        self.app._set_status('已载入待提取图片', ACCENT)

    def pick_outdir(self):
        p = filedialog.askdirectory(initialdir=self.outdir.get() or OUT_DIR)
        if p:
            self.outdir.set(p)

    def open_out(self):
        if not open_folder(self.outdir.get() or ensure_outdir()):
            messagebox.showinfo(APP_NAME, '输出目录: %s' % OUT_DIR)

    def on_drop(self, path):
        if os.path.isdir(path):
            self.outdir.set(path)
            self.app._set_status('已把输出目录设为该文件夹', ACCENT)
            return
        self.set_src(path)

    def clear(self):
        self.src.set('')
        self.drop.set_file(None)
        self.length.set('')
        self.shape.set('')
        self.auto_lbl.configure(
            text='密码已按历史自动填入 · 若图片旁有同名 .bwm.json, 长度/尺寸也会自动填好',
            fg=FG_MUTE)

    def run(self):
        src = self.src.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror(APP_NAME, '请先拖入/选择带水印的图片')
            return
        try:
            pi, pw = int(self.pwd_img.get()), int(self.pwd_wm.get())
        except ValueError:
            messagebox.showerror(APP_NAME, '密码必须是整数')
            return
        outdir = self.outdir.get().strip() or ensure_outdir()
        src_stem = os.path.splitext(os.path.basename(src))[0]
        mode = self.mode.get()

        if mode == 'text':
            try:
                n = int(self.length.get())
            except ValueError:
                messagebox.showerror(APP_NAME, '请填写水印长度(bit)')
                return
        else:
            try:
                wh = self.shape.get().lower().replace('*', 'x').split('x')
                sw, sh = int(wh[0]), int(wh[1])
            except Exception:
                messagebox.showerror(APP_NAME, '水印图尺寸请填写成 100x100 这种格式')
                return

        def job():
            bwm = WaterMark(password_img=pi, password_wm=pw)
            if mode == 'text':
                try:
                    txt = bwm.extract(filename=src, wm_shape=n, mode='str')
                except Exception:
                    txt = None
                if txt is None:
                    self.app.log('✗ 提取失败: 密码或水印长度不对(水印存在, 只是解不开)', 'err')
                    return False, '✗ 密码 / 水印长度不对'
                HISTORY.remember(pi, pw, outdir)
                self.app.log('✓ 提取成功, 隐藏的文字是:', 'ok')
                self.app.log('   %s' % txt, 'ok')
                p = os.path.join(outdir, '%s_水印内容.txt' % src_stem)
                try:
                    os.makedirs(outdir, exist_ok=True)
                    with open(p, 'w', encoding='utf-8') as f:
                        f.write(txt)
                    self.app.log('   已另存为 %s' % p, 'ok')
                    open_folder(p)
                except OSError as e:
                    self.app.log('   (结果文件写入失败: %s)' % e, 'err')
                return True, '✓ 文字水印提取成功'
            p = os.path.join(outdir, '%s_提取出的水印.png' % src_stem)
            bwm.extract(filename=src, wm_shape=(sh, sw), out_wm_name=p)
            HISTORY.remember(pi, pw, outdir)
            self.app.log('✓ 图片水印已还原: %s' % p, 'ok')
            open_folder(p)
            return True, '✓ 图片水印提取完成'

        self.app.run_async('正在提取水印…', job)


# ---------------- 自检 ----------------
def self_test():
    import tempfile
    import cv2
    import numpy as np

    out = []
    out.append('frozen=%s' % getattr(sys, 'frozen', False))
    out.append('exe=%s' % sys.executable)
    out.append('meipass=%s' % getattr(sys, '_MEIPASS', '-'))
    out.append('python=%s' % sys.version.split()[0])
    out.append('bwm=%s cv2=%s numpy=%s pywt=%s' % (
        BWM_VER, cv2.__version__, np.__version__, __import__('pywt').__version__))
    out.append('drag_and_drop=%s' % DND_OK)
    out.append('config_dir=%s' % appdata_dir())

    work = tempfile.mkdtemp(prefix='盲水印自检_')
    ok = True
    try:
        img = (np.random.RandomState(0).rand(512, 512, 3) * 255).astype(np.uint8)
        src = os.path.join(work, '原始图片.jpg')
        assert imwrite_unicode(src, img), 'write src failed'

        bwm = WaterMark(password_img=88, password_wm=88)
        bwm.read_img(src)
        bwm.read_wm('自检水印-OK', mode='str')
        n = len(bwm.wm_bit)
        emb = os.path.join(work, '嵌入结果.png')
        bwm.embed(emb)
        write_sidecar(emb, {'type': 'text', 'wm_bit_len': n,
                            'password_img': 88, 'password_wm': 88, 'payload': '自检水印-OK'})
        out.append('embed -> %s (%d bytes), wm_bit=%d' % (emb, os.path.getsize(emb), n))

        bwm2 = WaterMark(password_img=88, password_wm=88)
        txt = bwm2.extract(filename=emb, wm_shape=n, mode='str')
        out.append('extract -> %r' % txt)
        if txt != '自检水印-OK':
            ok = False

        sc = read_sidecar(emb)
        out.append('sidecar -> %s' % str(sc and (sc['wm_bit_len'], sc['payload'])))
        if not sc or sc['payload'] != '自检水印-OK':
            ok = False

        wm_img = (np.random.RandomState(1).rand(40, 40) > 0.5).astype(np.uint8) * 255
        wp = os.path.join(work, '水印图.png')
        assert imwrite_unicode(wp, wm_img)
        b3 = WaterMark(password_img=7, password_wm=7)
        b3.read_img(src)
        b3.read_wm(wp, mode='img')
        e3 = os.path.join(work, '图水印嵌入.png')
        b3.embed(e3)
        b4 = WaterMark(password_img=7, password_wm=7)
        x3 = os.path.join(work, '图水印提取.png')
        b4.extract(filename=e3, wm_shape=(40, 40), out_wm_name=x3)
        ex = imread_unicode(x3, cv2.IMREAD_GRAYSCALE)
        corr = float(np.corrcoef((ex > 128).flatten().astype(float),
                                 (wm_img > 128).flatten().astype(float))[0, 1])
        out.append('img-watermark roundtrip corr=%.4f' % corr)
        if corr < 0.9:
            ok = False

        out.append('default_out -> %s' % default_out('/x/照片.jpg', '_文字水印'))
        d = parse_drop('{C:/a b/图 1.png} {D:/x.png}')
        out.append('parse_drop -> %r' % d)
        if d != ['C:/a b/图 1.png', 'D:/x.png']:
            ok = False

        # 历史密码(用临时文件, 不污染真实配置)
        orig_file = History.FILE
        try:
            History.FILE = os.path.join(work, 'history.json')
            h = History()
            h.remember(4321, 8765, work)
            load_back = History()
            out.append('history pairs -> %s' % str(load_back.data['pairs'][:3]))
            out.append('history image/wm -> %s / %s'
                       % (str(load_back.top_images(3)), str(load_back.top_wms(3))))
            if not load_back.data['pairs'] or load_back.data['pairs'][0] != ['4321', '8765']:
                ok = False
            if load_back.data['image'].get('4321') != 1:
                ok = False
        finally:
            History.FILE = orig_file

        # Tk + 字体 + tkdnd + 历史密码自动填入
        try:
            r = DND_TK()
            r.withdraw()
            r.update()
            ver = ''
            if DND_OK:
                try:
                    ver = str(r.tk.call('package', 'require', 'tkdnd'))
                    r.drop_target_register(DND_FILES)
                except Exception as e:
                    ok = False
                    out.append('tkdnd 注册失败: %s' % e)
            fonts = detected_fonts(r)
            out.append('fonts -> bold=%s medium=%s regular=%s mono=%s'
                       % (fonts['bold'], fonts['medium'], fonts['regular'], fonts['mono']))
            if 'Noto Sans SC' not in (fonts['bold'] + fonts['medium']) and \
                    'Source Han Sans' not in (fonts['bold'] + fonts['medium']):
                out.append('  (提示: 本机未装思源黑体, 已回退到 %s)' % fonts['bold'])
            out.append('tk_root=OK tkdnd_version=%s' % (ver or 'n/a'))
            r.destroy()
        except Exception as e:
            ok = False
            out.append('tk_root=FAIL %s' % e)

        # 真实 App: 样式 / 警戒线颜色 / 历史密码自动填入
        try:
            a = App()
            a.update_idletasks()
            a.update()
            out.append('app_dnd %s' % a.dnd_self_check())
            out.append('theme BG=%s PANEL=%s LINE=%s ACCENT=%s stripe(ok)=%s'
                       % (BG, PANEL, LINE, ACCENT, a._state_color))
            if a._state_color != OK_GREEN:
                ok = False
            a.set_state('err')
            if a._state_color != ERR_RED:
                ok = False
            out.append('stripe(ok)=%s stripe(err)=%s' % (OK_GREEN, ERR_RED))
            a.set_state('ok')
            # 历史密码自动填入
            last = HISTORY.last_pair()
            out.append('extract auto-fill pwd -> A=%s B=%s (history=%s)'
                       % (a.tab_ext.pwd_img.get(), a.tab_ext.pwd_wm.get(), last))
            if last and (a.tab_ext.pwd_img.get() != last[0] or a.tab_ext.pwd_wm.get() != last[1]):
                ok = False
            a.destroy()
        except Exception as e:
            ok = False
            out.append('app FAIL %s' % traceback.format_exc().strip().splitlines()[-1])
    except Exception:
        ok = False
        out.append(traceback.format_exc())
    out.append('SELF_TEST=%s' % ('PASS' if ok else 'FAIL'))
    return '\n'.join(out), ok


if __name__ == '__main__':
    if '--selftest' in sys.argv:
        text, ok = self_test()
        if getattr(sys, 'frozen', False):
            try:
                with open(os.path.join(os.path.dirname(sys.executable),
                                       'selftest_report.txt'), 'w', encoding='utf-8') as f:
                    f.write(text)
            except Exception:
                pass
            try:
                import tkinter.messagebox as mb
                mb.showinfo('自检结果', text)
            except Exception:
                pass
        else:
            sys.stdout.write(text + '\n')
        sys.exit(0 if ok else 1)

    if '--preview' in sys.argv:
        try:
            i = sys.argv.index('--preview')
            secs = int(sys.argv[i + 1])
        except Exception:
            secs = 12
        app = App()
        try:
            app.nb.select(int(sys.argv[i + 2]))
        except Exception:
            pass
        try:
            import re as _re
            parts = sys.argv[i + 3].strip().split(',')
            m = _re.match(r'(\d+)[xX*](\d+)$', parts[0]) if parts else None
            if m:
                x = int(parts[1]) if len(parts) > 1 else 0
                y = int(parts[2]) if len(parts) > 2 else 0
                app.geometry('%sx%s+%d+%d' % (m.group(1), m.group(2), x, y))
        except Exception:
            pass
        app.after(secs * 1000, app.destroy)
        app.mainloop()
        sys.exit(0)

    App().mainloop()
