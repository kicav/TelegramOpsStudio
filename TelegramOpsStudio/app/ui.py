from __future__ import annotations

import asyncio
from pathlib import Path

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QGridLayout,
    QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem, QTextEdit,
    QVBoxLayout, QWidget,
)

from .config import APP_NAME, APP_VERSION, SESSIONS_DIR, ensure_dirs
from .credentials import delete_api_hash
from .db import Database
from .exporter import export_csv, export_xlsx, import_xlsx
from .license_updater import check_update, read_license
from .tasks import AsyncTask
from .telegram_service import authorize_account, InviteService, JoinService, MessengerService, ScannerService, MessageArchiveService, ScriptService


def table_set(table: QTableWidget, rows, cols):
    table.clear()
    table.setColumnCount(len(cols))
    table.setHorizontalHeaderLabels(cols)
    table.setRowCount(len(rows))
    for r, row in enumerate(rows):
        for c, key in enumerate(cols):
            value = row[key] if hasattr(row, "keys") and key in row.keys() else row.get(key, "")
            table.setItem(r, c, QTableWidgetItem(str(value if value is not None else "")))
    table.resizeColumnsToContents()


class AccountCombo(QComboBox):
    def __init__(self, db: Database):
        super().__init__(); self.db = db; self.reload()
    def reload(self):
        current = self.currentData()
        self.clear()
        for a in self.db.accounts():
            self.addItem(f"{a['phone']}  @{a['username']}", a["id"])
        if current:
            i = self.findData(current)
            if i >= 0: self.setCurrentIndex(i)


