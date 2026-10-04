#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edwin Combs
"""Duplicate Finder 1.2 — a single-file desktop app.
Run: python3 DuplicateFinder.py
Linux optional extras: sudo pacman -S tk python-pillow python-send2trash
Debian/Ubuntu: sudo apt install python3-tk python3-pil.imagetk python3-send2trash
Windows/macOS: python -m pip install Pillow Send2Trash (Tk included in python.org Python).
No packages are downloaded by this app. Pillow adds image previews; Send2Trash
adds OS trash support. Without trash support use Move to a holding folder.
Built-in tests: python3 DuplicateFinder.py --self-test
Exact byte duplicates only, not visually similar photos or re-encoded media.
Checks reduce accidental changes; a final filesystem check/action race remains.
Do not edit files concurrently with cleanup. Moves preserve metadata best-effort,
but do not promise preservation of ACLs, extended attributes or sparse allocation.
"""
from __future__ import annotations
import os, sys, stat, hashlib, threading, queue, subprocess, platform, shutil
from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict

VERSION = '1.2'
CHUNK = 1024 * 1024
class Cancelled(Exception): pass

def checkpoint(cancel):
    if cancel is not None and cancel.is_set(): raise Cancelled()

def signature(st):
    return st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns

@dataclass(frozen=True)
class Entry:
    path: str
    identity: tuple
    digest: str
    links: int = 1
    @property
    def size(self): return self.identity[2]
    @property
    def inode(self): return self.identity[:2]

def hash_checked(path, cancel=None, limit=None, expected=None):
    """Hash a regular file, checking descriptor and path identity on both sides."""
    checkpoint(cancel)
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode): raise ValueError('File is not a regular file (symlinks are excluded).')
    if expected is not None and signature(before) != expected: raise ValueError('File changed or was replaced since scanning.')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if signature(opened) != signature(before): raise ValueError('File changed while opening.')
        h = hashlib.sha256(); remaining = limit
        while remaining is None or remaining > 0:
            checkpoint(cancel)
            data = stream.read(CHUNK if remaining is None else min(CHUNK, remaining))
            if not data: break
            h.update(data)
            if remaining is not None: remaining -= len(data)
        after = os.fstat(stream.fileno())
    checkpoint(cancel)
    if signature(after) != signature(before) or signature(os.lstat(path)) != signature(before):
        raise ValueError('File changed while hashing; excluded from results.')
    return h.hexdigest(), signature(before), before.st_nlink

def verify(entry, cancel=None):
    digest, identity, _ = hash_checked(entry.path, cancel, expected=entry.identity)
    if digest != entry.digest: raise ValueError('Contents changed since scanning.')

def scan(folder, recursive=True, minimum=1, cancel=None, progress=None):
    folder = os.path.abspath(os.path.expanduser(folder))
    if not os.path.isdir(folder): raise ValueError('Choose an existing folder.')
    if minimum < 0: raise ValueError('Minimum size cannot be negative.')
    cancel = cancel or threading.Event(); errors=[]; candidates=[]; count=exempt=symlinks=0
    pending=[folder]; visited=set()
    def report(phase, done, total, path=''):
        if progress: progress(phase, done, total, path)
    while pending:
        checkpoint(cancel); current=pending.pop()
        try:
            st=os.stat(current); key=(st.st_dev,st.st_ino)
            if key in visited: continue
            visited.add(key)
            with os.scandir(current) as iterator:
                for child in iterator:
                    checkpoint(cancel)
                    try:
                        if child.is_symlink(): symlinks+=1; continue
                        if child.is_dir(follow_symlinks=False):
                            if recursive: pending.append(child.path)
                        elif child.is_file(follow_symlinks=False):
                            st=child.stat(follow_symlinks=False); count+=1
                            if st.st_size < minimum: exempt+=1
                            else: candidates.append((os.path.abspath(child.path),signature(st)))
                            if count % 50 == 0: report('Discovering files',count,None,child.path)
                    except OSError as e: errors.append(f'{child.path}: {e}')
        except OSError as e: errors.append(f'{current}: {e}')
    sizes=defaultdict(list)
    for path, identity in candidates: sizes[identity[2]].append((path,identity))
    jobs=[item for bucket in sizes.values() if len(bucket)>1 for item in bucket]
    total=len(jobs)*2; done=0; partial=defaultdict(list)
    for path, identity in jobs:
        checkpoint(cancel)
        try:
            digest,_,_=hash_checked(path,cancel,65536,identity)
            partial[(identity[2],digest)].append((path,identity))
        except (OSError,ValueError) as e: errors.append(f'{path}: {e}')
        done+=1; report('Checking file headers',done,total,path)
    fulljobs=[item for bucket in partial.values() if len(bucket)>1 for item in bucket]
    total=len(jobs)+len(fulljobs); groups=defaultdict(list)
    for path,identity in fulljobs:
        checkpoint(cancel)
        try:
            digest,identity,links=hash_checked(path,cancel,expected=identity)
            groups[(identity[2],digest)].append(Entry(path,identity,digest,links))
        except (OSError,ValueError) as e: errors.append(f'{path}: {e}')
        done+=1; report('Comparing full contents',done,total,path)
    report('Finished',total,total)
    result=[sorted(g,key=lambda e:e.path) for g in groups.values() if len(g)>1]
    result.sort(key=lambda g:(-g[0].size,g[0].path))
    return result,errors,{'files':count,'exempt':exempt,'symlinks':symlinks}

