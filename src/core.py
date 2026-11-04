"""Selected original parsing, storage and navigation rules; no desktop-input API.

Adapted from the private local prototype. Public examples use synthetic fixtures.
"""
import csv
import hashlib
import json
import os
import re
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

COLUMNS = ["微信名", "备注姓名", "电话号码"]

def extract_candidates(lines):
    """Preserve OCR text; never repair digits or label a guess as verified."""
    rows = []
    pattern = re.compile(r'(?<![A-Za-z0-9_])(?:\+\d{1,3}[ -]?)?\d(?:[\d ()-]*\d)?(?![A-Za-z0-9_])')
    for line in lines:
        for match in pattern.finditer(line['text']):
            raw = match.group().strip()
            digits = re.sub(r'\D', '', raw)
            if len(digits) < 7:
                continue
            normalized = ('+' if raw.startswith('+') else '') + digits
            domestic = digits[2:] if digits.startswith('86') and len(digits) == 13 else digits
            mobile_shape = bool(re.fullmatch(r'1[3-9]\d{9}', domestic))
            rows.append(dict(raw=raw, normalized=normalized,
                             confidence=line['confidence'],
                             format_hint='mainland_mobile_shape' if mobile_shape else 'other_or_suspicious_length',
                             status='needs_human_review', source_text=line['text'], box=line['box']))
    return rows

def texts(lines):
    return [line['text'].strip() for line in lines if line['text'].strip()]


def nickname(lines):
    values = texts(lines)
    for value in values:
        match = re.match(r'^昵称\s*[:：]?\s*(.+)$', value)
        if match:
            return match.group(1).strip()
    return values[0] if values else None


def phone_field(lines):
    """An empty OCR result alone is never evidence of an empty phone field."""
    description_y = [min(p[1] for p in row['box']) for row in lines if '描述' in row['text']]
    if not description_y:
        return None, 'phone_section_incomplete'
    bottom = min(description_y)
    section = [row for row in lines if max(p[1] for p in row['box']) < bottom]
    section_text = texts(section)
    candidates = extract_candidates(section)
    if candidates:
        # Preserve all original digits, including unexpected lengths.
        numbers = list(dict.fromkeys(item['normalized'] for item in candidates))
        return '；'.join(numbers), 'phone_visible'
    has_add_button = any('添加电话' in value for value in section_text)
    has_phone_title = any(value == '电话' for value in section_text)
    other_text = [value for value in section_text if value not in ('电话', '添加电话', '+添加电话')]
    if has_add_button and has_phone_title and not other_text:
        return '没有', 'phone_section_confirmed_empty'
    return None, 'phone_unreadable'

def stamp():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def atomic_json(path, data):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


class Pause(Exception):
    pass


