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
