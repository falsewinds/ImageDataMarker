from copy import deepcopy
import hashlib
import json
import os
from PIL import ImageTk, Image
import sqlite3 as sql
import time
import tkinter as tk
from tkinter import filedialog, messagebox as msgbox


tr = {
    "caption": "圖片資訊標記助手",
    "caption_short": "標記助手",
    # menu
    "setting": "設定",
    "ask_schema": "讀取標記規範",
    "ask_folder": "開啟圖片資料夾",
    "set_alpha": "遮罩透明度",
    # mark type
    "oval": "橢圓",
    "rectangle": "方形",
    "point": "點",
    "lines": "連續線段",
    "polygon": "多邊形",
    # message
    "mark_schema_title" : "選擇標記規範",
    "mark_schema_type" : "標記規範 JSON 檔案",
    "mark_completed": [
        "標記完成！",
        "選 Yes 進入下一張圖片",
        "選 No 開始新一組的標記"
    ],
    "open_folder_title": "選擇圖片資料夾",
    "no_schema": "讀取 %s 失敗！",
    "no_schema_item": "標記規範中沒有任何標記項目。",
    "no_more_image": "資料夾中的圖片都標記完成了！",
    "no_image": "資料夾中沒有圖片！",
    "hint": "請以%s標示%s的位置 (第 %d 組, %d/%d 張圖片)",
    "dbclick_ask_schema": "雙擊畫面來選擇標記規範",
    "dbclick_ask_folder": "雙擊畫面來開啟圖片資料夾",
    "resized": "偵測到視窗大小改變，目前圖片的標記已經重置。"
}

class SimplePoint:
    def __init__(self,x,y):
        self.set(x,y)

    def set(self,x,y):
        self.x = x
        self.y = y

    def copy(self,semipoint):
        self.x = semipoint.x
        self.y = semipoint.y

    def toDict(self):
        return { "x": self.x, "y": self.y }

    def toList(self):
        return [ self.x, self.y ]


