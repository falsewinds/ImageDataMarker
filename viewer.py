from canvaswindow import CanvasWindow

win = CanvasWindow(
    caption="圖片資料檢視工具",
    icon="postage_stamp.ico",
    translation={
        "open_folder_title": "開啟圖片資料夾"
    }
)

win.bind("<Left>", lambda ev: win.show_image(-1))
win.bind("<Right>", lambda ev: win.show_image(1))
win.bind("<space>", lambda ev: win.show_image(1))

maskalpha = 120
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

win.mainloop()

