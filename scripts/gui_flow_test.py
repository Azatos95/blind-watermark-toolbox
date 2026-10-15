# -*- coding: utf-8 -*-
"""v0.3 端到端: 模拟用户操作 + 历史密码记忆/自动填入 + 主题/警戒线 验证(真实 mainloop)

用法: 在仓库根目录执行  python scripts\\gui_flow_test.py
需要源图: 默认用 C:\\Users\\A\\Desktop\\图片盲水印\\盲水印嵌入\\pic\\ori_img.jpg,
        也可用环境变量 BWM_TEST_IMG 指定任意图片。
"""
import os
import sys
import time
from tkinter import messagebox

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import bwm_gui as G
from bwm_theme import History

messagebox.showerror = lambda *a, **k: print('  [错误对话框]', a[1:2], flush=True)
messagebox.showinfo = lambda *a, **k: print('  [提示对话框]', a[1:2], flush=True)

SRC = os.environ.get(
    'BWM_TEST_IMG',
    r'C:\Users\A\Desktop\图片盲水印\盲水印嵌入\pic\ori_img.jpg')
TESTDIR = os.path.join(REPO, 'flow_out')
os.makedirs(TESTDIR, exist_ok=True)

if not os.path.isfile(SRC):
    print('缺少测试原图: %s\n可用环境变量 BWM_TEST_IMG 指定图片路径。' % SRC)
    sys.exit(2)

# 用独立的历史文件, 不污染真实配置
HIST = os.path.join(TESTDIR, 'history_test.json')
if os.path.isfile(HIST):
    os.remove(HIST)
History.FILE = HIST
G.HISTORY = History()

G.OUT_DIR = TESTDIR
G.ensure_outdir = lambda: (os.makedirs(TESTDIR, exist_ok=True) or TESTDIR)
G.default_out = lambda src, suffix, force_lossless=True: os.path.join(
    TESTDIR, (os.path.splitext(os.path.basename(src))[0] if src else '结果') + suffix + '.png')
G.open_folder = lambda p: True

app = G.App()
res = {}


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def wait_idle(a, limit=240):
    end = time.time() + limit
    while a.busy and time.time() < end:
        a.update()
        time.sleep(0.05)
    pump(0.5)


def s4_style():
    print('--- 主题与样式 ---', flush=True)
    a = G.App()
    a.update()
    checks = {
        '主背景 #121416': G.BG == '#121416',
        '次级面板 #1A1D20': G.PANEL == '#1A1D20',
        '细框线 #303438': G.LINE == '#303438',
        '强调色 #D6B046': G.ACCENT == '#D6B046',
        '警戒线正常灰绿 #7E9B84': G.OK_GREEN == '#7E9B84',
        '警戒线出错红 #C0453F': G.ERR_RED == '#C0453F',
        '字体为思源黑体': ('Noto Sans SC' in a.F['bold']) or ('Source Han Sans' in a.F['bold']),
    }
    for k, v in checks.items():
        print('   [%s] %s' % ('OK' if v else 'MISS', k), flush=True)
    res['style_ok'] = all(checks.values())
    a.destroy()


def s3_state_bar():
    print('--- 警戒线状态栏 ---', flush=True)
    a = G.App()
    a.update()
    a.set_state('ok')
    ok_ok = (a._state_color == G.OK_GREEN)
    a.set_state('err')
    ok_err = (a._state_color == G.ERR_RED)
    a.set_state('busy')
    ok_busy = (a._state_color == G.ACCENT)
    print('   正常=灰绿 %s | 出错=红 %s | 处理中=强调 %s -> %s'
          % (ok_ok, ok_err, ok_busy, 'OK' if (ok_ok and ok_err and ok_busy) else 'FAIL'), flush=True)
    res['state_ok'] = ok_ok and ok_err and ok_busy
    a.destroy()


def s1_embed_text():
    print('--- ① 嵌入文字水印(故意用新密码 5566/7788) ---', flush=True)
    app.nb.select(0)
    app.update()
    app.tab_text.on_drop(SRC)
    pump(0.3)
    app.tab_text.pwd_img.set('5566')
    app.tab_text.pwd_wm.set('7788')
    app.tab_text.txt.delete('1.0', 'end')
    app.tab_text.txt.insert('1.0', 'v0.3历史密码测试')
    res['out1'] = app.tab_text.out.get()
    app.tab_text.run()
    wait_idle(app)
    print('   输出存在 = %s' % os.path.isfile(res['out1']), flush=True)
    print('   历史文件已写入 = %s' % os.path.isfile(HIST), flush=True)
    print('   记住的密码对 = %s' % str(G.HISTORY.data['pairs']), flush=True)
    print('   记住的图片密码 = %s' % str(G.HISTORY.top_images()), flush=True)


def s2_extract_autofill():
    print('--- ③ 重开软件(模拟第二天)+ 提取 ---', flush=True)
    a = G.App()
    a.update()
    print('   提取页自动填入: A=%s B=%s' % (a.tab_ext.pwd_img.get(), a.tab_ext.pwd_wm.get()), flush=True)
    res['autofill_ok'] = (a.tab_ext.pwd_img.get() == '5566' and a.tab_ext.pwd_wm.get() == '7788')
    tags = [w.winfo_children()[0].cget('text') for w in a.tab_ext.hist_box.winfo_children()
            if w.winfo_class() == 'Frame' and w.winfo_children()]
    print('   提取页历史标签 = %s' % str(tags), flush=True)
    res['tags_ok'] = any('5566 / 7788' in t for t in tags)
    a.nb.select(2)
    a.update()
    a.tab_ext.on_drop(res['out1'])
    pump(0.4)
    print('   拖入成品后: 长度=%s 密码=(%s,%s)'
          % (a.tab_ext.length.get(), a.tab_ext.pwd_img.get(), a.tab_ext.pwd_wm.get()), flush=True)
    a.tab_ext.run()
    wait_idle(a)
    p = os.path.join(a.tab_ext.outdir.get(),
                     os.path.splitext(os.path.basename(res['out1']))[0] + '_水印内容.txt')
    print('   提取结果文件存在 = %s' % os.path.isfile(p), flush=True)
    if os.path.isfile(p):
        txt = open(p, encoding='utf-8').read()
        print('   取回文字 = %r' % txt, flush=True)
        res['text_roundtrip'] = (txt == 'v0.3历史密码测试')
    a.destroy()


def runner():
    try:
        s4_style()
        s3_state_bar()
        s1_embed_text()
        s2_extract_autofill()
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        ok = (res.get('style_ok') and res.get('state_ok') and res.get('autofill_ok')
              and res.get('tags_ok') and res.get('text_roundtrip'))
        print('FLOW_TEST=%s' % ('PASS' if ok else 'FAIL'), flush=True)
        app.after(200, app.quit)


app.after(300, runner)
app.mainloop()
app.destroy()