class MarkCanvas(tk.Canvas):
    def __init__(self,parent,**kwargs):
        super().__init__(parent,kwargs)
        self.types = ["oval","rectangle","point","lines","polygon"]
        parent.bind("<Escape>", self.cancel)
        self.last = SimplePoint(0,0)
        self.result = {}
        self.drawing = False
        self.selected = None
        self.usetype(self.types[0])
        self.markcolor = "blue"
        self.linewidth = 1

    def setlistener(self,listener):
        complete = getattr(listener, "markcomplete", None)
        if callable(complete):
            self.completed = complete

    def changetype(self,event):
        if self.drawing:
            return
        next = self.types.index(self.type) + 1
        if next == len(self.types):
            next = 0
        self.usetype(self.types[next])

    def usetype(self,typename):
        if self.drawing:
            return
        self.unbind("<ButtonPress-1>")
        self.unbind("<ButtonRelease-1>")
        self.unbind("<B1-Motion>")
        self.unbind("<Button-1>")
        self.unbind("<Double-Button-1>")
        if typename=="oval":
            self.bind("<ButtonPress-1>", self.dragstart)
            self.bind("<ButtonRelease-1>", self.dragstop)
            self.bind("<B1-Motion>", self.dragoval)
        elif typename=="rectangle":
            self.unbind("<Button-1>")
            self.unbind("<Double-Button-1>")
            self.bind("<ButtonPress-1>", self.dragstart)
            self.bind("<ButtonRelease-1>", self.dragstop)
            self.bind("<B1-Motion>", self.dragrect)
        elif typename=="point":
            self.unbind("<ButtonPress-1>")
            self.unbind("<ButtonRelease-1>")
            self.unbind("<B1-Motion>")
            self.bind("<Button-1>", self.setpoint)
        elif typename=="lines":
            self.unbind("<ButtonPress-1>")
            self.unbind("<ButtonRelease-1>")
            self.unbind("<B1-Motion>")
            self.bind("<Button-1>", self.addpoint)
            self.bind("<Double-Button-1>", self.marklines)
        elif typename=="polygon":
            self.bind("<Button-1>", self.addpoint)
            self.bind("<Double-Button-1>", self.markpolygon)
        else:
            return
        self.type = typename
        self.bind("<Button-3>", self.cancel)
        self.clear()

    def setmarktag(self,tag):
        if not tag is None:
            self.marktag.append(tag)

    def clear(self):
        self.delete("startpoint")
        self.delete("temporary")
        self.points = []
        self.result = { "type": self.type }
        self.selected = None
        self.marktag = ["marked"]

    def cancel(self,event):
        self.clear()
        self.drawing = False

    def dragstart(self,event):
        self.selected = None
        self.drawing = True
        self.delete("startpoint")
        self.delete("temporary")
        self.last.copy(event)
        self.cross(self.last,5,"startpoint")

    def dragstop(self,event):
        self.selected = None
        if not self.drawing:
            return
        self.delete("startpoint")
        temp = self.find_withtag("temporary")
        if len(temp) <= 0:
            return
        self.itemconfigure("temporary",
            outline=self.markcolor, dash=(),
            tags=self.marktag)
        self.drawing = False
        self.completed()

    def dragoval(self,event):
        if not self.drawing:
            return
        dx, dy = abs(event.x-self.last.x), abs(event.y-self.last.y)
        r = max(dx,dy)
        if event.state & 0x0001 == 0x0001:
            dx = r
            dy = r
        temps = self.find_withtag("temporary")
        if len(temps) <= 0:
            self.create_oval(
                self.last.x-dx-1, self.last.y-dy-1,
                self.last.x+dx, self.last.y+dy,
                outline=self.markcolor,
                dash=(2,1), width=self.linewidth,
                tags="temporary")
        else:
            self.coords("temporary",
                self.last.x-dx-1, self.last.y-dy-1,
                self.last.x+dx, self.last.y+dy)
        self.result["center"] = self.last.toList()
        self.result["radius"] = [dx,dy]

    def dragrect(self,event):
        if not self.drawing:
            return
        temps = self.find_withtag("temporary")
        if len(temps) <= 0:
            self.create_rectangle(
                self.last.x, self.last.y,
                event.x, event.y,
                outline=self.markcolor, 
                dash=(2,1), width=self.linewidth,
                tags="temporary")
        else:
            self.coords("temporary",
                self.last.x, self.last.y,
                event.x, event.y)
        self.result["topleft"] = [min(self.last.x,event.x),min(self.last.y,event.y)]
        self.result["bottomright"] = [max(self.last.x,event.x),max(self.last.y,event.y)]
        self.result["width"] = abs(event.x-self.last.x)
        self.result["height"] = abs(event.y-self.last.y)

    def setpoint(self,event):
        self.cross(event,5,self.marktag)
        self.result["point"] = [event.x,event.y]
        self.completed()

    def addpoint(self,event):
        self.drawing = True
        if len(self.points) > 0:
            self.create_line(
                self.last.x, self.last.y,
                event.x, event.y,
                fill=self.markcolor,
                width=self.linewidth, dash=(2,1),
                tags="temporary")
        self.cross(event,5,"temporary")
        self.points.append((event.x,event.y))
        self.last.copy(event)

    def __copy_points(self):
        list = []
        for pt in self.points:
            list.append([pt[0],pt[1]])
        return list

    def marklines(self,event):
        if len(self.points) > 0:
            self.result["points"] = self.__copy_points()
            self.create_line(
                *self.points,
                fill=self.markcolor,
                width=self.linewidth,
                tags=self.marktag)
        self.drawing = False
        self.completed()
        self.clear()
        
    def markpolygon(self,event):
        if len(self.points) > 0:
            self.result["points"] = self.__copy_points()
            self.create_polygon(
                *self.points,
                fill="", outline=self.markcolor,
                width=self.linewidth,
                tags=self.marktag)
        self.drawing = False
        self.completed()
        self.clear()

    def cross(self,point,arm,tag):
        self.create_line((point.x-arm,point.y,point.x+arm,point.y),
            fill=self.markcolor,width=self.linewidth,tags=tag)
        self.create_line((point.x,point.y-arm,point.x,point.y+arm),
            fill=self.markcolor,width=self.linewidth,tags=tag)

    def movestart(self,event):
        self.selected = self.find_closest(event.x,event.y)
        self.last.copy(event)

    def movedrag(self,event):
        if self.selected is None:
            return
        dx, dy = event.x-self.last.x, event.y-self.last.y
        self.move(self.selected,dx,dy)
        self.last.copy(event)

    def movestop(self,event):
        self.selected = None

    def show(self,image):
        self.background = ImageTk.PhotoImage(image)
        self.delete("background")
        self.create_image(0,0,anchor="nw",image=self.background,tags="background")

    def mask(self,x,y,w,h,alpha):
        if alpha > 1:
            alpha /= 255
        mask_img = Image.new("RGBA", (w,h), (255,255,255,int(alpha*255)))
        self.masklayer = ImageTk.PhotoImage(mask_img)
        self.delete("mask")
        self.create_image(x,y,anchor="nw",image=self.masklayer,tags="mask")
        self.lower("mask")
        self.lower("background")

    def completed(self):
        print(self.result)


