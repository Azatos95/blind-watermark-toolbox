# -*- coding: utf-8 -*-
"""
盲水印工具箱 v0.2 —— blind_watermark 的独立 exe 图形界面

算法核心来自 guofei9987 的开源项目 blind_watermark (MIT License):
  https://github.com/guofei9987/blind_watermark
  原作者: 郭飞 (guofei9987@foxmail.com), Copyright (c) 2019 郭飞
本 GUI / 打包工程为二次开发, 同样以 MIT 协议开源, 详见 LICENSE。

功能:
- 文字水印 / 图片水印 / 提取 三个相互独立的标签页, 各自按钮与状态互不干扰
- 拖拽图片到窗口任意位置即可载入(依赖 tkinterdnd2)
- 自动生成输出路径(桌面「盲水印输出」文件夹), 文件名自动推导
- 侧车文件记录密码与水印长度, 提取时一键回填, 避免"第二天提不出来"
- 响应式: 全部使用 grid + 权重, 随窗口缩放自动重排
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
from tkinter import font as tkfont

import blind_watermark
try:
    blind_watermark.bw_notes.close()
except Exception:
    pass

from blind_watermark import WaterMark

APP_NAME = '盲水印工具箱'
APP_VER = '0.2'
BWM_VER = getattr(blind_watermark, '__version__', '?')

# ---------------- 配色 ----------------
BG = '#f4f6fa'
CARD = '#ffffff'
BORDER = '#dfe4ee'
TXT = '#1f2937'
SUB = '#6b7280'
ACCENT = '#2563eb'
ACCENT_DK = '#1d4ed8'
OKC = '#059669'
ERRC = '#dc2626'

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
    """返回 (root类, DND_FILES符号, 是否可用)"""
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
        depth = 0
        cur = ''
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
                 os.path.join(os.path.expanduser('~'), '.dsh', '盲水印输出')):
        if _writable(cand):
            return cand
    return os.getcwd()


def ensure_outdir():
    global OUT_DIR
    if not _writable(OUT_DIR):
        OUT_DIR = pick_out_dir()
    return OUT_DIR


def default_out(src, suffix, force_lossless=True):
    """由源文件推导输出路径, 统一放到桌面「盲水印输出」"""
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
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


def open_folder(path):
    """打开文件夹/定位文件。

    注意: 这个方法会被后台工作线程调用, 所以必须"永不阻塞、永不抛异常"。
    os.startfile 在非主线程(无 STA 消息泵)时可能卡死, 因此放进守护线程并加超时。
    """
    if not path:
        return False
    path = os.path.abspath(path)
    target = path if os.path.isdir(path) else os.path.dirname(path)
    if not os.path.isdir(target):
        return False

    # 首选 explorer: 稳定, 且能在后台线程安全调用
    try:
        if os.path.isfile(path):
            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)],
                             close_fds=True)
        else:
            subprocess.Popen(['explorer', os.path.normpath(target)], close_fds=True)
        return True
    except Exception:
        pass

    # 兜底: os.startfile 放进守护线程, 最多等 2 秒, 绝不拖住主流程
    def _sf(p):
        try:
            os.startfile(p)
        except Exception:
            pass

    th = threading.Thread(target=_sf, args=(target,), daemon=True)
    th.start()
    th.join(2.0)
    return True


# ---------------- UI 基础组件 ----------------
class Card(tk.Frame):
    """白底圆角感卡片容器"""

    def __init__(self, master, title=None, pad=16, **kw):
        super().__init__(master, bg=CARD, highlightbackground=BORDER,
                         highlightthickness=1, bd=0, **kw)
        self.body = self
        self.columnconfigure(0, weight=1)
        if title:
            tk.Label(self, text=title, bg=CARD, fg=TXT,
                     font=('Microsoft YaHei UI', 11, 'bold'),
                     anchor='w').grid(row=0, column=0, sticky='ew',
                                      padx=pad, pady=(pad - 4, 4))


class DropZone(tk.Frame):
    """可点击 / 可拖入的虚线区域, 显示当前文件"""

    def __init__(self, master, text='把图片拖到这里, 或点击选择', on_pick=None):
        super().__init__(master, bg='#eef4ff', highlightbackground='#9dbcf5',
                         highlightthickness=2, bd=0, cursor='hand2')
        self.on_pick = on_pick
        self.columnconfigure(0, weight=1)
        self.icon = tk.Label(self, text='🖼', bg='#eef4ff', fg=ACCENT,
                             font=('Segoe UI Emoji', 20))
        self.icon.grid(row=0, column=0, pady=(10, 0))
        self.hint = tk.Label(self, text=text, bg='#eef4ff', fg=ACCENT,
                             font=('Microsoft YaHei UI', 10, 'bold'))
        self.hint.grid(row=1, column=0)
        self.file_lbl = tk.Label(self, text='尚未选择文件', bg='#eef4ff', fg=SUB,
                                 font=('Microsoft YaHei UI', 9), wraplength=520,
                                 justify='center')
        self.file_lbl.grid(row=2, column=0, pady=(2, 10), padx=10)
        for w in (self, self.icon, self.hint, self.file_lbl):
            w.bind('<Button-1>', self._pick)

    def _pick(self, _e=None):
        if self.on_pick:
            self.on_pick()

    def set_file(self, path):
        if path:
            self.file_lbl.configure(text=os.path.basename(path), fg=TXT)
            self.configure(highlightbackground=OKC)
            self.icon.configure(text='✅', fg=OKC)
            self.hint.configure(text='已载入 — 拖入新图片可更换', fg=OKC)
        else:
            self.file_lbl.configure(text='尚未选择文件', fg=SUB)
            self.configure(highlightbackground='#9dbcf5')
            self.icon.configure(text='🖼', fg=ACCENT)
            self.hint.configure(text='把图片拖到这里, 或点击选择', fg=ACCENT)


def path_row(parent, row, label, var, on_browse, on_open=None, pad=16):
    tk.Label(parent, text=label, bg=CARD, fg=SUB,
             font=('Microsoft YaHei UI', 9)).grid(row=row, column=0, sticky='w',
                                                  padx=(pad, 4), pady=6)
    ent = tk.Entry(parent, textvariable=var, bg='#fbfcfe', fg=TXT, bd=1,
                   relief='solid', highlightthickness=0,
                   font=('Microsoft YaHei UI', 9))
    ent.grid(row=row, column=1, sticky='ew', padx=4, pady=6)
    box = tk.Frame(parent, bg=CARD)
    box.grid(row=row, column=2, sticky='e', padx=(4, pad))
    ttk.Button(box, text='浏览', width=6, command=on_browse).pack(side='left')
    if on_open:
        ttk.Button(box, text='打开', width=6, command=on_open).pack(side='left', padx=(4, 0))


def pwd_row(parent, row, label, var, pad=16, hint=None):
    tk.Label(parent, text=label, bg=CARD, fg=SUB,
             font=('Microsoft YaHei UI', 9)).grid(row=row, column=0, sticky='w',
                                                  padx=(pad, 4), pady=6)
    ent = tk.Entry(parent, textvariable=var, bg='#fbfcfe', fg=TXT, bd=1,
                   relief='solid', highlightthickness=0, width=12,
                   font=('Microsoft YaHei UI', 9))
    ent.grid(row=row, column=1, sticky='w', padx=4, pady=6)
    if hint:
        tk.Label(parent, text=hint, bg=CARD, fg=SUB,
                 font=('Microsoft YaHei UI', 8)).grid(row=row, column=2,
                                                      sticky='w', padx=4)


# ---------------- 主窗口 ----------------
class App(DND_TK):
    def __init__(self):
        super().__init__()
        self.title('%s v%s' % (APP_NAME, APP_VER))
        self.configure(bg=BG)
        self.minsize(720, 600)
        self._center(900, 720)

        self._setup_style()
        self.logq = queue.Queue()
        self.doneq = queue.Queue()      # 后台任务完成后回传结果(避免工作线程直接碰 Tk)
        self.busy = False
        self.drop_targets = []      # 注册了拖放的目标控件
        self.active_drop = None     # 当前标签页的接收回调
        self._last_dir = get_desktop()

        self._build_header()
        self._build_tabs()
        self._build_log()
        self._setup_dnd()

        self.after(120, self._drain_log)
        self.log('就绪 · blind_watermark %s · Python %s' %
                 (BWM_VER, sys.version.split()[0]))
        self.log('输出目录: %s' % ensure_outdir())
        if not DND_OK:
            self.log('提示: 未装 tkinterdnd2, 拖拽不可用, 请点「浏览」选择图片。')

    # ---- 窗口居中 ----
    def _center(self, w, h):
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x, y = max(0, (sw - w) // 2), max(0, (sh - h) // 3)
        self.geometry('%dx%d+%d+%d' % (w, h, x, y))

    # ---- 样式 ----
    def _setup_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use('clam')     # clam 才能自定义配色, 且跨版本一致
        except tk.TclError:
            pass
        try:
            fam = 'Microsoft YaHei UI'
            tkfont.nametofont('TkDefaultFont').configure(family=fam, size=9)
            tkfont.nametofont('TkTextFont').configure(family=fam, size=9)
        except Exception:
            pass

        st.configure('TFrame', background=BG)
        st.configure('TLabel', background=BG, foreground=TXT)
        st.configure('TNotebook', background=BG, borderwidth=0, tabmargins=(2, 6, 2, 0))
        st.configure('TNotebook.Tab', padding=(22, 9), font=('Microsoft YaHei UI', 10),
                     background='#e6eaf3', foreground=SUB, borderwidth=0)
        st.layout('TNotebook', [('Notebook.client', {'sticky': 'nswe'})])
        st.map('TNotebook.Tab',
               background=[('selected', CARD)],
               foreground=[('selected', ACCENT)],
               expand=[('selected', (0, 0, 0, 0))])
        st.configure('Card.TFrame', background=CARD)
        st.configure('Card.TLabel', background=CARD, foreground=TXT)

        st.configure('TButton', font=('Microsoft YaHei UI', 9), padding=(10, 6))
        st.configure('Go.TButton', font=('Microsoft YaHei UI', 10, 'bold'),
                     padding=(26, 10), background=ACCENT, foreground='white',
                     borderwidth=0, focuscolor=ACCENT)
        st.map('Go.TButton',
               background=[('active', ACCENT_DK), ('disabled', '#a9bce0')],
               foreground=[('disabled', '#eef2ff')])
        st.configure('Ghost.TButton', background=CARD, foreground=SUB,
                     borderwidth=1, relief='solid')
        st.map('Ghost.TButton', background=[('active', '#eef2ff')],
               foreground=[('active', ACCENT)])

        st.configure('TProgressbar', background=ACCENT, troughcolor='#e6eaf3',
                     borderwidth=0, thickness=4)

    # ---- 顶部 ----
    def _build_header(self):
        hd = tk.Frame(self, bg=BG)
        hd.pack(fill='x', padx=18, pady=(14, 4))
        hd.columnconfigure(1, weight=1)
        tk.Label(hd, text='💧', bg=BG, fg=ACCENT,
                 font=('Segoe UI Emoji', 20)).grid(row=0, column=0, rowspan=2, padx=(0, 10))
        tk.Label(hd, text=APP_NAME, bg=BG, fg=TXT,
                 font=('Microsoft YaHei UI', 15, 'bold'), anchor='w').grid(row=0, column=1, sticky='w')
        tk.Label(hd, text='图片里藏一段看不见的信息 · 截图 / 裁剪 / 旋转后依然能取回',
                 bg=BG, fg=SUB, font=('Microsoft YaHei UI', 9),
                 anchor='w').grid(row=1, column=1, sticky='w')
        self.dnd_badge = tk.Label(hd, text='拖拽已就绪' if DND_OK else '拖拽不可用',
                                  bg='#e7f6ef' if DND_OK else '#fdecec',
                                  fg=OKC if DND_OK else ERRC,
                                  font=('Microsoft YaHei UI', 8), padx=8, pady=3)
        self.dnd_badge.grid(row=0, column=2, rowspan=2, sticky='e')

    # ---- 标签页 ----
    def _build_tabs(self):
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True, padx=18, pady=(10, 0))
        self.tab_text = TextTab(self.nb, self)
        self.tab_img = ImageTab(self.nb, self)
        self.tab_ext = ExtractTab(self.nb, self)
        self.nb.add(self.tab_text, text='① 嵌入文字水印')
        self.nb.add(self.tab_img, text='② 嵌入图片水印')
        self.nb.add(self.tab_ext, text='③ 提取水印')
        self.nb.bind('<<NotebookTabChanged>>', lambda e: self._sync_drop())

    # ---- 底部日志 ----
    def _build_log(self):
        wrap = tk.Frame(self, bg=BG)
        wrap.pack(fill='x', padx=18, pady=(8, 4))
        self.status = tk.Label(wrap, text='就绪', bg=BG, fg=SUB,
                               font=('Microsoft YaHei UI', 9, 'bold'), anchor='w')
        self.status.pack(side='left')
        self.bar = ttk.Progressbar(wrap, mode='indeterminate', length=140)
        self.log_toggle = ttk.Button(wrap, text='收起日志', style='Ghost.TButton',
                                     command=self._toggle_log)
        self.log_toggle.pack(side='right')
        self.log_open_btn = ttk.Button(wrap, text='打开输出目录', style='Ghost.TButton',
                                       command=lambda: open_folder(ensure_outdir()))
        self.log_open_btn.pack(side='right', padx=(0, 6))

        self.logbox = tk.Frame(self, bg=BG)
        self.logbox.pack(fill='x', padx=18, pady=(0, 12))
        self.log_text = tk.Text(self.logbox, height=5, wrap='word', bg='#101827', fg='#c9d4e6',
                                insertbackground='#c9d4e6', bd=0, padx=10, pady=8,
                                font=('Consolas', 9), state='disabled')
        sb = ttk.Scrollbar(self.logbox, orient='vertical', command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.log_text.tag_configure('ok', foreground='#6ee7a8')
        self.log_text.tag_configure('err', foreground='#fca5a5')
        self.log_text.tag_configure('info', foreground='#93c5fd')

    def _toggle_log(self):
        if self.logbox.winfo_ismapped():
            self.logbox.pack_forget()
            self.log_toggle.configure(text='展开日志')
        else:
            self.logbox.pack(fill='x', padx=18, pady=(0, 12))
            self.log_toggle.configure(text='收起日志')

    # ---- 拖拽接线 ----
    def _setup_dnd(self):
        if not DND_OK:
            return
        for w in (self,):
            try:
                w.drop_target_register(DND_FILES)
                self.drop_targets.append(w)
            except Exception:
                pass
        self.dnd_bind('<<Drop>>', self._on_drop)
        self._sync_drop()

    def dnd_self_check(self):
        """返回打包后拖拽链路的自检字符串"""
        if not DND_OK:
            return 'no-tkdnd'
        try:
            subs = self.dnd_bind('<<Drop>>')
            return 'targets=%d bind=%s' % (len(self.drop_targets), subs)
        except Exception as e:
            return 'bind-fail %s' % e

    def _sync_drop(self):
        """按钮与拖拽接收方都跟随当前标签页, 三个标签互不影响"""
        try:
            cur = self.nb.index(self.nb.select())
        except Exception:
            cur = 0
        tab = (self.tab_text, self.tab_img, self.tab_ext)[cur]
        self.active_drop = tab.on_drop
        self._set_status('就绪 · %s' % tab.TITLE, SUB)

    def _on_drop(self, event):
        files = parse_drop(event.data)
        if not files or not self.active_drop:
            return
        self.active_drop(files[0])

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
        # 后台任务收尾也在这里做: 保证只在主线程/主循环里操作 Tk
        try:
            while True:
                title, ok, msg = self.doneq.get_nowait()
                self.exit_busy(msg if (msg and len(str(msg)) < 60) else (title + '完成'), ok)
        except queue.Empty:
            pass
        self.after(120, self._drain_log)

    def _set_status(self, text, color=SUB):
        self.status.configure(text=text, fg=color)

    def enter_busy(self, text):
        self.busy = True
        self._set_status(text, ACCENT)
        self.bar.pack(side='left', padx=10)
        self.bar.start(12)

    def exit_busy(self, text='就绪', ok=None):
        self.busy = False
        self.bar.stop()
        self.bar.pack_forget()
        col = SUB if ok is None else (OKC if ok else ERRC)
        self._set_status(text, col)

    def pick_open(self, var, save=False, defext='.png'):
        if save:
            p = filedialog.asksaveasfilename(initialdir=OUT_DIR,
                                             initialfile=os.path.basename(var.get() or ''),
                                             defaultextension=defext,
                                             filetypes=PIC_TYPES)
        else:
            p = filedialog.askopenfilename(initialdir=self._last_dir, filetypes=PIC_TYPES)
        if p:
            if not save:
                self._last_dir = os.path.dirname(p)
                var.set(p)
            else:
                var.set(p)
        return p

    def run_async(self, title, fn):
        """统一的后台执行: 进度条 + 异常兜底; 工作线程只写队列, 不直接操作 Tk"""
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


# ---------------- 通用标签页骨架 ----------------
class BaseTab(tk.Frame):
    TITLE = ''

    def __init__(self, master, app):
        super().__init__(master, bg=BG)
        self.app = app
        self.columnconfigure(0, weight=1)
        self._row = 0
        self._spacer_row = None

    def spacer(self):
        """兼容占位: 不再插入弹性行(会导致窗口拉大时中间出现大块空白)"""
        return None

    def on_drop(self, path):
        """子类实现: 接收到一个被拖入的文件路径"""
        raise NotImplementedError

    def new_card(self, title=None, sticky='ew', pady=(0, 10)):
        c = Card(self, title=title)
        c.grid(row=self._row, column=0, sticky='ew' if sticky == 'ew' else sticky, pady=pady)
        self._row += 1
        return c


# ---------------- ① 文字水印嵌入 ----------------
class TextTab(BaseTab):
    TITLE = '嵌入文字水印'

    def __init__(self, master, app):
        super().__init__(master, app)
        self.src = tk.StringVar()
        self.out = tk.StringVar()
        self.pwd_img = tk.StringVar(value='123')
        self.pwd_wm = tk.StringVar(value='123')

        # —— 卡片1: 选图 ——
        c1 = Card(self)
        c1.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        c1.columnconfigure(0, weight=1)
        self.drop = DropZone(c1, '把【原图】拖到这里, 或点击选择',
                             on_pick=lambda: self.pick_src())
        self.drop.grid(row=0, column=0, sticky='ew', padx=14, pady=14)
        self.drop.bind('<Double-Button-1>', lambda e: None)

        # —— 卡片2: 参数 ——
        c2 = Card(self, title='要藏进去的文字')
        c2.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        c2.columnconfigure(1, weight=1)
        self.txt = tk.Text(c2, height=3, wrap='word', bd=1, relief='solid',
                           bg='#fbfcfe', fg=TXT, font=('Microsoft YaHei UI', 10),
                           highlightthickness=0)
        self.txt.grid(row=1, column=0, columnspan=3, sticky='ew', padx=14, pady=(0, 6))
        self.txt.insert('1.0', '版权所有 · 请勿外传')
        self.cap = tk.Label(c2, text='', bg=CARD, fg=SUB, font=('Microsoft YaHei UI', 8))
        self.cap.grid(row=2, column=0, columnspan=3, sticky='w', padx=14)
        self.txt.bind('<KeyRelease>', lambda e: self.update_cap())

        pwd_row(c2, 3, '密码 A(图片)', self.pwd_img, hint='嵌入与提取必须一致')
        pwd_row(c2, 4, '密码 B(水印)', self.pwd_wm, hint='嵌入与提取必须一致')

        path_row(c2, 5, '输出到', self.out, self.pick_out, self.open_out)
        self.update_cap()

        # —— 操作条 ——
        bar = tk.Frame(self, bg=BG)
        bar.grid(row=3, column=0, sticky='ew', pady=(2, 6))
        bar.columnconfigure(0, weight=1)
        self.go = ttk.Button(bar, text='开始嵌入文字水印', style='Go.TButton',
                             command=self.run)
        self.go.grid(row=0, column=0, sticky='e')
        ttk.Button(bar, text='清空', style='Ghost.TButton',
                   command=self.clear).grid(row=0, column=1, padx=(8, 0))
        self.spacer()

    # 「选图」与「换图」同一条逻辑
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
        self.app._set_status('已从拖拽载入原图, 填写文字后点「开始嵌入文字水印」', ACCENT)

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
        self.cap.configure(text='占用 %d bit / 该图最多可放约 %s bit  %s'
                                % (n, limit, '（超出会失败）' if limit != '?' and n >= limit else ''))

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
            self.app.log('✔ 已生成: %s  (%.2f MB)' % (out, os.path.getsize(out) / 1048576), 'ok')
            ok = write_sidecar(out, {
                'type': 'text', 'bwm_version': BWM_VER, 'wm_bit_len': n,
                'password_img': pi, 'password_wm': pw,
                'payload': text, 'created': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
            })
            self.app.log('✔ 提取信息已随手保存: %s' % (os.path.basename(sidecar_path(out)) if ok else '(失败, 请手动记录)'), 'ok')
            self.app.log('  提取时只需选中这张图, 会自动回填参数。')
            open_folder(out)
            return True, '✔ 文字水印嵌入完成'

        self.app.run_async('正在嵌入文字水印…', job)


# ---------------- ② 图片水印嵌入 ----------------
class ImageTab(BaseTab):
    TITLE = '嵌入图片水印'

    def __init__(self, master, app):
        super().__init__(master, app)
        self.src = tk.StringVar()
        self.wm = tk.StringVar()
        self.out = tk.StringVar()
        self.pwd_img = tk.StringVar(value='123')
        self.pwd_wm = tk.StringVar(value='123')

        c1 = Card(self)
        c1.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        c1.columnconfigure(0, weight=1)
        c1.columnconfigure(1, weight=1)
        self.drop = DropZone(c1, '拖入【原图】', on_pick=self.pick_src)
        self.drop.grid(row=0, column=0, sticky='nsew', padx=(14, 7), pady=14)
        self.drop_wm = DropZone(c1, '拖入【水印图】', on_pick=self.pick_wm)
        self.drop_wm.grid(row=0, column=1, sticky='nsew', padx=(7, 14), pady=14)
        tk.Label(c1, text='提示: 水印图建议用黑白稿, 尺寸不要超过原图容量的 1/8',
                 bg=CARD, fg=SUB, font=('Microsoft YaHei UI', 8)).grid(
            row=1, column=0, columnspan=2, sticky='w', padx=14, pady=(0, 10))

        c2 = Card(self, title='参数')
        c2.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        c2.columnconfigure(1, weight=1)
        pwd_row(c2, 0, '密码 A(图片)', self.pwd_img, hint='嵌入与提取必须一致')
        pwd_row(c2, 1, '密码 B(水印)', self.pwd_wm, hint='嵌入与提取必须一致')
        path_row(c2, 2, '输出到', self.out, self.pick_out, self.open_out)

        bar = tk.Frame(self, bg=BG)
        bar.grid(row=3, column=0, sticky='ew', pady=(2, 6))
        bar.columnconfigure(0, weight=1)
        self.go = ttk.Button(bar, text='开始嵌入图片水印', style='Go.TButton', command=self.run)
        self.go.grid(row=0, column=0, sticky='e')
        ttk.Button(bar, text='清空', style='Ghost.TButton',
                   command=self.clear).grid(row=0, column=1, padx=(8, 0))
        self.spacer()

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
        """两张图都还没选 → 当原图; 已选原图 → 当水印图"""
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
            self.app.log('[图片水印] 水印: %s (%dx%d = %d bit)' % (os.path.basename(wm), w, h, w * h))
            try:
                bwm.embed(out)
            except AssertionError:
                return False, '水印太大, 超过这张原图的容量, 请换小一点的水印图'
            self.app.log('✔ 已生成: %s  (%.2f MB)' % (out, os.path.getsize(out) / 1048576), 'ok')
            ok = write_sidecar(out, {
                'type': 'img', 'bwm_version': BWM_VER,
                'wm_shape': [h, w], 'password_img': pi, 'password_wm': pw,
                'created': __import__('datetime').datetime.now().isoformat(timespec='seconds'),
            })
            self.app.log('✔ 提取信息已随手保存: %s' % (os.path.basename(sidecar_path(out)) if ok else '(失败, 请手动记录)'), 'ok')
            open_folder(out)
            return True, '✔ 图片水印嵌入完成'

        self.app.run_async('正在嵌入图片水印…', job)


# ---------------- ③ 提取 ----------------
class ExtractTab(BaseTab):
    TITLE = '提取水印'

    def __init__(self, master, app):
        super().__init__(master, app)
        self.src = tk.StringVar()
        self.outdir = tk.StringVar(value=ensure_outdir())
        self.pwd_img = tk.StringVar(value='123')
        self.pwd_wm = tk.StringVar(value='123')
        self.mode = tk.StringVar(value='text')
        self.length = tk.StringVar(value='')
        self.shape = tk.StringVar(value='')

        c1 = Card(self)
        c1.grid(row=1, column=0, sticky='ew', pady=(0, 10))
        c1.columnconfigure(0, weight=1)
        self.drop = DropZone(c1, '把【带水印的图片】拖到这里(可多张, 只取第一张)',
                             on_pick=self.pick_src)
        self.drop.grid(row=0, column=0, sticky='ew', padx=14, pady=14)
        self.auto_lbl = tk.Label(
            c1, text='ⓘ 若图片旁有同名 .bwm.json 信息文件, 参数会自动填好, 直接点提取即可',
            bg=CARD, fg=SUB, font=('Microsoft YaHei UI', 8), anchor='w')
        self.auto_lbl.grid(row=1, column=0, sticky='w', padx=14, pady=(0, 12))

        c2 = Card(self, title='水印类型')
        c2.grid(row=2, column=0, sticky='ew', pady=(0, 10))
        rb = tk.Frame(c2, bg=CARD)
        rb.grid(row=1, column=0, columnspan=3, sticky='w', padx=14, pady=(0, 4))
        for txt, val, sub in (
                ('文字水印(推荐, 更抗攻击)', 'text', '取出隐藏的文字'),
                ('图片水印', 'img', '还原出那张黑白水印图')):
            f = tk.Frame(rb, bg=CARD)
            f.pack(side='left', padx=(0, 22))
            tk.Radiobutton(f, text=txt, value=val, variable=self.mode, bg=CARD, fg=TXT,
                           activebackground=CARD, selectcolor=CARD, bd=0,
                           font=('Microsoft YaHei UI', 9, 'bold'),
                           command=self.sync_mode).pack(anchor='w')
            tk.Label(f, text=sub, bg=CARD, fg=SUB,
                     font=('Microsoft YaHei UI', 8)).pack(anchor='w', padx=22)

        c2.columnconfigure(1, weight=1)
        self.row_len = tk.Frame(c2, bg=CARD)
        self.row_len.grid(row=2, column=0, columnspan=3, sticky='w')
        tk.Label(self.row_len, text='水印长度(bit)', bg=CARD, fg=SUB,
                 font=('Microsoft YaHei UI', 9)).pack(side='left', padx=(14, 6))
        tk.Entry(self.row_len, textvariable=self.length, width=10, bg='#fbfcfe', bd=1,
                 relief='solid', font=('Microsoft YaHei UI', 9)).pack(side='left')
        tk.Label(self.row_len, text='← 嵌入时日志里会给出, 或看同名 .bwm.json', bg=CARD,
                 fg=SUB, font=('Microsoft YaHei UI', 8)).pack(side='left', padx=6)

        self.row_shape = tk.Frame(c2, bg=CARD)
        self.row_shape.grid(row=3, column=0, columnspan=3, sticky='w')
        tk.Label(self.row_shape, text='水印图尺寸(宽x高)', bg=CARD, fg=SUB,
                 font=('Microsoft YaHei UI', 9)).pack(side='left', padx=(14, 6))
        tk.Entry(self.row_shape, textvariable=self.shape, width=12, bg='#fbfcfe', bd=1,
                 relief='solid', font=('Microsoft YaHei UI', 9)).pack(side='left')
        tk.Label(self.row_shape, text='例 100x100', bg=CARD, fg=SUB,
                 font=('Microsoft YaHei UI', 8)).pack(side='left', padx=6)

        pwd_row(c2, 4, '密码 A(图片)', self.pwd_img)
        pwd_row(c2, 5, '密码 B(水印)', self.pwd_wm)
        path_row(c2, 6, '结果存到', self.outdir, self.pick_outdir, self.open_out)
        self.sync_mode()

        bar = tk.Frame(self, bg=BG)
        bar.grid(row=3, column=0, sticky='ew', pady=(2, 6))
        bar.columnconfigure(0, weight=1)
        self.go = ttk.Button(bar, text='开始提取水印', style='Go.TButton', command=self.run)
        self.go.grid(row=0, column=0, sticky='e')
        ttk.Button(bar, text='清空', style='Ghost.TButton',
                   command=self.clear).grid(row=0, column=1, padx=(8, 0))
        self.spacer()

    def sync_mode(self):
        if self.mode.get() == 'text':
            self.row_len.grid()
            self.row_shape.grid_remove()
            if getattr(self, 'go', None) is not None:
                self.go.configure(text='开始提取文字水印')
        else:
            self.row_shape.grid()
            self.row_len.grid_remove()
            if getattr(self, 'go', None) is not None:
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
            self.pwd_img.set(str(sc.get('password_img', self.pwd_img.get())))
            self.pwd_wm.set(str(sc.get('password_wm', self.pwd_wm.get())))
            if sc.get('type') == 'img':
                self.mode.set('img')
                h, w = sc.get('wm_shape', [0, 0])
                self.shape.set('%dx%d' % (w, h))
            else:
                self.mode.set('text')
                self.length.set(str(sc.get('wm_bit_len', '')))
            self.sync_mode()
            self.auto_lbl.configure(
                text='✔ 已读取同名信息文件, 密码/长度自动填好, 直接点提取', fg=OKC)
            self.app.log('发现提取信息文件, 已自动回填参数: %s' % os.path.basename(sidecar_path(path)), 'ok')
        else:
            self.auto_lbl.configure(
                text='ⓘ 未找到同名 .bwm.json, 请手动填写水印长度与密码', fg=SUB)
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
        self.auto_lbl.configure(text='ⓘ 若图片旁有同名 .bwm.json 信息文件, 参数会自动填好, 直接点提取即可', fg=SUB)

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
                    self.app.log('✘ 提取失败: 密码或水印长度不对(水印存在, 只是解不开)', 'err')
                    return False, '✘ 密码 / 水印长度不对'
                self.app.log('✔ 提取成功, 隐藏的文字是:', 'ok')
                self.app.log('   %s' % txt, 'ok')
                p = os.path.join(outdir, '%s_水印内容.txt' % src_stem)
                try:
                    ensure = os.makedirs(outdir, exist_ok=True)
                    with open(p, 'w', encoding='utf-8') as f:
                        f.write(txt)
                    self.app.log('   已另存为 %s' % p, 'ok')
                    open_folder(p)
                except OSError as e:
                    self.app.log('   (结果文件写入失败: %s)' % e, 'err')
                return True, '✔ 文字水印提取成功'
            else:
                p = os.path.join(outdir, '%s_提取出的水印.png' % src_stem)
                bwm.extract(filename=src, wm_shape=(sh, sw), out_wm_name=p)
                self.app.log('✔ 图片水印已还原: %s' % p, 'ok')
                open_folder(p)
                return True, '✔ 图片水印提取完成'

        self.app.run_async('正在提取水印…', job)


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
            out.append('MISMATCH!')

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

        out.append('default_out(%r) -> %s' % ('D:/x/照片.jpg', default_out('D:/x/照片.jpg', '_文字水印')))
        d = parse_drop('{C:/a b/图 1.png} {D:/x.png}')
        out.append('parse_drop -> %r' % d)
        if d != ['C:/a b/图 1.png', 'D:/x.png']:
            ok = False
        # Tk 能否构建 + tkdnd 是否真的注册成功(打包后必须验证)
        try:
            r = DND_TK()
            r.withdraw()
            r.update()
            ver = ''
            if DND_OK:
                try:
                    ver = str(r.tk.call('package', 'require', 'tkdnd'))
                    # 真正做一次注册/反注册, 注册失败会抛 TclError
                    r.drop_target_register(DND_FILES)
                    r.drag_source_register(1, DND_FILES)
                    listed = r.tk.call('tkdnd::drop_target', 'register', r._w, ())
                    out.append('tkdnd drop_target ok (%s)' % (listed or 'registered'))
                except Exception as e:
                    ok = False
                    out.append('tkdnd 注册失败: %s' % e)
            out.append('tk_root=OK tkdnd_version=%s' % (ver or 'n/a'))
            r.destroy()
        except Exception as e:
            ok = False
            out.append('tk_root=FAIL %s' % e)

        # 真实 App 的拖拽接线是否生效(不进入 mainloop)
        try:
            a = App()
            a.update_idletasks()
            a.update()
            info = a.dnd_self_check()
            out.append('app_dnd %s' % info)
            if not info.startswith('targets=1') or 'on_drop' not in info:
                ok = False
            a.destroy()
        except Exception as e:
            ok = False
            out.append('app_dnd FAIL %s' % e)
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

    # 演示/截图模式: --preview [秒数] [标签页序号]  打开界面并在 N 秒后自动关闭
    if '--preview' in sys.argv:
        try:
            i = sys.argv.index('--preview')
            secs = int(sys.argv[i + 1])
        except Exception:
            secs = 12
        app = App()
        try:
            tab_idx = int(sys.argv[i + 2])
            app.nb.select(tab_idx)
        except Exception:
            pass
        # 可选: --preview <秒> <标签页> [宽x高] [x,y]  方便演示/截图, 例如 --preview 10 0 880x730,800,120
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
