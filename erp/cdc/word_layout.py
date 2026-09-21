from __future__ import annotations
import io,zipfile,copy
from lxml import etree
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';NS={'w':W};Q=lambda n:f'{{{W}}}{n}'

def normalize_word_layout(payload:bytes):
    source=io.BytesIO(payload);out=io.BytesIO();changed={};report={'headers_centered':0,'footers_centered':0,'update_fields':False,'parts':[]}
    with zipfile.ZipFile(source) as z:
        for info in z.infolist():
            raw=z.read(info.filename);new=raw
            if info.filename.startswith('word/header') and info.filename.endswith('.xml'):new,count=_center_paragraphs(raw);report['headers_centered']+=count
            elif info.filename.startswith('word/footer') and info.filename.endswith('.xml'):new,count=_center_paragraphs(raw);report['footers_centered']+=count
            elif info.filename=='word/settings.xml':new,flag=_update_fields(raw);report['update_fields']=flag
            if new!=raw:changed[info.filename]=new;report['parts'].append(info.filename)
        with zipfile.ZipFile(out,'w') as target:
            target.comment=z.comment
            for info in z.infolist():target.writestr(copy.copy(info),changed.get(info.filename,z.read(info.filename)))
    return out.getvalue(),report

def _xml(raw):return etree.fromstring(raw,parser=etree.XMLParser(resolve_entities=False,no_network=True,remove_blank_text=False))
def _dump(root):return etree.tostring(root,encoding='UTF-8',xml_declaration=True,standalone='yes')
def _center_paragraphs(raw):
    root=_xml(raw);count=0
    for p in root.xpath('.//w:p',namespaces=NS):
        text=''.join(p.xpath('.//w:t/text()',namespaces=NS)).strip()
        if not text and not p.xpath('.//w:fldChar|.//w:instrText',namespaces=NS):continue
        ppr=p.find(Q('pPr'))
        if ppr is None:ppr=etree.Element(Q('pPr'));p.insert(0,ppr)
        jc=ppr.find(Q('jc'))
        if jc is None:jc=etree.SubElement(ppr,Q('jc'))
        if jc.get(Q('val'))!='center':jc.set(Q('val'),'center');count+=1
    return (_dump(root),count) if count else (raw,0)
def _update_fields(raw):
    root=_xml(raw);node=root.find(Q('updateFields'))
    if node is None:node=etree.SubElement(root,Q('updateFields'))
    if node.get(Q('val'))=='true':return raw,True
    node.set(Q('val'),'true');return _dump(root),True