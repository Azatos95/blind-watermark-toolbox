import sys, tkinter as tk, bwm_gui as G
app = G.App()
def geo(w,h):
    app.geometry("%dx%d" % (w,h)); app.update_idletasks(); app.update()
    nb_h = app.nb.winfo_height()
    ok_all = True
    for i,tab in enumerate((app.tab_text, app.tab_img, app.tab_ext)):
        app.nb.select(i); app.update_idletasks(); app.update()
        # 计算该页内容底部(相对标签页)
        bottom = 0
        for ch in tab.winfo_children():
            bottom = max(bottom, ch.winfo_y() + ch.winfo_height())
        fits = bottom <= tab.winfo_height()
        ok_all = ok_all and fits
        print("  %dx%d tab%d: 内容高=%d 可视高=%d %s" % (w,h,i+1,bottom,tab.winfo_height(),"OK" if fits else "被裁切!"))
    return ok_all
print("=== 响应式检查 ===")
allok = True
for w,h in ((900,720),(720,600),(1100,820),(1280,900),(760,620)):
    allok = geo(w,h) and allok
print("ALL_FIT=%s" % allok)
app.destroy()