class MarkSchemaItem:
    pass

class MarkController:
    def __init__(self):
        self.configuration = {}
        # Image List
        self.imagelist = []
        self.imagepath = None
        self.imagefolder = None
        self.imagecursor = -1
        # MarkItem List
        self.itemlist = []
        self.itemcursor = -1
        # Marks Data for Image
        self.data = {}
        self.marksets = None
        self.markset = None
        # Alpha Mask
        self.alpha = 0.5
        # Statics
        self.imagecount = 0
        self.markscount = 0

    def load_configuration(self):
        try:
            fp = open("./last.json",mode="r",encoding="utf-8")
        except:
            return
        cfg = json.load(fp)
        if "schema" in cfg:
            self.use_schema(cfg["schema"])
        if len(self.itemlist) <= 0:
            return
        if "folder" in cfg:
            self.open_folder(cfg["folder"])
            if "index" in cfg:
                self.imagecursor = cfg["index"]
                self.load_image(self.imagelist[self.imagecursor])

    def save_configuration(self):
        fp = open("./last.json",mode="w",encoding="utf-8")
        json.dump(self.configuration,fp,indent=4)

    def close(self):
        self.save_configuration()

    def ask_schema(self):
        jsonpath = filedialog.askopenfilename(
            title=tr["mark_schema_title"],
            initialdir=".",
            filetypes=[(tr["mark_schema_type"],"*.json")])
        if not os.path.isfile(jsonpath):
            return
        self.use_schema(jsonpath)

    def use_schema(self,jsonfile):
        try:
            fp = open(jsonfile,mode="r",encoding="utf-8")
        except:
            msgbox.showerror(title=tr["caption_short"],
                message=tr["no_schema"] % (jsonfile))
            return
        self.configuration["schema"] = jsonfile
        self.schema = { "key": "marks", "items": json.load(fp) }
        self.itemcursor = -1
        self.itemlist.clear()
        queue = [self.schema]
        while len(queue)>0:
            cursor = queue.pop(0)
            branch = []
            if "branch" in cursor:
                for b in cursor["branch"]:
                    b["key"] = "_" + b["key"]
                    branch.append(b)
            if len(branch)<=0:
                branch = [{"key":"","name":""}]
            newschemas = []
            if "items" in cursor:
                if "ancients" in cursor:
                    ancients = cursor["ancients"]
                else:
                    ancients = []
                ancients.append(cursor)
                for it in cursor["items"]:
                    for b in branch:
                        it_copy = deepcopy(it)
                        it_copy["ancients"] = deepcopy(ancients)
                        it_copy["key"] += b["key"]
                        it_copy["name"] = b["name"] + it["name"]
                        if not "color" in it and "color" in b:
                            it_copy["color"] = b["color"]
                        newschemas.append(it_copy)
                queue[0:0] = newschemas
                continue
            for b in branch:
                item = MarkSchemaItem()
                item.path = []
                group = []
                ancient_color = "black" # default color
                for a in cursor["ancients"][1:]:
                    item.path.append(a["key"])
                    group.append(a["name"])
                    if "color" in a:
                        ancient_color = a["color"]
                item.group = "-".join(group)
                item.key = cursor["key"] + b["key"]
                item.name = b["name"] + cursor["name"]
                item.type = cursor["type"]
                if "color" in cursor:
                    item.color = cursor["color"]
                elif "color" in b:
                    item.color = b["color"]
                else:
                    item.color = ancient_color
                self.itemlist.append(item)
        if len(self.itemlist) > 0:
            self.close_folder()
        else:
            msgbox.showerror(title=tr["caption_short"],
                message=tr["no_schema_item"])

    def prev_mark(self):
        self.itemcursor -= 1
        if self.itemcursor < 0:
            self.itemcursor = 0
            return
        self.use_mark()

    def next_mark(self):
        self.itemcursor += 1
        if self.itemcursor >= len(self.itemlist):
            if self.markset:
                self.markscount += 1
                self.marksets.append(deepcopy(self.markset))
                self.markset = {}
            nextpic = msgbox.askyesno(title=tr["caption_short"],
                message="\n".join(tr["mark_completed"]))
            if nextpic:
                self.save_db()
                self.imagecount += 1
                if not self.next_image():
                    msgbox.showinfo(title=tr["caption_short"],
                        message=tr["no_more_image"])
                    self.close_folder()
                    del self.configuration["folder"]
                    del self.configuration["index"]
                return
            else:
                self.itemcursor = 0
        self.use_mark()

    def use_mark(self):
        markset_index = len(self.marksets) + 1
        markset_tag = "markset%d" % (markset_index)
        item = self.itemlist[self.itemcursor]
        lbl_hint.config(text=tr["hint"] % (
            tr[item.type], item.name,
            markset_index,
            self.imagecursor+1, len(self.imagelist)
        ))
        canvas.delete("%s&&%s" % (item.key,markset_tag))
        canvas.usetype(item.type)
        canvas.setmarktag(item.key)
        canvas.setmarktag(markset_tag)
        canvas.markcolor = item.color

    def markcomplete(self):
        canvas.usetype("none")
        item = self.itemlist[self.itemcursor]
        cur_grp = self.markset
        for k in item.path:
            if not k in cur_grp:
                cur_grp[k] = {}
            cur_grp = cur_grp[k]
        cur_grp[item.key] = deepcopy(canvas.result)
        self.next_mark()

    def create_db(self):
        db_path = self.imagefolder + "/data.db"
        try:
            db = sql.connect(db_path)
            db.execute("""CREATE TABLE IF NOT EXISTS markschemata (
                id CHAR(32) PRIMARY KEY,
                json BLOB NOT NULL
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS jsondata (
                id CHAR(32) PRIMARY KEY,
                path TEXT NOT NULL,
                schema CHAR(32) NOT NULL,
                json BLOB NOT NULL,
                marks INT NOT NULL,
                modified TEXT NOT NULL
            )""")
            db.commit()
            db_old_file = self.imagefolder + "/data.sqlite"
            if os.path.isfile(db_old_file):
                schema_str = json.dumps(self.schema)
                schema_id = hashlib.md5(schema_str.encode()).hexdigest()
                db.execute("""INSERT INTO markschemata
                    (id,json) VALUES (?,?)""",
                    (schema_id,schema_str))
                db.commit()
                db_old = sql.connect(db_old_file)
                lines = db_old.execute("SELECT * FROM jsondata").fetchall()
                for line in lines:
                    db.execute("""INSERT INTO jsondata
                        (id,path,schema,json,marks,modified)
                        VALUES (?,?,?,?,?,?)""",
                        (
                            line[0], line[1],
                            schema_id, line[2],
                            line[3], line[4]
                        )
                    )
                db.commit()
                db_old.close()
            db.close()
        except sql.Error as e:
            print(e)

    def save_db(self):
        datetime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        db_path = self.imagefolder + "/data.sqlite"
        img_str = self.imagepath[len(self.imagefolder)+1:]
        img_id = hashlib.md5(img_str.encode()).hexdigest()
        json_str = json.dumps(self.data)
        schema_str = json.dumps(self.schema)
        schema_id = hashlib.md5(schema_str.encode()).hexdigest()
        try:
            db = sql.connect(db_path)
            db.execute("""INSERT OR IGNORE INTO markschemata
                (id,json) VALUES (?,?)""",
                ( schema_id, schema_str )
            )
            db.execute("""INSERT OR REPLACE INTO jsondata
                (id,path,schema,json,marks,modified)
                VALUES (?,?,?,?,?,?)""",
                (
                    img_id, img_str,
                    schema_id, json_str,
                    len(self.marksets),
                    datetime
                )
            )
            db.commit()
            db.close()
        except sql.Error as e:
            print(e)

    def ask_folder(self):
        folder = filedialog.askdirectory(
            title=tr["open_folder_title"],
            initialdir=".")
        if not os.path.isdir(folder):
            return
        self.open_folder(folder)

    def __find_images(self,folder):
        for _,dirs,fns in os.walk(folder):
            for dir in dirs:
                self.__find_images(folder+"/"+dir)
            for fn in fns:
                _, ext = fn.split(".")
                if not ext in ["jpg","jpeg","png","webp"]:
                    continue
                self.imagelist.append(folder+"/"+fn)

    def open_folder(self,folder):
        self.imagefolder = folder
        self.create_db()
        self.configuration["folder"] = folder
        self.imagecursor = -1
        self.imagelist.clear()
        self.__find_images(folder)
        self.imagecount = 0
        self.markscount = 0
        container.unbind("<Double-Button-1>")
        if not self.next_image():
            msgbox.showerror(title=tr["caption_short"],
                message=tr["no_image"])
            self.close_folder()

    def close_folder(self):
        self.imagecursor = -1
        self.imagelist.clear()
        # clear & hide canvas
        canvas.delete("all")
        canvas.usetype("none")
        canvas.place_forget()
        # re-register double-click method to container
        lbl_hint.config(text=tr["dbclick_ask_folder"])
        container.bind("<Double-Button-1>",lambda ev: self.ask_folder())

    def open_url(self,url):
        return

    def prev_image(self):
        if len(self.imagelist) <= 0:
            return False
        if self.imagecursor < 0:
            self.imagecursor = 0
        else:
            self.imagecursor -= 1
        if self.imagecursor < 0:
            self.imagecursor = 0
            return False
        self.load_image(self.imagelist[self.imagecursor])
        return True

    def next_image(self):
        if len(self.imagelist) <= 0:
            return False
        if self.imagecursor < 0:
            self.imagecursor = 0
        else:
            self.imagecursor += 1
        if self.imagecursor >= len(self.imagelist):
            self.imagecursor = len(self.imagelist) - 1
            return False
        self.load_image(self.imagelist[self.imagecursor])
        return True

    def load_image(self,path):
        canvas.usetype("none")
        canvas.delete("all")
        self.configuration["index"] = self.imagecursor
        self.imagepath = path
        mw, mh = container.winfo_width(), container.winfo_height()
        img = Image.open(path)
        w, h = img.size
        ratio = max(w/mw, h/mh)
        scale = 1
        if ratio>1:
            w = int(w / ratio)
            h = int(h / ratio)
            img = img.resize((w,h), Image.ANTIALIAS)
            scale = 1 / ratio
        #self.image = img
        canvas.place(x=(mw-w)/2,y=(mh-h)/2,width=w,height=h)
        canvas.show(img)
        canvas.mask(0,0,w,h,self.alpha)
        self.data = {
            "width": w,
            "height": h,
            "scale": scale,
            "marks": []
        }
        # new image
        self.marksets = self.data["marks"]
        self.markset = {}
        self.itemcursor = 0
        self.use_mark()

    def reload_image(self):
        if self.imagepath is None:
            return
        self.load_image(self.imagepath)
        msgbox.showwarning(title=tr["caption_short"],
            message=tr["resized"])

    def set_alpha(self,alpha):
        if alpha > 1:
            alpha / 255
        self.alpha = alpha
        canvas.mask(0,0,
            canvas.winfo_width(),
            canvas.winfo_height(),
            self.alpha)


