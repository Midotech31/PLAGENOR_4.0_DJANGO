"""Conservative OOXML editing: only explicit text spans and selected table rows change.

This module deliberately uses only Python's standard library. XML parts not touched
by an operation retain their original bytes, including prefixes and declarations.
"""
from __future__ import annotations
import copy
import difflib
import hashlib
import io
import re
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from xml.parsers import expat
from xml.sax.saxutils import escape

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
NS = W + '|'
MAX_EXPANDED = 96 * 1024 * 1024
MAX_ENTRIES = 4096

class DocumentError(ValueError):
    """An edit cannot be applied without violating the source contract."""

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def xml_text(text: str) -> str:
    if not isinstance(text, str) or len(text) > 100000:
        raise DocumentError('Texte absent, invalide ou trop long.')
    if any(ord(c) < 32 and c not in '\t\n\r' for c in text):
        raise DocumentError('Le texte contient un caractère de contrôle interdit.')
    if any(0xD800 <= ord(c) <= 0xDFFF or ord(c) in (0xFFFE,0xFFFF) for c in text):
        raise DocumentError('Le texte contient un caractère Unicode invalide.')
    return text

def safe_zip(data: bytes, maximum: int = MAX_EXPANDED) -> zipfile.ZipFile:
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = z.namelist()
        if len(names) != len(set(names)) or len(names) > MAX_ENTRIES:
            raise DocumentError('Archive ambiguë ou trop volumineuse.')
        total = 0
        for i in z.infolist():
            p = PurePosixPath(i.filename)
            if '\\' in i.filename or p.is_absolute() or '..' in p.parts or ':' in i.filename:
                raise DocumentError('Chemin non autorisé dans l’archive.')
            if (i.external_attr >> 16) & 0o170000 == 0o120000:
                raise DocumentError('Les liens symboliques ne sont pas autorisés.')
            total += i.file_size
            if total > maximum or i.flag_bits & 1:
                raise DocumentError('Archive chiffrée ou trop volumineuse.')
        if z.testzip() is not None:
            raise DocumentError('Archive endommagée.')
        return z
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise DocumentError('Le fichier n’est pas une archive valide.') from exc

@dataclass
class Node:
    name: str
    attrs: dict
    start: int
    opening_end: int
    parent: 'Node | None' = None
    children: list['Node'] = field(default_factory=list)
    end: int = 0
    closing_start: int = 0
    characters: str = ''
    index: int = 0

    def descendants(self, name: str | None = None):
        for child in self.children:
            if name is None or child.name == name:
                yield child
            yield from child.descendants(name)

    def ancestor(self, name: str):
        n = self.parent
        while n:
            if n.name == name:
                return n
            n = n.parent
        return None

    @property
    def text(self):
        if self.name == NS + 't':
            return self.characters
        return ''.join(n.characters for n in self.descendants(NS + 't'))


def tag_end(data: bytes, start: int) -> int:
    quote = None
    for i in range(start, len(data)):
        c = data[i]
        if quote:
            if c == quote:
                quote = None
        elif c in (34, 39):
            quote = c
        elif c == 62:
            return i + 1
    raise DocumentError('Balise XML incomplète.')


def parse_xml(data: bytes) -> Node:
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise DocumentError('Les déclarations d’entités XML sont interdites.')
    parser = expat.ParserCreate(namespace_separator='|')
    stack, roots, counters = [], [], defaultdict(int)
    def start(name, attrs):
        counters[name] += 1
        index = parser.CurrentByteIndex
        n = Node(name, attrs, index, tag_end(data, index), stack[-1] if stack else None, index=counters[name]-1)
        if stack: stack[-1].children.append(n)
        else: roots.append(n)
        stack.append(n)
    def end(name):
        n = stack.pop()
        if data[n.opening_end-2:n.opening_end] == b'/>':
            n.closing_start = n.end = n.opening_end
        else:
            n.closing_start = parser.CurrentByteIndex
            n.end = tag_end(data, n.closing_start)
    def chars(value):
        if stack: stack[-1].characters += value
    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.CharacterDataHandler = chars
    parser.ExternalEntityRefHandler = lambda *args: 0
    try:
        parser.Parse(data, True)
    except expat.ExpatError as exc:
        raise DocumentError('XML non valide.') from exc
    if len(roots) != 1:
        raise DocumentError('Racine XML invalide.')
    return roots[0]


