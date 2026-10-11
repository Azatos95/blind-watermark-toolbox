# -*- coding: utf-8 -*-
"""模拟用户点击链路: 拖入图片 -> 点嵌入 -> 点提取 (用真实 mainloop, 和实际运行一致)"""
import os
import time
from tkinter import messagebox

import bwm_gui as G

# 沙箱只允许写工作区/临时目录, 测试时把默认输出目录指到工作区(真实使用仍是桌面)
TESTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flow_out')
os.makedirs(TESTDIR, exist_ok=True)
G.OUT_DIR = TESTDIR
G.ensure_outdir = lambda: (os.makedirs(TESTDIR, exist_ok=True) or TESTDIR)
G.default_out = lambda src, suffix, force_lossless=True: os.path.join(
    TESTDIR, (os.path.splitext(os.path.basename(src))[0] if src else '结果') + suffix + '.png')
G.open_folder = lambda p: True

messagebox.showerror = lambda *a, **k: print('  [错误对话框]', a[1:2], flush=True)
messagebox.showinfo = lambda *a, **k: print('  [提示对话框]', a[1:2], flush=True)

SRC = r'C:\Users\A\Desktop\图片盲水印\盲水印嵌入\pic\ori_img.jpg'
WM = r'C:\Users\A\Desktop\图片盲水印\盲水印嵌入\pic\watermark.png'

app = G.App()
results = {}


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def wait_idle(limit=240):
    end = time.time() + limit
    while app.busy and time.time() < end:
        app.update()
        time.sleep(0.05)
    pump(0.5)
    return not app.busy


def s1_text_embed():
    app.nb.select(0)
    app.update()
    app.tab_text.on_drop(SRC)
    pump(0.3)
    results['out_text'] = app.tab_text.out.get()
    print('① 拖入原图 -> 自动输出路径: %s' % results['out_text'], flush=True)
    app.tab_text.txt.delete('1.0', 'end')
    app.tab_text.txt.insert('1.0', 'GUI点击链路测试')
    app.tab_text.run()
    ok = wait_idle()
    results['text_ok'] = os.path.isfile(results['out_text']) and ok and not app.busy
    print('① 点击嵌入 -> busy=%s 文件存在=%s' % (app.busy, os.path.isfile(results['out_text'])), flush=True)
    sc = G.read_sidecar(results['out_text'])
    print('   侧车文件: %s %s' % (os.path.basename(G.sidecar_path(results['out_text'])),
                                  sc and (sc['type'], sc['wm_bit_len'])), flush=True)


def s2_text_extract():
    app.nb.select(2)
    app.update()
    app.tab_ext.on_drop(results['out_text'])
    pump(0.3)
    print('③ 拖入成品 -> 自动回填: 类型=%s 长度=%s 密码=(%s,%s)' % (
        app.tab_ext.mode.get(), app.tab_ext.length.get(),
        app.tab_ext.pwd_img.get(), app.tab_ext.pwd_wm.get()), flush=True)
    app.tab_ext.run()
    wait_idle()
    p = os.path.join(app.tab_ext.outdir.get(),
                     os.path.splitext(os.path.basename(results['out_text']))[0] + '_水印内容.txt')
    results['txt'] = p
    print('③ 点击提取 -> 结果文件存在=%s' % os.path.isfile(p), flush=True)
    if os.path.isfile(p):
        print('   拿到文字 = %r' % open(p, encoding='utf-8').read(), flush=True)


def s3_img_embed():
    app.nb.select(1)
    app.update()
    app.tab_img.on_drop(SRC)
    pump(0.25)
    app.tab_img.on_drop(WM)
    pump(0.25)
    results['out_img'] = app.tab_img.out.get()
    print('② 先拖原图再拖水印图: 原图=%s 水印=%s' % (
        os.path.basename(app.tab_img.src.get()), os.path.basename(app.tab_img.wm.get())), flush=True)
    print('   自动输出路径: %s' % results['out_img'], flush=True)
    app.tab_img.run()
    wait_idle()
    results['img_ok'] = os.path.isfile(results['out_img']) and not app.busy
    print('② 点击嵌入 -> busy=%s 文件存在=%s' % (app.busy, os.path.isfile(results['out_img'])), flush=True)
    sc = G.read_sidecar(results['out_img'])
    print('   侧车: %s' % str(sc and (sc['type'], sc['wm_shape'])), flush=True)


def s4_img_extract():
    app.nb.select(2)
    app.update()
    app.tab_ext.on_drop(results['out_img'])
    pump(0.3)
    print('③ 拖入成品 -> 类型=%s 尺寸=%s' % (app.tab_ext.mode.get(), app.tab_ext.shape.get()), flush=True)
    app.tab_ext.run()
    wait_idle()
    p = os.path.join(app.tab_ext.outdir.get(),
                     os.path.splitext(os.path.basename(results['out_img']))[0] + '_提取出的水印.png')
    print('③ 点击提取 -> 还原图存在=%s' % os.path.isfile(p), flush=True)
    if os.path.isfile(p):
        import cv2
        import numpy as np
        a = G.imread_unicode(p, cv2.IMREAD_GRAYSCALE)
        b = G.imread_unicode(WM, cv2.IMREAD_GRAYSCALE)
        corr = np.corrcoef((a > 128).flatten().astype(float), (b > 128).flatten().astype(float))[0, 1]
        results['corr'] = corr
        print('   与原水印相关性 = %.4f' % corr, flush=True)


def runner():
    try:
        for fn in (s1_text_embed, s2_text_extract, s3_img_embed, s4_img_extract):
            fn()
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        ok = (results.get('text_ok') and os.path.isfile(results.get('txt', ''))
              and results.get('img_ok') and results.get('corr', 0) > 0.9)
        print('FLOW_TEST=%s' % ('PASS' if ok else 'FAIL'), flush=True)
        app.after(200, app.quit)


app.after(300, runner)
app.mainloop()
app.destroy()