def precheck(target, group, keepers, cancel=None):
    if target not in group: raise ValueError('Target is not in this group.')
    if not keepers or any(k not in group for k in keepers): raise ValueError('Keep at least one valid copy in this group.')
    if target in keepers: raise ValueError('Cannot remove a retained copy.')
    if any(k.digest != target.digest or k.size != target.size for k in keepers): raise ValueError('Retained files do not match the target.')
    for keeper in keepers: verify(keeper,cancel)
    verify(target,cancel)

# Trash is never implemented as permanent unlink. Failure always preserves source.
def trash_path(path):
    try: from send2trash import send2trash
    except ImportError: raise RuntimeError('Trash support is unavailable. Install Send2Trash or use Move to a holding folder.')
    send2trash(path)

def act(target, group, keepers, mode, destination='', cancel=None):
    precheck(target,group,keepers,cancel)
    if mode=='trash':
        checkpoint(cancel); trash_path(target.path); return None
    if mode!='move': raise ValueError('Unknown action.')
    if not destination.strip(): raise ValueError('Choose a destination folder.')
    destdir=Path(destination).expanduser().absolute()
    if not destdir.is_dir(): raise ValueError('Destination folder does not exist.')
    if destdir.resolve()==Path(target.path).parent.resolve(): raise ValueError('Choose a different destination folder.')
    source=Path(target.path); dest=destdir/source.name; index=0
    while True:
        checkpoint(cancel)
        try: output=dest.open('xb'); break
        except FileExistsError:
            index+=1; dest=destdir/f'{source.stem}_dup{index}{source.suffix}'
    # Exclusive creation protects existing destinations even if one appears concurrently.
    reserved=signature(os.fstat(output.fileno()))[:2]; committed=False
    try:
        with output:
            flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)|getattr(os,'O_NONBLOCK',0)
            with os.fdopen(os.open(target.path,flags),'rb') as incoming:
                if signature(os.fstat(incoming.fileno()))!=target.identity: raise ValueError('Source changed before copying.')
                h=hashlib.sha256()
                while True:
                    checkpoint(cancel); chunk=incoming.read(CHUNK)
                    if not chunk: break
                    output.write(chunk); h.update(chunk)
                if h.hexdigest()!=target.digest or signature(os.fstat(incoming.fileno()))!=target.identity:
                    raise ValueError('Source changed during copying.')
            output.flush(); os.fsync(output.fileno())
        # Verify the destination bytes too before removing the source.
        copied,_,_=hash_checked(str(dest),cancel)
        if signature(os.lstat(dest))[:2]!=reserved or copied!=target.digest: raise ValueError('Destination changed during copying.')
        try: shutil.copystat(target.path,dest,follow_symlinks=False)
        except OSError: pass
        precheck(target,group,keepers,cancel)
        checkpoint(cancel); os.unlink(target.path); committed=True
        return str(dest)
    finally:
        if not committed:
            try:
                if signature(os.lstat(dest))[:2]==reserved: os.unlink(dest)
            except OSError: pass

def open_external(path):
    path=os.path.abspath(path)
    if platform.system()=='Windows': os.startfile(path); return
    command=['open' if platform.system()=='Darwin' else 'xdg-open',path]
    result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=20)
    if result.returncode: raise RuntimeError(result.stderr.decode(errors='replace') or 'Viewer could not open the file.')

def human(size):
    for unit in ['B','KiB','MiB','GiB','TiB']:
        if size<1024 or unit=='TiB': return f'{size:,.0f} {unit}' if unit=='B' else f'{size:,.1f} {unit}'
        size/=1024