class Store:
    def __init__(self, folder):
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(folder / 'progress.sqlite3')
        self.db.execute('CREATE TABLE IF NOT EXISTS contacts (identity TEXT PRIMARY KEY, name TEXT, remark TEXT, phone TEXT, audit TEXT)')
        self.db.commit()

    def has(self, identity):
        return self.db.execute('SELECT 1 FROM contacts WHERE identity=?', (identity,)).fetchone() is not None

    def save(self, identity, record, audit):
        # Never silently overwrite a different person after an OCR collision.
        existing = self.db.execute('SELECT name,remark,phone FROM contacts WHERE identity=?', (identity,)).fetchone()
        values = tuple(record[key] for key in COLUMNS)
        if existing is not None and existing != values:
            raise Pause('联系人标识冲突，已暂停；请核对源截图。')
        self.db.execute('INSERT OR IGNORE INTO contacts VALUES (?,?,?,?,?)', (identity, *values, json.dumps(audit, ensure_ascii=False)))
        self.db.commit()

    def records(self):
        return [dict(zip(COLUMNS, row)) for row in self.db.execute('SELECT name,remark,phone FROM contacts ORDER BY rowid')]

    def export(self):
        records = self.records()
        with (self.folder / '联系人.csv').open('w', newline='', encoding='utf-8-sig') as handle:
            writer = csv.writer(handle, quoting=csv.QUOTE_ALL)
            writer.writerow(COLUMNS)
            writer.writerows([["'" + v if v.startswith(('=', '+', '-', '@')) else v for v in row.values()] for row in records])
        # Minimal OpenXML with inline strings: no Excel library, Codex runtime,
        # formulas or numeric coercion is needed by the independent program.
        ns = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        rows = []
        for number, values in enumerate([COLUMNS] + [list(row.values()) for row in records], 1):
            cells = ''.join(f'<c r="{col}{number}" t="inlineStr" s="{1 if number == 1 else 2}"><is><t xml:space="preserve">{escape(value)}</t></is></c>' for col, value in zip('ABC', values))
            rows.append(f'<row r="{number}" ht="25" customHeight="1">{cells}</row>')
        sheet = f'<worksheet xmlns="{ns}"><sheetViews><sheetView workbookViewId="0" showGridLines="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="30" customWidth="1"/><col min="2" max="2" width="45" customWidth="1"/><col min="3" max="3" width="28" customWidth="1"/></cols><sheetData>{"".join(rows)}</sheetData><autoFilter ref="A1:C{len(records)+1}"/></worksheet>'
        content_types = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'
        styles = f'<styleSheet xmlns="{ns}"><fonts count="2"><font><sz val="11"/><name val="Microsoft YaHei"/></font><font><b/><color rgb="FFFFFFFF"/><sz val="11"/><name val="Microsoft YaHei"/></font></fonts><fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF243247"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/><xf numFmtId="49" fontId="1" fillId="2" borderId="0" applyAlignment="1"><alignment horizontal="center" vertical="center"/></xf><xf numFmtId="49" fontId="0" fillId="0" borderId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="center"/></xf></cellXfs></styleSheet>'
        temporary = self.folder / '联系人.tmp.xlsx'
        with zipfile.ZipFile(temporary, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('[Content_Types].xml', content_types)
            archive.writestr('_rels/.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
            archive.writestr('xl/workbook.xml', f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="联系人" sheetId="1" r:id="rId1"/></sheets></workbook>')
            archive.writestr('xl/_rels/workbook.xml.rels', '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
            archive.writestr('xl/styles.xml', styles)
            archive.writestr('xl/worksheets/sheet1.xml', sheet)
        os.replace(temporary, self.folder / '联系人.xlsx')
        atomic_json(self.folder / '联系人.json', records)
        return len(records)

def mid(row):
    return (sum(p[0] for p in row['box'])/4,sum(p[1] for p in row['box'])/4)


def find(lines, text):
    return next((row for row in lines if row['text']==text),None)


def profile_fields(lines):
    nickname = None
    identity = None
    identity_needs_confirmation=False
    for line in lines:
        match = re.match(r'^昵称\s*[:：]?\s*(.+)$',line['text'])
        if match:
            nickname = match.group(1).strip()
        match = re.match(r'^微信号\s*[:：]?\s*(.+)$',line['text'])
        if match:
            raw=match.group(1).strip()
            if re.fullmatch(r'[A-Za-z0-9_.-]+',raw):
                identity=raw
            elif re.fullmatch(r'wxid\s+[A-Za-z0-9]+',raw):
                identity=re.sub(r'^wxid\s+','wxid_',raw)
                identity_needs_confirmation=True
    titles = [line['text'] for line in lines if mid(line)[0]>85 and mid(line)[1]<70 and not re.match(r'^(微信号|昵称|地区)',line['text'])]
    display = titles[0] if titles else None
    no_remark = any('添加备注名' in line['text'] for line in lines)
    if not nickname and no_remark:
        nickname = display
    if not nickname or not identity or not display or not find(lines,'备注'):
        raise Pause('昵称、微信号或资料结构未识别完整，已暂停。请确认选中的是普通好友。')
    return {'name':nickname,'identity':identity,'display':display,'no_remark':no_remark,'identity_needs_confirmation':identity_needs_confirmation}


def edit_fields(lines, no_remark):
    if not any('设置备注和标签' in row['text'] for row in lines):
        raise Pause('未识别到备注设置窗口，已暂停。')
    cancel = find(lines,'取消')
    if cancel is None:
        # A cursor overlay can cover the second glyph. Only accept the
        # calibrated dialog's partial label when it shares the bottom button
        # row with 完成 and is the button to its right. No generic fuzzy click.
        partial,done=find(lines,'取'),find(lines,'完成')
        if partial and done and abs(mid(partial)[1]-mid(done)[1])<15 and mid(partial)[0]-mid(done)[0]>70:
            cancel=partial
    label = find(lines,'备注名')
    tag = find(lines,'标签')
    phone = find(lines,'电话')
    if not all((cancel,label,tag,phone)):
        raise Pause('备注窗口关键标签缺失，已暂停。')
    remark = ''.join(row['text'] for row in lines if mid(label)[1]<mid(row)[1]<mid(tag)[1])
    phone_lines = [row for row in lines if mid(row)[1]>=mid(phone)[1]-5]
    value,status = phone_field(phone_lines)
    return {'remark':'没有' if no_remark else remark or '待核对','phone':value or '待核对','phone_status':status,'cancel':mid(cancel)}


def selected_row(image):
    import numpy as np
    data = np.asarray(image.convert('RGB'))
    strip = data[140:810,110:290,:].astype('int16')
    green = ((strip[:,:,1]>95)&(strip[:,:,1]>strip[:,:,0]*1.5)&(strip[:,:,1]>strip[:,:,2]*1.15)).mean(axis=1)>0.70
    indices = np.where(green)[0]
    if len(indices)<25:
        raise Pause('未识别到通讯录中绿色选中行。请先选中要开始的好友。')
    return int(indices[0]+140),int(indices[-1]+140)


def header_hash(image):
    return hashlib.sha256(image.crop((470,110,810,215)).tobytes()).hexdigest()


def avatar_rows(image):
    """Locate every visible avatar, including contacts whose names are emoji."""
    import numpy as np
    data=np.asarray(image.convert('RGB')).astype('int16')
    background=np.median(data[140:810,110:120,:],axis=1)
    avatar=data[140:810,128:170,:]
    active=(np.max(np.abs(avatar-background[:,None,:]),axis=2)>30).mean(axis=1)>0.20
    active=np.convolve(active.astype('int32'),np.ones(3,dtype='int32'),mode='same')>0
    edges=np.diff(np.r_[False,active,False].astype('int32'))
    starts,ends=np.where(edges==1)[0],np.where(edges==-1)[0]
    return [(int(a+140),int(b+140)) for a,b in zip(starts,ends) if 27<=b-a<=65]


def tail_is_blank(image,bottom):
    import numpy as np
    data=np.asarray(image.convert('RGB')).astype('int16')
    if bottom+5>=805:
        return True
    area=data[bottom+5:805,125:320,:]
    background=np.median(data[bottom+5:805,110:120,:],axis=1)
    return int((np.max(np.abs(area-background[:,None,:]),axis=2)>35).sum())<30


def advance(desktop):
    old=desktop.capture()
    original=header_hash(old)
    unchanged_scrolls=0
    for attempt in range(5):
        _,bottom=selected_row(old)
        rows=avatar_rows(old)
        candidates=[(a+b)//2 for a,b in rows if (a+b)//2>bottom+8]
        if candidates:
            desktop.click(200,candidates[0])
            new=desktop.capture()
            if header_hash(new)==original:
                return 'navigation_stalled_or_end_needs_check'
            return 'advanced'
        old_list=old.crop((110,140,320,810)).tobytes()
        desktop.scroll_list()
        new=desktop.capture()
        if old_list==new.crop((110,140,320,810)).tobytes():
            unchanged_scrolls+=1
            if unchanged_scrolls<2:
                old=new
                continue
            if tail_is_blank(new,bottom):
                return 'visible_list_end_reached_scope_from_selected_start'
            return 'navigation_stalled_or_end_needs_check'
        unchanged_scrolls=0
        old=new
    return 'navigation_stalled_or_end_needs_check'
