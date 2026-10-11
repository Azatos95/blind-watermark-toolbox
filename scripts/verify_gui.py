# -*- coding: utf-8 -*-
"""无头验证:导入 bwm_gui(即打包入口)后,核心功能是否正常 + 真实文件用正确尺寸能否提取"""
import os, sys, shutil, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import cv2
import numpy as np
import bwm_gui  # 导入即触发 cv2 Unicode 补丁 + blind_watermark 初始化

print('[A] bwm_gui 模块导入成功; cv2.imread 已被替换 ->', cv2.imread.__name__)
print('[B] 无头环境下创建 Tk 根窗口:', end=' ')
import tkinter as tk
try:
    root = tk.Tk(); root.withdraw(); print('OK (有显示环境)'); root.destroy()
except Exception as e:
    print('SKIP (%s)' % e)

WORK = os.path.join(HERE, 'ascii_test')
os.makedirs(WORK, exist_ok=True)
# 带中文的目录也能读写了(补丁生效)
CN = os.path.join(HERE, '中文目录测试')
os.makedirs(CN, exist_ok=True)

SRC = r'C:\Users\A\Desktop\图片盲水印\盲水印嵌入\pic'
shutil.copyfile(os.path.join(SRC, 'ori_img.jpg'), os.path.join(WORK, 'ori_img.jpg'))
shutil.copyfile(os.path.join(SRC, 'watermark.png'), os.path.join(WORK, 'watermark.png'))

from blind_watermark import WaterMark

print('\n[C] 图片水印 100x100 走 Unicode 路径 嵌入+提取')
bwm = WaterMark(password_wm=1, password_img=1)
bwm.read_img(os.path.join(WORK, 'ori_img.jpg'))
bwm.read_wm(os.path.join(WORK, 'watermark.png'), mode='img')
emb_cn = os.path.join(CN, '嵌入结果.png')
bwm.embed(emb_cn)
print('    输出:', emb_cn, os.path.getsize(emb_cn), 'bytes')

bwm2 = WaterMark(password_wm=1, password_img=1)
ext_cn = os.path.join(CN, '提取结果.png')
bwm2.extract(filename=emb_cn, wm_shape=(100, 100), out_wm_name=ext_cn)
ex = cv2.imread(ext_cn, cv2.IMREAD_GRAYSCALE)
ori_wm = cv2.imread(os.path.join(WORK, 'watermark.png'), cv2.IMREAD_GRAYSCALE)
print('    提取图:', ext_cn, ex.shape)
print('    与原水印灰度相关性 = %.4f' % np.corrcoef((ex > 128).flatten().astype(float),
                                                    (ori_wm > 128).flatten().astype(float))[0, 1])

print('\n[D] 用用户桌面【已生成的】embedded.png 直接提取 (wm_shape=100x100)')
try:
    b3 = WaterMark(password_wm=1, password_img=1)
    out3 = os.path.join(WORK, 'from_desktop.png')
    b3.extract(filename=r'C:\Users\A\Desktop\图片盲水印\盲水印嵌入\output\embedded.png',
               wm_shape=(100, 100), out_wm_name=out3)
    e3 = cv2.imread(out3, cv2.IMREAD_GRAYSCALE)
    print('    OK, 与原水印相关性 = %.4f' % np.corrcoef((e3 > 128).flatten().astype(float),
                                                     (ori_wm > 128).flatten().astype(float))[0, 1])
except Exception:
    traceback.print_exc()

print('\n[E] 文字水印 嵌入->提取 往返')
b4 = WaterMark(password_wm=42, password_img=42)
b4.read_img(os.path.join(WORK, 'ori_img.jpg'))
b4.read_wm('机密-2026-测试', mode='str')
emb4 = os.path.join(CN, '文字水印.png')
b4.embed(emb4)
n = len(b4.wm_bit)
b5 = WaterMark(password_wm=42, password_img=42)
print('    提取:', repr(b5.extract(filename=emb4, wm_shape=n, mode='str')))

print('\nALL GUI/UNICODE CHECKS DONE')
