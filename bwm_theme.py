# -*- coding: utf-8 -*-
"""历史密码存储 / 字体检测(供 bwm_gui 使用)"""
import json
import os


# ---------------- 配置与历史记录 ----------------
def appdata_dir():
    """可写的配置目录(优先 %APPDATA%, 回退到用户目录)"""
    for cand in (os.path.join(os.environ.get('APPDATA') or '', '盲水印工具箱')
                 if os.environ.get('APPDATA') else None,
                 os.path.join(os.path.expanduser('~'), '.盲水印工具箱')):
        if not cand:
            continue
        try:
            os.makedirs(cand, exist_ok=True)
            probe = os.path.join(cand, '.w')
            with open(probe, 'w'):
                pass
            os.remove(probe)
            return cand
        except OSError:
            continue
    return os.getcwd()


class History:
    """记住用过的密码, 提取时自动填入。

    只保存"密码对"和次数, 不保存任何图片内容或水印明文。
    """

    FILE = os.path.join(appdata_dir(), 'history.json')
    MAX_KEEP = 12

    def __init__(self):
        self.data = {'image': {}, 'wm': {}, 'pairs': [], 'recent_output_dirs': []}
        self.load()

    # ---- 读写 ----
    def load(self):
        """读历史。用 utf-8-sig: 用户手动编辑/系统工具写入时可能带 BOM,
        带 BOM 的 JSON 用 utf-8 解码会抛异常, 会导致整份历史被静默丢弃。"""
        try:
            with open(self.FILE, encoding='utf-8-sig') as f:
                d = json.load(f)
            if isinstance(d, dict):
                for k in self.data:
                    if k in d and isinstance(d[k], type(self.data[k])):
                        self.data[k] = d[k]
            return True
        except Exception:
            return False

    def save(self):
        try:
            os.makedirs(os.path.dirname(self.FILE), exist_ok=True)
            with open(self.FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except OSError:
            return False

    # ---- 记录 ----
    @staticmethod
    def _bump(bucket, value):
        if value is None or value == '':
            return
        key = str(value)
        bucket[key] = int(bucket.get(key, 0)) + 1
        while len(bucket) > History.MAX_KEEP:
            bucket.pop(min(bucket, key=lambda k: bucket[k]), None)

    def remember(self, pwd_img, pwd_wm, out_dir=None):
        """记一次成功的密码组合(按使用次数排序)"""
        pi, pw = str(pwd_img), str(pwd_wm)
        self._bump(self.data['image'], pi)
        self._bump(self.data['wm'], pw)
        pairs = [p for p in self.data['pairs'] if not (p[0] == pi and p[1] == pw)]
        pairs.insert(0, [pi, pw])
        self.data['pairs'] = pairs[:self.MAX_KEEP]
        if out_dir:
            dirs = [d for d in self.data['recent_output_dirs'] if d != out_dir]
            dirs.insert(0, out_dir)
            self.data['recent_output_dirs'] = dirs[:5]
        self.save()

    # ---- 查询 ----
    def last_pair(self):
        return self.data['pairs'][0] if self.data['pairs'] else None

    def top_images(self, limit=6):
        return sorted(self.data['image'], key=lambda k: (-self.data['image'][k], k))[:limit]

    def top_wms(self, limit=6):
        return sorted(self.data['wm'], key=lambda k: (-self.data['wm'][k], k))[:limit]

    def last_output_dir(self):
        d = self.data.get('recent_output_dirs') or []
        return d[0] if d else None


# ---------------- 字体 ----------------
FONT_CANDIDATES_BOLD = [
    'Source Han Sans SC Bold', 'Noto Sans SC Bold', 'Source Han Sans CN Bold',
    '思源黑体 Bold', 'Source Han Sans SC', 'Noto Sans SC',
]
FONT_CANDIDATES_MEDIUM = [
    'Source Han Sans SC Medium', 'Noto Sans SC Medium', 'Source Han Sans CN Medium',
    '思源黑体 Medium', 'Source Han Sans SC', 'Noto Sans SC',
]
FONT_CANDIDATES_REGULAR = [
    'Source Han Sans SC', 'Noto Sans SC', 'Source Han Sans CN', '思源黑体',
]
FONT_FALLBACK = ['Microsoft YaHei UI', 'Microsoft YaHei', 'Segoe UI', 'TkDefaultFont']

MONO_CANDIDATES = ['Cascadia Mono', 'Consolas', 'Sarasa Mono SC', 'DejaVu Sans Mono']


# ---------------- 高 DPI 支持 ----------------
DPI_AWARENESS_DONE = False
SCALE = 1.0


def enable_dpi_awareness():
    """让进程按真实物理像素渲染。

    必须在 import tkinter 之前调用。若进程未声明 DPI 感知, Windows 会把整个
    窗口按系统缩放比例(如 150%)先放大再光栅化 —— 字体笔画被拉伸, 明显发虚。
    声明 Per-Monitor V2 之后文字按真实像素渲染, 清晰度显著提升。
    """
    global DPI_AWARENESS_DONE
    if os.name != 'nt' or DPI_AWARENESS_DONE:
        return False
    ok = False
    try:
        import ctypes
        # 1) Windows 10 1703+: Per-Monitor V2 (值 = -4)
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
            ok = True
        except Exception:
            pass
        # 2) Windows 8.1+: Per-Monitor
        if not ok:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
                ok = True
            except Exception:
                pass
        # 3) Vista+: 系统级
        if not ok:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                ok = True
            except Exception:
                pass
    except Exception:
        ok = False
    DPI_AWARENESS_DONE = ok
    return ok


def system_dpi():
    """取主显示器的真实 DPI(96 = 100%, 120 = 125%, 144 = 150%)"""
    if os.name != 'nt':
        return 96
    try:
        import ctypes
        dc = ctypes.windll.user32.GetDC(0)
        dpi = ctypes.windll.gdi32.GetDeviceCaps(dc, 88)   # LOGPIXELSX
        ctypes.windll.user32.ReleaseDC(0, dc)
        return int(dpi) or 96
    except Exception:
        return 96


def compute_scale():
    """UI 缩放系数: 相对 96 DPI。同时接受环境变量覆盖, 便于调试。"""
    global SCALE
    env = os.environ.get('BWM_UI_SCALE')
    if env:
        try:
            SCALE = max(1.0, min(3.0, float(env)))
            return SCALE
        except ValueError:
            pass
    SCALE = max(1.0, min(3.0, system_dpi() / 96.0))
    return SCALE


def sp(n):
    """按缩放系数换算尺寸(至少 1px), 用于窗口/间距"""
    return max(1, int(round(n * SCALE)))


def detect_font_weights(root, families):
    """探测某个字族实际可用的字重, 返回 {'bold':bool,'medium':bool}

    Noto Sans SC 之类的可变字体在 Tk 里 family 名可能带字重后缀,
    所以既检查独立字重族(如 'Noto Sans SC Medium'), 也检查同一族的 bold 变体。
    """
    res = {'bold': False, 'medium': False}
    try:
        import tkinter.font as tkfont
        avail = set(families)
        # 同族 bold 变体是否可用
        for fam in (families or []):
            if fam in avail:
                try:
                    f = tkfont.Font(root=root, family=fam, size=10, weight='bold')
                    if f.actual('weight') == 'bold':
                        res['bold'] = True
                except Exception:
                    pass
                break
        for fam in avail:
            if 'Medium' in fam or 'DemiLight' in fam or 'SemiBold' in fam:
                res['medium'] = True
                break
    except Exception:
        pass
    return res



def pick_font(root, candidates):
    """在候选列表里挑第一个本机可用的字体族"""
    try:
        import tkinter.font as tkfont
        available = set(tkfont.families(root))
    except Exception:
        available = set()
    for name in list(candidates) + FONT_FALLBACK:
        if name in available:
            return name
    return 'TkDefaultFont'


def detected_fonts(root):
    return {
        'bold': pick_font(root, FONT_CANDIDATES_BOLD),
        'medium': pick_font(root, FONT_CANDIDATES_MEDIUM),
        'regular': pick_font(root, FONT_CANDIDATES_REGULAR),
        'mono': pick_font(root, MONO_CANDIDATES),
    }