def own_text_nodes(paragraph: Node):
    return [n for n in paragraph.descendants(NS+'t') if n.ancestor(NS+'p') is paragraph]


def edit_text_nodes(nodes: list[Node], value: str, raw: bytes) -> list[tuple[int,int,bytes]]:
    """Distribute a text diff to its existing runs; leave all run properties intact."""
    value = xml_text(value)
    if '\n' in value or '\r' in value or '\t' in value:
        raise DocumentError('Modifiez les paragraphes séparément ; les retours et tabulations internes ne sont pas aplatis.')
    old = ''.join(n.characters for n in nodes)
    if value == old:
        return []
    if not nodes:
        raise DocumentError('Ce bloc sans texte ne peut pas être remplacé.')
    owners = []
    for i,n in enumerate(nodes): owners.extend([i]*len(n.characters))
    output = ['' for _ in nodes]
    matcher = difflib.SequenceMatcher(None, old, value, autojunk=False)
    for tag, a, b, c, d in matcher.get_opcodes():
        if tag == 'equal':
            for offset, char in enumerate(value[c:d]): output[owners[a+offset]] += char
        elif tag in ('insert', 'replace'):
            owner = owners[a] if a < len(owners) else (owners[-1] if owners else 0)
            output[owner] += value[c:d]
    edits=[]
    for n,new in zip(nodes,output):
        if new == n.characters: continue
        if raw[n.opening_end-2:n.opening_end] == b'/>':
            prefix=raw[n.start:n.opening_end-2]
            tagname=re.match(rb'<([^\s/>]+)',prefix).group(1)
            edits.append((n.start,n.end,prefix+(b'' if b'xml:space=' in prefix else b' xml:space="preserve"')+b'>'+escape(new).encode()+b'</'+tagname+b'>'))
        else:
            edits.append((n.opening_end,n.closing_start,escape(new).encode('utf-8')))
            opening=raw[n.start:n.opening_end]
            if (new.startswith(' ') or new.endswith(' ')) and b'xml:space=' not in opening:
                edits.append((n.opening_end-1,n.opening_end-1,b' xml:space="preserve"'))
    return edits


def apply_byte_edits(data:bytes, edits:list[tuple[int,int,bytes]]) -> bytes:
    edits=sorted(edits,key=lambda x:(x[0],x[1]))
    end=0
    for a,b,v in edits:
        if a < end or a<0 or b<a or b>len(data):
            raise DocumentError('Deux modifications documentaires se chevauchent.')
        end=b
    chunks=[];cursor=0
    for a,b,v in edits:
        chunks.extend((data[cursor:a],v));cursor=b
    chunks.append(data[cursor:])
    return b''.join(chunks)


def guarded_paragraph(n:Node) -> str:
    if any(c.name in (NS+'instrText',NS+'fldChar',NS+'fldSimple',NS+'ins',NS+'del',NS+'tab',NS+'br') for c in n.descendants()) or n.attrs.get('_protected_field') or n.ancestor(NS+'fldSimple'):
        return 'Champ Word : modification directe protégée'
    if n.ancestor(NS+'del') or n.ancestor(NS+'ins'):
        return 'Modification suivie à examiner dans Word'
    return ''


