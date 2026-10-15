"""面板独立性与模式切换校验

用法: 在仓库根目录执行  python scripts/independence_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bwm_gui as G

app = G.App()
app.update()
print("=== 按钮独立性与模式切换检查 ===")
print("①文字页按钮:", app.tab_text.go.cget('text'), "| ②图片页按钮:", app.tab_img.go.cget('text'))

app.tab_text.src.set('A')
app.tab_img.src.set('B')
app.tab_text.txt.delete('1.0', 'end')
print("两页状态互不干扰: 文字页src=%s 图片页src=%s"
      % (app.tab_text.src.get(), app.tab_img.src.get()))

# 用 grid_info 判断行是否显示(winfo_ismapped 在未选中页恒为 0)
rows = lambda: ('长度行:' + ('显示' if app.tab_ext.row_len.grid_info() else '隐藏'),
                '尺寸行:' + ('显示' if app.tab_ext.row_shape.grid_info() else '隐藏'))

app.nb.select(2)
app.update()
app.tab_ext.mode.set('text')
app.tab_ext.sync_mode()
app.update()
print("提取页 文字模式: 按钮=%s %s" % (app.tab_ext.go.cget('text'), rows()))
app.tab_ext.mode.set('img')
app.tab_ext.sync_mode()
app.update()
print("提取页 图片模式: 按钮=%s %s" % (app.tab_ext.go.cget('text'), rows()))

print("拖拽接收方随标签页切换:", end='  ')
for i, name in enumerate(('文字页', '图片页', '提取页')):
    app.nb.select(i)
    app.update()
    print("%s->%s" % (name, app.active_drop.__self__.__class__.__name__), end='  ')
print()
print("输出目录探测:", G.pick_out_dir())

# 断言便于 CI 判断
ok = (app.tab_text.go.cget('text') != app.tab_img.go.cget('text')
      and app.tab_text.src.get() == 'A' and app.tab_img.src.get() == 'B')
app.destroy()
print("INDEPENDENCE=%s" % ("PASS" if ok else "FAIL"))
sys.exit(0 if ok else 1)