class App:
    def __init__(self,root):
        import tkinter as tk
        from tkinter import ttk
        self.tk=tk; self.ttk=ttk; self.root=root; self.events=queue.Queue(); self.cancel=threading.Event()
        self.groups=[]; self.errors=[]; self.rows={}; self.marked=set(); self.busy=False; self.photo=None; self.preview_generation=0
        root.title('Duplicate Finder '+VERSION); root.geometry(f'{min(1320,root.winfo_screenwidth()-60)}x{min(900,root.winfo_screenheight()-80)}'); root.minsize(1000,700)
        style=ttk.Style(); style.theme_use('clam')
        style.configure('TFrame',background='#f4f6fa'); style.configure('TLabel',background='#f4f6fa',foreground='#25334a')
        style.configure('Title.TLabel',font=('Arial',22,'bold')); style.configure('Accent.TButton',font=('Arial',11,'bold'),padding=9)
        style.configure('Treeview',rowheight=28,font=('Arial',10)); style.configure('Treeview.Heading',font=('Arial',10,'bold'))
        outer=ttk.Frame(root,padding=18); outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='Duplicate Finder',style='Title.TLabel').pack(anchor='w')
        ttk.Label(outer,text='Find identical contents. Preview a file, then select the copies you want to remove.').pack(anchor='w',pady=(4,14))
        settings=ttk.Frame(outer); settings.pack(fill='x')
        self.folder=tk.StringVar(value=str(Path.home())); self.recursive=tk.BooleanVar(value=True); self.minimum=tk.StringVar(value='1'); self.unit=tk.StringVar(value='KiB')
        ttk.Label(settings,text='Folder').grid(row=0,column=0,padx=(0,8))
        ttk.Entry(settings,textvariable=self.folder).grid(row=0,column=1,sticky='ew')
        self.browse=ttk.Button(settings,text='Browse...',command=self.choose_folder); self.browse.grid(row=0,column=2,padx=8)
        self.scanbutton=ttk.Button(settings,text='Scan folder',style='Accent.TButton',command=self.start_scan); self.scanbutton.grid(row=0,column=3)
        settings.columnconfigure(1,weight=1)
        options=ttk.Frame(outer); options.pack(fill='x',pady=12)
        ttk.Checkbutton(options,text='Include subfolders',variable=self.recursive).pack(side='left')
        ttk.Label(options,text='Ignore files smaller than').pack(side='left',padx=(24,8))
        ttk.Entry(options,textvariable=self.minimum,width=9).pack(side='left')
        ttk.Combobox(options,textvariable=self.unit,values=['B','KiB','MiB','GiB'],width=6,state='readonly').pack(side='left',padx=6)
        self.cancelbutton=ttk.Button(options,text='Cancel',command=self.cancel.set,state='disabled'); self.cancelbutton.pack(side='right')
        self.status=tk.StringVar(value='Choose a folder to begin. Symlinks are excluded.'); ttk.Label(outer,textvariable=self.status).pack(anchor='w')
        self.bar=ttk.Progressbar(outer); self.bar.pack(fill='x',pady=(7,12))
        panes=ttk.Panedwindow(outer,orient='horizontal'); panes.pack(fill='both',expand=True)
        left=ttk.Frame(panes); right=ttk.Frame(panes,padding=(14,0,0,0)); panes.add(left,weight=1); panes.add(right,weight=1)
        root.after(100, lambda: panes.sashpos(0, max(420, int(panes.winfo_width() * .50))))
        self.tree=ttk.Treeview(left,columns=('pick','size','path'),show='tree headings',selectmode='browse')
        # Draw checkbox icons with pixels, never a Unicode glyph from a font.
        self.check_icons={}
        for checked in (False,True):
            icon=tk.PhotoImage(master=root,width=18,height=18)
            icon.put('#ffffff',to=(1,1,17,17))
            for rectangle in [(1,1,17,2),(1,16,17,17),(1,1,2,17),(16,1,17,17)]:
                icon.put('#8a96a8',to=rectangle)
            if checked:
                for start,end in [((4,9),(7,12)),((7,12),(13,5))]:
                    steps=max(abs(end[0]-start[0]),abs(end[1]-start[1]))
                    for n in range(steps+1):
                        x=round(start[0]+(end[0]-start[0])*n/steps);y=round(start[1]+(end[1]-start[1])*n/steps)
                        icon.put('#16803c',to=(x,y,x+2,y+2))
            self.check_icons[checked]=icon
        self.tree.heading('#0',text='File / duplicate group'); self.tree.column('#0',width=210,minwidth=130)
        for col,label,width in [('pick','Remove?',80),('size','Size',85),('path','Location',310)]:
            self.tree.heading(col,text=label); self.tree.column(col,width=width,minwidth=60,stretch=col=='path')
        scroll=ttk.Scrollbar(left,orient='vertical',command=self.tree.yview); self.tree.configure(yscrollcommand=scroll.set)
        self.tree.grid(row=0,column=0,sticky='nsew'); scroll.grid(row=0,column=1,sticky='ns'); left.rowconfigure(0,weight=1); left.columnconfigure(0,weight=1)
        horizontal=ttk.Scrollbar(left,orient='horizontal',command=self.tree.xview); horizontal.grid(row=1,column=0,sticky='ew'); self.tree.configure(xscrollcommand=horizontal.set)
        self.tree.bind('<<TreeviewSelect>>',self.preview); self.tree.bind('<Button-1>',self.click); self.tree.bind('<space>',self.toggle)
        self.previewtitle=tk.StringVar(value='File preview'); ttk.Label(right,textvariable=self.previewtitle,font=('Arial',13,'bold')).pack(anchor='w')
        self.imagelabel=ttk.Label(right,anchor='center'); self.imagelabel.pack(fill='x',pady=8)
        self.text=tk.Text(right,width=45,height=12,wrap='word',font=('Arial',11),background='white',relief='flat',padx=12,pady=12,state='disabled'); self.text.pack(fill='both',expand=True)
        self.openbutton=ttk.Button(right,text='Open in default viewer',command=self.external,state='disabled'); self.openbutton.pack(fill='x',pady=(8,0))
        bottom=ttk.Frame(outer); bottom.pack(fill='x',pady=(14,0))
        self.selectbutton=ttk.Button(bottom,text='Select extra copies',command=self.select_extras); self.selectbutton.pack(side='left')
        self.clearbutton=ttk.Button(bottom,text='Clear selection',command=self.clear); self.clearbutton.pack(side='left',padx=8)
        self.errorsbutton=ttk.Button(bottom,text='Scan errors',command=self.show_errors); self.errorsbutton.pack(side='left')
        self.movebutton=ttk.Button(bottom,text='Move selected...',command=lambda:self.start_action('move')); self.movebutton.pack(side='right')
        self.trashbutton=ttk.Button(bottom,text='Trash selected...',command=lambda:self.start_action('trash')); self.trashbutton.pack(side='right',padx=8)
        self.selection=tk.StringVar(value='0 selected'); ttk.Label(outer,textvariable=self.selection).pack(anchor='w',pady=(8,0))
        self.set_text('Select a file to see its contents or an image preview. Audio and video open in your default player.\n\nCleanup always retains a copy. Permanent deletion is not offered.\n\nImage previews use optional Pillow. Trash uses optional Send2Trash. Use Move if trash support is unavailable.')
        # Fixed control rows surround the expanding results area.
        outer_widgets=outer.winfo_children()
        for widget in outer_widgets: widget.pack_forget()
        for row, widget in enumerate(outer_widgets):
            widget.grid(row=row,column=0,sticky='nsew',pady=(0,10) if row < 6 else (0,0))
        outer.columnconfigure(0,weight=1); outer.rowconfigure(6,weight=1)
        right_widgets=right.winfo_children()
        for widget in right_widgets: widget.pack_forget()
        for row, widget in enumerate(right_widgets):
            widget.grid(row=row,column=0,sticky='nsew',pady=(0,8))
        right.columnconfigure(0,weight=1);right.rowconfigure(1,weight=0);right.rowconfigure(2,weight=1);self.imagelabel.grid_remove()
        root.protocol('WM_DELETE_WINDOW',self.close); root.after(80,self.poll)
    def set_text(self,text):
        self.text.configure(state='normal'); self.text.delete('1.0','end'); self.text.insert('1.0',text); self.text.configure(state='disabled')
    def choose_folder(self):
        from tkinter import filedialog
        folder=filedialog.askdirectory(initialdir=self.folder.get())
        if folder:self.folder.set(folder)
    def set_busy(self,busy):
        self.busy=busy
        for button in [self.scanbutton,self.browse,self.selectbutton,self.clearbutton,self.movebutton,self.trashbutton]: button.configure(state='disabled' if busy else 'normal')
        self.cancelbutton.configure(state='normal' if busy else 'disabled')
    def start_scan(self):
        from tkinter import messagebox
        if self.busy:return
        try:
            value=float(self.minimum.get())
            if not __import__('math').isfinite(value) or value<0:raise ValueError()
            minimum=int(value*1024**['B','KiB','MiB','GiB'].index(self.unit.get()))
            folder=os.path.abspath(os.path.expanduser(self.folder.get()))
            if not os.path.isdir(folder):raise ValueError()
        except (ValueError,OverflowError):messagebox.showerror('Invalid settings','Choose an existing folder and a non-negative minimum size.'); return
        recursive=self.recursive.get(); self.cancel=threading.Event(); self.set_busy(True); self.marked.clear(); self.groups=[]; self.errors=[]; self.rows={}; self.tree.delete(*self.tree.get_children()); self.update_selection()
        self.status.set('Discovering files...'); self.bar.configure(mode='indeterminate'); self.bar.start(12)
        def worker():
            try:
                last=[0.0]
                def progress(phase,done,total,path=''):
                    import time
                    now=time.monotonic()
                    if now-last[0]>.08 or phase=='Finished': self.events.put(('progress',(phase,done,total)));last[0]=now
                self.events.put(('scan',scan(folder,recursive,minimum,self.cancel,progress)))
            except Cancelled:self.events.put(('cancelled',None))
            except Exception as e:self.events.put(('error',str(e)))
        threading.Thread(target=worker,daemon=True).start()
    def populate(self):
        self.tree.delete(*self.tree.get_children()); self.rows={}; self.marked.clear()
        for gi,group in enumerate(self.groups):
            parent=self.tree.insert('','end',iid=f'g{gi}',text=f'Set {gi+1} · {len(group)} files',open=True)
            for i,entry in enumerate(group):
                iid=f'f{gi}-{i}'; self.rows[iid]=(gi,entry)
                linked=' [hard link]' if entry.links>1 else ''
                self.tree.insert(parent,'end',iid=iid,text=Path(entry.path).name+linked,image=self.check_icons[False],values=('Keep',human(entry.size),str(Path(entry.path).parent)))
        self.update_selection()
    def update_selection(self):
        for iid,(gi,entry) in self.rows.items():
            checked=entry.path in self.marked
            self.tree.set(iid,'pick','Remove' if checked else 'Keep')
            self.tree.item(iid,image=self.check_icons[checked])
        self.selection.set(f'{len(self.marked)} selected · at least one file in every group must stay')
    def click(self,event):
        if self.tree.identify_column(event.x)=='#1' or self.tree.identify_element(event.x,event.y) in ('Treeitem.image','image'):
            iid=self.tree.identify_row(event.y)
            if iid:self.tree.selection_set(iid); self.toggle()
    def toggle(self,event=None):
        from tkinter import messagebox
        if self.busy:return 'break'
        selected=self.tree.selection()
        if not selected or selected[0] not in self.rows:return 'break'
        gi,entry=self.rows[selected[0]]
        if entry.path in self.marked:self.marked.remove(entry.path)
        elif sum(e.path not in self.marked for e in self.groups[gi])<=1:messagebox.showinfo('Keep one copy','At least one copy in this group must remain.');return 'break'
        else:self.marked.add(entry.path)
        self.update_selection();return 'break'
    def select_extras(self):
        if self.busy:return
        # Select individual regular copies only; leave hard-linked names for manual review.
        self.marked.clear()
        for group in self.groups:
            for entry in group[1:]:
                if entry.links==1:self.marked.add(entry.path)
        self.update_selection()
    def clear(self):
        self.marked.clear(); self.update_selection()
    def selected_entry(self):
        selected=self.tree.selection();return self.rows.get(selected[0],(None,None))[1] if selected else None
    def preview(self,event=None):
        entry=self.selected_entry(); self.preview_generation+=1; generation=self.preview_generation
        self.photo=None; self.imagelabel.configure(image='');self.imagelabel.grid_remove();self.imagelabel.master.rowconfigure(1,weight=0);self.imagelabel.master.rowconfigure(2,weight=1);self.text.configure(height=12); self.openbutton.configure(state='normal' if entry else 'disabled')
        if not entry:self.previewtitle.set('File preview');self.set_text('Select a file in a duplicate group.');return
        self.previewtitle.set(Path(entry.path).name); self.set_text(f'{entry.path}\n{human(entry.size)}\n\nLoading preview...')
        preview_width=max(260,self.imagelabel.master.winfo_width()-24)
        preview_height=max(160,min(460,self.imagelabel.master.winfo_height()//2))
        def worker():
            try:
                ext=Path(entry.path).suffix.lower(); image=None
                if ext in {'.png','.jpg','.jpeg','.gif','.bmp','.webp','.tif','.tiff'}:
                    try:
                        from PIL import Image
                        with Image.open(entry.path) as source:
                            if source.width*source.height>30_000_000:raise ValueError('Image too large for embedded preview; open in default viewer.')
                            source.thumbnail((preview_width,preview_height));image=source.copy()
                        content='Image preview. Open in default viewer for full resolution.'
                    except ImportError:content='Install Pillow for embedded image previews, or use Open in default viewer.'
                elif ext in {'.mp4','.mkv','.avi','.mov','.webm','.mp3','.flac','.ogg','.wav','.m4a','.pdf','.cbz','.cbr'}:
                    content='Use Open in default viewer to read or play this file.'
                else:
                    with open(entry.path,'rb') as stream:data=stream.read(64001)
                    if b'\x00' in data[:1024]:content='Binary data (first 256 bytes):\n\n'+data[:256].hex(' ')
                    else:
                        lines=data[:64000].decode('utf-8','replace').splitlines();content='\n'.join(lines[:100])
                        if len(data)>64000 or len(lines)>100:content+='\n\n[Preview truncated]'
                self.events.put(('preview',(generation,entry,content,image)))
            except Exception as e:self.events.put(('preview',(generation,entry,f'Preview unavailable: {e}',None)))
        threading.Thread(target=worker,daemon=True).start()
    def external(self):
        entry=self.selected_entry()
        if not entry:return
        def worker():
            try:open_external(entry.path)
            except Exception as e:self.events.put(('viewer_error',str(e)))
        threading.Thread(target=worker,daemon=True).start()
    def start_action(self,mode):
        from tkinter import filedialog,messagebox
        if self.busy:return
        targets=[(entry,group,[k for k in group if k.path not in self.marked]) for group in self.groups for entry in group if entry.path in self.marked]
        if not targets:messagebox.showinfo('No files selected','Click Remove? beside a file, or use Select extra copies.');return
        destination=''
        if mode=='trash':
            try:import send2trash
            except ImportError:messagebox.showerror('Trash unavailable','Install Send2Trash, or choose Move selected to put the copies in a holding folder.');return
        else:
            destination=filedialog.askdirectory(title='Choose a holding folder')
            if not destination:return
        # Review every exact target and keeper in a scrollable modal before enabling action.
        dialog=self.tk.Toplevel(self.root); dialog.title('Review selected files'); dialog.geometry('920x650'); dialog.minsize(700,440); dialog.transient(self.root);dialog.grab_set()
        frame=self.ttk.Frame(dialog,padding=16);frame.pack(fill='both',expand=True)
        self.ttk.Label(frame,text=f'{"Trash" if mode=="trash" else "Move"} {len(targets)} selected file(s)?',font=('Arial',15,'bold')).pack(anchor='w')
        frame.columnconfigure(0,weight=1); frame.rowconfigure(1,weight=1)
        # Grid reserves a dedicated footer; the scrollable list cannot cover buttons.
        header=frame.winfo_children()[0]; header.pack_forget(); header.grid(row=0,column=0,sticky='w',pady=(0,12))
        listframe=self.ttk.Frame(frame);listframe.grid(row=1,column=0,sticky='nsew')
        listframe.columnconfigure(0,weight=1);listframe.rowconfigure(0,weight=1)
        review=self.tk.Text(listframe,wrap='word',width=60,height=15,padx=10,pady=10)
        review.grid(row=0,column=0,sticky='nsew')
        scrollbar=self.ttk.Scrollbar(listframe,command=review.yview)
        review.configure(yscrollcommand=scrollbar.set);scrollbar.grid(row=0,column=1,sticky='ns')
        footer=self.ttk.Frame(frame,padding=(0,14,0,0));footer.grid(row=2,column=0,sticky='ew')
        lines=[f'Destination: {destination}' if destination else 'Files will go to the operating system trash.','Only the listed paths will be acted on. Hard-link aliases are never automatically removed.','']
        for entry,group,keepers in targets:lines.extend([f'REMOVE: {entry.path}','KEEP: '+ '\nKEEP: '.join(k.path for k in keepers),''])
        review.insert('1.0','\n'.join(lines));review.configure(state='disabled')
        def confirmed():
            dialog.destroy();self.run_actions(targets,mode,destination)
        self.ttk.Button(footer,text='Cancel',command=dialog.destroy).pack(side='left')
        self.ttk.Button(footer,text='Confirm '+('trash' if mode=='trash' else 'move'),style='Accent.TButton',command=confirmed).pack(side='right')
        dialog.bind('<Escape>',lambda e:dialog.destroy())
    def run_actions(self,targets,mode,destination):
        self.cancel=threading.Event();self.set_busy(True);self.bar.configure(mode='determinate',value=0,maximum=len(targets));self.status.set('Rechecking files before cleanup...')
        def worker():
            succeeded=[];failed=[]
            for i,(entry,group,keepers) in enumerate(targets):
                if self.cancel.is_set():break
                try:final=act(entry,group,keepers,mode,destination,self.cancel);succeeded.append((entry.path,final))
                except Cancelled:break
                except Exception as e:failed.append(f'{entry.path}: {e}')
                self.events.put(('action_progress',(i+1,len(targets))))
            self.events.put(('actions',(succeeded,failed,self.cancel.is_set())))
        threading.Thread(target=worker,daemon=True).start()
    def show_errors(self):
        from tkinter import messagebox
        if not self.errors:messagebox.showinfo('Scan errors','No errors recorded for the last completed scan.');return
        self.show_report('Scan errors','\n\n'.join(self.errors))
    def show_report(self,title,text):
        win=self.tk.Toplevel(self.root);win.title(title);win.geometry('800x480')
        widget=self.tk.Text(win,wrap='word');widget.pack(side='left',fill='both',expand=True)
        scroll=self.ttk.Scrollbar(win,command=widget.yview);scroll.pack(side='right',fill='y');widget.configure(yscrollcommand=scroll.set);widget.insert('1.0',text);widget.configure(state='disabled')
    def poll(self):
        from tkinter import messagebox
        try:
            while True:
                kind,data=self.events.get_nowait()
                if kind=='progress':
                    phase,done,total=data;self.status.set(f'{phase} · {done:,}'+(f' / {total:,}' if total else ''))
                    if total is not None:self.bar.stop();self.bar.configure(mode='determinate',maximum=max(total,1),value=done)
                elif kind=='scan':
                    self.bar.stop();self.set_busy(False);self.groups,self.errors,counts=data;self.populate()
                    self.status.set(f'{counts["files"]:,} files · {len(self.groups):,} duplicate groups · {counts["exempt"]:,} below minimum · {len(self.errors)} errors'+(' — scan incomplete; inspect errors' if self.errors else ''))
                elif kind in ('cancelled','error'):
                    self.bar.stop();self.set_busy(False);self.status.set('Scan cancelled. No files changed.' if kind=='cancelled' else 'Scan failed.')
                    if kind=='error':messagebox.showerror('Scan failed',data)
                elif kind=='preview':
                    generation,entry,content,picture=data
                    if generation==self.preview_generation:
                        self.set_text(f'{entry.path}\n{human(entry.size)}\n\n{content}')
                        if picture is not None:
                            from PIL import ImageTk
                            self.photo=ImageTk.PhotoImage(picture);self.imagelabel.configure(image=self.photo);self.imagelabel.grid();self.imagelabel.master.rowconfigure(1,weight=1);self.imagelabel.master.rowconfigure(2,weight=0);self.text.configure(height=6)
                elif kind=='viewer_error':messagebox.showerror('Could not open file',data)
                elif kind=='action_progress':self.bar.configure(value=data[0]);self.status.set(f'Cleanup · {data[0]} / {data[1]}')
                elif kind=='actions':
                    succeeded,failed,cancelled=data;self.set_busy(False)
                    # Every cleanup invalidates the scan, including inode metadata of hard links.
                    self.groups=[];self.rows={};self.marked.clear();self.tree.delete(*self.tree.get_children());self.update_selection();self.preview_generation+=1
                    self.status.set(f'{len(succeeded)} completed · {len(failed)} failed'+(' · cancelled' if cancelled else '')+' · rescan before further cleanup')
                    report=['COMPLETED: '+p+(f' → {dest}' if dest else '') for p,dest in succeeded]+['FAILED: '+error for error in failed]
                    if cancelled:report.append('Cancelled. Completed actions remain applied.')
                    self.show_report('Cleanup results','\n\n'.join(report) or 'Cancelled. No actions completed.')
        except queue.Empty:pass
        self.root.after(80,self.poll)
    def close(self):
        from tkinter import messagebox
        if self.busy:
            self.cancel.set();messagebox.showinfo('Cancelling','Cancellation requested. Wait for the operation to stop, then close the window.');return
        self.root.destroy()

def self_test():
    import unittest,tempfile
    from unittest.mock import patch
    class Tests(unittest.TestCase):
        def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.p=Path(self.tmp.name)
        def files(self):
            for n in ['a','b']:(self.p/n).write_bytes(b'same')
            return scan(str(self.p))[0][0]
        def test_names_and_recursion(self):
            self.files();(self.p/'sub').mkdir();(self.p/'sub'/'renamed').write_bytes(b'same')
            self.assertEqual(len(scan(str(self.p))[0][0]),3);self.assertEqual(len(scan(str(self.p),False)[0][0]),2)
        def test_minimum(self):self.files();self.assertFalse(scan(str(self.p),minimum=5)[0]);self.assertTrue(scan(str(self.p),minimum=4)[0])
        def test_full_hash(self):
            for n,tail in [('a',b'a'),('b',b'b')]:(self.p/n).write_bytes(b'x'*65536+tail)
            self.assertFalse(scan(str(self.p))[0])
        def test_cancel_mid_hash(self):
            self.files();token=threading.Event()
            def progress(*args):token.set()
            with self.assertRaises(Cancelled):scan(str(self.p),cancel=token,progress=progress)
        def test_progress_bounded(self):
            self.files();events=[];scan(str(self.p),progress=lambda *e:events.append(e))
            self.assertTrue(all(e[2] is None or e[1]<=e[2] for e in events))
        def test_missing_keeper(self):
            group=self.files();os.unlink(group[1].path)
            with self.assertRaises(OSError):act(group[0],group,[group[1]],'move',str(self.p))
            self.assertTrue(Path(group[0].path).exists())
        def test_empty_keeper(self):
            g=self.files()
            with self.assertRaises(ValueError):act(g[0],g,[],'trash')
        def test_changed_source(self):
            g=self.files();Path(g[0].path).write_bytes(b'changed')
            with self.assertRaises(ValueError):act(g[0],g,[g[1]],'trash')
        def test_changed_keeper(self):
            g=self.files();Path(g[1].path).write_bytes(b'changed')
            with self.assertRaises(ValueError):act(g[0],g,[g[1]],'trash')
        def test_trash_failure(self):
            g=self.files()
            with patch(__name__+'.trash_path',side_effect=RuntimeError('unavailable')):
                with self.assertRaises(RuntimeError):act(g[0],g,[g[1]],'trash')
            self.assertTrue(Path(g[0].path).exists())
        def test_move_collision(self):
            g=self.files();dest=self.p/'holding folder';dest.mkdir();(dest/'a').write_bytes(b'unrelated')
            final=act(g[0],g,[g[1]],'move',str(dest));self.assertEqual((dest/'a').read_bytes(),b'unrelated');self.assertEqual(Path(final).read_bytes(),b'same');self.assertFalse(Path(g[0].path).exists())
        def test_replaced_symlink(self):
            if not hasattr(os,'symlink'):self.skipTest('symlinks unavailable')
            g=self.files();os.unlink(g[0].path);os.symlink(g[1].path,g[0].path)
            with self.assertRaises(ValueError):act(g[0],g,[g[1]],'trash')
            self.assertTrue(os.path.islink(g[0].path))
        def test_hardlink_alias_never_removed(self):
            if not hasattr(os,'link'):self.skipTest('hardlinks unavailable')
            g=self.files();os.link(self.p/'a',self.p/'alias');g=scan(str(self.p))[0][0]
            target=next(e for e in g if Path(e.path).name=='a');keeper=next(e for e in g if Path(e.path).name=='b')
            def fake_trash(path):os.unlink(path)
            with patch(__name__+'.trash_path',side_effect=fake_trash):act(target,g,[keeper],'trash')
            self.assertTrue((self.p/'alias').exists())
        def test_symlink_cycle_skipped(self):
            self.files();os.symlink(self.p,self.p/'cycle');result=scan(str(self.p));self.assertEqual(result[2]['symlinks'],1)
        def test_cross_group_keeper(self):
            g=self.files();other=Entry(g[1].path,g[1].identity,'wrong')
            with self.assertRaises(ValueError):act(g[0],g,[other],'trash')
        def test_destination_appears_concurrently(self):
            g=self.files();dest=self.p/'dest';dest.mkdir();original=Path.open;injected=[False]
            def racing_open(path,*args,**kwargs):
                if path==dest/'a' and args and args[0]=='xb' and not injected[0]:
                    injected[0]=True
                    with original(path,'wb') as stream:stream.write(b'unrelated')
                return original(path,*args,**kwargs)
            with patch.object(Path,'open',racing_open):final=act(g[0],g,[g[1]],'move',str(dest))
            self.assertEqual((dest/'a').read_bytes(),b'unrelated');self.assertEqual(Path(final).read_bytes(),b'same')
        def test_copy_failure_preserves_source(self):
            g=self.files();dest=self.p/'dest';dest.mkdir()
            with patch('os.fsync',side_effect=OSError('disk failure')):
                with self.assertRaises(OSError):act(g[0],g,[g[1]],'move',str(dest))
            self.assertTrue(Path(g[0].path).exists());self.assertEqual(list(dest.iterdir()),[])
        def test_keeper_cannot_be_target(self):
            g=self.files()
            with self.assertRaises(ValueError):act(g[0],g,[g[0]],'trash')
        def test_dangling_destination(self):
            g=self.files();dest=self.p/'dest';dest.mkdir();os.symlink(dest/'missing',dest/'a')
            final=act(g[0],g,[g[1]],'move',str(dest));self.assertTrue(os.path.islink(dest/'a'));self.assertEqual(Path(final).read_bytes(),b'same')
        def test_windows_opener_avoids_shell(self):
            with patch('platform.system',return_value='Windows'),patch.object(os,'startfile',create=True) as opener:
                open_external(str(self.p/'file & name.txt'));opener.assert_called_once_with(str(self.p/'file & name.txt'))
        def test_move_cancel_preserves_source(self):
            g=self.files();dest=self.p/'dest';dest.mkdir();cancel=threading.Event();cancel.set()
            with self.assertRaises(Cancelled):act(g[0],g,[g[1]],'move',str(dest),cancel)
            self.assertTrue(Path(g[0].path).exists());self.assertEqual(list(dest.iterdir()),[])
        def test_changed_during_hash(self):
            g=self.files();original=checkpoint;calls=[0]
            def mutate(token):
                calls[0]+=1
                if calls[0]==3:Path(g[0].path).write_bytes(b'other')
                original(token)
            with patch(__name__+'.checkpoint',side_effect=mutate):
                with self.assertRaises(ValueError):hash_checked(g[0].path)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    return 0 if result.wasSuccessful() else 1

def main():
    if '--self-test' in sys.argv:return self_test()
    try:
        import tkinter as tk
        root=tk.Tk();App(root);root.mainloop();return 0
    except ImportError:
        print('Tkinter is required. CachyOS: sudo pacman -S tk\nDebian/Ubuntu: sudo apt install python3-tk',file=sys.stderr);return 1
    except Exception as e:
        print(f'Cannot start Duplicate Finder: {e}',file=sys.stderr);return 1
if __name__=='__main__':raise SystemExit(main())
