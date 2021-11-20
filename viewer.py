import json
import os
from PIL import ImageTk, Image
import sqlite3 as sql
import time
import tkinter as tk
from tkinter import filedialog, messagebox as msgbox

tr = {
    "caption": "圖片資料檢視工具",
    "open_folder_title": "開啟圖片資料夾"
}

root = tk.Tk()
iconfile = "postage_stamp.ico"
if os.path.isfile(iconfile):
    root.iconbitmap(iconfile)
root.title("%s v.%s" % ( tr["caption"], "Alpha" ))
root.geometry("800x600")
root.state("zoomed")

container = tk.Frame(root, bg="black")
container.pack(anchor="n", fill="both", expand=True)
canvas = tk.Canvas(container, highlightthickness=0, relief="ridge")

def ask_folder(event):
    folder = filedialog.askdirectory(
        title=tr["open_folder_title"],
        initialdir=".")
    if not os.path.isdir(folder):
        return
    open_folder(folder)
container.bind("<Double-Button-1>", ask_folder)

images = []
index = -1
def open_folder(folder):
    global index
    dbfile = folder + "/data.db"
    if os.path.isfile(dbfile):
        try:
            db = sql.connect(dbfile)
            lines = db.execute("SELECT * FROM jsondata").fetchall()
            for line in lines:
                images.append({
                    "path": folder + "/" + line[1],
                    "data": json.loads(line[3])
                })
            db.close()
        except sql.Error as e:
            print(e)
    else:
        for _,_,fns in os.walk(folder):
            for fn in fns:
                _, ext = fn.split(".")
                if not ext in ["jpg","jpeg","png","webp"]:
                    continue
                images.append({
                    "path": folder + "/" + fn
                })
    index = 0
    show_image(0)

maskalpha = 120
masklayer = None
def mask(alpha,w,h):
    global masklayer, maskalpha
    if alpha<0: alpha = 0
    if alpha>200: alpha = 200
    maskalpha = alpha
    mask = Image.new("RGBA", (w,h), (255,255,255,alpha))
    masklayer = ImageTk.PhotoImage(mask)
    canvas.delete("mask")
    canvas.create_image(0,0,anchor="nw",image=masklayer,tags="mask")
def set_alpha(event):
    global maskalpha
    if event.num == 5 or event.delta == -120:
        maskalpha -= 20
    if event.num == 4 or event.delta == 120:
        maskalpha += 20
    mask(maskalpha,canvas.winfo_width(), canvas.winfo_height())
    canvas.lower("mask")
    canvas.lower("background")
container.bind("<MouseWheel>", set_alpha)
canvas.bind("<MouseWheel>", set_alpha)

background = None
def show_image(offset):
    global index
    n = index + offset
    if n<0 or n>=len(images):
        return
    image = images[n]
    index = n
    canvas.delete("all")
    mw, mh = container.winfo_width(), container.winfo_height()
    img = Image.open(image["path"])
    w, h = img.size
    ratio = max(w/mw, h/mh)
    scale = 1
    if ratio>1:
        w = int(w / ratio)
        h = int(h / ratio)
        img = img.resize((w,h), Image.ANTIALIAS)
        scale = 1 / ratio
    canvas.pack()
    canvas.place(x=(mw-w)/2,y=(mh-h)/2,width=w,height=h)
    global background, masklayer
    background = ImageTk.PhotoImage(img)
    canvas.delete("background")
    canvas.create_image(0,0,anchor="nw",image=background,tags="background")
    if "data" in image:
        mask(maskalpha,w,h)
        data = image["data"]
        mark_scale = scale / data["scale"]
        markset_count = 0
        for markset in data["marks"]:
            markset_count += 1
            for k, m in markset.items():
                show_mark(k,m,mark_scale,"set %d" % markset_count)

def show_mark(key,mark,scale,settag):
    if not "type" in mark:
        for k, m in mark.items():
            show_mark("-".join([key,k]),m,scale,settag)
        return
    tags = (key,settag)
    type = mark["type"]
    if type=="oval":
        cx, cy = [int(n*scale) for n in mark["center"]]
        rx, ry = [int(n*scale) for n in mark["radius"]]
        canvas.create_oval(
            cx-rx-1, cy-ry-1, cx+rx, cy+ry,
            outline="blue", width=1, tags=tags)
    elif type=="rectangle":
        x, y = [int(n*scale) for n in mark["topleft"]]
        canvas.create_rectangle(
            x, y, x+int(mark["width"]*scale), y+int(mark["height"]*scale),
            outline="blue", width=1, tags=tags)
    elif type=="point":
        arm = 5
        x, y = [int(n*scale) for n in mark["point"]]
        canvas.create_line(x-arm,y,x+arm,y,fill="blue",width=1,tags=tags)
        canvas.create_line(x,y-arm,x,y+arm,fill="blue",width=1,tags=tags)
    elif type=="lines":
        pts = [(int(x*scale),int(y*scale)) for [x,y] in mark["points"]]
        canvas.create_line(*pts,fill="blue",width=1,tags=tags)
    elif type=="polygon":
        pts = [(int(x*scale),int(y*scale)) for [x,y] in mark["points"]]
        canvas.create_polygon(*pts,
            fill="", outline="blue", width=1,
            tags=tags)

def after_resized(event):
    root.after_idle(lambda : show_image(0))
container.bind("<Configure>", after_resized)


def onclosed():
    root.destroy()
root.protocol("WM_DELETE_WINDOW", onclosed)

root.bind("<Left>",lambda ev: show_image(-1))
root.bind("<Right>",lambda ev: show_image(1))
root.bind("<space>",lambda ev: show_image(1))

root.update()


root.mainloop()