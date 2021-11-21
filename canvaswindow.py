from copy import deepcopy
import hashlib
import json
import os
from PIL import ImageTk, Image
import sqlite3 as sql
import time
import tkinter as tk
from tkinter import filedialog, messagebox as msgbox

class MarkSchemaItem:
    def __init__(self,branch,dict):
        self.path = []
        group = []
        ancient_color = "black" # default color
        for a in dict["ancients"][1:]:
            self.path.append(a["key"])
            group.append(a["name"])
            if "color" in a:
                ancient_color = a["color"]
        self.group = "-".join(group)
        self.key = dict["key"] + branch["key"]
        self.name = branch["name"] + dict["name"]
        self.type = dict["type"]
        if "color" in dict:
            self.color = dict["color"]
        elif "color" in branch:
            self.color = branch["color"]
        else:
            self.color = ancient_color

class MarkCanvasItem:
    def __init__(self,set,scalar,type,item,**kwargs):
        if type=="oval":
            self.center = tuple(kwargs["center"])
            self.radius = tuple(kwargs["radius"])
        elif type=="rectangle":
            self.point = tuple(kwargs["topleft"])
            self.size = (kwargs["width"],kwargs["height"])
        elif type=="point":
            self.point = tuple(kwargs["point"])
        elif type=="lines" or type=="polygon":
            self.points = tuple(kwargs["points"])
        self.type = type
        self.key = kwargs["key"]
        self.color = kwargs["color"]
        self.linewidth = 1
        self.scalar = scalar
        self.set = set
        self.arm = 5
        if "arm" in kwargs:
            self.arm = int(self.arm)

    def __scalepoint(self,pt):
        return [int(i*self.scalar) for i in pt]
    def __scalepoints(self,pts):
        return [(int(x*self.scalar),int(y*self.scalar)) for x,y in pts]

    def draw(self,canvas):
        tags = ("set%d" % self.set, self.key)
        outline = {
            "fill": "",
            "outline": self.color,
            "width": self.linewidth,
            "tags": tags
        }
        fill = {
            "fill": self.color,
            "width": self.linewidth,
            "tags": tags
        }
        if self.type=="oval":
            x, y, rx, ry = self.center + self.radius
            pos = tuple(self.__scalepoint([x-rx-1,y-ry-1,x+rx,y+ry]))
            self.id = (canvas.create_oval(*pos,**outline),)
        elif self.type=="rectangle":
            x, y, w, h = self.point + self.size
            pos = tuple(self.__scalepoint([x,y,x+w,y+h]))
            self.id = (canvas.create_rectangle(*pos,**outline),)
        elif self.type=="point":
            x, y = self.__scalepoint(self.point)
            self.id = (
                canvas.create_line(x-self.arm-1,y,x+self.arm,y,**fill),
                canvas.create_line(x,y-self.arm-1,x,y+self.arm,**fill)
            )
        elif self.type=="lines":
            pts = tuple(self.__scalepoints(self.points))
            self.id = (canvas.create_line(*pts,**outline),)
        elif self.type=="polygon":
            pts = tuple(self.__scalepoints(self.points))
            self.id = (canvas.create_polygon(*pts,**outline),)
        return self.id