ctrl = MarkController()
root = tk.Tk()
iconfile = "postage_stamp.ico"
if os.path.isfile(iconfile):
    root.iconbitmap(iconfile)
root.title("%s v.%s" % ( tr["caption"], "Alpha" ))
root.geometry("800x600")
root.state("zoomed")

menu = tk.Menu(root)
mnu_setting = tk.Menu(menu, tearoff=False)
menu.add_cascade(menu=mnu_setting, label=tr["setting"])
mnu_setting.add_command(label=tr["ask_schema"], command=ctrl.ask_schema)
mnu_setting.add_command(label=tr["ask_folder"], command=ctrl.ask_folder)
mnu_setting.add_separator()

mnu_alpha = tk.Menu(menu, tearoff=False)
menu_alpha = tk.Variable(root)
def change_alpha():
    ctrl.set_alpha(menu_alpha.get())
mnu_alpha.add_radiobutton(label="75%",
    value=0.75, variable=menu_alpha,
    command=change_alpha)
mnu_alpha.add_radiobutton(label="50%",
    value=0.5, variable=menu_alpha,
    command=change_alpha)
mnu_alpha.add_radiobutton(label="25%",
    value=0.25, variable=menu_alpha,
    command=change_alpha)
mnu_alpha.add_radiobutton(label="0%",
    value=0, variable=menu_alpha,
    command=change_alpha)
menu_alpha.set(0.5)

mnu_setting.add_cascade(menu=mnu_alpha, label=tr["set_alpha"])
root.config(menu=menu)

container = tk.Frame(root, bg="black")
container.pack(anchor="n", fill="both", expand=True)
container.bind("<Double-Button-1>",lambda ev: ctrl.ask_schema())
def after_resized(event):
    root.after_idle(lambda : ctrl.reload_image())
container.bind("<Configure>", after_resized)
canvas = MarkCanvas(container, highlightthickness=0, relief="ridge")
canvas.setlistener(ctrl)

lbl_hint = tk.Label(root, bg="white", font=("微軟正黑體",16,"bold"),
    text=tr["dbclick_ask_schema"])
lbl_hint.pack(anchor="s", fill="x", expand=False)

#ctrl.use_schema("./schema/human2.json")
def onclosed():
    ctrl.close()
    root.destroy()
root.protocol("WM_DELETE_WINDOW", onclosed)

root.bind("<Left>",lambda ev: ctrl.prev_mark())
root.bind("<Right>",lambda ev: ctrl.next_mark())
root.bind("<space>",lambda ev: ctrl.next_mark())

root.update()
ctrl.load_configuration()

root.mainloop()