class Document:
    def __init__(self, data: bytes, expected_sha: str | None = None):
        self.data = data
        self.digest = sha(data)
        if expected_sha and self.digest != expected_sha:
            raise DocumentError('Le modèle a changé : son empreinte ne correspond pas à la référence.')
        self.z = safe_zip(data)
        if 'word/document.xml' not in self.z.namelist() or '[Content_Types].xml' not in self.z.namelist():
            raise DocumentError('Ce fichier n’est pas un document Word OOXML.')
        if any('vbaProject' in n or n.lower().endswith('.bin') and 'vba' in n.lower() for n in self.z.namelist()):
            raise DocumentError('Les macros ne sont pas prises en charge.')
        self.parts={}
        self.paragraphs={}
        self.tables={}
        self.source_index=[]
        for info in self.z.infolist():
            if not info.filename.endswith('.xml') or not info.filename.startswith('word/'):
                continue
            raw=self.z.read(info.filename)
            root=parse_xml(raw)
            self.parts[info.filename]=(raw,root)
            depth=0
            for node in root.descendants():
                if node.name==NS+'fldChar':
                    typ=node.attrs.get(NS+'fldCharType')
                    if typ=='begin': depth+=1
                    owner=node.ancestor(NS+'p')
                    if owner is not None: owner.attrs['_protected_field']='true'
                    if typ=='end': depth=max(0,depth-1)
                elif depth and node.name==NS+'p':
                    node.attrs['_protected_field']='true'
                elif depth and node.name==NS+'t':
                    node.attrs['_inside_field']='true'
            for p in root.descendants(NS+'p'):
                pid=f'{info.filename}:p{p.index}:{sha(raw[p.start:p.end])[:12]}'
                text=''.join(n.characters for n in own_text_nodes(p))
                self.paragraphs[pid]=(info.filename,p)
                style=next((c.attrs.get(NS+'val','') for c in p.descendants(NS+'pStyle')),'')
                self.source_index.append({'id':pid,'part':info.filename,'index':p.index,'text':text,'style':style,
                    'guard':guarded_paragraph(p),'in_table':bool(p.ancestor(NS+'tbl')),'rtl':any(c.name==NS+'bidi' for c in p.descendants()),
                    'sha256':sha(raw[p.start:p.end])})
            for t in root.descendants(NS+'tbl'):
                tid=f'{info.filename}:t{t.index}:{sha(raw[t.start:t.end])[:12]}'
                self.tables[tid]=(info.filename,t)

    def table_catalog(self):
        out=[]
        for tid,(part,t) in self.tables.items():
            rows=[]
            for ri,r in enumerate(c for c in t.children if c.name==NS+'tr'):
                cells=[]
                for c in (c for c in r.children if c.name==NS+'tc'):
                    texts=[p for p in c.descendants(NS+'p') if p.ancestor(NS+'tc') is c]
                    cells.append({'text':'\n'.join(''.join(n.characters for n in own_text_nodes(p)) for p in texts),
                        'paragraph_ids':[self.paragraph_id(part,p) for p in texts],
                        'span':next((n.attrs.get(NS+'val','1') for n in c.descendants(NS+'gridSpan')),'1'),
                        'merged':any(n.name==NS+'vMerge' for n in c.descendants())})
                unsafe=any(n.name in (NS+'vMerge',NS+'fldChar',NS+'fldSimple',NS+'ins',NS+'del',NS+'commentReference',NS+'commentRangeStart',NS+'sectPr') for n in r.descendants())
                rows.append({'index':ri,'cells':cells,'cloneable':not unsafe and bool(cells)})
            out.append({'id':tid,'part':part,'index':t.index,'nested':bool(t.ancestor(NS+'tbl')),'rows':rows})
        return out

    def editable_segments(self, paragraph_id: str) -> list[list[Node]]:
        """Editable text islands; breaks, tabs and field results are never flattened.

        A paragraph may contain a protected field and also ordinary text. Only
        explicitly anchored ordinary-text segments can use the span-edit API.
        """
        if paragraph_id not in self.paragraphs:
            raise DocumentError('Ancrage de paragraphe inconnu.')
        _, paragraph = self.paragraphs[paragraph_id]
        segments, current = [], []
        barriers = {NS + name for name in ('br', 'cr', 'tab', 'fldChar', 'instrText',
                                           'drawing', 'object', 'fldSimple', 'ins', 'del')}
        for node in paragraph.descendants():
            if node.ancestor(NS+'p') is not paragraph:
                continue
            forbidden = (node.attrs.get('_inside_field') or
                         node.ancestor(NS+'fldSimple') or node.ancestor(NS+'ins') or
                         node.ancestor(NS+'del'))
            if node.name in barriers or forbidden:
                if current:
                    segments.append(current)
                    current = []
                continue
            if node.name == NS+'t':
                current.append(node)
        if current:
            segments.append(current)
        return segments

    def paragraph_id(self,part,p):
        raw=self.parts[part][0]
        return f'{part}:p{p.index}:{sha(raw[p.start:p.end])[:12]}'

    def inspection(self):
        raw,body=self.parts['word/document.xml']
        return {'sha256':self.digest,'parts':len(self.z.infolist()),'paragraphs':len(self.paragraphs),
          'text_characters':sum(len(b['text']) for b in self.source_index),
          'tables':len(self.tables),'body_tables':sum(part=='word/document.xml' and node.parent is not None and node.parent.name==NS+'body' for part,node in self.tables.values()),
          'sections':len(list(body.descendants(NS+'sectPr'))),
          'media':{n:sha(self.z.read(n)) for n in self.z.namelist() if n.startswith('word/media/')},
          'source_errors':[b for b in self.source_index if 'Erreur !' in b['text']],
          'fonts':sorted({v for n in body.descendants(NS+'rFonts') for k,v in n.attrs.items() if k.rsplit('|',1)[-1] in ('ascii','hAnsi','cs','eastAsia')})}

    def generate(self, paragraph_edits: dict | None = None, table_edits: dict | None = None,
                 omitted: list[str] | None = None,
                 span_edits: dict | None = None) -> tuple[bytes,dict]:
        paragraph_edits=paragraph_edits or {}; table_edits=table_edits or {}; omitted=omitted or []
        if not isinstance(paragraph_edits,dict) or not isinstance(table_edits,dict) or not isinstance(omitted,list):
            raise DocumentError('Format des modifications invalide.')
        span_edits = {} if span_edits is None else span_edits
        if not isinstance(span_edits, dict) or len(span_edits) > 10000:
            raise DocumentError('Format des modifications ciblées invalide.')
        edits=defaultdict(list); changed=[]
        for pid, operations in span_edits.items():
            if pid in paragraph_edits or pid in omitted:
                raise DocumentError('Un bloc ne peut pas être modifié par deux méthodes.')
            if not isinstance(operations, list) or len(operations) > 100:
                raise DocumentError('Modifications ciblées invalides.')
            segments = self.editable_segments(pid)
            part, _ = self.paragraphs[pid]
            raw = self.parts[part][0]
            seen = set()
            for op in operations:
                if not isinstance(op, dict) or set(op) != {'segment', 'before', 'after'}:
                    raise DocumentError('Modification ciblée incomplète.')
                index = op['segment']
                if type(index) is not int or not 0 <= index < len(segments) or index in seen:
                    raise DocumentError('Segment inconnu ou dupliqué.')
                seen.add(index)
                before = ''.join(n.characters for n in segments[index])
                if op['before'] != before:
                    raise DocumentError('Le texte source du segment ne correspond plus.')
                patch = edit_text_nodes(segments[index], op['after'], raw)
                if patch:
                    edits[part].extend(patch)
                    changed.append({'kind': 'controlled_span', 'id': pid,
                                    'segment': index, 'old': before, 'new': op['after']})
        drawing_id=[max([int(n.attrs.get('id','0')) for _,root in self.parts.values() for n in root.descendants() if n.name.endswith('|docPr') and n.attrs.get('id','0').isdigit()] or [0])]
        def drawing_fresh(match):
            drawing_id[0]+=1
            return match.group(1)+str(drawing_id[0]).encode()+b'"'
        for pid,value in paragraph_edits.items():
            if pid not in self.paragraphs: raise DocumentError('Un paragraphe ne correspond plus au modèle.')
            part,p=self.paragraphs[pid]
            if guarded_paragraph(p): raise DocumentError('Le champ Word doit être modifié dans son logiciel de référence.')
            raw=self.parts[part][0]
            patch=edit_text_nodes(own_text_nodes(p),value,raw)
            if patch: edits[part].extend(patch);changed.append({'kind':'paragraph','id':pid,'old':p.text,'new':value})
        for tid,operations in table_edits.items():
            if tid not in self.tables: raise DocumentError('Un tableau ne correspond plus au modèle.')
            part,t=self.tables[tid]; raw=self.parts[part][0]
            rows=[r for r in t.children if r.name==NS+'tr']
            if not isinstance(operations,list) or len(operations)>2000:raise DocumentError('Trop de lignes ajoutées.')
            for serial,op in enumerate(operations):
                ri=op.get('source_row');after=op.get('after_row',ri)
                if not isinstance(ri,int) or not isinstance(after,int) or not 0<=ri<len(rows) or not 0<=after<len(rows):raise DocumentError('Ligne modèle invalide.')
                row=rows[ri]
                if any(n.name in (NS+'vMerge',NS+'fldChar',NS+'fldSimple',NS+'ins',NS+'del',NS+'commentReference',NS+'commentRangeStart',NS+'sectPr') for n in row.descendants()):
                    raise DocumentError('Cette ligne comporte une fusion ou un champ complexe non duplicable.')
                fragment=raw[row.start:row.end]
                clone_edits=[];cells=[c for c in row.children if c.name==NS+'tc']
                values=op.get('cells')
                if not isinstance(values,list) or len(values)!=len(cells):raise DocumentError('Nombre de cellules incorrect.')
                for cell,value in zip(cells,values):
                    nodes=list(cell.descendants(NS+'t'))
                    if not nodes and value:
                        xml_text(value)
                        ps=[n for n in cell.descendants(NS+'p') if n.ancestor(NS+'tc') is cell]
                        if len(ps)!=1 or any(n.name in (NS+'drawing',NS+'fldChar',NS+'sectPr') for n in ps[0].descendants()):
                            raise DocumentError('Cette cellule vide possède une structure non prise en charge.')
                        pos=ps[0].closing_start
                        if raw[ps[0].opening_end-2:ps[0].opening_end]==b'/>':
                            raise DocumentError('Paragraphe vide auto-fermant : ancrage de texte absent.')
                        new=b'<w:r><w:t xml:space="preserve">'+escape(value).encode()+b'</w:t></w:r>'
                        clone_edits.append((pos-row.start,pos-row.start,new))
                    if nodes:clone_edits.extend((a-row.start,b-row.start,v) for a,b,v in edit_text_nodes(nodes,value,raw))
                fragment=apply_byte_edits(fragment,clone_edits)
                # Remove bookmarks in a new row: no source reference can target a newly created bookmark.
                fragment=re.sub(rb'<w:bookmark(?:Start|End)\b[^>]*/>',b'',fragment)
                # IDs used by Word for paragraph/text and drawing identity must be new.
                seed=sha((tid+str(serial)).encode())
                count=[0]
                def fresh(m):
                    count[0]+=1
                    return m.group(1)+sha((seed+str(count[0])).encode())[:8].upper().encode()+b'"'
                fragment=re.sub(rb'((?:w14:paraId|w14:textId)=")[^"]+"',fresh,fragment)
                fragment=re.sub(rb'(<wp:docPr\b[^>]*\bid=")\d+"',drawing_fresh,fragment)
                edits[part].append((rows[after].end,rows[after].end,fragment))
                changed.append({'kind':'row_added','table':tid,'after_row':after,'source_row':ri,'cells':values})
        for pid in omitted:
            if pid not in self.paragraphs:raise DocumentError('Bloc conditionnel inconnu.')
            part,p=self.paragraphs[pid]
            if p.parent is None or p.parent.name!=NS+'body' or any(n.name in (NS+'sectPr',NS+'bookmarkStart',NS+'bookmarkEnd',NS+'fldChar',NS+'drawing') for n in p.descendants()):
                raise DocumentError('Ce bloc structurel ne peut pas être supprimé sans casser le modèle.')
            edits[part].append((p.start,p.end,b''));changed.append({'kind':'paragraph_omitted','id':pid})
        # Combine consecutive insertions at one anchor, with their requested order preserved.
        for part,patches in list(edits.items()):
            inserts={};plain=[]
            for a,b,v in patches:
                if a==b:inserts[(a,b)]=inserts.get((a,b),b'')+v
                else:plain.append((a,b,v))
            edits[part]=plain+[(a,b,v) for (a,b),v in inserts.items()]
        patched={}
        for part,patches in edits.items():
            patched[part]=apply_byte_edits(self.parts[part][0],patches)
            parse_xml(patched[part])
        if not patched:
            output=self.data
        else:
            buf=io.BytesIO()
            with zipfile.ZipFile(buf,'w') as out:
                out.comment=self.z.comment
                for item in self.z.infolist(): out.writestr(copy.copy(item),patched.get(item.filename,self.z.read(item.filename)))
            output=buf.getvalue()
        check=Document(output) if patched else self
        preserved={n:sha(self.z.read(n)) for n in self.z.namelist() if n not in patched}
        if any(sha(check.z.read(n))!=h for n,h in preserved.items()):raise DocumentError('Une partie protégée a été altérée.')
        report={'source_sha256':self.digest,'output_sha256':sha(output),'changed_parts':list(patched),'changes':changed,
                'preserved_parts':preserved,'retained_parts':len(check.z.namelist()),'source_parts':len(self.z.namelist()),
                'source_errors_preserved':len(self.inspection()['source_errors']),
                'validation':'OOXML_CHECKED','word_validation':'NOT_RUN','legal_validation':'NON_VALIDE'}
        return output,report