class DashboardTab(QWidget):
    def __init__(self, db):
        super().__init__(); self.db = db; self.labels = {}
        lay = QVBoxLayout(self)
        title = QLabel("Telegram Ops Studio — Dashboard"); title.setStyleSheet("font-size:22px;font-weight:700")
        lay.addWidget(title)
        grid = QGridLayout(); lay.addLayout(grid)
        names = [("accounts","Accounts"),("members","Members"),("opted_in","Opted-in"),("jobs","Jobs"),("success_actions","Successful actions")]
        for i,(key,label) in enumerate(names):
            box=QGroupBox(label); v=QVBoxLayout(box); n=QLabel("0"); n.setAlignment(Qt.AlignCenter); n.setStyleSheet("font-size:26px;font-weight:700"); v.addWidget(n); grid.addWidget(box,i//3,i%3); self.labels[key]=n
        b=QPushButton("Refresh"); b.clicked.connect(self.refresh); lay.addWidget(b); lay.addStretch(); self.refresh()
    def refresh(self):
        for k,v in self.db.stats().items(): self.labels[k].setText(str(v))


class AccountsTab(QWidget):
    def __init__(self, db):
        super().__init__(); self.db=db
        lay=QVBoxLayout(self)
        form=QFormLayout(); self.phone=QLineEdit(); self.api_id=QLineEdit(); self.api_hash=QLineEdit(); self.api_hash.setEchoMode(QLineEdit.Password)
        form.addRow("Phone",self.phone); form.addRow("API ID",self.api_id); form.addRow("API Hash",self.api_hash); lay.addLayout(form)
        buttons=QHBoxLayout(); auth=QPushButton("Authorize / Add session"); auth.clicked.connect(self.authorize); delete=QPushButton("Delete selected"); delete.clicked.connect(self.delete_selected); proxy=QPushButton("Static proxy"); proxy.clicked.connect(self.proxy_dialog); buttons.addWidget(auth); buttons.addWidget(proxy); buttons.addWidget(delete); lay.addLayout(buttons)
        self.table=QTableWidget(); lay.addWidget(self.table); self.refresh()
    def refresh(self): table_set(self.table,self.db.accounts(),["id","phone","username","display_name","status","proxy_type","proxy_host","proxy_port"])
    def authorize(self):
        try: api_id=int(self.api_id.text().strip()); phone=self.phone.text().strip(); api_hash=self.api_hash.text().strip()
        except ValueError: QMessageBox.warning(self,"Input","API ID must be an integer"); return
        if not phone or not api_hash: QMessageBox.warning(self,"Input","Phone and API Hash are required"); return
        ensure_dirs(); session=str(SESSIONS_DIR / phone.replace("+","").replace(" ",""))
        def code_provider(): return QInputDialog.getText(self,"Telegram code","Enter login code")[0]
        def pass_provider(): return QInputDialog.getText(self,"2FA","Enter 2FA password",QLineEdit.Password)[0]
        try:
            asyncio.run(authorize_account(self.db,phone,api_id,api_hash,session,code_provider,pass_provider))
            self.refresh(); QMessageBox.information(self,"Account","Authorized successfully")
        except Exception as e: QMessageBox.critical(self,"Authorization failed",str(e))
    def _selected_id(self):
        r=self.table.currentRow(); return int(self.table.item(r,0).text()) if r>=0 else None
    def delete_selected(self):
        i=self._selected_id()
        if not i:return
        a=self.db.account(i); delete_api_hash(a["phone"]); self.db.delete_account(i); self.refresh()
    def proxy_dialog(self):
        i=self._selected_id()
        if not i: return
        text,ok=QInputDialog.getText(self,"Static proxy","type,host,port,user,password\nExample: socks5,127.0.0.1,1080,,")
        if ok:
            p=[x.strip() for x in text.split(",")]+[""]*5
            try:self.db.update_proxy(i,p[0],p[1],int(p[2]),p[3],p[4]);self.refresh()
            except Exception as e: QMessageBox.warning(self,"Proxy",str(e))


class ScannerTab(QWidget):
    def __init__(self,db):
        super().__init__(); self.db=db; self.scanner=ScannerService(db); self.pool=QThreadPool.globalInstance()
        lay=QVBoxLayout(self); self.account=AccountCombo(db); self.group=QLineEdit(); self.group.setPlaceholderText("@group or https://t.me/...")
        top=QHBoxLayout(); top.addWidget(self.account); top.addWidget(self.group); lay.addLayout(top)
        buttons=QHBoxLayout(); ov=QPushButton("Public overview"); ov.clicked.connect(self.overview); scan=QPushButton("Detailed scan — managed group");scan.clicked.connect(self.scan); expc=QPushButton("Export CSV");expc.clicked.connect(lambda:self.export(False)); expx=QPushButton("Export XLSX");expx.clicked.connect(lambda:self.export(True)); imp=QPushButton("Import members");imp.clicked.connect(self.import_members)
        for b in (ov,scan,expc,expx,imp):buttons.addWidget(b)
        lay.addLayout(buttons); self.status=QLabel(); lay.addWidget(self.status); self.table=QTableWidget(); lay.addWidget(self.table)
    def _account(self): return self.account.currentData()
    def _run(self,factory):
        task=AsyncTask(factory); task.signals.result.connect(self._done); task.signals.error.connect(lambda e: QMessageBox.critical(self,"Task failed",e)); self.pool.start(task)
    def _done(self,r): self.status.setText(str(r)); self.refresh_table()
    def overview(self): self._run(lambda progress:self.scanner.overview(self._account(),self.group.text().strip()))
    def scan(self): self._run(lambda progress:self.scanner.scan_managed(self._account(),self.group.text().strip()))
    def refresh_table(self): table_set(self.table,self.db.member_rows(),["id","user_id","username","first_name","last_name","last_seen","source_group","consent_status","status"])
    def export(self,xlsx):
        path,_=QFileDialog.getSaveFileName(self,"Export members","members.xlsx" if xlsx else "members.csv","Excel (*.xlsx)" if xlsx else "CSV (*.csv)")
        if path: (export_xlsx if xlsx else export_csv)(self.db.member_rows(),path)
    def import_members(self):
        path,_=QFileDialog.getOpenFileName(self,"Import","","Members (*.csv *.xlsx)")
        if not path:return
        try:
            if path.lower().endswith(".csv"): n=self.db.import_csv(path)
            else:
                rows=import_xlsx(path); by={}
                for r in rows:
                    if not r.get("user_id"): continue
                    source=str(r.get("source_group") or "import")
                    by.setdefault(source,[]).append({"user_id":int(r["user_id"]),"access_hash":int(r["access_hash"]) if r.get("access_hash") else None,"username":r.get("username") or "","first_name":r.get("first_name") or "","last_name":r.get("last_name") or "","phone":r.get("phone") or "","is_bot":bool(r.get("is_bot")),"is_deleted":bool(r.get("is_deleted")),"last_seen":r.get("last_seen") or "","consent_status":r.get("consent_status") or "unknown","consent_note":r.get("consent_note") or ""})
                n=sum(self.db.save_members(ms,s,False) for s,ms in by.items())
            self.refresh_table(); QMessageBox.information(self,"Import",f"Imported {n} records")
        except Exception as e: QMessageBox.critical(self,"Import failed",str(e))


class FilterTab(QWidget):
    def __init__(self,db):
        super().__init__();self.db=db;lay=QVBoxLayout(self);opts=QHBoxLayout();self.exclude_bots=QCheckBox("Exclude bots");self.exclude_bots.setChecked(True);self.exclude_deleted=QCheckBox("Exclude deleted");self.exclude_deleted.setChecked(True);self.consent=QComboBox();self.consent.addItems(["All","opted_in","opted_out","unknown"]);apply=QPushButton("Apply");apply.clicked.connect(self.refresh)
        for w in (self.exclude_bots,self.exclude_deleted,QLabel("Consent"),self.consent,apply):opts.addWidget(w)
        lay.addLayout(opts);self.table=QTableWidget();lay.addWidget(self.table);mark=QHBoxLayout();optin=QPushButton("Mark selected: opted_in");optin.clicked.connect(lambda:self.mark("opted_in"));optout=QPushButton("Mark selected: opted_out");optout.clicked.connect(lambda:self.mark("opted_out"));unknown=QPushButton("Mark selected: unknown");unknown.clicked.connect(lambda:self.mark("unknown"));mark.addWidget(optin);mark.addWidget(optout);mark.addWidget(unknown);lay.addLayout(mark);self.refresh()
    def refresh(self):
        c=None if self.consent.currentText()=="All" else self.consent.currentText();rows=self.db.member_rows(bots=not self.exclude_bots.isChecked(),deleted=not self.exclude_deleted.isChecked(),consent=c);table_set(self.table,rows,["id","user_id","username","first_name","last_name","source_group","consent_status","status"])
    def mark(self,status):
        for idx in self.table.selectionModel().selectedRows(): self.db.set_consent(int(self.table.item(idx.row(),0).text()),status,"Set in Filter tab")
        self.refresh()


class InviteTab(QWidget):
    def __init__(self,db):
        super().__init__();self.db=db;self.service=InviteService(db);self.pool=QThreadPool.globalInstance();lay=QVBoxLayout(self);form=QFormLayout();self.account=AccountCombo(db);self.target=QLineEdit();self.limit=QSpinBox();self.limit.setRange(1,200);self.limit.setValue(20);self.dry=QCheckBox("Dry run");self.dry.setChecked(True);form.addRow("Account",self.account);form.addRow("Managed target group",self.target);form.addRow("Max opted-in users",self.limit);form.addRow("Safety",self.dry);lay.addLayout(form);start=QPushButton("Run invite queue");start.clicked.connect(self.run);lay.addWidget(start);self.status=QLabel();lay.addWidget(self.status);self.note=QLabel("Only opted-in records are eligible. The target must be administered by the selected account. FloodWait stops the job; it does not rotate accounts.");self.note.setWordWrap(True);lay.addWidget(self.note);lay.addStretch()
    def run(self):
        amin=float(self.db.get_setting("invite_delay_min","8"));amax=float(self.db.get_setting("invite_delay_max","15"));
        async def factory(progress):return await self.service.run(self.account.currentData(),self.target.text().strip(),self.limit.value(),amin,amax,self.dry.isChecked(),progress)
        task=AsyncTask(factory);task.signals.progress.connect(lambda i,n,u:self.status.setText(f"{i}/{n}: {u}"));task.signals.result.connect(lambda r:self.status.setText(f"Success={r.success} Failed={r.failed} Skipped={r.skipped} {r.stopped_reason}"));task.signals.error.connect(lambda e:QMessageBox.critical(self,"Invite failed",e));self.pool.start(task)


class MessengerTab(QWidget):
    def __init__(self,db):
        super().__init__();self.db=db;self.service=MessengerService(db);self.pool=QThreadPool.globalInstance();lay=QVBoxLayout(self);self.tabs=QTabWidget();lay.addWidget(self.tabs)
        g=QWidget();gl=QFormLayout(g);self.ga=AccountCombo(db);self.gt=QLineEdit();self.gmsg=QTextEdit();gb=QPushButton("Send to managed group");gb.clicked.connect(self.send_group);gl.addRow("Account",self.ga);gl.addRow("Managed group",self.gt);gl.addRow("Message",self.gmsg);gl.addRow(gb);self.tabs.addTab(g,"Group")
        u=QWidget();ul=QFormLayout(u);self.ua=AccountCombo(db);self.umsg=QTextEdit();self.ulimit=QSpinBox();self.ulimit.setRange(1,200);self.ulimit.setValue(20);ub=QPushButton("Send to opted-in users");ub.clicked.connect(self.send_users);self.ustatus=QLabel();ul.addRow("Account",self.ua);ul.addRow("Message",self.umsg);ul.addRow("Limit",self.ulimit);ul.addRow(ub);ul.addRow(self.ustatus);self.tabs.addTab(u,"Opted-in users")
    def send_group(self):
        task=AsyncTask(lambda progress:self._group());task.signals.result.connect(lambda _:QMessageBox.information(self,"Message","Sent"));task.signals.error.connect(lambda e:QMessageBox.critical(self,"Message failed",e));self.pool.start(task)
    async def _group(self): await self.service.send_group(self.ga.currentData(),self.gt.text().strip(),self.gmsg.toPlainText())
    def send_users(self):
        amin=float(self.db.get_setting("message_delay_min","8"));amax=float(self.db.get_setting("message_delay_max","15"));
        async def factory(progress):return await self.service.send_opted_in(self.ua.currentData(),self.umsg.toPlainText(),self.ulimit.value(),amin,amax,progress)
        task=AsyncTask(factory);task.signals.progress.connect(lambda i,n,u:self.ustatus.setText(f"{i}/{n}: {u}"));task.signals.result.connect(lambda r:self.ustatus.setText(f"Success={r.success} Failed={r.failed} {r.stopped_reason}"));task.signals.error.connect(lambda e:QMessageBox.critical(self,"Campaign failed",e));self.pool.start(task)


class JoinTab(QWidget):
    def __init__(self,db):
        super().__init__();self.db=db;self.service=JoinService(db);self.pool=QThreadPool.globalInstance();lay=QFormLayout(self);self.account=AccountCombo(db);self.group=QLineEdit();join=QPushButton("Join with selected account");leave=QPushButton("Leave with selected account");join.clicked.connect(lambda:self.run(True));leave.clicked.connect(lambda:self.run(False));self.status=QLabel();lay.addRow("Account",self.account);lay.addRow("Group/channel",self.group);lay.addRow(join);lay.addRow(leave);lay.addRow(self.status)
    def run(self,is_join):
        async def factory(progress):
            return await (self.service.join(self.account.currentData(),self.group.text().strip()) if is_join else self.service.leave(self.account.currentData(),self.group.text().strip()))
        task=AsyncTask(factory);task.signals.result.connect(lambda r:self.status.setText("Success" + (f": {r}" if r else "")));task.signals.error.connect(lambda e:QMessageBox.critical(self,"Join/Leave failed",e));self.pool.start(task)


class ProxyPoolTab(QWidget):
    def __init__(self,db):
        super().__init__();self.db=db;lay=QVBoxLayout(self);buttons=QHBoxLayout();add=QPushButton("Import / add proxy");add.clicked.connect(self.add_proxy);delete=QPushButton("Delete selected proxy");delete.clicked.connect(self.delete_proxy);assign=QPushButton("Assign selected proxy to account");assign.clicked.connect(self.assign);buttons.addWidget(add);buttons.addWidget(delete);buttons.addWidget(assign);lay.addLayout(buttons);self.account=AccountCombo(db);lay.addWidget(self.account);self.table=QTableWidget();lay.addWidget(self.table);self.refresh()
    def refresh(self): table_set(self.table,self.db.proxies(),["id","proxy_type","host","port","username","label","enabled"])
    def _id(self):
        r=self.table.currentRow();return int(self.table.item(r,0).text()) if r>=0 else None
    def add_proxy(self):
        text,ok=QInputDialog.getText(self,"Proxy","type,host,port,user,password,label")
        if not ok:return
        p=[x.strip() for x in text.split(",")]+[""]*6
        try:self.db.add_proxy(p[0] or "socks5",p[1],int(p[2]),p[3],p[4],p[5]);self.refresh()
        except Exception as e:QMessageBox.warning(self,"Proxy",str(e))
    def delete_proxy(self):
        i=self._id();
        if i:self.db.delete_proxy(i);self.refresh()
    def assign(self):
        i=self._id();a=self.account.currentData()
        if i and a:
            try:self.db.assign_proxy(a,i);QMessageBox.information(self,"Proxy","Assigned. Proxy changes take effect on the next connection.")
            except Exception as e:QMessageBox.warning(self,"Proxy",str(e))


class ArchiveScriptTab(QWidget):
    def __init__(self,db):
        super().__init__();self.db=db;self.archive=MessageArchiveService(db);self.script=ScriptService(db);self.pool=QThreadPool.globalInstance();lay=QVBoxLayout(self);tabs=QTabWidget();lay.addWidget(tabs)
        a=QWidget();al=QVBoxLayout(a);top=QHBoxLayout();self.aa=AccountCombo(db);self.ag=QLineEdit();self.alimit=QSpinBox();self.alimit.setRange(1,5000);self.alimit.setValue(200);go=QPushButton("Archive managed group");go.clicked.connect(self.run_archive);save=QPushButton("Export archive CSV");save.clicked.connect(self.export_archive);top.addWidget(self.aa);top.addWidget(self.ag);top.addWidget(self.alimit);top.addWidget(go);top.addWidget(save);al.addLayout(top);self.atable=QTableWidget();al.addWidget(self.atable);self.archive_rows=[];tabs.addTab(a,"Get messages")
        b=QWidget();bl=QFormLayout(b);self.sa=AccountCombo(db);self.starget=QLineEdit();self.srepeat=QSpinBox();self.srepeat.setRange(1,10);self.srepeat.setValue(1);self.script_text=QTextEdit();self.script_text.setPlaceholderText("One step per line: delay_seconds | reply_to_index | text\nExample:\n0||Hello team\n2|0|Reply to first message");run=QPushButton("Run managed script");run.clicked.connect(self.run_script);self.sstatus=QLabel();bl.addRow("Account",self.sa);bl.addRow("Managed group",self.starget);bl.addRow("Repeat",self.srepeat);bl.addRow("Script",self.script_text);bl.addRow(run);bl.addRow(self.sstatus);tabs.addTab(b,"Seeding / Script")
    def run_archive(self):
        task=AsyncTask(lambda progress:self.archive.archive_managed(self.aa.currentData(),self.ag.text().strip(),self.alimit.value()));task.signals.result.connect(self.archive_done);task.signals.error.connect(lambda e:QMessageBox.critical(self,"Archive failed",e));self.pool.start(task)
    def archive_done(self,rows):
        self.archive_rows=rows;table_set(self.atable,rows,["message_id","sender_id","date","reply_to_message_id","has_media","media_type","text"])
    def export_archive(self):
        if not self.archive_rows:return
        path,_=QFileDialog.getSaveFileName(self,"Export archive","messages.csv","CSV (*.csv)")
        if not path:return
        import csv
        keys=["message_id","sender_id","date","reply_to_message_id","has_media","media_type","text"]
        with open(path,"w",newline="",encoding="utf-8-sig") as f:
            w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(self.archive_rows)
    def run_script(self):
        steps=[]
        for line in self.script_text.toPlainText().splitlines():
            if not line.strip():continue
            parts=line.split("|",2);parts += [""]*(3-len(parts));
            try:delay=float(parts[0] or 0)
            except:delay=0
            reply=int(parts[1]) if parts[1].strip().isdigit() else None
            steps.append({"delay":delay,"reply_to_index":reply,"text":parts[2]})
        if not steps:return
        async def factory(progress):return await self.script.run_managed_sequence(self.sa.currentData(),self.starget.text().strip(),steps,self.srepeat.value(),progress)
        task=AsyncTask(factory);task.signals.progress.connect(lambda i,n,t:self.sstatus.setText(f"{i}/{n}: {t}"));task.signals.result.connect(lambda r:self.sstatus.setText(f"Success={r.success} Failed={r.failed} {r.stopped_reason}"));task.signals.error.connect(lambda e:QMessageBox.critical(self,"Script failed",e));self.pool.start(task)


class LogsTab(QWidget):
    def __init__(self,db):
        super().__init__();self.db=db;lay=QVBoxLayout(self);b=QPushButton("Refresh");b.clicked.connect(self.refresh);lay.addWidget(b);self.table=QTableWidget();lay.addWidget(self.table);self.refresh()
    def refresh(self):table_set(self.table,self.db.logs(),["id","created_at","action_type","account_phone","target","user_id","username","outcome","error_code","detail"])


class SettingsTab(QWidget):
    def __init__(self,db):
        super().__init__();self.db=db;lay=QFormLayout(self);self.fields={}
        for key,label in [("invite_delay_min","Invite delay min (s)"),("invite_delay_max","Invite delay max (s)"),("message_delay_min","Message delay min (s)"),("message_delay_max","Message delay max (s)"),("daily_invite_cap","Daily invite cap"),("campaign_limit","Campaign default limit"),("update_manifest_url","Update manifest HTTPS URL")]:
            w=QLineEdit(self.db.get_setting(key,""));self.fields[key]=w;lay.addRow(label,w)
        save=QPushButton("Save settings");save.clicked.connect(self.save);lay.addRow(save)
    def save(self):
        for k,w in self.fields.items():self.db.set_setting(k,w.text().strip())
        QMessageBox.information(self,"Settings","Saved")


class LicenseUpdateTab(QWidget):
    def __init__(self,db):
        super().__init__();self.db=db;lay=QVBoxLayout(self);lic=QPushButton("Inspect local license JSON");lic.clicked.connect(self.license);upd=QPushButton("Check update manifest");upd.clicked.connect(self.update);self.out=QTextEdit();self.out.setReadOnly(True);lay.addWidget(lic);lay.addWidget(upd);lay.addWidget(self.out)
    def license(self):
        path,_=QFileDialog.getOpenFileName(self,"License","","JSON (*.json)")
        if path:self.out.setPlainText(str(read_license(path)))
    def update(self):
        try:self.out.setPlainText(str(check_update(self.db.get_setting("update_manifest_url",""))))
        except Exception as e:self.out.setPlainText(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__();ensure_dirs();self.db=Database();self.setWindowTitle(f"{APP_NAME} {APP_VERSION}");self.resize(1250,800);tabs=QTabWidget();self.setCentralWidget(tabs)
        self.widgets=[DashboardTab(self.db),AccountsTab(self.db),ScannerTab(self.db),FilterTab(self.db),InviteTab(self.db),MessengerTab(self.db),JoinTab(self.db),ProxyPoolTab(self.db),ArchiveScriptTab(self.db),LogsTab(self.db),SettingsTab(self.db),LicenseUpdateTab(self.db)]
        names=["Dashboard","Accounts & Sessions","Scanner","Filter & Consent","Invite Queue","Messaging","Join / Leave","Proxy Pool","Get Messages / Seeding","Logs","Settings","License / Update"]
        for w,n in zip(self.widgets,names):tabs.addTab(w,n)
        tabs.currentChanged.connect(self._refresh)
    def _refresh(self,_):
        for w in self.widgets:
            if hasattr(w,"account") and hasattr(w.account,"reload"): w.account.reload()
            if hasattr(w,"ga") and hasattr(w.ga,"reload"): w.ga.reload(); w.ua.reload()
            if hasattr(w,"refresh") and type(w).__name__ in {"DashboardTab","LogsTab"}: w.refresh()
