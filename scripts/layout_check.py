"""响应式布局校验: 多种窗口尺寸 × 三个标签页, 检查内容是否被裁切

用法: 在仓库根目录执行  python scripts/layout_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bwm_gui as G

app = G.App()


def geo(w, h):
    app.geometry("%dx%d" % (w, h))
    app.update_idletasks()
    app.update()
    ok_all = True
    for i, tab in enumerate((app.tab_text, app.tab_img, app.tab_ext)):
        app.nb.select(i)
        app.update_idletasks()
        app.update()
        # 计算该页内容底部(相对标签页)
        bottom = 0
        for ch in tab.winfo_children():
            bottom = max(bottom, ch.winfo_y() + ch.winfo_height())
        fits = bottom <= tab.winfo_height()
        ok_all = ok_all and fits
        print("  %dx%d tab%d: 内容高=%d 可视高=%d %s"
              % (w, h, i + 1, bottom, tab.winfo_height(), "OK" if fits else "被裁切!"))
    return ok_all


print("=== 响应式检查 ===")
allok = True
for w, h in ((900, 720), (720, 600), (1100, 820), (1280, 900), (760, 620)):
    allok = geo(w, h) and allok
print("ALL_FIT=%s" % allok)
app.destroy()
sys.exit(0 if allok else 1)