class CanvasWindow(tk.Tk):
    def __init__(self,**kwargs):
        super().__init__()
        self.__configuration = {}
        self.__schema = {}
        self.__schemajson = None
        self.__item = None
        self.__itemlist = []
        self.__itemcursor = -1
        self.__data = None
        self.__marksets = None
        self.__markset = None
        self.__canvasdata = {}
        self.__imagelist = []
        self.__imagecursor = -1
        self.__tkimage = None
        self.__tkmask = None
        self.__markdata = {}
        self.__schemata = {}
        self.__listener = None
        self.stringmap = {
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
        if "translation" in kwargs:
            trans = kwargs["translation"]
            if isinstance(trans,dict):
                for k,v in trans.items():
                    self.stringmap[k] = v

        caption = self.stringmap["caption"]
        version = "Alpha"
        if "caption" in kwargs: caption = kwargs["caption"]
        if "version" in kwargs: version = kwargs["version"]
        self.title("%s v.%s" % (caption,version))

        if "icon" in kwargs:
            iconfile = kwargs["icon"]
            if os.path.isfile(iconfile):
                self.iconbitmap(iconfile)
        size = "800x600"
        if "size" in kwargs:
            size = kwargs["size"]
        else:
            wh = [800,600]
            if "width" in kwargs: wh[0] = int(kwargs["width"])
            if "height" in kwargs: wh[1] = int(kwargs["height"])
            size = "x".join([str(i) for i in wh])
        self.geometry(size)
        if not ("maximum" in kwargs and bool(kwargs["maximum"])):
            self.state("zoomed")

        self.__linewidth = 1
        if "linewidth" in kwargs:
            self.__linewidth = int(kwargs["linewidth"])
        if self.__linewidth <= 0:
            self.__linewidth = 1

        self.maskalpha = 120
        if "maskalpha" in kwargs:
            self.maskalpha = int(kwargs["maskalpha"])

        self.__readonly = False
        if "readonly" in kwargs:
            if bool(kwargs["readonly"]):
                self.__readonly = True

        # Canvas & Container
        self.container = tk.Frame(self, bg="black")
        self.container.pack(anchor="n", fill="both", expand=True)
        self.container.bind("<Double-Button-1>", self.initialize)

        self.canvas = tk.Canvas(self.container,
            highlightthickness=0, relief="ridge")

        self.update()
        self.protocol("WM_DELETE_WINDOW", lambda : self.close())

        def delay():
            self.update()
            self.load_configuration()
            self.container.bind("<Configure>", self.after_resized)
        self.after_idle(delay)

    def set_listener(self,hint):
        if hint is None: return
        self.__listener = hint
        if self.__readonly or not self.__schemajson is None:
            hint.config(text=self.stringmap["dbclick_ask_folder"])
        else:
            hint.config(text=self.stringmap["dbclick_ask_schema"])

    def load_configuration(self):
        try:
            fp = open("./last.json",mode="r",encoding="utf-8")
        except:
            return
        cfg = json.load(fp)
        if "schema" in cfg:
            self.use_schema(cfg["schema"])
        if len(self.__itemlist) <= 0:
            return
        if "folder" in cfg:
            self.open_folder(cfg["folder"])
            if "index" in cfg:
                self.imagecursor = int(cfg["index"])
                self.show_image(0)

    def save_configuration(self):
        fp = open("./last.json",mode="w",encoding="utf-8")
        json.dump(self.__configuration,fp,indent=4)

    def initialize(self,event):
        if self.__readonly or not self.__schemajson is None:
            self.ask_folder()
        else:
            self.ask_schema()

    def after_resized(self,event):
        def resized():
            if len(self.__imagelist) <= 0:
                return
            self.show_image(0)
            msgbox.showwarning(
                title=self.stringmap["caption_short"],
                message=self.stringmap["resized"])
        self.after_idle(resized)

    def close(self):
        self.save_configuration()
        self.destroy()

    def ask_schema(self):
        jsonpath = filedialog.askopenfilename(
            title=self.stringmap["mark_schema_title"],
            initialdir=".",
            filetypes=[(self.stringmap["mark_schema_type"],"*.json")])
        if not os.path.isfile(jsonpath):
            return
        self.use_schema(jsonpath)

    def use_schema(self,jsonfile):
        try:
            fp = open(jsonfile,mode="r",encoding="utf-8")
        except:
            msgbox.showerror(title=self.stringmap["caption_short"],
                message=self.stringmap["no_schema"] % (jsonfile))
            return
        self.__configuration["schema"] = jsonfile
        self.parse_schema({ "key": "marks", "items": json.load(fp) })
        if len(self.__itemlist) > 0:
            self.close_folder()
        else:
            msgbox.showerror(title=self.stringmap["caption_short"],
                message=self.stringmap["no_schema_item"])

    def parse_schema(self,schema_dict):
        self.__itemcursor = -1
        self.__itemlist.clear()
        self.__schema = {}
        self.__schemajson = schema_dict
        queue = [schema_dict]
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
                item = MarkSchemaItem(b,cursor)
                self.__itemlist.append(item)
                key = "/".join(item.path + [item.key])
                self.__schema[key] = item

    def ask_folder(self):
        folder = filedialog.askdirectory(
            title=self.stringmap["open_folder_title"],
            initialdir=".")
        if not os.path.isdir(folder):
            return
        self.open_folder(folder)

    def open_folder(self,folder):
        if not os.path.isdir(folder):
            self.close_folder()
            return
        self.__configuration["folder"] = folder
        self.__rootdirectory = folder
        self.__imagelist.clear()
        self.load_images(folder,False)
        self.__imagecursor = 0
        if not self.show_image(0):
            msgbox.showerror(
                title=self.stringmap["caption_short"],
                message=self.stringmap["no_image"])
            self.close_folder()
            return
        if not self.__readonly:
            self.mask(self.maskalpha)
            self.container.unbind("<Double-Button-1>")
            if not self.__data:
                w, h, s = self.__imagesize
                self.__data = {
                    "width": w,
                    "height": h,
                    "scale": s,
                    "marks": []
                }
            self.__marksets = self.__data["marks"]
            self.__markset = {}
            self.__itemcursor = 0
            self.use_mark(0)

    def close_folder(self):
        self.__imagecursor = -1
        self.__imagelist.clear()
        # clear & hide canvas
        self.canvas.delete("all")
        self.canvas.place_forget()
        # re-register double-click method to container
        self.container.bind("<Double-Button-1>", self.initialize)
        if not self.__listener is None:
            self.__listener.config(text=self.stringmap["dbclick_ask_folder"])
        # release image(s)
        if not self.__tkimage is None: del self.__tkimage

    def load_images(self,folder,recursive):
        queue = [folder]
        while len(queue) > 0:
            path = queue.pop(0)
            for _,dirs,fns in os.walk(path):
                if recursive:
                    for dir in dirs:
                        queue.append(os.path.join(path,dir))
                for fn in fns:
                    _, ext = fn.split(".")
                    if not ext in ["jpg","jpeg","png","webp"]:
                        continue
                    self.__imagelist.append(os.path.join(path,fn))

    def show_image(self,modifier):
        index = self.__imagecursor + int(modifier)
        if index < 0 or index >= len(self.__imagelist):
            return False
        self.__configuration["index"] = index
        self.__imagecursor = index
        imagepath = self.__imagelist[self.__imagecursor]
        self.canvas.delete("all")
        self.__drawing = False
        image = Image.open(imagepath)
        self.__imagename = imagepath[len(self.__rootdirectory)+1:]
        self.__imagehash = hashlib.md5(self.__imagename.encode()).hexdigest()
        # scale to fit container
        max_w = self.container.winfo_width()
        max_h = self.container.winfo_height()
        w, h = image.size
        ratio = max(w/max_w,h/max_h)
        scale = 1
        if ratio > 1:
            scale = 1 / ratio
            w = int(w*scale)
            h = int(h*scale)
            image = image.resize((w,h), Image.ANTIALIAS)
        self.__imagesize = (w,h,scale)
        if not self.__tkimage is None: del self.__tkimage
        self.__tkimage = ImageTk.PhotoImage(image)
        self.canvas.place(
            x=int((max_w-w)/2), y=int((max_h-h)/2),
            width=w, height=h)
        self.canvas.delete("background")
        self.canvas.create_image(0,0,anchor="nw",
            image=self.__tkimage, tags="background")
        self.draw_marks()
        return True

    def __draw_cross(self,pt,arm,tag):
        if self.__item is None: return
        style = {
            "fill": self.__item.color,
            "width": self.__linewidth,
            "tags": tag
        }
        x, y = pt
        self.canvas.create_line(x-arm-1,y,x+arm,y,style)
        self.canvas.create_line(x,y-arm-1,x,y+arm,style)

    def __drag_start(self,event):
        if self.__item is None: return
        self.__drawing = True
        self.canvas.delete("startpoint")
        self.canvas.delete("temporary")
        self.__lastpoint = (event.x,event.y)
        self.__draw_cross(self.__lastpoint,5,"startpoint")

    def __drag_stop(self,event):
        if self.__item is None: return
        if not self.__drawing:
            return
        self.canvas.delete("startpoint")
        temp = self.canvas.find_withtag("temporary")
        if len(temp) <= 0:
            return
        self.canvas.itemconfigure("temporary",
            outline=self.__item.color, dash=(),
            tags=self.__marktags)
        self.__drawing = False
        self.__complete_mark()

    def __draw_oval(self,event):
        if not self.__drawing: return
        x, y = self.__lastpoint
        dx, dy = abs(event.x-x), abs(event.y-y)
        r = max(dx,dy)
        if event.state & 0x0001 == 0x0001:
            dx = r
            dy = r
        pos = (x-dx-1, y-dy-1, x+dx, y+dy)
        temps = self.canvas.find_withtag("temporary")
        if len(temps) <= 0:
            self.canvas.create_oval(*pos,
                outline=self.__item.color,
                dash=(2,1), width=self.__linewidth,
                tags="temporary")
        else:
            self.canvas.coords("temporary",*pos)
        self.__canvasdata["center"] = [x,y]
        self.__canvasdata["radius"] = [dx,dy]

    def __draw_rect(self,event):
        if not self.__drawing: return
        x, y = self.__lastpoint
        pos = (x,y,event.x,event.y)
        temps = self.canvas.find_withtag("temporary")
        if len(temps) <= 0:
            self.canvas.create_rectangle(*pos,
                outline=self.__item.color,
                dash=(2,1), width=self.__linewidth,
                tags="temporary")
        else:
            self.canvas.coords("temporary",*pos)
        self.__canvasdata["topleft"] = [min(x,event.x),min(y,event.y)]
        self.__canvasdata["bottomright"] = [max(x,event.x),max(y,event.y)]
        self.__canvasdata["width"] = abs(event.x-x)
        self.__canvasdata["height"] = abs(event.y-y)

    def __set_point(self,event):
        self.__draw_cross((event.x,event.y),5,self.__marktags)
        self.__canvasdata["point"] = [event.x,event.y]
        self.__complete_mark()

    def __add_point(self,event):
        self.__drawing = True
        if len(self.__pointlist) > 0:
            x, y = self.__pointlist[-1]
            self.canvas.create_line(
                x, y, event.x, event.y,
                fill=self.__item.color,
                width=self.__linewidth, dash=(2,1),
                tags="temporary")
        self.__draw_cross((event.x,event.y),5,"temporary")
        self.__pointlist.append((event.x,event.y))

    def __mark_lines(self,event):
        if self.__pointlist and len(self.__pointlist) > 1:
            self.__canvasdata["points"] = [[x,y] for (x,y) in self.__pointlist]
            self.canvas.create_line(*self.__pointlist,
                fill=self.__item.color,
                width=self.__linewidth,
                tags=self.__marktags)
            self.__drawing = False
            self.__complete_mark()
        
    def __mark_polygon(self,event):
        if self.__pointlist and len(self.__pointlist) > 1:
            self.__canvasdata["points"] = [[x,y] for (x,y) in self.__pointlist]
            self.canvas.create_polygon(*self.__pointlist,
                fill="", outline=self.__item.color,
                width=self.__linewidth,
                tags=self.__marktags)
            self.__drawing = False
            self.__complete_mark()

    def __cancel_mark(self,event):
        self.canvas.delete("startpoint")
        self.canvas.delete("temporary")
        self.__canvasdata = { "type": self.__item.type }
        self.__drawing = False

    def use_mark(self,modifier):
        if self.__drawing: return
        index = self.__itemcursor + modifier
        if index < 0: return
        if index >= len(self.__itemlist):
            if self.__markset:
                # self.markscount += 1
                self.__marksets.append(deepcopy(self.__markset))
                self.__markset = {}
            nextpic = msgbox.askyesno(
                title=self.stringmap["caption_short"],
                message="\n".join(self.stringmap["mark_completed"]))
            if nextpic:
                self.save_db()
                # self.imagecount += 1
                if not self.show_image(1):
                    msgbox.showinfo(
                        title=self.stringmap["caption_short"],
                        message=self.stringmap["no_more_image"])
                    self.close_folder()
                    del self.__configuration["folder"]
                    del self.__configuration["index"]
                return
            else:
                index = 0
        self.__itemcursor = index
        self.__item = self.__itemlist[index]
        self.__marktags = (
            "set%d" % (len(self.__marksets)+1),
            self.__item.key,
            self.__item.type
        )
        # Show message in Hint label (if any)
        if not self.__listener is None:
            self.__listener.config(
                text=self.stringmap["hint"] % (
                    self.stringmap[self.__item.type],
                    self.__item.name,
                    len(self.__marksets)+1,
                    self.__imagecursor+1,
                    len(self.__imagelist)
                ))
        self.canvas.delete("&&".join(self.__marktags))
        self.__pointlist = []
        type = self.__item.type
        # unbind event
        self.canvas.unbind("<ButtonPress-1>")
        self.canvas.unbind("<ButtonRelease-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<Button-1>")
        self.canvas.unbind("<Double-Button-1>")
        if type=="oval":
            self.canvas.bind("<ButtonPress-1>", self.__drag_start)
            self.canvas.bind("<ButtonRelease-1>", self.__drag_stop)
            self.canvas.bind("<B1-Motion>", self.__draw_oval)
        elif type=="rectangle":
            self.canvas.bind("<ButtonPress-1>", self.__drag_start)
            self.canvas.bind("<ButtonRelease-1>", self.__drag_stop)
            self.canvas.bind("<B1-Motion>", self.__draw_rect)
        elif type=="point":
            self.canvas.bind("<Button-1>", self.__set_point)
        elif type=="lines":
            self.canvas.bind("<Button-1>", self.__add_point)
            self.canvas.bind("<Double-Button-1>", self.__mark_lines)
        elif type=="polygon":
            self.canvas.bind("<Button-1>", self.__add_point)
            self.canvas.bind("<Double-Button-1>", self.__mark_polygon)
        else:
            return
        self.canvas.bind("<Button-3>", self.__cancel_mark)
        self.bind("<Escape>", self.__cancel_mark)
        self.canvas.delete("startpoint")
        self.canvas.delete("temporary")
        self.__canvasdata = { "type": type }

    def __complete_mark(self):
        self.canvas.unbind("<ButtonPress-1>")
        self.canvas.unbind("<ButtonRelease-1>")
        self.canvas.unbind("<B1-Motion>")
        self.canvas.unbind("<Button-1>")
        self.canvas.unbind("<Double-Button-1>")
        cur_grp = self.__markset
        for k in self.__item.path:
            if not k in cur_grp:
                cur_grp[k] = {}
            cur_grp = cur_grp[k]
        cur_grp[self.__item.key] = deepcopy(self.__canvasdata)
        self.use_mark(1)

    def draw_marks(self):
        self.__markmap = []
        data = self.load_markdata_from_db(self.__imagehash)
        if data is None: return
        self.__data = data
        _,_,scale = self.__imagesize
        self.__markscalar = scale / data["scale"]
        markcount = 0
        if "marks" in data:
            count = 0
            for markset in data["marks"]:
                count += 1
                self.__markmap.append({})
                queue = [markset]
                while len(queue) > 0:
                    mark = queue.pop(0)
                    parent = ()
                    if "__parent__" in mark:
                        parent = mark["__parent__"]
                    for k,v in mark.items():
                        if k=="__parent__": continue
                        if "type" in v:
                            self.show_mark(count,parent,k,v)
                            markcount += 1
                        else:
                            v["__parent__"] = parent + (k,)
                            queue.append(v)
        if markcount > 0:
            self.mask(self.maskalpha)

    def show_mark(self,set,parent,key,markitem):
        pathkey = "/".join(parent + (key,))
        if not pathkey in self.__schema:
            return
        item = self.__schema[pathkey]
        color = item.color
        mark = MarkCanvasItem(set,self.__markscalar,
            **markitem, item=item,
            key=pathkey, color=color)
        id = mark.draw(self.canvas)
        self.__markmap[set-1][pathkey] = mark

    def find_mark(self,set,key):
        if set < 0 or set >= len(self.__markmap):
            return None
        marks = self.__markmap[set]
        if key in marks:
            return marks[key]
        return None

    def mask(self,alpha):
        if isinstance(alpha,float):
            alpha = int(alpha*255)
        self.canvas.delete("masklayer")
        if alpha <= 0:
            return
        if alpha > 255: alpha = 255
        w,h,_ = self.__imagesize
        image = Image.new("RGBA", (w,h), (255,255,255,alpha))
        if not self.__tkmask is None: del self.__tkmask
        self.__tkmask = ImageTk.PhotoImage(image)
        self.canvas.create_image(0,0,anchor="nw",
            image=self.__tkmask, tags="masklayer")
        self.canvas.lower("masklayer")
        self.canvas.lower("background")
        self.maskalpha = alpha

    def create_db(self):
        db_path = os.path.join(self.__rootdirectory,"/data.db")
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
            db.close()
        except sql.Error as e:
            print(e)

    def save_db(self):
        datetime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        db_path = os.path.join(self.__rootdirectory,"/data.db")
        json_str = json.dumps(self.__data)
        schema_str = json.dumps(self.__schemajson)
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
                    self.__imagehash, self.__imagename,
                    schema_id, json_str,
                    len(self.__marksets),
                    datetime
                )
            )
            db.commit()
            db.close()
        except sql.Error as e:
            print(e)

    def load_db(self,folder):
        return
        dbfile = os.path.join(folder,"data.db")
        if not os.path.isfile(dbfile): return False
        if not self.__database is None:
            del self.__database
        self.__database = {}
        try:
            db = sql.connect(dbfile)
            lines = db.execute("SELECT * FROM jsondata").fetchall()
            for line in lines:
                hash = line[0]
                self.__database[hash] = json.loads(line[3])
            db.close()
        except sql.Error as e:
            print(e)

    def load_markdata_from_db(self,imagehash):
        dbfile = os.path.join(self.__rootdirectory,"data.db")
        if not os.path.isfile(dbfile): return None
        try:
            db = sql.connect(dbfile)
            markdata = db.execute(
                "SELECT * FROM jsondata WHERE id=?",
                (imagehash,)).fetchone()
            if not markdata is None:
                self.__markdata[imagehash] = json.loads(markdata[3])
                schema_id = markdata[2]
                if not schema_id in self.__schemata:    
                    schema = db.execute(
                        "SELECT * FROM markschemata WHERE id=?",
                        (schema_id,)).fetchone()
                    self.__schemata[schema_id] = json.loads(schema[1])
                self.parse_schema(self.__schemata[schema_id])
            db.close()
        except sql.Error as e:
            print(e)
        if imagehash in self.__markdata:
            return self.__markdata[imagehash]
        return None

    def start_search(self):
        self.canvas.bind("<Motion>",self.search_move)

    def stop_search(self):
        self.canvas.unbind("<Motion>")

    def search_move(self,event):
        tags = self.canvas.gettags("current")
        print(tags)