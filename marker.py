from canvaswindow import CanvasWindow
import tkinter as tk

maskalpha = 120
win = CanvasWindow(
    caption="圖片資訊標記助手",
    icon="postage_stamp.ico",
    maskalpha=maskalpha
)

lbl_hint = tk.Label(win, bg="white", font=("微軟正黑體",16,"bold"))
lbl_hint.pack(anchor="s", fill="x", expand=False)
win.set_listener(lbl_hint)

def scroll(event):
    global maskalpha
    if event.num == 5 or event.delta == -120:
        maskalpha -= 20
        if maskalpha < 0: maskalpha = 0
    if event.num == 4 or event.delta == 120:
        maskalpha += 20
        if maskalpha > 200: maskalpha = 200
    win.mask(maskalpha)
win.container.bind("<MouseWheel>", scroll)
win.canvas.bind("<MouseWheel>", scroll)

win.bind("<Left>",lambda ev: win.use_mark(-1))
win.bind("<Right>",lambda ev: win.use_mark(1))
win.bind("<space>",lambda ev: win.use_mark(1))

win.mainloop()