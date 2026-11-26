#!/usr/bin/env python3
"""Build the final thesis .docx; every result number is read from persisted artifacts.

Rerun after more cases are admitted or the benchmark/human study finishes:

    .venv/bin/python scripts/build_thesis_docx.py

Inputs (all optional; a missing one renders a clearly marked "[Chờ dữ liệu]" block, never a number):
  dataset funnel      app.admission_progress over experiments/candidate-registry.json + review packets
  development results results/evaluation/*.json with dataset_role == development_pilot
  official benchmark  results/evaluation/official-test-B0-B3.json   (experiments/evaluate.py output,
                      manifest dataset_role == official_test)
  grounding           results/review-handoff/claim-review-official*/ (two-reviewer claim labels)
  human timing        results/evaluation/human-timing-observed-v1.json (scripts/summarize_human_study.py)
Writes docs/submission/khoa_luan_final.docx and a sibling .status.json listing what is still pending.
"""
import argparse
import datetime as dt
import glob
import json
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.admission_progress import progress

OUT=ROOT/'docs/submission/khoa_luan_final.docx'
OFFICIAL='results/evaluation/official-test-B0-B3.json'
HUMAN='results/evaluation/human-timing-observed-v1.json'
MODES=('B0','B1','B2','B3')
SUPPORTED={'supported'};UNSUPPORTED={'unsupported','contradicted'}


def load(path,default=None):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return default


def pct(x):return '—' if x is None else f'{x*100:.1f}%'.replace('.',',')
def num(x,d=2):return '—' if x is None else f'{x:,.{d}f}'.replace(',','X').replace('.',',').replace('X','.')
def ci(c):return '—' if not c else f'[{pct(c[0])}; {pct(c[1])}]'


# ---------------------------------------------------------------- facts from artifacts

def dataset_facts(root):
    funnel=progress(root);plan=load(root/'experiments/scenario-plan.json',{'scenarios':[]})['scenarios']
    admitted={r['scenario_id'] for r in funnel['scenarios'] if r['state']=='admitted'}
    by=lambda key:{v:(sum(r[key]==v for r in plan),sum(r[key]==v and r['scenario_id'] in admitted for r in plan))
                  for v in dict.fromkeys(r[key] for r in plan)}
    registry=load(root/'experiments/candidate-registry.json',{'attempts':[]})['attempts']
    return {'funnel':funnel,'by_split':by('split'),'by_fault':by('fault_class'),'groups':len({r['group_id'] for r in plan}),
            'attempts':len(registry),'failed_attempts':sum(a['execution_status']!='captured_requires_review' for a in registry),
            'complete':funnel['admitted']>=funnel['target']}


def development_facts(root):
    rows=[]
    for path in sorted(glob.glob(str(root/'results/evaluation/*.json'))):
        data=load(path,{})
        if not isinstance(data,dict) or data.get('dataset_role')!='development_pilot':continue
        if not isinstance(data.get('summaries'),list) or not all(isinstance(s,dict) and 'top1_correct' in s for s in data['summaries']):continue
        top={s['mode']:(s['top1_correct']['count'],s['denominator']) for s in data['summaries'] if s['fault_class']=='all'}
        rows.append({'file':Path(path).name,'cases':data.get('case_count'),'top1':top})
    reports=[load(p,{}) for p in glob.glob(str(root/'results/diagnoses/*/B*/result.json'))]
    costs=[r['generated'].get('estimated_paid_api_cost_usd') for r in reports if r.get('generated')]
    latency=[r['generated'].get('api_latency_seconds') for r in reports if r.get('generated')]
    tokens=[r['generated'].get('usage_metadata',{}).get('total_token_count') for r in reports if r.get('generated')]
    clean=lambda xs:[x for x in xs if isinstance(x,(int,float))]
    return {'evaluations':rows,'reports':len(reports),'cost_total':sum(clean(costs)) if clean(costs) else None,
            'latency_median':statistics.median(clean(latency)) if clean(latency) else None,
            'tokens_median':statistics.median(clean(tokens)) if clean(tokens) else None}


def official_facts(root):
    data=load(root/OFFICIAL)
    if not data or data.get('dataset_role')!='official_test':return {'available':False}
    summary={(s['mode'],s['fault_class']):s for s in data['summaries']}
    per={}
    for mode in MODES:
        rows=[r for r in data['rows'] if r['mode']==mode];cost=[];latency=[]
        for row in rows:
            report=load(row.get('report',''),{}) if row.get('report') else {}
            generated=report.get('generated') or {}
            if isinstance(generated.get('estimated_paid_api_cost_usd'),(int,float)):cost.append(generated['estimated_paid_api_cost_usd'])
            if isinstance(report.get('analysis_latency_seconds'),(int,float)):latency.append(report['analysis_latency_seconds'])
        per[mode]={'cost_mean':statistics.mean(cost) if cost else None,'latency_median':statistics.median(latency) if latency else None}
    return {'available':True,'cases':data['case_count'],'summary':summary,'per_mode':per,
            'fault_classes':sorted({k[1] for k in summary if k[1]!='all'})}


def final_label(unit):
    def label(x):return x.get('label') if isinstance(x,dict) else x
    if unit.get('adjudication'):return label(unit['adjudication'])
    a,b=label(unit.get('reviewer_1')),label(unit.get('reviewer_2'))
    return a if a and a==b else None


def grounding_facts(root):
    folders=sorted(glob.glob(str(root/'results/review-handoff/claim-review-official*')))
    if not folders:return {'available':False,'reason':'Chưa có bộ phiếu chấm claim cho tập test chính thức.'}
    folder=Path(folders[-1]);manifest=load(folder/'coordinator-manifest.json',{})
    modes={m['review_id']:m['mode'] for m in manifest.get('reviewer_mapping_do_not_distribute_with_forms',[])}
    per={};unlabeled=0
    for path in folder.glob('REVIEW-*.json'):
        review=load(path,{});mode=modes.get(review.get('review_id'))
        labels=[final_label(u) for u in review.get('units',[])]
        if not mode or not labels or any(l is None for l in labels):unlabeled+=1;continue
        row=per.setdefault(mode,{'units':0,'supported':0,'reports':0,'reports_with_unsupported':0})
        row['units']+=len(labels);row['supported']+=sum(l in SUPPORTED for l in labels)
        row['reports']+=1;row['reports_with_unsupported']+=any(l in UNSUPPORTED for l in labels)
    if unlabeled or not per:
        return {'available':False,'reason':f'{unlabeled} phiếu chưa đủ nhãn của hai reviewer hoặc phân xử.'}
    return {'available':True,'per_mode':per,'folder':folder.name}


def human_facts(root):
    data=load(root/HUMAN)
    cancelled=load(root/'experiments/human-study-cancelled.json',{})
    if cancelled.get('status')=='cancelled_before_any_session':return {'available':False,'cancelled':True,'record':cancelled}
    if not data or data.get('status')!='completed_observed_pilot':return {'available':False}
    return {'available':True,**data}


def live_facts(root):
    rows=[load(p,{}) for p in glob.glob(str(root/'results/live-diagnoses/*/ttd.json'))]
    ok=[r['ttd_seconds'] for r in rows if r.get('status')=='report_generated' and isinstance(r.get('ttd_seconds'),(int,float))]
    return {'available':bool(ok),'count':len(rows),'ok':len(ok),'failed':len(rows)-len(ok),
            'median':statistics.median(ok) if ok else None,'min':min(ok) if ok else None,'max':max(ok) if ok else None}


def collect(root=ROOT):
    root=Path(root)
    return {'preliminary':load(root/'results/evaluation/preliminary-test-B0-B3.json'),'live':live_facts(root),'dataset':dataset_facts(root),'development':development_facts(root),'official':official_facts(root),
            'grounding':grounding_facts(root),'human':human_facts(root),
            'built_at':dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).strftime('%d/%m/%Y %H:%M (UTC+7)')}


def pending_items(facts):
    items=[]
    d=facts['dataset']
    if not d['complete']:items.append(f'Dataset: {d["funnel"]["admitted"]}/200 ca admitted (cần reviewer duyệt; nếu dừng sớm, báo cáo theo quy tắc dừng sớm khi có ≥10 ca test admitted).')
    if not facts['official']['available']:items.append('Benchmark B0–B3 trên 40 ca test chính thức chưa chạy ('+OFFICIAL+').')
    if not facts['grounding']['available']:items.append('Evidence grounding/hallucination: '+facts['grounding'].get('reason',''))
    if not facts['human']['available'] and not facts['human'].get('cancelled'):items.append('Đo thời gian người thật (RB16) chưa hoàn tất ('+HUMAN+').')
    if not facts['live']['available']:items.append('Live TTD alert → report chưa đo (scripts/auto_diagnose.py).')
    if not facts['human'].get('cancelled') and not (facts['human']['available'] and facts['official']['available']):items.append('ROI/Net value chưa tính được vì thiếu số đo người thật hoặc chi phí test.')
    return items



META=ROOT/'config/thesis-meta.json'


def test_count(root=ROOT):
    return sum(line.lstrip().startswith('def test_') for p in (Path(root)/'tests').glob('test_*.py') for line in p.read_text().splitlines())


def case_analysis(root=ROOT):
    """Per-case Top-1 of each mode plus token/cost per mode, from the official manifest if any, else the preliminary one."""
    root=Path(root)
    for name,role in (('manifest.json','official_test'),('manifest-preliminary.json','preliminary_unreviewed_test')):
        for path in sorted(glob.glob(str(root/'results/prospective-benchmark/*/test'/name))):
            manifest=load(path,{})
            if manifest.get('dataset_role')!=role or (role=='official_test' and manifest.get('status')!='prepared_for_scoring'):continue
            base=Path(path).parent;rows=[];usage={m:{'tokens':[],'cost':[],'latency':[]} for m in ('B1','B2','B3')}
            for case in manifest['cases']:
                row={'scenario_id':case['scenario_id'],'fault':case['expected']['fault_type'],'target':case['expected']['target']}
                for mode in ('B0','B1','B2','B3'):
                    saved=load(base/case['reports'][mode],{});report=(saved.get('generated') or {}).get('report') or {}
                    hyp=report.get('hypotheses') or [];row[mode]=(hyp[0]['service'],hyp[0]['fault_type']) if hyp else None
                    if mode!='B0' and saved.get('generated'):
                        g=saved['generated'];usage[mode]['tokens'].append((g.get('usage_metadata') or {}).get('prompt_token_count') or 0)
                        usage[mode]['cost'].append(g.get('estimated_paid_api_cost_usd') or 0);usage[mode]['latency'].append(g.get('api_latency_seconds') or 0)
                rows.append(row)
            return {'role':role,'rows':rows,'usage':usage}
    return None


def live_rows(root=ROOT):
    rows=[]
    for path in sorted(glob.glob(str(Path(root)/'results/live-diagnoses/*/ttd.json'))):
        t=load(path,{});report=load(Path(root)/'results/diagnoses'/str(t.get('context_id'))/t.get('mode','B3')/'result.json',{}) if t.get('context_id') else {}
        hyp=((report.get('generated') or {}).get('report') or {}).get('hypotheses') or []
        rows.append({**t,'top1':f'{hyp[0]["service"]} / {hyp[0]["fault_type"]}' if hyp else '—',
                     'cost':(report.get('generated') or {}).get('estimated_paid_api_cost_usd')})
    return rows


# ---------------------------------------------------------------- document (FIT NEU template)

def build(facts,output=OUT,root=ROOT,submission=True):
    SUBMISSION=submission
    from docx import Document
    from docx.enum.section import WD_SECTION
    from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
    from docx.enum.text import WD_ALIGN_PARAGRAPH,WD_TAB_ALIGNMENT
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm,Pt,RGBColor

    meta=json.loads(Path(META).read_text())
    C,J,L=WD_ALIGN_PARAGRAPH.CENTER,WD_ALIGN_PARAGRAPH.JUSTIFY,WD_ALIGN_PARAGRAPH.LEFT
    doc=Document();font='Times New Roman'

    def set_font(style,size,bold=False,italic=False):
        style.font.name=font;style.font.size=Pt(size);style.font.bold=bold;style.font.italic=italic;style.font.color.rgb=RGBColor(0,0,0)
        rpr=style.element.get_or_add_rPr();fonts=rpr.find(qn('w:rFonts'))
        if fonts is None:fonts=OxmlElement('w:rFonts');rpr.append(fonts)
        for key in list(fonts.attrib):
            if key.endswith('Theme'):fonts.attrib.pop(key)
        for key in ('ascii','hAnsi','eastAsia','cs'):fonts.set(qn('w:'+key),font)

    # 2.2.1: TNR 13, justified, line spacing 1.3. 2.2.2: chapter 18 caps bold centred; sections 13 bold, 6pt/0pt.
    normal=doc.styles['Normal'];set_font(normal,13)
    normal.paragraph_format.line_spacing=1.3;normal.paragraph_format.alignment=J
    normal.paragraph_format.space_after=Pt(6);normal.paragraph_format.first_line_indent=Cm(1)
    for name,size in (('Heading 1',18),('Heading 2',13),('Heading 3',13),('Heading 4',13)):
        st=doc.styles[name];set_font(st,size,bold=True);pf=st.paragraph_format
        pf.keep_with_next=True;pf.first_line_indent=Cm(0);pf.left_indent=Cm(0);pf.line_spacing=1.3
        pf.space_before=Pt(6);pf.space_after=Pt(0);pf.alignment=C if name=='Heading 1' else L
        if name=='Heading 1':pf.page_break_before=True;pf.space_after=Pt(12)
    from docx.enum.style import WD_STYLE_TYPE
    figcap=doc.styles.add_style('Figure Caption',WD_STYLE_TYPE.PARAGRAPH);figcap.base_style=doc.styles['Normal'];set_font(figcap,13,italic=True)
    figcap.paragraph_format.alignment=C;figcap.paragraph_format.first_line_indent=Cm(0);figcap.paragraph_format.space_after=Pt(10)
    cap=doc.styles['Caption'];set_font(cap,13,bold=True);cap.paragraph_format.alignment=C
    cap.paragraph_format.first_line_indent=Cm(0);cap.paragraph_format.keep_with_next=True;cap.paragraph_format.space_after=Pt(3)
    for st in doc.styles:
        for border in list(st.element.iter(qn('w:pBdr'))):border.getparent().remove(border)
    for name in ('List Bullet','List Number'):
        st=doc.styles[name];set_font(st,13);st.paragraph_format.first_line_indent=None;st.paragraph_format.line_spacing=1.3

    sec=doc.sections[0]
    def margins(s):
        s.page_width=Cm(21);s.page_height=Cm(29.7);s.top_margin=s.bottom_margin=Cm(2.5)
        s.left_margin=Cm(3.5);s.right_margin=Cm(2.5);s.footer_distance=Cm(1.2)
    margins(sec)
    pending=[];state={'chapter':0,'table':0,'eq':0,'fig':0,'first_in_section':False}
    FIG=Path(root)/'docs/submission/figures'

    # ------------------------------------------------------------------ helpers
    def para(text='',bold=False,italic=False,align=None,size=None,after=None,indent=True,keep=False):
        p=doc.add_paragraph()
        if text:
            r=p.add_run(text);r.bold=bold;r.italic=italic
            if size:r.font.size=Pt(size)
        if align is not None:p.alignment=align
        if not indent or align in (C,L):p.paragraph_format.first_line_indent=Cm(0)
        if after is not None:p.paragraph_format.space_after=Pt(after)
        if keep:p.paragraph_format.keep_with_next=True
        return p

    def rich(parts):
        """parts: list of (text, bold) for a paragraph with an inline bold lead."""
        p=doc.add_paragraph()
        for text,bold in parts:p.add_run(text).bold=bold
        return p

    def bullets(items,numbered=False):
        for item in items:
            p=doc.add_paragraph(style='List Number' if numbered else 'List Bullet');p.add_run(item);p.paragraph_format.space_after=Pt(3)

    def place(parent,elem,before):
        """Insert elem before the first existing child named in `before` (keeps OOXML schema order)."""
        for child in parent:
            if child.tag in {qn('w:'+t) for t in before}:child.addprevious(elem);return elem
        parent.append(elem);return elem

    def shade(p,fill):
        s=OxmlElement('w:shd')
        for k,v in (('val','clear'),('color','auto'),('fill',fill)):s.set(qn('w:'+k),v)
        place(p._p.get_or_add_pPr(),s,('tabs','suppressAutoHyphens','kinsoku','wordWrap','overflowPunct','topLinePunct','autoSpaceDE',
              'autoSpaceDN','bidi','adjustRightInd','snapToGrid','spacing','ind','contextualSpacing','mirrorIndents','suppressOverlap',
              'jc','textDirection','textAlignment','textboxTightWrap','outlineLvl','divId','cnfStyle','rPr','sectPr','pPrChange'))

    def wait(text,formal=None):
        pending.append(text)
        if SUBMISSION and formal:
            para(formal);return
        p=doc.add_paragraph();shade(p,'FFF2CC');p.paragraph_format.first_line_indent=Cm(0)
        r=p.add_run('[Chờ dữ liệu] ');r.bold=True;r.font.color.rgb=RGBColor(0x9C,0x57,0x00);p.add_run(text).italic=True

    def field(p,instr,placeholder=''):
        r=p.add_run()
        def fc(kind):
            f=OxmlElement('w:fldChar');f.set(qn('w:fldCharType'),kind);r._r.append(f)
        fc('begin');t=OxmlElement('w:instrText');t.set(qn('xml:space'),'preserve');t.text=instr;r._r.append(t);fc('separate')
        if placeholder:
            t=OxmlElement('w:t');t.text=placeholder;r._r.append(t)
        fc('end')

    def H(text,level=1,first=False):
        if level==1 and text.startswith('CHƯƠNG'):state['chapter']=int(text.split()[1].rstrip('.'));state['table']=0;state['eq']=0;state['fig']=0
        h=doc.add_heading(text,level)
        if level==1 and state['first_in_section']:h.paragraph_format.page_break_before=False;state['first_in_section']=False
        return h

    def F(name):
        """Reserve the next figure label only if the image exists."""
        if not any((FIG/(name+ext)).is_file() for ext in ('.png','.jpg')):return None
        state['fig']+=1;return f'Hình {state["chapter"]}.{state["fig"]}'

    def figure(label,name,title,width=15.5):
        img=next(FIG/(name+ext) for ext in ('.png','.jpg') if (FIG/(name+ext)).is_file())
        p=para(align=C,after=2);p.paragraph_format.keep_with_next=True;p.add_run().add_picture(str(img),width=Cm(width))
        doc.add_paragraph(f'{label}. {title}',style='Figure Caption')

    def T():
        state['table']+=1;return f'Bảng {state["chapter"]}.{state["table"]}'

    def table(label,title,headers,rows,widths):
        c=doc.add_paragraph(f'{label}. {title}',style='Caption')
        t=doc.add_table(rows=1,cols=len(headers));t.autofit=False;t.alignment=1
        borders=OxmlElement('w:tblBorders')
        for edge in ('top','left','bottom','right','insideH','insideV'):
            e=OxmlElement('w:'+edge)
            for k,v in (('val','single'),('sz','4'),('color','000000')):e.set(qn('w:'+k),v)
            borders.append(e)
        place(t._tbl.tblPr,borders,('shd','tblLayout','tblCellMar','tblLook','tblCaption','tblDescription'))
        for i,h in enumerate(headers):t.rows[0].cells[i].text=h
        for row in rows:
            for cell,value in zip(t.add_row().cells,row):cell.text=str(value)
        for ri,row in enumerate(t.rows):
            trpr=row._tr.get_or_add_trPr();trpr.append(OxmlElement('w:cantSplit'))
            if ri==0:trpr.append(OxmlElement('w:tblHeader'))
            for ci_,cell in enumerate(row.cells):
                cell.width=Cm(widths[ci_]);cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
                if ri==0:
                    s=OxmlElement('w:shd')
                    for k,v in (('val','clear'),('color','auto'),('fill','D9E2F3')):s.set(qn('w:'+k),v)
                    place(cell._tc.get_or_add_tcPr(),s,('noWrap','tcMar','textDirection','tcFitText','vAlign','hideMark'))
                for p in cell.paragraphs:
                    p.alignment=C if ri==0 else L;pf=p.paragraph_format;pf.space_after=Pt(1);pf.line_spacing=1.15;pf.first_line_indent=Cm(0)
                    for r in p.runs:r.font.size=Pt(12);r.bold=ri==0
        para('',after=0)

    def equation(text):
        """2.2.3: numbered in parentheses, aligned right."""
        state['eq']+=1;label=f'({state["chapter"]}.{state["eq"]})'
        p=doc.add_paragraph();p.paragraph_format.first_line_indent=Cm(0)
        stops=p.paragraph_format.tab_stops;stops.add_tab_stop(Cm(7.5),WD_TAB_ALIGNMENT.CENTER);stops.add_tab_stop(Cm(15),WD_TAB_ALIGNMENT.RIGHT)
        r=p.add_run('\t'+text+'\t'+label);r.italic=False
        return label

    def new_section(fmt=None,start=None,number=True):
        s=doc.add_section(WD_SECTION.NEW_PAGE);margins(s);state['first_in_section']=True
        s.footer.is_linked_to_previous=False;fp=s.footer.paragraphs[0];fp.alignment=C;fp.paragraph_format.first_line_indent=Cm(0)
        for r in list(fp.runs):r._r.getparent().remove(r._r)
        if number:field(fp,'PAGE','1')
        pg=s._sectPr.find(qn('w:pgNumType'))
        if pg is None:pg=place(s._sectPr,OxmlElement('w:pgNumType'),('cols','formProt','vAlign','noEndnote','titlePg','textDirection','bidi','rtlGutter','docGrid','printerSettings'))
        if fmt:pg.set(qn('w:fmt'),fmt)
        if start:pg.set(qn('w:start'),str(start))
        return s

    def page_border(s):
        # Same border as the faculty template (twistedLines1, sz 18).
        borders=OxmlElement('w:pgBorders');borders.set(qn('w:zOrder'),'back')
        for edge,space in (('top','1'),('left','4'),('bottom','1'),('right','4')):
            e=OxmlElement('w:'+edge)
            for k,v in (('val','twistedLines1'),('sz','18'),('space',space),('color','auto')):e.set(qn('w:'+k),v)
            borders.append(e)
        place(s._sectPr,borders,('lnNumType','pgNumType','cols','formProt','vAlign','noEndnote','titlePg','textDirection','bidi','rtlGutter','docGrid','printerSettings'))

    def spine(paragraph):
        """Vertical spine text box at the left edge of the main cover, as in the template."""
        from docx.oxml import parse_xml
        from xml.sax.saxutils import escape
        items=[meta['academic_term'],meta['major'],meta['student'].upper(),meta['student_id']]
        runs=''.join(('<w:r><w:rPr><w:b/><w:sz w:val="24"/></w:rPr><w:tab/></w:r>' if i else '')+
                     f'<w:r><w:rPr><w:b/><w:sz w:val="24"/></w:rPr><w:t xml:space="preserve">{escape(t)}</w:t></w:r>' for i,t in enumerate(items))
        xml=('<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
             'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
             'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
             'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"><w:drawing>'
             '<wp:anchor distT="0" distB="0" distL="0" distR="0" simplePos="0" relativeHeight="251660288" behindDoc="0" locked="0" layoutInCell="1" allowOverlap="1">'
             '<wp:simplePos x="0" y="0"/><wp:positionH relativeFrom="page"><wp:posOffset>420000</wp:posOffset></wp:positionH>'
             '<wp:positionV relativeFrom="page"><wp:posOffset>900000</wp:posOffset></wp:positionV><wp:extent cx="613410" cy="9194165"/>'
             '<wp:effectExtent l="0" t="0" r="0" b="0"/><wp:wrapNone/><wp:docPr id="9001" name="Spine"/><wp:cNvGraphicFramePr/>'
             '<a:graphic><a:graphicData uri="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"><wps:wsp>'
             '<wps:cNvSpPr txBox="1"/><wps:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="613410" cy="9194165"/></a:xfrm>'
             '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></wps:spPr>'
             '<wps:txbx><w:txbxContent><w:p><w:pPr><w:tabs><w:tab w:val="center" w:pos="5900"/><w:tab w:val="center" w:pos="9600"/>'
             '<w:tab w:val="right" w:pos="13000"/></w:tabs><w:spacing w:after="0"/><w:ind w:firstLine="0"/></w:pPr>'+runs+'</w:p></w:txbxContent></wps:txbx>'
             '<wps:bodyPr rot="0" vert="vert" wrap="square" lIns="91440" tIns="45720" rIns="91440" bIns="45720" anchor="ctr" upright="1"><a:noAutofit/></wps:bodyPr>'
             '</wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing></w:r>')
        paragraph._p.append(parse_xml(xml))

    def front_title(text):
        p=para(text,bold=True,align=C,size=18,after=12);p.paragraph_format.keep_with_next=True;return p

    d=facts['dataset'];f=d['funnel'];dev=facts['development'];off=facts['official'];gr=facts['grounding'];hu=facts['human'];lv=facts['live']
    month=dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).strftime('%m/%Y').lstrip('0')

    # ------------------------------------------------------------------ covers (template: border, logo, no page number)
    def cover(extra,with_spine=False,signature=False):
        first=para(meta['university'],bold=True,align=C,size=14,after=0)
        if with_spine:spine(first)
        para(meta['school'],bold=True,align=C,size=14,after=0)
        para('--------oOo--------',align=C,after=18)
        logo=Path(root)/meta.get('logo','')
        if meta.get('logo') and logo.is_file():
            p=para(align=C,after=18);p.add_run().add_picture(str(logo),width=Cm(3.6))
        else:
            p=para('[Logo Đại học Kinh tế Quốc dân]',align=C,italic=True,after=18);shade(p,'FFF2CC')
        para('',after=24)
        para('KHÓA LUẬN TỐT NGHIỆP',bold=True,align=C,size=22,after=24)
        para(meta['title'],bold=True,align=C,size=18,after=6)
        para(meta['title_en'],italic=True,align=C,size=13,after=36)
        t=doc.add_table(rows=0,cols=2);t.alignment=1
        for k,v in [('Tên sinh viên',meta['student'])]+extra+[('Giảng viên hướng dẫn',meta['supervisor_title']+' '+meta['supervisor'])]:
            cells=t.add_row().cells;cells[0].width=Cm(5.5);cells[1].width=Cm(7.5)
            for cell,text in ((cells[0],k),(cells[1],': '+v)):
                p=cell.paragraphs[0];p.paragraph_format.first_line_indent=Cm(0);p.alignment=L;r=p.add_run(text);r.bold=True;r.font.size=Pt(14)
        if signature:
            p=para('(Chữ ký GVHD)',italic=True,after=0);p.alignment=WD_ALIGN_PARAGRAPH.RIGHT;p.paragraph_format.right_indent=Cm(1.5)
            para('',after=48)
        else:para('',after=60);para('',after=60)
        para(f'{meta["place"]}, {month}',bold=True,align=C,size=14)
    # Cover margins follow the template's first section (top/bottom 2.5 cm, left 4 cm, right 2 cm).
    sec.left_margin=Cm(4);sec.right_margin=Cm(2)
    page_border(sec)
    cover([],with_spine=True)
    doc.add_paragraph().add_run().add_break(__import__('docx.enum.text',fromlist=['WD_BREAK']).WD_BREAK.PAGE)
    cover([('Mã sinh viên',meta['student_id']),('Lớp',meta['class']),('Ngành',meta['major'].capitalize().replace('máy tính','máy tính')),
           ('Khoa',meta['faculty'].replace('KHOA ','').capitalize())],signature=True)

    # ------------------------------------------------------------------ front matter (roman numbering)
    new_section(fmt='lowerRoman',start=1)
    front_title('MỤC LỤC');field(para(indent=False),'TOC \\o "1-3" \\h \\z \\u','Nhấn chuột phải → Update Field (F9) để cập nhật mục lục.')
    H('LỜI CAM ĐOAN')
    para(f'Khóa luận này do tôi tự thực hiện trong học kỳ cuối, với sự định hướng của {meta["supervisor_title"]} {meta["supervisor"]}. '
         'Mọi con số trong các chương được tính từ dữ liệu thực nghiệm mà tôi thu trên testbed riêng và lưu lại cùng mã nguồn, nên người đọc có thể '
         'chạy lại để đối chiếu; chỗ nào chưa có số đo thì được để trống và ghi chú rõ thay vì ước đoán. Ý tưởng, số liệu hay hình bảng lấy từ '
         'công trình khác đều được dẫn nguồn theo chuẩn IEEE.')
    para('Trong quá trình thực hiện, tôi có sử dụng trợ lý trí tuệ nhân tạo Claude (Anthropic) để hỗ trợ viết và kiểm thử mã nguồn, soạn thảo và biên tập '
         'văn bản báo cáo. Mọi nội dung có sự hỗ trợ của công cụ này đều đã được tôi đọc, kiểm tra lại với mã nguồn và dữ liệu, và tôi chịu trách nhiệm về '
         'chúng. Các số liệu, bảng và hình về kết quả được tính trực tiếp từ dữ liệu thực nghiệm đã lưu, không do công cụ AI tạo ra. Mô hình Gemini (Google) '
         'được dùng như một thành phần của hệ thống được nghiên cứu, không dùng để viết báo cáo.')
    para('Nếu có sai lệch so với những điều nêu trên, tôi chịu trách nhiệm trước Khoa và Nhà trường.')
    for text,b,it in ((f'{meta["place"]}, ngày …… tháng …… năm {dt.date.today().year}',False,True),('Sinh viên',True,False),
                      ('(Ký và ghi rõ họ tên)',False,True),('',False,False),('',False,False),(meta['student'],True,False)):
        p=para(text,bold=b,italic=it,after=0,align=C)
        p.paragraph_format.left_indent=Cm(8)
    H('LỜI CẢM ƠN')
    para(f'Những góp ý của {meta["supervisor_title"]} {meta["supervisor"]}, nhất là về cách thu hẹp phạm vi, chọn ba nhóm lỗi và đánh giá bằng cả '
         'chi phí lẫn độ chính xác, đã định hình phần lớn khóa luận này. Em cảm ơn Thầy vì đã dành thời gian đọc và phản biện từng bản nháp.')
    para('Em cũng cảm ơn các thầy cô Khoa Công nghệ thông tin, Trường Công nghệ, Đại học Kinh tế Quốc dân về những môn học làm nền cho đề tài, '
         'và cảm ơn gia đình, bạn bè đã ở bên em trong những tuần chạy thực nghiệm kéo dài.')
    H('DANH MỤC TỪ VIẾT TẮT')
    abbreviations=[('AIOps','Artificial Intelligence for IT Operations','Trí tuệ nhân tạo cho vận hành CNTT'),
        ('API','Application Programming Interface','Giao diện lập trình ứng dụng'),('CI','Confidence Interval','Khoảng tin cậy'),
        ('CPU','Central Processing Unit','Bộ xử lý trung tâm'),('KB','Knowledge Base','Cơ sở tri thức'),
        ('LLM','Large Language Model','Mô hình ngôn ngữ lớn'),('MRR','Mean Reciprocal Rank','Hạng nghịch đảo trung bình'),
        ('MTTR','Mean Time To Resolution','Thời gian khắc phục trung bình'),('OOM','Out Of Memory','Hết bộ nhớ'),
        ('RAG','Retrieval-Augmented Generation','Sinh văn bản tăng cường truy xuất'),('RCA','Root Cause Analysis','Phân tích nguyên nhân gốc'),
        ('SRE','Site Reliability Engineering','Kỹ thuật độ tin cậy hệ thống'),('TTD','Time To Diagnosis','Thời gian chẩn đoán'),
        ('UI','User Interface','Giao diện người dùng'),('UTC','Coordinated Universal Time','Giờ phối hợp quốc tế')]
    t=doc.add_table(rows=1,cols=3);t.style='Table Grid'
    for i,h in enumerate(('Viết tắt','Tiếng Anh','Tiếng Việt')):t.rows[0].cells[i].text=h
    for row in abbreviations:
        for cell,v in zip(t.add_row().cells,row):cell.text=v
    for ri,row in enumerate(t.rows):
        for ci_,cell in enumerate(row.cells):
            cell.width=Cm((2.5,6.5,6)[ci_])
            for p in cell.paragraphs:
                p.paragraph_format.first_line_indent=Cm(0);p.alignment=L
                for r in p.runs:r.font.size=Pt(12);r.bold=ri==0
    H('DANH MỤC BẢNG')
    field(para(indent=False),'TOC \\h \\z \\t "Caption,1"','Nhấn chuột phải → Update Field (F9) để cập nhật danh mục bảng.')
    H('DANH MỤC HÌNH')
    field(para(indent=False),'TOC \\h \\z \\t "Figure Caption,1"','Nhấn chuột phải → Update Field (F9) để cập nhật danh mục hình.')

    # ------------------------------------------------------------------ main body (arabic numbering from 1)
    new_section(fmt='decimal',start=1)
    H('MỞ ĐẦU')
    para('Hệ thống phần mềm hiện đại thường được xây dựng theo kiến trúc microservices và vận hành trên Kubernetes. Khi xảy ra sự cố, '
         'dấu vết của nó phân tán ở log, metric và trace của nhiều dịch vụ, khiến việc tìm nguyên nhân gốc phụ thuộc lớn vào kinh nghiệm '
         'của kỹ sư vận hành. Các mô hình ngôn ngữ lớn có khả năng tổng hợp thông tin và suy luận trên văn bản, mở ra khả năng xây dựng '
         'trợ lý hỗ trợ chẩn đoán, nhưng cũng có nguy cơ đưa ra kết luận không có căn cứ.')
    rich([('Tên đề tài: ',True),(meta['title'].capitalize()+'.',False)])
    rich([('Mục đích: ',True),('xây dựng và đánh giá một trợ lý chẩn đoán sự cố kết hợp mô hình ngôn ngữ lớn (LLM) với sinh văn bản tăng cường '
          'truy xuất (RAG) trên telemetry đa nguồn, có bằng chứng truy ngược và có đánh giá định lượng về độ chính xác, thời gian và chi phí.',False)])
    rich([('Phương pháp: ',True),('thực nghiệm có kiểm soát trên testbed Sock Shop/Kubernetes; lỗi được tiêm bằng Chaos Mesh để tạo nhãn '
          'đúng; dữ liệu thu theo protocol được ghim bằng hash và duyệt độc lập; bốn cấu hình B0–B3 được so sánh trên cùng tập kiểm thử.',False)])
    res=(f'đã xây dựng pipeline đầy đủ từ alert tới báo cáo chẩn đoán; {f["captured_scenarios"]}/200 cấu hình đã được thu, '
         f'{f["admitted"]}/200 ca đã được duyệt vào bộ dữ liệu')
    if lv['available']:res+=f'; thời gian từ alert tới báo cáo trên đường live có trung vị {num(lv["median"],1)} giây'
    rich([('Kết quả chính: ',True),(res+'.',False)])
    pre=facts.get('preliminary')
    if not off['available'] and pre:
        para(f'Benchmark chính thức trên các ca đã được duyệt độc lập chưa hoàn tất; bốn cấu hình đã được chạy sơ bộ trên {pre["case_count"]} ca test '
             'chưa qua review độc lập (mục 4.5), kết quả chỉ mang tính sơ bộ.')
    if not off['available']:wait('Kết quả benchmark chính thức trên tập test sẽ được bổ sung vào phần này khi hoàn tất.',
        formal='Benchmark chính thức trên các ca đã qua duyệt độc lập chưa hoàn tất tại thời điểm nộp và được nêu là việc tiếp theo ở phần Kết luận.')
    para('Ngoài phần mở đầu và kết luận, khóa luận gồm bốn chương: Chương 1 trình bày tổng quan về đề tài; Chương 2 trình bày cơ sở lý thuyết; '
         'Chương 3 trình bày phương pháp nghiên cứu và thiết kế hệ thống; Chương 4 trình bày kết quả và thảo luận.')

    # ======================================================= CHƯƠNG 1
    H('CHƯƠNG 1. TỔNG QUAN VỀ ĐỀ TÀI')
    H('1.1. Lý do chọn đề tài',2)
    H('1.1.1. Bối cảnh vận hành hệ thống microservices',3)
    para('Kiến trúc microservices chia một ứng dụng thành nhiều dịch vụ nhỏ, triển khai độc lập và giao tiếp qua mạng. Cách tiếp cận này '
         'giúp phát triển và mở rộng linh hoạt, nhưng làm tăng số thành phần cần giám sát và số đường lan truyền lỗi. Một sự cố ở một dịch vụ '
         'có thể biểu hiện thành độ trễ hoặc lỗi ở dịch vụ khác phía trước, khiến triệu chứng và nguyên nhân nằm ở hai nơi khác nhau.')
    para('Để quan sát hệ thống, các đội vận hành thu ba loại telemetry chính: metric (chuỗi thời gian về tài nguyên và yêu cầu), log (bản ghi '
         'sự kiện của ứng dụng) và distributed trace (đường đi của một yêu cầu qua các dịch vụ). Lượng dữ liệu này lớn và phân tán ở nhiều '
         'công cụ khác nhau.')
    H('1.1.2. Hạn chế của chẩn đoán thủ công',3)
    para('Khi nhận cảnh báo, kỹ sư phải mở dashboard, truy vấn log, đọc trace, đối chiếu runbook và loại trừ dần các giả thuyết. Quy trình này '
         'tốn thời gian, phụ thuộc kinh nghiệm cá nhân và làm tăng thời gian khắc phục trung bình (MTTR). Cảnh báo dựa trên ngưỡng chỉ cho biết '
         'triệu chứng vượt mức, không cho biết nguyên nhân gốc.')
    para('Mô hình ngôn ngữ lớn có thể đọc và tóm tắt bằng chứng từ nhiều nguồn. Tuy nhiên, nếu không được cung cấp bằng chứng có cấu trúc '
         'và tri thức vận hành phù hợp, mô hình có thể tạo ra kết luận nghe hợp lý nhưng không được dữ liệu hỗ trợ. Đề tài được chọn để '
         'kiểm chứng một cách định lượng khi nào và ở mức độ nào LLM kết hợp RAG thực sự giúp ích cho chẩn đoán sự cố.')
    H('1.1.3. Quy trình xử lý sự cố trong thực tế',3)
    para('Trong mô hình vận hành phổ biến, một sự cố đi qua năm bước: phát hiện, phân loại mức độ, chẩn đoán, khắc phục và rút kinh nghiệm sau sự cố [10]. '
         'Phát hiện thường được tự động hóa bằng luật cảnh báo; khắc phục có thể dựa vào runbook hoặc thao tác quay lui phiên bản. Bước chẩn đoán là bước '
         'khó tự động nhất vì nó đòi hỏi suy luận trên nhiều nguồn dữ liệu có cấu trúc khác nhau và trên hiểu biết về kiến trúc hệ thống.')
    para('Người trực sự cố thường bắt đầu từ cảnh báo, mở dashboard để xem dịch vụ nào có tài nguyên hoặc độ trễ bất thường, sau đó lọc log theo khoảng thời gian '
         'và tìm trace của các yêu cầu lỗi. Mỗi bước chuyển đổi giữa các công cụ làm mất thời gian và dễ bỏ sót tín hiệu. Khi hệ thống có nhiều dịch vụ, một sự cố '
         'thật thường kéo theo nhiều cảnh báo phụ ở các dịch vụ phía trước, và cảnh báo đến sớm nhất chưa chắc nằm ở dịch vụ gây lỗi.')
    para('Một khó khăn khác là nhiễu nền. Hệ thống đang chạy luôn có những lỗi không liên quan tới sự cố hiện tại, ví dụ một dịch vụ phụ ghi lỗi kết nối lặp đi lặp lại '
         'từ trước. Người có kinh nghiệm biết bỏ qua các tín hiệu này; một công cụ tự động thì phải được thiết kế và đánh giá để không bị chúng đánh lừa. Chương 4 '
         'cho thấy đây chính là kiểu sai phổ biến nhất của các cấu hình chỉ dùng log.')
    H('1.2. Mục đích và câu hỏi nghiên cứu',2)
    H('1.2.1. Mục đích',3)
    bullets(['Dựng một chuỗi xử lý liền mạch trên Kubernetes, đi từ cảnh báo tới báo cáo chẩn đoán, có thể dựng lại trọn vẹn trên một laptop.',
             'Tích hợp LLM và RAG để đề xuất nguyên nhân gốc, hướng khắc phục và trích dẫn mã bằng chứng từ telemetry.',
             'Xây dựng bộ dữ liệu 200 ca có nhãn đúng bằng Chaos Engineering, với protocol thu thập được ghim trước và duyệt độc lập.',
             'Đánh giá các cấu hình bằng độ chính xác, mức độ có căn cứ của kết luận, thời gian chẩn đoán, chi phí API và giá trị giờ công.'])
    H('1.2.2. Câu hỏi nghiên cứu',3)
    bullets(['RQ1: So với bộ luật ngưỡng chạy trên cùng ngữ cảnh (B0), mô hình ngôn ngữ có truy xuất tri thức (B3) chỉ ra đúng dịch vụ và loại lỗi thường xuyên hơn không?',
             'RQ2: Khi bổ sung metric và trace bên cạnh log (B3 so với B2), tỷ lệ chẩn đoán đúng có tăng và số nhận định thiếu căn cứ có giảm không?',
             'RQ3: Việc đưa runbook vào prompt qua truy xuất (B2 so với B1) có làm chẩn đoán tốt lên không?',
             'RQ4: Thời gian rút ngắn được có đủ lớn để bù tiền gọi API và đem lại giá trị cho người vận hành không?'])
    H('1.3. Đối tượng và phạm vi nghiên cứu',2)
    H('1.3.1. Đối tượng nghiên cứu',3)
    para('Đối tượng nghiên cứu là quá trình chẩn đoán nguyên nhân gốc của sự cố trong hệ thống microservices dựa trên telemetry, và vai trò '
         'của LLM, RAG, dữ liệu đa nguồn trong quá trình đó.')
    H('1.3.2. Phạm vi nghiên cứu',3)
    para('Mọi thí nghiệm diễn ra trên Sock Shop, một cửa hàng trực tuyến mẫu triển khai trong Minikube. Đề tài chỉ xét ba kiểu sự cố: dịch vụ '
         'bị thiếu CPU hoặc bộ nhớ, đường mạng giữa hai dịch vụ bị chậm hoặc rơi gói, và Pod bị dừng đột ngột. Sản phẩm chỉ đưa ra giả thuyết kèm '
         'bằng chứng để người vận hành quyết định; nó không tự can thiệp vào hệ thống thật. Sự cố do cấu hình sai không được đưa vào vì rất khó '
         'tạo ra một cách lặp lại được và có nhãn rõ ràng như ba kiểu trên.')
    H('1.4. Ý nghĩa khoa học và thực tiễn',2)
    para('Về khoa học, đề tài cung cấp một pipeline đánh giá tái lập được, trong đó nhãn đúng được tách khỏi ngữ cảnh của mô hình, mọi nguồn '
         'khoa học được ghim bằng hash và các so sánh dùng cùng tập kiểm thử với khoảng tin cậy. Về thực tiễn, đề tài đo trực tiếp thời gian '
         'và chi phí của việc dùng LLM, làm cơ sở để đánh giá giá trị vận hành thay vì chỉ dựa vào độ chính xác.')
    H('1.5. Tổng quan các nghiên cứu liên quan',2)
    H('1.5.1. Phân tích nguyên nhân gốc dựa trên telemetry',3)
    para('Các hướng RCA cho microservices ra đời trước khi có LLM chủ yếu dựa vào phát hiện bất thường trên chuỗi thời gian, dựng đồ thị phụ '
         'thuộc giữa dịch vụ hoặc suy luận nhân quả. Nhóm tác giả DiagFusion ghép log, metric và trace vào một mô hình học đồ thị và cho thấy '
         'cách ghép này chẩn đoán tốt hơn khi chỉ dùng từng nguồn riêng [2]. RCAEval đi theo hướng khác: thay vì đề xuất thuật toán mới, họ '
         'công bố một bộ benchmark với 735 ca lỗi trên ba hệ thống và 15 phương pháp đối chứng để các nghiên cứu sau so sánh cùng điều kiện [4]. '
         'MicroOps thì tập trung vào việc sinh dữ liệu mô phỏng cho các mô hình AIOps [5].')
    H('1.5.2. Tri thức sự cố và mô hình ngôn ngữ lớn',3)
    para('Ghosh và cộng sự dùng khoảng hai nghìn biên bản điều tra sự cố nội bộ của Salesforce làm kho tri thức, từ đó gợi ý nguyên nhân cho sự '
         'cố mới dựa trên những ca tương tự đã xử lý [1]. Ở quy mô lớn hơn, nhóm của Ahmed thử nghiệm LLM trên hơn bốn mươi nghìn sự cố của '
         'Microsoft và ghi nhận mô hình có thể đề xuất nguyên nhân cùng bước khắc phục hữu ích; tuy vậy dữ liệu này thuộc doanh nghiệp nên '
         'người ngoài không thể chạy lại [3]. Gần đây, Guan và cộng sự sắp xếp các sự cố đã giải quyết thành bộ nhớ có cấu trúc để LLM tra cứu [6].')
    H('1.5.3. Khoảng trống nghiên cứu',3)
    lbl=T()
    para(f'{lbl} đặt các công trình trên cạnh đề tài này. Nhìn tổng thể, còn bốn điểm để một khóa luận có thể đóng góp. Thứ nhất, phần lớn '
         'công trình đề xuất thuật toán chứ ít khi dựng trọn một hệ thống chạy được từ cảnh báo tới báo cáo. Thứ hai, các đánh giá LLM thường '
         'dùng dữ liệu đóng. Thứ ba, hiếm có nghiên cứu quy mô nhỏ dùng Chaos Engineering để tự tạo nhãn đúng rồi đưa cả ba nguồn telemetry và '
         'tri thức truy xuất vào cùng một phép so sánh. Thứ tư, tiền gọi API thường không được đặt cạnh thời gian kỹ sư tiết kiệm được.')
    table(lbl,'So sánh đề tài với các công trình liên quan',['Công trình','Dữ liệu/phương pháp','Khoảng trống so với đề tài'],[
        ['ICA – Salesforce 2022 [1]','Hồ sơ sự cố + truy xuất','Không có pipeline chaos và telemetry live'],
        ['DiagFusion 2023 [2]','Log + metric + trace + GNN','Không dùng LLM/RAG sinh giải thích'],
        ['Microsoft ICSE 2023 [3]','>40.000 sự cố + LLM','Không phải testbed tái lập'],
        ['RCAEval 2024 [4]','735 ca lỗi, 15 baseline','Không tập trung RAG/runbook và chi phí'],
        ['MicroOps 2024 [5]','Nền tảng sinh dữ liệu AIOps','Không phải trợ lý RCA dùng LLM'],
        ['Đề tài này','Sock Shop + Chaos Mesh + LLM/RAG','Ba nhóm lỗi, 200 ca, một máy cá nhân']],[4.2,5.3,5.5])
    H('1.6. Bố cục khóa luận',2)
    para('Chương 2 trình bày các khái niệm và công nghệ nền tảng. Chương 3 mô tả phương pháp nghiên cứu, kiến trúc, bộ dữ liệu và thiết kế thực '
         'nghiệm. Chương 4 trình bày kết quả, thảo luận câu hỏi nghiên cứu và các mối đe dọa đến tính hợp lệ.')

    # ======================================================= CHƯƠNG 2
    H('CHƯƠNG 2. CƠ SỞ LÝ THUYẾT')
    H('2.1. Kiến trúc microservices và Kubernetes',2)
    H('2.1.1. Kiến trúc microservices',3)
    para('Trong kiến trúc microservices, mỗi dịch vụ đảm nhận một chức năng nghiệp vụ, có dữ liệu riêng và giao tiếp với dịch vụ khác qua HTTP '
         'hoặc hàng đợi thông điệp. Ưu điểm là khả năng triển khai và mở rộng độc lập; nhược điểm là hệ thống trở thành một hệ phân tán, nơi '
         'độ trễ mạng, lỗi một phần và lan truyền lỗi theo chuỗi gọi là hiện tượng thường gặp [10].')
    para('Sock Shop là ứng dụng mẫu mô phỏng cửa hàng bán tất gồm các dịch vụ front-end, catalogue, carts, orders, payment, shipping, user, '
         'queue-master cùng các cơ sở dữ liệu MongoDB, MySQL và RabbitMQ [11]. Luồng thanh toán đi qua nhiều dịch vụ, nên phù hợp để quan sát '
         'lan truyền lỗi.')
    H('2.1.2. Kubernetes',3)
    para('Kubernetes là nền tảng điều phối container. Đơn vị triển khai nhỏ nhất là Pod; Deployment duy trì số bản sao mong muốn và thay Pod '
         'lỗi. Mỗi container khai báo request và limit cho CPU và bộ nhớ: vượt limit CPU dẫn tới bị điều tiết (throttling), vượt limit bộ nhớ '
         'dẫn tới bị hệ điều hành dừng với trạng thái OOMKilled. Readiness probe quyết định Pod có nhận lưu lượng hay không; liveness probe '
         'quyết định khởi động lại container [12]. Những cơ chế này tạo ra chính các tín hiệu mà hệ thống chẩn đoán cần đọc.')
    H('2.2. Khả năng quan sát (observability)',2)
    H('2.2.1. Metric và Prometheus',3)
    para('Prometheus thu metric theo mô hình kéo (pull) từ các endpoint, lưu dưới dạng chuỗi thời gian có nhãn và cho phép truy vấn bằng PromQL '
         '[13]. Ví dụ, tốc độ sử dụng CPU của một container được tính bằng hàm rate trên bộ đếm container_cpu_usage_seconds_total trong cửa sổ '
         'một phút; tỷ lệ này chia cho limit CPU cho biết mức độ bão hòa.')
    H('2.2.2. Log và Loki',3)
    para('Loki lưu log theo luồng được đánh nhãn (namespace, pod, container) thay vì đánh chỉ mục toàn văn, giúp nhẹ hơn ELK ở quy mô nhỏ. Log '
         'được thu bởi agent (trong đề tài là Grafana Alloy) và truy vấn theo khoảng thời gian.')
    H('2.2.3. Distributed tracing và Jaeger',3)
    para('Distributed tracing ghi lại mỗi yêu cầu dưới dạng một trace gồm nhiều span; mỗi span là một thao tác có thời điểm bắt đầu, thời lượng, '
         'dịch vụ và quan hệ cha – con [14]. Từ span client và server có thể suy ra cạnh gọi có hướng giữa hai dịch vụ và độ trễ trên cạnh đó, '
         'là tín hiệu quan trọng để phân biệt lỗi mạng với lỗi tại dịch vụ. Jaeger thu và truy vấn trace, hỗ trợ định dạng Zipkin.')
    H('2.2.4. Cảnh báo với Alertmanager',3)
    para('Prometheus đánh giá các luật cảnh báo định kỳ; khi biểu thức vượt ngưỡng liên tục trong khoảng thời gian “for”, cảnh báo chuyển sang '
         'trạng thái firing và được gửi tới Alertmanager. Alertmanager gom nhóm, khử trùng lặp và chuyển cảnh báo tới receiver, trong đề tài là '
         'webhook của incident collector.')
    H('2.3. Chaos Engineering',2)
    H('2.3.1. Nguyên lý',3)
    para('Chaos Engineering là phương pháp chủ động tiêm lỗi có kiểm soát vào hệ thống để kiểm chứng khả năng chịu lỗi [9]. Quy trình gồm xác '
         'định trạng thái ổn định, đưa ra giả thuyết, tiêm lỗi với phạm vi ảnh hưởng nhỏ và quan sát. Trong đề tài, Chaos Engineering được dùng '
         'để tạo sự cố có nhãn đúng: biết chính xác loại lỗi, mục tiêu, thời điểm bắt đầu và kết thúc.')
    H('2.3.2. Chaos Mesh',3)
    para('Chaos Mesh triển khai lỗi dưới dạng tài nguyên tùy biến của Kubernetes [15]. StressChaos tạo tải CPU hoặc chiếm bộ nhớ trong container; '
         'NetworkChaos dùng netem của Linux để thêm độ trễ hoặc mất gói trên lưu lượng giữa các dịch vụ theo hướng xác định; PodChaos dừng hoặc '
         'làm lỗi Pod. Controller báo trạng thái AllInjected khi lỗi đã được áp dụng, là mốc thời gian dùng để neo cửa sổ quan sát.')
    H('2.4. Phân tích nguyên nhân gốc và AIOps',2)
    H('2.4.1. Khái niệm',3)
    para('Phân tích nguyên nhân gốc (RCA) là xác định thành phần và cơ chế gây ra sự cố, phân biệt với các triệu chứng lan truyền. Trong khóa '
         'luận, một chẩn đoán được coi là đúng khi khớp cả dịch vụ (hoặc cạnh gọi có hướng với lỗi mạng) và nhóm lỗi. Thời gian chẩn đoán '
         '(TTD) là khoảng từ khi có cảnh báo tới khi có báo cáo chẩn đoán; MTTR bao gồm cả thời gian khắc phục.')
    H('2.4.2. Các hướng tiếp cận',3)
    para('AIOps áp dụng học máy cho vận hành: phát hiện bất thường trên metric, gom cụm log, xây đồ thị phụ thuộc từ trace, suy luận nhân quả. '
         'Các phương pháp này cho kết quả xếp hạng nhưng thường khó giải thích. LLM bổ sung khả năng diễn giải bằng ngôn ngữ tự nhiên và kết '
         'hợp tri thức dạng văn bản như runbook, với điều kiện được cung cấp bằng chứng phù hợp.')
    H('2.5. Mô hình ngôn ngữ lớn',2)
    H('2.5.1. Kiến trúc Transformer và LLM',3)
    para('Các LLM hiện nay dựa trên kiến trúc Transformer với cơ chế self-attention, cho phép mỗi token tham chiếu tới mọi token khác trong ngữ '
         'cảnh [16]. Mô hình được huấn luyện trước trên lượng văn bản lớn rồi tinh chỉnh để làm theo chỉ dẫn. Đề tài dùng Gemini '
         '(gemini-3.8-flash) qua API với mức suy luận thấp để cân bằng chất lượng và chi phí [7].')
    H('2.5.2. Prompt và đầu ra có cấu trúc',3)
    para('Prompt gồm chỉ dẫn nhiệm vụ, ngữ cảnh sự cố và tri thức truy xuất được. Đầu ra được ràng buộc theo lược đồ JSON (danh sách giả thuyết, '
         'mã bằng chứng, hành động đề xuất, bằng chứng còn thiếu, độ tin cậy) và được kiểm tra hợp lệ trước khi lưu, nhờ đó có thể chấm điểm tự động.')
    H('2.5.3. Hallucination và tính có căn cứ',3)
    para('Hallucination là hiện tượng mô hình đưa ra nhận định không được dữ liệu đầu vào hỗ trợ. Việc một báo cáo trích dẫn mã bằng chứng tồn '
         'tại chưa chứng minh nhận định được bằng chứng đó hỗ trợ; vì vậy tính có căn cứ (grounding) cần được người chấm đánh giá trên từng nhận định.')
    H('2.6. Sinh văn bản tăng cường truy xuất',2)
    H('2.6.1. Nguyên lý RAG và embedding',3)
    para('RAG bổ sung cho LLM các đoạn tri thức được truy xuất từ kho tài liệu theo độ tương đồng với truy vấn [8]. Văn bản được chuyển thành vector '
         'embedding; độ tương đồng giữa vector truy vấn q và vector tài liệu d thường đo bằng cosine:')
    equation('cos(q, d) = (q · d) / (‖q‖ · ‖d‖)')
    para('trong đó q · d là tích vô hướng và ‖·‖ là chuẩn Euclid; giá trị càng gần 1 thì hai văn bản càng tương đồng. Đề tài dùng mô hình '
         'gemini-embedding-001 với vector 768 chiều.')
    H('2.6.2. Qdrant và LangChain',3)
    para('Qdrant là cơ sở dữ liệu vector hỗ trợ tìm kiếm tương đồng kèm lọc theo metadata, cho phép giới hạn kết quả theo vai trò tài liệu và '
         'phiên bản cơ sở tri thức. LangChain cung cấp các thành phần nối truy xuất, prompt và mô hình thành một chuỗi xử lý; đề tài dùng '
         'langchain-core để chạy song song nhánh truy xuất và nhánh ngữ cảnh.')
    H('2.7. Tiền xử lý log với Drain',2)
    H('2.7.1. Bài toán phân tích log',3)
    para('Log ứng dụng chứa nhiều dòng có cùng khuôn mẫu nhưng khác tham số (mã định danh, thời gian, địa chỉ). Đưa nguyên văn vào LLM gây lãng phí '
         'token và nhiễu. Phân tích log (log parsing) tách phần hằng thành template và phần biến thành tham số.')
    H('2.7.2. Thuật toán Drain',3)
    para('Drain phân tích log trực tuyến bằng cây có độ sâu cố định: dòng log được định tuyến theo số token và các token đầu tới một nhóm lá, '
         'sau đó so khớp với các template trong nhóm theo độ tương đồng; nếu vượt ngưỡng thì gộp và thay token khác nhau bằng ký tự đại diện [17]. '
         'Đề tài dùng thư viện Drain3 để gom log thành template kèm số lần xuất hiện.')
    H('2.8. Phương pháp đánh giá',2)
    H('2.8.1. Độ chính xác Top-k và khoảng tin cậy Wilson',3)
    para('Top-1 accuracy là tỷ lệ ca có giả thuyết đứng đầu đúng; Top-3 accuracy là tỷ lệ ca có giả thuyết đúng trong ba giả thuyết đầu. Báo cáo '
         'lỗi hoặc thiếu được tính là sai. Với n ca và tỷ lệ đúng p̂, khoảng tin cậy Wilson mức 95% là [18]:')
    equation('(p̂ + z²/2n ± z·√(p̂(1−p̂)/n + z²/4n²)) / (1 + z²/n)')
    para('trong đó z = 1,96. Khoảng Wilson ổn định hơn khoảng Wald khi n nhỏ hoặc p̂ gần 0 hoặc 1, phù hợp tập kiểm thử 40 ca.')
    H('2.8.2. Chất lượng truy xuất',3)
    para('Với tập runbook liên quan R do người chấm gán và danh sách k kết quả truy xuất, Recall@k và hạng nghịch đảo được tính như sau:')
    equation('Recall@k = |R ∩ top-k| / |R|')
    equation('MRR = (1/N) · Σ 1/rankᵢ')
    para('trong đó rankᵢ là vị trí của tài liệu liên quan đầu tiên trong ca thứ i (bằng 0 nếu không có trong top-k) và N là số ca.')
    H('2.8.3. Mô hình giá trị kinh tế',3)
    para('Thời gian tiết kiệm và giá trị ròng trên mỗi sự cố được định nghĩa:')
    equation('T_saved = T_baseline − T_assistant')
    equation('NetValue = (T_saved / 3600) · C_hour − API_cost')
    para('trong đó T tính bằng giây, C_hour là chi phí giờ công giả định (VNĐ/giờ) và API_cost là chi phí API quy đổi. T_baseline và T_assistant '
         'chỉ được lấy từ phiên đo người thật; C_hour được công bố kèm phân tích độ nhạy.')

    H('2.9. Cơ chế tài nguyên và lỗi trong container',2)
    H('2.9.1. Giới hạn CPU',3)
    para('Linux kiểm soát tài nguyên của container qua cgroup. Với CPU, limit khai báo trong Kubernetes được chuyển thành hạn mức thời gian CPU trong mỗi chu kỳ '
         'lập lịch (mặc định 100 ms): container có limit 0,2 core chỉ được chạy tổng cộng 20 ms trong mỗi 100 ms. Khi dùng hết hạn mức, các tiến trình trong '
         'container bị tạm dừng tới chu kỳ sau, gọi là throttling. Hệ quả quan sát được không phải là lỗi mà là thời gian xử lý yêu cầu tăng lên, và mức sử dụng '
         'CPU đo được dừng ở gần đúng giá trị limit.')
    para('Điều này giải thích vì sao luật cảnh báo CPU trong đề tài so sánh mức sử dụng với limit của chính Pod thay vì với một ngưỡng tuyệt đối: một dịch vụ dùng '
         '0,19 core có thể đang bão hòa nếu limit là 0,2 core, nhưng hoàn toàn bình thường nếu limit là 1 core.')
    H('2.9.2. Giới hạn bộ nhớ và OOM',3)
    para('Với bộ nhớ, limit là trần cứng. Khi lượng bộ nhớ đang dùng chạm trần và hạt nhân không thu hồi được thêm, bộ phận OOM killer chọn và dừng một tiến trình '
         'trong cgroup đó; Kubernetes ghi nhận container kết thúc với lý do OOMKilled và khởi động lại nó. Vì bộ nhớ đệm tệp có thể được thu hồi, kubelet dùng '
         'chỉ số working set, bằng bộ nhớ đang dùng trừ phần đệm tệp không hoạt động, để đánh giá áp lực thật. Đề tài dùng đúng chỉ số này trong cổng soak.')
    para('Một lỗi tiêm thêm bộ nhớ có thể cho hai biểu hiện khác nhau: nếu tổng vẫn dưới limit, ta thấy bộ nhớ tăng rồi giảm; nếu vượt limit, container bị dừng '
         'và khởi động lại, tức là biểu hiện giống lỗi Pod. Trong đợt thu dữ liệu, ca S0041 tiêm thêm 60% limit vào shipping vốn đã dùng khoảng 406/500 MiB, '
         'nên shipping bị OOMKilled ngay sau một giây. Đây là ví dụ thực tế cho thấy ranh giới giữa hai nhóm lỗi không phải lúc nào cũng rõ.')
    H('2.10. Mô hình dữ liệu telemetry',2)
    H('2.10.1. Chuỗi thời gian và PromQL',3)
    para('Trong Prometheus, mỗi chuỗi thời gian được xác định bởi tên metric và tập nhãn, ví dụ tên container_cpu_usage_seconds_total với nhãn namespace, pod, '
         'container. Bộ đếm (counter) chỉ tăng và bị đặt lại về 0 khi tiến trình khởi động lại; hàm rate tính tốc độ tăng trung bình trong một cửa sổ và tự xử lý '
         'việc đặt lại này. Độ trễ được ghi dưới dạng histogram gồm tổng thời gian và số yêu cầu; độ trễ trung bình trong một phút bằng rate của tổng chia rate '
         'của số yêu cầu. Prometheus trong đề tài thu mẫu 15 giây một lần.')
    para('Một chi tiết kỹ thuật quan trọng là chuỗi của container cũ có thể còn hiển thị một thời gian ngắn sau khi container khởi động lại. Nếu cộng gộp theo Pod '
         'mà không lọc, mức sử dụng có thể bị tính gấp đôi. Truy vấn của đề tài nối chuỗi cAdvisor với mã container hiện hành do kube-state-metrics báo cáo để '
         'chỉ giữ container đang chạy.')
    H('2.10.2. Trace và cạnh gọi có hướng',3)
    para('Một trace là cây các span. Mỗi span có mã trace, mã span, mã span cha, loại span (client hoặc server), dịch vụ, thời điểm bắt đầu và thời lượng. Khi '
         'dịch vụ A gọi dịch vụ B, A tạo span client và B tạo span server con của nó. Từ cặp này có thể suy ra cạnh có hướng A→B và độ trễ trên cạnh. Với lỗi mạng, '
         'thông tin hướng là bắt buộc: độ trễ giữa orders và payment do mạng chậm sẽ làm orders chậm theo, nên nếu chỉ nhìn metric thì dễ quy lỗi cho orders.')
    H('2.10.3. Mô phỏng lỗi mạng bằng netem',3)
    para('netem là bộ lập lịch hàng đợi (qdisc) của Linux cho phép thêm độ trễ, độ dao động (jitter), mất gói hoặc trùng gói vào lưu lượng đi ra của một giao '
         'diện mạng. Chaos Mesh cài qdisc này vào không gian mạng của Pod mục tiêu và giới hạn theo đích, nên lỗi chỉ ảnh hưởng tới một cạnh gọi cụ thể. Mất gói '
         '10–30% ở tầng mạng không đồng nghĩa với 10–30% yêu cầu HTTP thất bại, vì TCP truyền lại gói; biểu hiện chủ yếu là độ trễ tăng và phân tán.')
    H('2.11. Sinh văn bản, truy xuất vector và phân tích log',2)
    H('2.11.1. Sinh văn bản có cấu trúc và chi phí token',3)
    para('LLM sinh văn bản tuần tự từng token, mỗi bước chọn token tiếp theo dựa trên phân phối xác suất có điều kiện theo toàn bộ ngữ cảnh trước đó. Để kết '
         'quả chấm được bằng máy, đầu ra được ràng buộc theo một lược đồ JSON và được kiểm tra hợp lệ sau khi nhận. Chi phí API tính theo số token đầu vào và '
         'đầu ra; với các mô hình có bước suy luận nội bộ, token suy luận cũng được tính như token đầu ra. Vì vậy, đưa thêm metric và trace vào prompt có thể cải '
         'thiện chẩn đoán nhưng chắc chắn làm tăng chi phí, và cần được đo thay vì giả định.')
    H('2.11.2. Tìm kiếm láng giềng gần đúng',3)
    para('Tìm vector gần nhất chính xác trong tập lớn tốn thời gian tuyến tính. Qdrant dùng chỉ mục HNSW, một đồ thị nhiều tầng trong đó tầng trên thưa giúp di '
         'chuyển nhanh tới vùng gần truy vấn và tầng dưới dày giúp tinh chỉnh kết quả, cho độ phức tạp tìm kiếm xấp xỉ logarit [19]. Với năm runbook và vài chục ca '
         'đã giải quyết, lợi ích tốc độ không đáng kể; lý do chọn Qdrant là khả năng lọc theo metadata (vai trò tài liệu, phiên bản cơ sở tri thức) ngay trong truy vấn.')
    H('2.11.3. Ví dụ phân tích log bằng Drain',3)
    para('Giả sử có ba dòng log: “Connection refused to 10.0.0.5:8080”, “Connection refused to 10.0.0.7:8080” và “Order 4512 created”. Drain tách token theo '
         'khoảng trắng và định tuyến theo độ dài: hai dòng đầu có bốn token nên vào cùng nhánh, dòng thứ ba có ba token nên vào nhánh khác. Trong nhánh đầu, hai '
         'dòng giống nhau ở ba trên bốn vị trí, vượt ngưỡng tương đồng, nên được gộp thành template “Connection refused to <*>” với số lần xuất hiện bằng 2 [17]. '
         'Nhờ vậy, hàng nghìn dòng log lặp lại trong cửa sổ quan sát được rút gọn thành vài chục template kèm số đếm trước khi đưa vào prompt.')
    H('2.12. Tính hợp lệ của thực nghiệm phần mềm',2)
    H('2.12.1. Các loại mối đe dọa',3)
    para('Theo cách phân loại phổ biến trong thực nghiệm kỹ thuật phần mềm, có bốn nhóm mối đe dọa [20]. Tính hợp lệ nội tại hỏi liệu khác biệt đo được có thực sự '
         'do yếu tố đang xét gây ra hay do yếu tố khác. Tính hợp lệ cấu trúc hỏi liệu chỉ số có đo đúng khái niệm cần đo. Tính hợp lệ bên ngoài hỏi kết quả có tổng '
         'quát hóa được ra ngoài môi trường thử nghiệm. Tính hợp lệ của kết luận thống kê hỏi cỡ mẫu và phép kiểm định có đủ để kết luận.')
    H('2.12.2. Rò rỉ dữ liệu và chia nhóm',3)
    para('Trong đánh giá có truy xuất, rò rỉ xảy ra khi thông tin của ca kiểm thử xuất hiện trong cơ sở tri thức hoặc trong quá trình tinh chỉnh. Chia ngẫu nhiên '
         'từng ca là không đủ, vì hai ca cùng loại lỗi, cùng mục tiêu và chỉ khác cường độ gần như là một. Đề tài chia theo họ kịch bản: mọi cấu hình cùng loại '
         'lỗi, biến thể và mục tiêu nằm trong cùng một tập, và chỉ tập reference được phép vào cơ sở tri thức.')
    H('2.13. Lan truyền lỗi và cơ chế tự phục hồi',2)
    H('2.13.1. Lan truyền lỗi giữa các dịch vụ',3)
    para('Trong một chuỗi gọi đồng bộ, dịch vụ phía trước phải chờ dịch vụ phía sau trả lời. Khi dịch vụ phía sau chậm, thời gian chờ cộng dồn lên phía trước, và '
         'nếu dịch vụ phía trước dùng một số lượng luồng xử lý có hạn thì các luồng này bị chiếm, làm các yêu cầu không liên quan cũng chậm theo. Vì vậy cảnh báo '
         'thường xuất hiện ở dịch vụ giao tiếp với người dùng (front-end) trước, trong khi nguyên nhân nằm sâu hơn trong chuỗi.')
    para('Lan truyền theo chiều ngược lại cũng xảy ra: một dịch vụ phía trước bị quá tải có thể gửi ít yêu cầu hơn xuống phía sau, làm các chỉ số phía sau trông '
         'như đang tốt lên. Chẩn đoán dựa trên một chỉ số đơn lẻ dễ nhầm trong cả hai trường hợp; cần đối chiếu đồng thời tài nguyên, độ trễ trên từng cạnh và '
         'nội dung log theo thời gian.')
    H('2.13.2. Cơ chế tự phục hồi của Kubernetes',3)
    para('Kubernetes tự động thay Pod bị dừng để duy trì số bản sao khai báo trong Deployment. Readiness probe loại Pod khỏi danh sách nhận lưu lượng khi Pod chưa '
         'sẵn sàng; liveness probe khởi động lại container khi Pod không phản hồi quá số lần cho phép. Với container khởi động lại liên tục, thời gian chờ giữa các '
         'lần tăng dần theo cấp số.')
    para('Các cơ chế này rút ngắn thời gian gián đoạn nhưng cũng xóa dấu vết: một Pod bị dừng có thể được thay trong vài giây, và nếu cửa sổ quan sát bắt đầu sau '
         'đó thì chỉ còn thấy một Pod mới vừa khởi động. Đề tài ghi lại thời điểm tạo Pod và bộ đếm khởi động lại như các metric riêng để mô hình còn thấy được sự '
         'kiện đã xảy ra.')
    H('2.14. Thiết kế chỉ dẫn cho mô hình chẩn đoán',2)
    H('2.14.1. Nguyên tắc chỉ dẫn',3)
    para('Chất lượng câu trả lời của LLM phụ thuộc nhiều vào chỉ dẫn. Với bài toán chẩn đoán, ba nguyên tắc quan trọng là: chỉ kết luận từ dữ liệu được cung cấp, '
         'trích dẫn bằng chứng cụ thể cho từng kết luận, và được phép từ chối kết luận khi bằng chứng không đủ. Nguyên tắc thứ ba thường bị bỏ qua, nhưng một câu '
         'trả lời “chưa đủ bằng chứng” có giá trị hơn một giả thuyết sai được trình bày tự tin.')
    para('Một vấn đề riêng của dữ liệu vận hành là phân biệt lỗi mới với lỗi nền đã tồn tại từ trước. Chỉ dẫn cần nhắc mô hình xét diễn biến theo thời gian, ví dụ '
         'so giá trị đầu cửa sổ với giá trị lớn nhất, thay vì chỉ đếm số lần lỗi xuất hiện.')
    H('2.14.2. Vai trò của tri thức truy xuất',3)
    para('Runbook cung cấp tri thức chung: dấu hiệu điển hình của từng loại lỗi và các bước kiểm tra. Ca đã giải quyết cung cấp tri thức cụ thể: triệu chứng thực tế '
         'trong hệ thống này đã từng tương ứng với nguyên nhân nào. Hai loại tri thức bổ sung cho nhau, nhưng cả hai đều chỉ là gợi ý; chỉ dẫn của đề tài nói rõ '
         'runbook là hướng dẫn, không phải bằng chứng, để mô hình không suy luận ngược từ runbook ra kết luận khi dữ liệu không ủng hộ.')
    # ======================================================= CHƯƠNG 3
    H('CHƯƠNG 3. PHƯƠNG PHÁP NGHIÊN CỨU VÀ THIẾT KẾ HỆ THỐNG')
    H('3.1. Phương pháp nghiên cứu',2)
    H('3.1.1. Thực nghiệm có kiểm soát',3)
    para('Đề tài dùng phương pháp thực nghiệm: tiêm lỗi đã biết vào testbed, thu telemetry, cho các cấu hình chẩn đoán cùng một đầu vào và so sánh '
         'với nhãn đúng. Ba nguyên tắc được giữ xuyên suốt: nhãn đúng không bao giờ xuất hiện trong ngữ cảnh của mô hình; mọi nguồn ảnh hưởng tới '
         'kết quả được ghim bằng hash trước khi thu; không báo cáo số liệu chưa đo.')
    H('3.1.2. Quy trình thực hiện',3)
    lbl=T();para(f'Các bước thực hiện và điều kiện để chuyển bước được tóm tắt trong {lbl}.')
    table(lbl,'Quy trình thực hiện đề tài',['Bước','Nội dung','Điều kiện qua bước'],[
        ['1','Ghim môi trường và testbed','Node Ready, checkout thành công, image được kiểm kê'],
        ['2','Xác minh telemetry','Metric, log, trace liên dịch vụ truy vấn được'],
        ['3','Hiệu chỉnh trên các biến thể lỗi','Tác động đúng mục tiêu, cleanup và recovery'],
        ['4','Chuẩn hóa ngữ cảnh, RAG, LLM, giao diện','Báo cáo đúng lược đồ, có mã bằng chứng và sổ chi phí'],
        ['5','Ổn định testbed, lập kế hoạch dữ liệu','Soak 600 giây đạt, kế hoạch 200 cấu hình được audit'],
        ['6','Thu dữ liệu theo release đã ghim','Ca được reviewer độc lập duyệt'],
        ['7','Benchmark B0–B3 trên tập test','Cấu hình đóng băng, cùng ca và cùng cửa sổ'],
        ['8','Chấm grounding, đo người dùng, phân tích','Có số đo thật, công bố giới hạn']],[1.4,6.4,7.2])
    H('3.2. Kiến trúc hệ thống',2)
    H('3.2.1. Kiến trúc logic',3)
    para('Luồng dữ liệu đi từ Sock Shop trên Kubernetes tới Prometheus, Loki (qua Alloy) và Jaeger; luật cảnh báo của Prometheus gửi tới Alertmanager, '
         'từ đó tới incident collector (FastAPI). Collector lấy cửa sổ telemetry quanh cảnh báo; Context Builder dùng Drain3 và bộ chọn metric/trace '
         'để tạo ngữ cảnh có mã bằng chứng; bộ truy xuất lấy runbook và các ca đã giải quyết từ Qdrant; LangChain gọi Gemini để sinh báo cáo; '
         'báo cáo được hiển thị trên Streamlit. Nhãn đúng, trạng thái chaos và bộ đếm qdisc được lưu riêng, không bao giờ vào ngữ cảnh hoặc cơ sở tri thức.')
    fl=F('architecture')
    if fl:
        para(f'Các thành phần và luồng dữ liệu nói trên được minh họa trong {fl}.');figure(fl,'architecture','Kiến trúc logic của hệ thống chẩn đoán sự cố')
    H('3.2.2. Công nghệ sử dụng',3)
    lbl=T();para(f'Các thành phần và phiên bản đã triển khai được liệt kê trong {lbl}. Nhà cung cấp LLM được chuyển từ OpenAI (dự kiến trong đề '
                 'cương) sang Gemini ngày 20/11/2026; các thành phần còn lại và protocol đánh giá giữ nguyên.')
    table(lbl,'Công nghệ và phiên bản đã triển khai',['Thành phần','Lựa chọn','Ghi chú'],[
        ['Hạ tầng','Minikube, Kubernetes v1.37.0, 4 CPU, 7 GiB','MacBook Air M2 16 GB'],
        ['Ứng dụng','Sock Shop, 14 deployment','3 dịch vụ Go build ARM64; còn lại giả lập AMD64'],
        ['Chaos','Chaos Mesh 2.8.8','StressChaos, NetworkChaos, PodChaos'],
        ['Telemetry','Prometheus 29.47.2, Loki 7.7.0, Alloy 1.16.0, Jaeger','Chart được ghim phiên bản'],
        ['Collector','FastAPI 0.3.1','Một job thu đồng thời, RAM tối đa 512 MiB'],
        ['Tiền xử lý','Drain3 0.9.11, context schema 0.4.1','Mã bằng chứng cho từng dòng ngữ cảnh'],
        ['Truy xuất','Qdrant, gemini-embedding-001 (768 chiều)','5 runbook + bộ nhớ ca reference'],
        ['LLM','gemini-3.8-flash, prompt 0.2.0','Mức suy luận thấp'],
        ['Giao diện','Streamlit 1.67.0, Grafana','8 tab; dashboard sinh từ PromQL của collector']],[3.2,6.3,5.5])
    H('3.3. Testbed',2)
    H('3.3.1. Hạ tầng và ứng dụng',3)
    para('Testbed chạy trên một MacBook Air M2 RAM 16 GB, Docker VM 8 GiB, Minikube 7 GiB và 4 CPU. Phần lớn image Sock Shop chỉ có bản AMD64 nên '
         'chạy qua lớp giả lập; ba dịch vụ Go (payment, catalogue, user) được build lại cho ARM64 từ mã nguồn đã ghim. Bộ sinh lưu lượng thực hiện '
         'liên tục hành trình duyệt, thêm giỏ hàng và thanh toán.')
    H('3.3.2. Hiệu chỉnh độ ổn định',3)
    para('Trong quá trình chạy dài, testbed gặp OOM ở một số dịch vụ và cơ sở dữ liệu. Các biện pháp đã áp dụng gồm tăng RAM node dựa trên đo cgroup, '
         'giới hạn cache MongoDB 128 MiB, chính sách bộ nhớ cho MySQL, nâng cấp collector và tăng tài nguyên catalogue. Trước mỗi lô thu dữ liệu, '
         'một phép soak 600 giây kiểm tra sức khỏe Pod, OOM tại cgroup node, áp lực bộ nhớ, lưu lượng không lỗi và tính liên tục theo giờ UTC; '
         'bất kỳ vi phạm nào đều dừng đợt thu.')
    H('3.4. Phát hiện sự cố và thu thập telemetry',2)
    H('3.4.1. Luật cảnh báo',3)
    para('Các luật cảnh báo gồm SockShopCPUHigh và SockShopMemoryHigh (sử dụng vượt 75% limit trong 15 giây), PodLifecycleChange (Pod được thay mới) '
         'và RequestSlow cho các route /orders, /cart của front-end (độ trễ trung bình trên 250 ms với ít nhất 5 yêu cầu mỗi phút). Cảnh báo chỉ '
         'mô tả triệu chứng, không gán sẵn nguyên nhân.')
    H('3.4.2. Incident collector',3)
    para('Collector nhận webhook, khử trùng lặp theo nhãn và thời điểm bắt đầu cảnh báo, rồi chờ hết khoảng sau cảnh báo để lấy đủ dữ liệu. Ba nguồn '
         'được truy vấn song song có giới hạn số dòng và số trace; nếu chạm giới hạn, ca được đánh dấu partial thay vì âm thầm cắt bớt. Mỗi nguồn được '
         'lưu cùng hash để phát hiện thay đổi về sau.')
    H('3.5. Xây dựng ngữ cảnh chẩn đoán',2)
    H('3.5.1. Log',3)
    para('Log được lọc theo container đang chạy để tránh lẫn dữ liệu của container cũ, che các giá trị nhạy cảm rồi gom bằng Drain3. Mỗi template '
         'kèm dịch vụ, số lần xuất hiện và một mã bằng chứng dạng E-Lxxx.')
    H('3.5.2. Metric và trace',3)
    para('Metric được tóm tắt theo Pod hoặc route với giá trị đầu cửa sổ, lớn nhất, nhỏ nhất; ưu tiên các chuỗi biến động mạnh và giữ kèm limit tài '
         'nguyên để mô hình đánh giá mức bão hòa. Trace được tóm tắt theo cạnh gọi client giữa các dịch vụ, tối đa tám cạnh, trước các span lặp. '
         'Ngữ cảnh có định danh là hash của nội dung, nên cùng đầu vào luôn cho cùng mã.')
    H('3.6. Truy xuất tri thức',2)
    H('3.6.1. Cơ sở tri thức runbook',3)
    para('Năm runbook phủ CPU, bộ nhớ, độ trễ mạng, mất gói và lỗi Pod, mỗi runbook có mã, phiên bản và nhóm lỗi trong phần metadata. Truy vấn truy '
         'xuất được dựng từ các tín hiệu nổi bật của ngữ cảnh; kết quả được lọc theo vai trò và phiên bản cơ sở tri thức.')
    H('3.6.2. Bộ nhớ ca đã giải quyết',3)
    para('Theo đề cương, ngoài runbook hệ thống còn truy xuất các ca sự cố đã xác nhận. Chỉ ca đã được duyệt và thuộc tập reference mới được đưa vào '
         'một collection riêng; ca validation và test bị chặn ngay trong mã. Mỗi tài liệu gồm triệu chứng từ cùng cửa sổ quan sát của mô hình và '
         'kết luận đã duyệt, không chứa tham số chaos. Việc đưa bộ nhớ ca vào cấu hình chính thức phải được ghi vào protocol trước khi mở tập test.')
    H('3.7. Sinh báo cáo chẩn đoán',2)
    H('3.7.1. Prompt và lược đồ báo cáo',3)
    para('Prompt phiên bản 0.2.0 yêu cầu mô hình chỉ dựa vào bằng chứng trong ngữ cảnh, xếp hạng giả thuyết theo dịch vụ và nhóm lỗi, trích mã bằng '
         'chứng cho từng giả thuyết và nêu bằng chứng còn thiếu. Lược đồ báo cáo được trình bày ở Phụ lục A.')
    H('3.7.2. Sổ ghi lời gọi API',3)
    para('Mỗi lời gọi được ghi phiên bản mô hình trả về, thời gian, số token, độ trễ và chi phí ước tính theo bảng giá công bố ngày 20/11/2026. Chi '
         'phí này là ước tính, chưa đối chiếu hóa đơn và chưa gồm embedding.')
    H('3.8. Bộ dữ liệu',2)
    H('3.8.1. Kế hoạch 200 cấu hình',3)
    l1=T();l2=T()
    para(f'Kế hoạch gồm 200 cấu hình thuộc {d["groups"]} họ kịch bản, phân bố theo nhóm lỗi như {l1} và theo tập dữ liệu như {l2}. Các cấu hình cùng '
         'loại lỗi, biến thể và mục tiêu luôn nằm cùng tập để tránh ca gần trùng xuất hiện ở cả cơ sở tri thức và tập test.')
    table(l1,'Phân bố cấu hình theo nhóm lỗi',['Nhóm lỗi','Kế hoạch','Đã duyệt'],[[k,v[0],v[1]] for k,v in d['by_fault'].items()],[8,3.5,3.5])
    table(l2,'Phân bố cấu hình theo tập dữ liệu',['Tập','Kế hoạch','Đã duyệt'],[[k,v[0],v[1]] for k,v in d['by_split'].items()],[8,3.5,3.5])
    H('3.8.2. Cửa sổ quan sát và chống rò rỉ nhãn',3)
    para('Cửa sổ dùng cho mọi cấu hình được chốt trước: 30 giây trước đến 30 giây sau thời điểm controller xác nhận đã tiêm lỗi, chỉ giữ span đã kết '
         'thúc. Dữ liệu thô toàn lượt phục vụ kiểm tra tác động và phục hồi; dữ liệu cho mô hình được lưu riêng và được tái dựng từ dữ liệu thô '
         'trước khi duyệt để phát hiện sai lệch. Vì cửa sổ neo theo thời điểm tiêm, độ trễ đo trên dữ liệu này là độ trễ phát lại, không phải TTD live.')
    H('3.8.3. Quy trình thu và duyệt',3)
    bullets(['Release v3 ghim hash 50 tệp nguồn, kế hoạch, cấu hình mô hình và prompt; controller từ chối chạy nếu nguồn thay đổi.',
             'Mỗi lô tối đa bốn ca, lỗi Pod đặt cuối lô; soak 600 giây trước mỗi lô; lỗi sức khỏe hoặc cleanup dừng đợt thu, không tự thử lại.',
             'Reviewer độc lập xác nhận tác động đúng mục tiêu, phục hồi, telemetry phù hợp và kiểm tra trùng lặp, ghi mã, thời điểm và lý do.',
             'Công cụ duyệt kiểm lại hash dữ liệu thô, cửa sổ quan sát, provenance và kế hoạch, ghi qua transaction có rollback.',
             'Ca bị từ chối chỉ được thu lại cùng cấu hình khi mọi lần thu đều bị từ chối có lý do; lần thu cũ được giữ trong thống kê.',
             'Từ release v4, thứ tự thu được xen kẽ phân tầng: mỗi lượt chọn tập dữ liệu thiếu nhiều nhất so với tỷ lệ 120/40/40, rồi nhóm lỗi '
             'thiếu nhất, rồi họ kịch bản ít được chọn nhất, để dừng ở bất kỳ điểm nào cũng giữ được tỷ lệ; cấu hình trong kế hoạch không đổi.',
             'Quy tắc dừng sớm được chốt trước khi có kết quả test: nếu không đủ 200 ca, báo cáo trên mọi ca đã duyệt tại thời điểm dừng với n '
             'riêng cho từng tập và nhóm lỗi, khoảng tin cậy Wilson 95%, không ngoại suy; benchmark chỉ báo cáo khi có ít nhất 10 ca test '
             'phủ cả ba nhóm lỗi.'])
    fl=F('schedule')
    if fl:
        para(f'{fl} cho thấy số cấu hình mỗi tập theo tiến độ thu khi dùng lịch xen kẽ phân tầng: ở bất kỳ điểm dừng nào, tỷ lệ giữa ba tập '
             'vẫn bám sát 3:1:1.');figure(fl,'schedule','Số cấu hình theo tập dữ liệu khi thu theo lịch xen kẽ phân tầng',14)
    H('3.8.4. Lược đồ nhãn',3)
    lbl=T();para(f'Mỗi ca được duyệt được xuất theo lược đồ của đề cương như trong {lbl}; vị trí bằng chứng và runbook liên quan lấy từ phiếu reviewer.')
    table(lbl,'Lược đồ nhãn của một ca',['Trường','Nội dung'],[
        ['incident_id, scenario_id, split','Định danh ca, cấu hình và tập dữ liệu'],['fault_type, target','Nhóm lỗi; dịch vụ hoặc cạnh gọi có hướng'],
        ['chaos_parameters','Cường độ, thời lượng, bộ chọn'],['start_time, end_time','Thời điểm xác nhận tiêm và hoàn tất cleanup'],
        ['metrics/log/trace_window','Đường dẫn dữ liệu trong cửa sổ quan sát'],['expected_root_cause','Dịch vụ/cạnh và nhóm lỗi chuẩn'],
        ['expected_evidence','Vị trí bằng chứng reviewer đã đối chiếu'],['runbook_id','Runbook liên quan do reviewer gán']],[5.5,9.5])
    H('3.9. Thiết kế thực nghiệm',2)
    H('3.9.1. Các cấu hình so sánh',3)
    lbl=T();para(f'Bốn cấu hình được so sánh trên cùng ca và cùng cửa sổ quan sát như trong {lbl}.')
    table(lbl,'Các cấu hình so sánh',['Mã','Cấu hình','So sánh chính'],[
        ['B0','Luật và ngưỡng trên cùng ngữ cảnh, không LLM','Baseline vận hành (RQ1)'],['B1','LLM, chỉ log, không truy xuất','Năng lực LLM thuần'],
        ['B2','LLM + RAG, chỉ log','B1 so với B2: đóng góp của RAG (RQ3)'],['B3','LLM + RAG, log + metric + trace','B2 so với B3: đóng góp đa nguồn (RQ2)']],[1.5,7,6.5])
    H('3.9.2. Chỉ số đánh giá',3)
    lbl=T();para(f'Các chỉ số và cách đo được tóm tắt trong {lbl}.')
    table(lbl,'Chỉ số đánh giá',['Chỉ số','Cách đo'],[
        ['Top-1/Top-3 accuracy','Khớp dịch vụ hoặc cạnh có hướng và nhóm lỗi; báo cáo lỗi tính là sai; khoảng tin cậy Wilson 95%'],
        ['Grounding','Tỷ lệ nhận định được hai người chấm (hoặc phân xử) gán supported'],
        ['Hallucination','Tỷ lệ báo cáo có ít nhất một nhận định unsupported hoặc contradicted'],
        ['Độ trễ phát lại / TTD live','Từ ngữ cảnh tới báo cáo / từ lúc collector nhận cảnh báo tới báo cáo'],
        ['Chi phí API','Token thực tế nhân bảng giá ngày chạy'],['Thời gian người dùng','Phiên đo ẩn đáp án, 14 nhiệm vụ, 7 cặp cùng họ']],[4.5,10.5])
    H('3.9.3. Đo thời gian người dùng',3)
    para('Phiên đo gồm 14 nhiệm vụ, chia thành 7 cặp ca khác nhau cùng họ kịch bản: một ca dùng dashboard (B0), một ca dùng trợ lý (B3). Người tham gia '
         'không được xem nhãn đúng của tập test trước khi hoàn tất phiên. Thời gian được đo bằng đồng hồ đơn điệu và đối chiếu với giờ UTC.')
    H('3.10. Giao diện và vận hành',2)
    H('3.10.1. Giao diện Streamlit',3)
    para('Giao diện gồm tám tab: tổng quan tiến độ, incident từ collector, phân tích telemetry và B0, báo cáo đã lưu, runbook, dataset và kiểm thử, '
         'review dữ liệu, đo thời gian. Mở giao diện không gọi API; nút chẩn đoán là thao tác gửi riêng.')
    H('3.10.2. Dashboard Grafana và chẩn đoán tự động',3)
    para('Dashboard Grafana được sinh từ chính các truy vấn PromQL của collector, kèm log Loki và liên kết Jaeger. Worker chẩn đoán tự động lấy '
         'incident mới từ collector, dựng ngữ cảnh, gọi B3 và ghi TTD; worker bắt buộc giới hạn số lượt gọi, lọc theo nhãn cảnh báo và tự tạm dừng '
         'khi đang thu dữ liệu để cảnh báo của kịch bản không bị chẩn đoán live.')

    H('3.11. Chi tiết các thành phần',2)
    H('3.11.1. Luật cảnh báo',3)
    lbl=T()
    para(f'Các luật cảnh báo đang triển khai được liệt kê trong {lbl}. Mọi luật đều yêu cầu điều kiện kéo dài ít nhất 15 giây để tránh báo động do dao động ngắn.')
    table(lbl,'Luật cảnh báo trong Prometheus',['Cảnh báo','Điều kiện','Ý nghĩa'],[
        ['SockShopCPUHigh','CPU dùng / limit CPU của Pod > 0,75','Áp lực CPU tại Pod'],
        ['SockShopMemoryHigh','Working set / limit bộ nhớ > 0,75','Áp lực bộ nhớ tại Pod'],
        ['SockShopCatalogueSlow','Độ trễ trung bình /catalogue > 250 ms','Triệu chứng chậm của trang danh mục'],
        ['SockShopRequestSlow','Độ trễ trung bình /cart, /orders > 250 ms và ≥ 5 yêu cầu/phút','Triệu chứng chậm ở luồng giỏ hàng, đặt hàng'],
        ['SockShopPodNotReady','Pod không ở trạng thái Ready','Gián đoạn dịch vụ'],
        ['SockShopPodLifecycleChange','Pod được tạo trong 60 giây gần nhất','Pod vừa bị thay thế']],[4.2,6.3,4.5])
    para('Các luật chỉ mô tả triệu chứng tại nơi quan sát được. Chẳng hạn RequestSlow chỉ cho biết route của front-end chậm, không cho biết cạnh mạng nào gây chậm; '
         'việc xác định cạnh là nhiệm vụ của bước chẩn đoán.')
    H('3.11.2. Giao diện lập trình của collector',3)
    lbl=T()
    para(f'Collector cung cấp các endpoint trong {lbl}. Dữ liệu thô của mỗi incident được lưu thành tệp riêng cùng manifest ghi cửa sổ thời gian, giới hạn truy vấn và lỗi nếu có.')
    table(lbl,'Endpoint của incident collector',['Phương thức và đường dẫn','Chức năng'],[
        ['POST /alerts','Nhận webhook từ Alertmanager, khử trùng lặp theo nhãn và thời điểm bắt đầu, tạo incident'],
        ['POST /incidents/manual','Tạo incident thủ công để kiểm tra pipeline'],
        ['GET /incidents','Liệt kê incident và trạng thái thu (queued, collecting, captured, partial)'],
        ['GET /incidents/{id}','Trạng thái và manifest của một incident'],
        ['GET /incidents/{id}/files/{source}','Tải dữ liệu thô metrics, logs, traces hoặc manifest'],
        ['GET /health','Kiểm tra sức khỏe dịch vụ']],[5.5,9.5])
    H('3.11.3. Lược đồ ngữ cảnh chẩn đoán',3)
    lbl=T()
    para(f'Ngữ cảnh gửi cho mô hình có cấu trúc như {lbl}. Mỗi dòng bằng chứng mang một mã riêng để báo cáo trích dẫn và để người chấm truy ngược.')
    table(lbl,'Các trường chính của ngữ cảnh (schema 0.4.1)',['Trường','Nội dung'],[
        ['incident_id','CTX- cộng 16 ký tự hash của nội dung'],['window_start, window_end','Cửa sổ quan sát'],
        ['metrics[]','metric, pod hoặc service/route, giá trị đầu cửa sổ, lớn nhất, nhỏ nhất, mã E-Mxxx'],
        ['logs[]','service, template Drain3, số lần xuất hiện, mã E-Lxxx'],
        ['traces[]','service, operation, span_kind, duration_ms, quan hệ cha – con, mã E-Txxx'],
        ['missing_sources','Nguồn bị thiếu, nếu có'],['selection_policy','Quy tắc chọn metric và trace đã áp dụng']],[4.5,10.5])
    H('3.11.4. Baseline luật B0',3)
    para('B0 chạy cục bộ trên cùng ngữ cảnh, không dùng LLM hay truy xuất. Với mỗi Pod có CPU hoặc bộ nhớ đạt ít nhất 75% limit, B0 đề xuất lỗi cạn kiệt tài nguyên với '
         'điểm bằng tỷ lệ sử dụng; Pod có mẫu không Ready hoặc bộ đếm khởi động lại tăng được đề xuất lỗi Pod với điểm 1; route có độ trễ trung bình trên 250 ms '
         'được ghi nhận nhưng không gán loại lỗi, vì độ trễ một mình không phân biệt được lỗi mạng với lỗi ứng dụng. Giả thuyết được sắp theo điểm và giữ tối đa ba. '
         'Thiết kế này mô phỏng cách một kỹ sư đọc dashboard theo ngưỡng, và cố ý không suy diễn cạnh mạng.')
    H('3.12. Kế hoạch kịch bản chi tiết',2)
    H('3.12.1. Các họ kịch bản',3)
    lbl=T()
    para(f'Toàn bộ 28 họ kịch bản trong kế hoạch được liệt kê trong {lbl}, kèm tập dữ liệu và số cấu hình của mỗi họ.')
    fams={}
    for r in json.loads((Path(root)/'experiments/scenario-plan.json').read_text())['scenarios']:
        fam=fams.setdefault(r['group_id'],{'fault':r['fault_class'],'variant':r['variant'],'target':r['target'],'split':r['split'],'n':0});fam['n']+=1
    vname={'memory':'Bộ nhớ','cpu':'CPU','network-loss':'Mất gói','network-delay':'Độ trễ mạng','pod-failure':'Dừng Pod'}
    table(lbl,'Các họ kịch bản trong kế hoạch 200 cấu hình',['Họ','Biến thể','Mục tiêu','Tập','Số cấu hình'],
          [[k,vname.get(v['variant'],v['variant']),' → '.join(v['target']) if isinstance(v['target'],list) else v['target'],v['split'],v['n']] for k,v in fams.items()],[1.8,3.2,4.6,3,2.4])
    H('3.12.2. Tham số theo biến thể',3)
    lbl=T()
    para(f'Mỗi biến thể có miền tham số như trong {lbl}. Ngoài cường độ, các cấu hình còn khác nhau ở thời lượng lỗi (30–120 giây) và kiểu lưu lượng '
         '(thấp, trung bình, cao, hoặc có khoảng nghỉ giữa các hành trình với lỗi Pod).')
    table(lbl,'Miền tham số của các biến thể lỗi',['Biến thể','Tham số','Miền giá trị'],[
        ['CPU','Số worker, tải mỗi worker','1–2 worker, 100%'],['Bộ nhớ','Lượng bộ nhớ thêm so với limit','60–80% limit'],
        ['Độ trễ mạng','Độ trễ, jitter','100–600 ms, jitter 20 ms'],['Mất gói','Tỷ lệ mất gói','10–30%'],['Dừng Pod','Kiểu, số bản sao','pod-kill, 1 bản sao']],[3.5,6,5.5])
    H('3.13. Kiểm soát chất lượng thu thập',2)
    H('3.13.1. Cổng soak trước mỗi lô',3)
    para('Trước mỗi lô, hệ thống chạy lưu lượng bình thường trong 600 giây và lấy mẫu 30 giây một lần. Lô chỉ được bắt đầu khi đồng thời thỏa mãn: mọi Pod Ready, '
         'không có khởi động lại hay thay Pod mới, số lần OOM tại cgroup của node không tăng, áp lực bộ nhớ (PSI) dưới ngưỡng, hành trình thanh toán không có yêu cầu '
         'lỗi, và thời gian thực theo UTC khớp với thời gian đo bằng đồng hồ đơn điệu. Điều kiện cuối phát hiện máy bị ngủ: trong đợt thu, nó đã nhiều lần chặn đúng các lần '
         'máy chuyển sang chế độ ngủ, tránh việc ghi nhận một cửa sổ quan sát bị đứt quãng.')
    H('3.13.2. Kiểm tra cấu trúc của từng ca',3)
    lbl=T()
    para(f'Sau mỗi ca, công cụ kiểm tra tự động các điều kiện trong {lbl}. Ca không đạt làm dừng đợt thu; ca đạt vẫn phải được người duyệt xác nhận tác động.')
    table(lbl,'Các kiểm tra cấu trúc tự động',['Kiểm tra','Điều kiện đạt'],[
        ['pipeline_completed','Ca đi hết các bước tới capture'],['controller_all_injected','Chaos Mesh báo AllInjected'],
        ['cleanup_recorded','Tài nguyên chaos đã xóa, không lỗi'],['raw_sources_present','Có đủ metric, log, trace'],
        ['exports_not_truncated','Không chạm giới hạn log hoặc trace'],['recovery_recorded','Hệ thống phục hồi, không có vấn đề tồn đọng'],
        ['traffic_exercised','Có hành trình thanh toán hoàn tất'],['non_target_lifecycle_unchanged','Pod ngoài mục tiêu không bị thay hoặc khởi động lại'],
        ['node_local_oom_unchanged','Không có OOM mới ở cấp node']],[5.5,9.5])
    H('3.13.3. Ghi kết quả duyệt và tự khôi phục',3)
    para('Khi áp dụng phiếu duyệt, công cụ tái dựng cửa sổ quan sát từ dữ liệu thô, so hash từng nguồn, kiểm tra provenance và kế hoạch, rồi cập nhật cùng lúc năm '
         'tệp (nhãn đúng, đánh giá tác động, registry, hồ sơ bàn giao, biên nhận) trong một giao dịch có sao lưu; lỗi giữa chừng được hoàn tác toàn bộ. Mỗi '
         'cấu hình chỉ có tối đa một lần thu được duyệt.')
    para('Trong đợt thu, các lỗi bộ nhớ cường độ cao đôi khi làm chính dịch vụ mục tiêu bị OOM. Ca đó vẫn hợp lệ, nhưng bước kiểm tra trước ca kế tiếp phát hiện '
         'Pod đã khởi động lại và dừng đợt thu. Một tiến trình giám sát chỉ tự tiếp tục khi lần khởi động lại duy nhất là OOM của đúng dịch vụ vừa bị tiêm lỗi bộ '
         'nhớ, trong khoảng thời gian tiêm, mọi Pod Ready và không còn tài nguyên chaos; mọi trường hợp khác chờ người kiểm tra.')
    H('3.14. Kiểm thử phần mềm',2)
    H('3.14.1. Chiến lược kiểm thử',3)
    para('Kiểm thử tập trung vào các thuộc tính mà một lỗi lập trình có thể làm sai kết quả nghiên cứu: nhãn đúng không lọt vào ngữ cảnh, cửa sổ quan sát không '
         'chứa dữ liệu sau mốc cắt, ca chưa duyệt không được chấm như chính thức, lần thu lỗi không bị âm thầm loại khỏi thống kê, và không ghi đè phiếu duyệt '
         'đã có. Kiểm thử dùng dữ liệu tổng hợp và không gọi API, nên chạy được trên máy bất kỳ.')
    H('3.14.2. Phạm vi kiểm thử',3)
    lbl=T()
    para(f'Các nhóm kiểm thử chính được tóm tắt trong {lbl}.')
    table(lbl,'Các nhóm kiểm thử tự động',['Nhóm','Nội dung kiểm tra'],[
        ['Ngữ cảnh và telemetry','Chọn container hiện hành, gom log, khử trùng lặp span, đánh dấu export không đầy đủ'],
        ['Cửa sổ quan sát','Không lấy mẫu hoặc span hoàn tất sau mốc cắt; không ghi đè export'],
        ['Kế hoạch và lịch thu','200 cấu hình duy nhất, tỷ lệ tập khi dừng sớm, lỗi Pod cuối lô'],
        ['Duyệt và admission','Phiếu thiếu trường bị từ chối, giao dịch hoàn tác khi lỗi, một ca duyệt mỗi cấu hình'],
        ['Chấm điểm','Khớp dịch vụ hoặc cạnh có hướng, báo cáo thiếu tính là sai, khoảng Wilson'],
        ['Bộ nhớ ca và TTD','Chỉ ca reference đã duyệt vào bộ nhớ; TTD tính từ lúc nhận cảnh báo'],
        ['Tự khôi phục','Chỉ tiếp tục với OOM của chính mục tiêu, mọi lý do khác chờ người']],[4.5,10.5])
    para(f'Tổng cộng bộ kiểm thử có {test_count(root)} ca và đều đạt tại thời điểm dựng tài liệu.')
    H('3.15. Triển khai và tái lập',2)
    H('3.15.1. Các bước dựng lại môi trường',3)
    lbl=T()
    para(f'Toàn bộ môi trường được dựng lại bằng các lệnh trong {lbl}. Mỗi lệnh ghi bằng chứng vào thư mục kết quả để có thể đối chiếu sau.')
    table(lbl,'Các lệnh chính để dựng lại môi trường',['Lệnh','Tác dụng'],[
        ['make cluster-start','Khởi động Minikube với Kubernetes và tài nguyên đã ghim'],
        ['make qdrant-start','Khởi động Qdrant cho cơ sở tri thức'],
        ['make sock-shop-forward, make monitoring-forward, make collector-forward','Mở các cổng tới Sock Shop, Prometheus, Loki, Jaeger và collector'],
        ['make smoke, make telemetry-check','Kiểm tra hành trình thanh toán và truy vấn được cả ba nguồn telemetry'],
        ['make stability','Soak 600 giây với cổng sức khỏe và cổng thời gian'],
        ['make ui','Khởi động giao diện Streamlit'],
        ['make test','Chạy bộ kiểm thử tự động'],
        ['make admission-preview, make admission-apply','Xem trước và áp dụng phiếu duyệt'],
        ['make thesis','Vẽ hình và sinh lại khóa luận từ dữ liệu']],[6.5,8.5])
    H('3.15.2. Ghim phiên bản và bằng chứng',3)
    para('Phiên bản chart, image và thư viện Python được ghim trong các tệp khóa. Trước mỗi đợt thu, một release ghi hash của 50 tệp nguồn ảnh hưởng tới kết quả, '
         'gồm kế hoạch, mã thu thập, mã dựng ngữ cảnh, prompt, runbook và cấu hình mô hình; bản sao các tệp này được lưu cạnh release. Mỗi ca lưu provenance gồm '
         'hash của các tệp trên tại thời điểm chạy. Nhờ đó, khi đọc một kết quả bất kỳ, có thể biết chính xác phiên bản mã và cấu hình đã sinh ra nó.')
    para('Khóa API được lưu ngoài kho mã, trong tệp môi trường bị loại khỏi Git. Mọi lần gọi Gemini được ghi vào sổ gọi API cùng phạm vi đã được duyệt; công cụ '
         'chạy benchmark từ chối trước khi gọi nếu số lượt vượt hạn mức, và không tự thử lại khi lỗi.')
    H('3.16. Thiết kế prompt và báo cáo',2)
    H('3.16.1. Nội dung chỉ dẫn',3)
    para('Chỉ dẫn phiên bản 0.2.0 yêu cầu mô hình: chỉ chẩn đoán từ dữ liệu quan sát; coi runbook là hướng dẫn chứ không phải bằng chứng; trả về tối đa ba giả thuyết '
         'khác nhau và chỉ trích dẫn mã bằng chứng có trong ngữ cảnh; xét diễn biến theo thời gian và phân biệt lỗi nền kéo dài với dấu hiệu của sự cố mới. Với giả '
         'thuyết lỗi mạng, mô hình chỉ được ghi cạnh dạng bên gọi → bên được gọi khi dữ liệu xác định được cả hai đầu và chiều gọi, ví dụ qua span client; một route '
         'chậm không đủ để kết luận về cạnh hay nguyên nhân mạng. Khi không xác định được, mô hình phải chọn Unknown hoặc báo thiếu bằng chứng và nêu bằng chứng còn '
         'thiếu. Hành động đề xuất chỉ để kỹ sư xác nhận; phần giải thích viết bằng tiếng Việt.')
    para('Prompt gồm ba khối: chỉ dẫn nhiệm vụ, ngữ cảnh sự cố dạng JSON và danh sách tri thức truy xuất được. Hash của chỉ dẫn và của lược đồ báo cáo được ghim '
         'trong release, nên mọi thay đổi chỉ dẫn sau khi thu dữ liệu đều bị phát hiện.')
    H('3.16.2. Kiểm tra báo cáo và sổ gọi API',3)
    para('Báo cáo trả về được kiểm tra theo lược đồ: đúng kiểu dữ liệu, tối đa ba giả thuyết, loại lỗi thuộc danh sách cho phép, mã bằng chứng tồn tại trong ngữ cảnh. '
         'Báo cáo không hợp lệ được giữ lại và tính là sai trong thống kê thay vì bị gọi lại. Mỗi lần gọi ghi một bản ghi gồm mã lần gọi, mô hình yêu cầu và mô hình '
         'thực sự trả lời, thời điểm, số token, độ trễ, chi phí ước tính và nguồn bảng giá.')
    H('3.17. Giao diện người dùng',2)
    H('3.17.1. Các chức năng',3)
    lbl=T()
    para(f'Giao diện Streamlit gồm tám tab với chức năng như trong {lbl}.')
    table(lbl,'Các tab của giao diện',['Tab','Chức năng'],[
        ['Tổng quan','Chỉ số tiến độ, funnel thu và duyệt dữ liệu, trạng thái đợt thu, cập nhật mỗi 15 giây'],
        ['Incident','Danh sách incident từ collector, dựng ngữ cảnh từ một incident live'],
        ['Phân tích','Xem telemetry đã chuẩn hóa, chạy B0 cục bộ, gửi chẩn đoán tới Gemini khi người dùng bấm'],
        ['Báo cáo','Xem các báo cáo đã lưu, giả thuyết, bằng chứng trích dẫn, chi phí và độ trễ'],
        ['Runbook','Đọc runbook và ghi phiếu đánh giá nội dung runbook'],
        ['Dataset & kiểm thử','Kết quả audit kế hoạch, danh sách ca, kết quả kiểm thử dữ liệu'],
        ['Review dữ liệu','Phiếu duyệt độc lập từng ca: kiểm tra cấu trúc, metric theo pha, dữ liệu thô, nhãn runbook'],
        ['Đo thời gian','Phiên đo thời gian chẩn đoán ẩn đáp án (đã hủy trong đợt nộp này)']],[3.5,11.5])
    H('3.17.2. Minh họa giao diện',3)
    f1=F('ui-overview');f2=F('ui-review')
    if f1 and f2:
        para(f'{f1} là tab Tổng quan và {f2} là tab Review dữ liệu, chụp ngày 23/11/2026 trong quá trình phát triển nên số liệu trên ảnh là của thời điểm đó.')
        figure(f1,'ui-overview','Tab Tổng quan của giao diện (ảnh chụp ngày 23/11/2026)',10.5)
        figure(f2,'ui-review','Tab Review dữ liệu của giao diện (ảnh chụp ngày 23/11/2026)',10.5)
    H('3.18. Tổ chức lưu trữ và kiểm soát truy cập',2)
    H('3.18.1. Tổ chức thư mục dữ liệu',3)
    lbl=T()
    para(f'Dữ liệu và kết quả được tổ chức như trong {lbl}; nhãn đúng và dữ liệu dành cho mô hình luôn nằm ở các thư mục tách biệt.')
    table(lbl,'Tổ chức lưu trữ chính',['Thư mục','Nội dung'],[
        ['data/candidates/<ca>/','Nhãn đúng, dữ liệu thô ba nguồn, cửa sổ quan sát cho mô hình, trạng thái chaos, provenance, phiếu duyệt gốc'],
        ['results/dataset-collection/','Nhật ký từng đợt thu, kế hoạch lô, nhật ký tự khôi phục'],
        ['results/collection-releases/','Release đã ghim hash và bản sao nguồn'],
        ['results/stability/','Kết quả soak, mẫu theo thời gian, lưu lượng'],
        ['results/diagnoses/<ngữ cảnh>/<cấu hình>/','Báo cáo chẩn đoán và ngữ cảnh đã gửi'],
        ['results/api-calls/','Sổ ghi từng lần gọi API'],
        ['results/review-handoff/','Phiếu duyệt độc lập, hàng đợi review, phiếu chấm nhận định'],
        ['results/evaluation/','Kết quả chấm điểm và kiểm tra']],[6,9])
    H('3.18.2. Kiểm soát truy cập và chi phí',3)
    para('Khóa API nằm trong tệp môi trường bị loại khỏi Git và không bao giờ được ghi vào log, URL hay manifest. Việc gửi dữ liệu lên dịch vụ đám mây chỉ diễn ra qua '
         'gói yêu cầu đã được duyệt: mỗi gói ghi ngữ cảnh, câu truy vấn embedding và runbook được phép, cùng hash của chúng; công cụ chạy so lại hash trước khi gọi và '
         'từ chối nếu có thay đổi. Dữ liệu nhãn đúng, trạng thái chaos và phiếu duyệt không bao giờ được gửi đi.')
    # ======================================================= CHƯƠNG 4
    H('CHƯƠNG 4. KẾT QUẢ VÀ THẢO LUẬN')
    H('4.1. Kết quả xây dựng hệ thống',2)
    H('4.1.1. Testbed và pipeline',3)
    para('Testbed, telemetry ba nguồn, Chaos Mesh, collector, ngữ cảnh, truy xuất, sinh báo cáo, giao diện, dashboard và worker chẩn đoán tự động '
         'đã được triển khai và chạy trên một máy cá nhân. 200/200 manifest lỗi đã qua kiểm tra dry-run phía server; năm biến thể lỗi đã được hiệu '
         'chỉnh và xác minh tác động.')
    H('4.1.2. Kiểm thử phần mềm',3)
    para(f'Bộ kiểm thử tự động gồm {test_count(root)} ca kiểm thử Python, bao phủ xử lý telemetry, tách nhãn khỏi ngữ cảnh, chấm điểm, duyệt dữ liệu '
         'có transaction, chống rò rỉ của bộ nhớ ca, tính TTD và sinh khóa luận. Kiểm thử dùng dữ liệu giả lập, không gọi API.')
    H('4.2. Tiến độ bộ dữ liệu',2)
    lbl=T();c=f['counts']
    para(f'Trạng thái của 200 cấu hình tại thời điểm dựng tài liệu ({facts["built_at"]}) được trình bày trong {lbl}. Registry ghi {d["attempts"]} lần thu, '
         f'trong đó {d["failed_attempts"]} lần không hoàn chỉnh được giữ lại kèm lý do.')
    table(lbl,'Trạng thái thu thập và duyệt dữ liệu',['Trạng thái','Số cấu hình'],[['Đã thu hoàn chỉnh',f['captured_scenarios']],
        ['Chờ reviewer',c['pending_review']+c['approved_record_incomplete']],['Đã duyệt, chờ áp dụng',c['approved_ready_to_apply']],
        ['Bị từ chối, cần thu lại',c['rejected_requires_new_attempt']],['Đã duyệt chính thức',f['admitted']],['Chưa thu',c['not_captured']]],[10,5])
    fl=F('dataset')
    if fl:
        para(f'{fl} so sánh số cấu hình đã thu và đã duyệt với kế hoạch của từng tập.');figure(fl,'dataset','Tiến độ thu và duyệt dữ liệu theo tập',13.5)
    if not d['complete']:wait(f'Bộ dữ liệu mới có {f["admitted"]}/200 ca được duyệt; kết quả chính thức tính khi đủ 200 ca, hoặc theo quy tắc dừng sớm (mục 3.8.3) khi có ít nhất 10 ca test được duyệt.',
             formal='Tại thời điểm nộp, đợt thu dữ liệu vẫn đang tiếp tục và chưa có ca nào hoàn tất bước duyệt độc lập; vì vậy các kết quả trên tập test ở mục 4.5 được trình bày ở mức sơ bộ.')
    H('4.3. Kết quả trên dữ liệu phát triển',2)
    lbl=T()
    para(f'Các ca phát triển dùng để hiệu chỉnh pipeline trước khi mở tập test được tóm tắt trong {lbl}. Mỗi dòng là một tập riêng với phiên bản ngữ '
         'cảnh hoặc prompt khác nhau, không được cộng gộp và không dùng để kết luận độ chính xác tổng thể.')
    rows=[[e['file'].replace('.json',''),e['cases']]+[f'{e["top1"][m][0]}/{e["top1"][m][1]}' if m in e['top1'] else '—' for m in MODES] for e in dev['evaluations']]
    table(lbl,'Số ca đúng Top-1 trên các tập phát triển',['Tập phát triển','Số ca','B0','B1','B2','B3'],rows,[5.8,1.6,1.9,1.9,1.9,1.9])
    para(f'Tổng cộng {dev["reports"]} báo cáo Gemini đã lưu, trung vị độ trễ API {num(dev["latency_median"])} giây, trung vị {num(dev["tokens_median"],0)} '
         f'token mỗi báo cáo, chi phí ước tính {num(dev["cost_total"],4)} USD.')
    H('4.3.1. Những gì các ca phát triển cho thấy',3)
    para('Ngay từ các ca CPU đầu tiên, B1 và B2 đã chọn queue-master, dịch vụ có lỗi nền liên tục, trong khi B3 chỉ ra đúng dịch vụ bị tiêm lỗi. Kết quả này lặp lại ở '
         'ca shipping và ở hai ca mạng chạy với ngữ cảnh 0.4.1, và là động lực để bổ sung vào chỉ dẫn yêu cầu phân biệt lỗi nền với sự cố mới. Các ca phát triển '
         'cũng cho thấy B0 nhận tốt lỗi Pod nhờ bộ đếm khởi động lại, nhưng không có cách nào xác định cạnh mạng.')
    H('4.3.2. Các điều chỉnh trước khi thu dữ liệu chính thức',3)
    para('Từ kết quả phát triển, pipeline được điều chỉnh trước khi chốt release: ngữ cảnh lên phiên bản 0.4.1, giữ limit tài nguyên theo Pod và tối đa tám cạnh client '
         'trước các span lặp; chỉ dẫn lên phiên bản 0.2.0 với quy tắc về cạnh có hướng và lỗi nền; luật RequestSlow được thêm cho các route /orders và /cart để phát '
         'hiện lỗi mạng mà trước đó không có cảnh báo nào bắt được. Sau khi chốt release, các thành phần này không thay đổi nữa, nên kết quả trên tập test không bị '
         'ảnh hưởng bởi việc tinh chỉnh theo chính tập đó.')
    H('4.4. Thời gian chẩn đoán trên đường live',2)
    rows=live_rows(root)
    if rows:
        lbl=T()
        para(f'Worker chẩn đoán tự động được chạy với giới hạn năm lượt gọi trên các lỗi CPU demo nằm ngoài bộ dữ liệu. Kết quả từng incident được trình '
             f'bày trong {lbl}; trung vị TTD là {num(lv["median"],1)} giây, trong đó khoảng 30 giây là thời gian collector chờ đủ cửa sổ sau cảnh báo.')
        table(lbl,'TTD từ cảnh báo tới báo cáo trên đường live',['Incident','Top-1 B3','TTD (s)','Chờ cửa sổ (s)','LLM + truy xuất (s)','Chi phí (USD)'],
              [[r['incident_id'][-8:],r['top1'],num(r.get('ttd_seconds'),1),num(r['components_seconds'].get('alert_to_capture'),1),
                num(r['components_seconds'].get('llm_and_retrieval'),1),num(r.get('cost'),4)] for r in rows],[2.2,4.4,1.6,2.2,2.6,2])
        fl=F('ttd')
        if fl:
            para(f'Thành phần thời gian của từng incident được thể hiện trong {fl}.');figure(fl,'ttd','Phân rã TTD từ cảnh báo tới báo cáo trên đường live',13.5)
        para('Khoảng 70% TTD là thời gian collector chủ động chờ đủ 30 giây dữ liệu sau cảnh báo, nhằm có đủ bằng chứng về diễn biến sau thời điểm phát hiện. '
             'Rút ngắn khoảng chờ sẽ giảm TTD nhưng có thể làm thiếu bằng chứng; đây là đánh đổi cần đánh giá riêng. Phần do LLM và truy xuất chỉ chiếm 6–9 giây.')
        para('Đây là số đo minh họa đường live trên một loại lỗi, không phải độ chính xác chung, và được báo cáo tách khỏi độ trễ phát lại của benchmark.')
    else:
        wait('Chạy scripts/auto_diagnose.py để đo TTD từ cảnh báo tới báo cáo.',formal='TTD trên đường live chưa được đo trong bản nộp này.')
    H('4.5. Kết quả benchmark trên tập test',2)
    if off['available']:
        l1=T();l2=T()
        para(f'Độ chính xác của bốn cấu hình trên {off["cases"]} ca test được trình bày trong {l1}; kết quả theo nhóm lỗi trong {l2}.')
        table(l1,f'Độ chính xác trên {off["cases"]} ca test',['Cấu hình','n','Báo cáo lỗi','Top-1','95% CI','Top-3','95% CI'],
              [[m,s['denominator'],s['missing_or_invalid_reports'],pct(s['top1_correct']['rate']),ci(s['top1_correct']['wilson_95_ci']),
                pct(s['top3_correct']['rate']),ci(s['top3_correct']['wilson_95_ci'])] for m in MODES for s in [off['summary'].get((m,'all'))] if s],
              [1.7,1,1.8,1.7,3.2,1.7,3.2])
        table(l2,'Top-1 theo nhóm lỗi',['Nhóm lỗi','B0','B1','B2','B3'],
              [[fc]+[pct(off['summary'][(m,fc)]['top1_correct']['rate']) if (m,fc) in off['summary'] else '—' for m in MODES] for fc in off['fault_classes']],[6,2.25,2.25,2.25,2.25])
        l3=T();para(f'Độ trễ phát lại và chi phí theo cấu hình được trình bày trong {l3}.')
        table(l3,'Độ trễ phát lại và chi phí trên tập test',['Cấu hình','Trung vị độ trễ (s)','Chi phí TB/ca (USD)'],
              [[m,num(off['per_mode'][m]['latency_median']),num(off['per_mode'][m]['cost_mean'],5)] for m in MODES],[3,6,6])
    elif facts.get('preliminary'):
        pre=facts['preliminary'];ps={(x['mode'],x['fault_class']):x for x in pre['summaries']}
        para(f'Benchmark chính thức (chỉ trên ca đã được duyệt độc lập) chưa có. Để có kết quả trước hạn nộp, bốn cấu hình được chạy sơ bộ trên '
             f'{pre["case_count"]} ca test đã thu theo protocol nhưng chưa qua review độc lập. Kết quả dưới đây là sơ bộ: một số ca có thể bị loại '
             'sau khi duyệt, nên không thay thế benchmark chính thức và không được gộp với nó.')
        lbl=T()
        if pre['reportable']:
            para(f'Độ chính xác sơ bộ của bốn cấu hình được trình bày trong {lbl}.')
            table(lbl,f'Độ chính xác sơ bộ trên {pre["case_count"]} ca test chưa qua review độc lập',['Cấu hình','n','Báo cáo lỗi','Top-1','95% CI','Top-3','95% CI'],
                  [[m,x['denominator'],x['missing_or_invalid_reports'],pct(x['top1_correct']['rate']),ci(x['top1_correct']['wilson_95_ci']),
                    pct(x['top3_correct']['rate']),ci(x['top3_correct']['wilson_95_ci'])] for m in MODES for x in [ps.get((m,'all'))] if x],[1.7,1,1.8,1.7,3.2,1.7,3.2])
            l2=T();faults=sorted({k[1] for k in ps if k[1]!='all'})
            para(f'Kết quả sơ bộ theo nhóm lỗi được trình bày trong {l2}.')
            table(l2,'Số ca đúng Top-1 sơ bộ theo nhóm lỗi',['Nhóm lỗi','n','B0','B1','B2','B3'],
                  [[fc,ps[('B0',fc)]['denominator']]+[f'{ps[(m,fc)]["top1_correct"]["count"]}/{ps[(m,fc)]["denominator"]}' for m in MODES] for fc in faults],[5.5,1.5,2,2,2,2])
        else:
            para(f'Mới có {pre["case_count"]} ca, chưa đạt ngưỡng tối thiểu 10 ca phủ đủ ba nhóm lỗi; số ca đúng được liệt kê trong {lbl} chỉ để minh họa, '
                 'không tính tỷ lệ hay khoảng tin cậy và không dùng để kết luận.')
            table(lbl,f'Số ca đúng sơ bộ trên {pre["case_count"]} ca test chưa qua review (minh họa)',['Cấu hình','Top-1 đúng','Top-3 đúng','Báo cáo lỗi'],
                  [[m,f'{x["top1_correct"]["count"]}/{x["denominator"]}',f'{x["top3_correct"]["count"]}/{x["denominator"]}',x['missing_or_invalid_reports']]
                   for m in MODES for x in [ps.get((m,'all'))] if x],[3,4,4,4])
        fl=F('benchmark') if pre['reportable'] else None
        if fl:
            para(f'{fl} biểu diễn tỷ lệ đúng Top-1 và Top-3 sơ bộ kèm khoảng tin cậy Wilson 95%.');figure(fl,'benchmark','Tỷ lệ đúng sơ bộ của bốn cấu hình trên tập test',13.5)
        wait('Benchmark chính thức trên các ca test đã được duyệt độc lập (quy tắc dừng sớm, tối thiểu 10 ca) sẽ thay cho kết quả sơ bộ này.',
             formal='Khi các ca test hoàn tất duyệt độc lập, benchmark chính thức theo quy tắc dừng sớm (tối thiểu 10 ca phủ đủ ba nhóm lỗi) sẽ thay thế kết quả sơ bộ này; nếu có ca bị loại khi duyệt, kết quả có thể thay đổi.')
    else:
        wait('Bảng độ chính xác B0–B3 (Top-1, Top-3, khoảng tin cậy Wilson 95%, theo nhóm lỗi), độ trễ phát lại và chi phí trên 40 ca test. Cần đủ 200 ca, '
             'đóng băng protocol, phạm vi API được duyệt, rồi chạy experiments/evaluate.py và lưu tại '+OFFICIAL+'.',
             formal='Benchmark trên tập test chưa được thực hiện trong bản nộp này.')
    ca=case_analysis(root)
    if ca:
        from experiments.evaluate import target_key
        label_role='sơ bộ (chưa qua review độc lập)' if ca['role']!='official_test' else 'chính thức'
        def tgt(t):return ' → '.join(t) if isinstance(t,list) else str(t)
        def short(f):return {'Resource Exhaustion':'Tài nguyên','Network Delay / Packet Loss':'Mạng','Pod Failure':'Pod','Unknown':'Không rõ'}.get(f,f)
        H('4.6. Phân tích từng ca test',2)
        H('4.6.1. Giả thuyết đứng đầu của từng cấu hình',3)
        lbl=T()
        para(f'Giả thuyết xếp hạng đầu của mỗi cấu hình trên từng ca test ({label_role}) được trình bày trong {lbl}. Dấu ✓ đánh dấu giả thuyết khớp cả dịch vụ '
             '(hoặc cạnh có hướng) lẫn nhóm lỗi.')
        rows=[]
        for r in ca['rows']:
            cells=[r['scenario_id'],short(r['fault']),tgt(r['target'])]
            for m in MODES:
                h=r[m]
                if not h:cells.append('—');continue
                ok=target_key(h[0])==target_key(r['target']) and h[1]==r['fault']
                cells.append(f'{h[0]} / {short(h[1])}'+(' ✓' if ok else ''))
            rows.append(cells)
        table(lbl,'Giả thuyết đứng đầu theo ca và cấu hình',['Ca','Lỗi','Mục tiêu','B0','B1','B2','B3'],rows,[1.4,1.6,2.4,2.4,2.4,2.4,2.4])
        n=len(ca['rows'])
        svc={m:sum(1 for r in ca['rows'] if r[m] and target_key(r[m][0])==target_key(r['target'])) for m in MODES}
        bg={m:sum(1 for r in ca['rows'] if r[m] and r[m][0]=='queue-master') for m in MODES}
        H('4.6.2. Phân tích lỗi',3)
        para(f'Nếu chỉ xét dịch vụ hoặc cạnh có hướng mà bỏ qua nhóm lỗi, số ca B3 chỉ đúng vị trí là {svc["B3"]}/{n}, so với {svc["B0"]}/{n} của B0, '
             f'{svc["B1"]}/{n} của B1 và {svc["B2"]}/{n} của B2. Chỉ số này không phải chỉ số chính của khóa luận nhưng giúp tách hai kiểu sai: sai vị trí và đúng vị trí '
             'nhưng sai loại lỗi.')
        para(f'Kiểu sai phổ biến nhất của B1 và B2 là chọn queue-master, lần lượt ở {bg["B1"]}/{n} và {bg["B2"]}/{n} ca. Dịch vụ này ghi lỗi kết nối tới Docker socket '
             'lặp lại liên tục từ trước khi tiêm lỗi; khi chỉ có log, mô hình coi chuỗi lỗi dày đặc này là tín hiệu mạnh nhất. B3 có thêm metric tài nguyên và trace, '
             'và trong các ca này đã chọn dịch vụ có biến động thật thay vì queue-master; nhiều khả năng là nhờ thấy được thay đổi về tài nguyên hoặc độ trễ trong cửa sổ. Đây là bằng chứng định tính cho giả '
             'thuyết của RQ2 rằng dữ liệu đa nguồn giúp lọc nhiễu nền.')
        para('Với lỗi mạng, B3 nhận đúng nhóm lỗi ở cả ba ca nhưng chỉ chỉ ra đúng cạnh ở một ca; hai ca còn lại B3 chọn một cạnh khác cũng xuất phát từ front-end. '
             'Nguyên nhân khả dĩ là độ trễ trên cạnh orders → payment làm chậm cả chuỗi gọi phía trên, và trong cửa sổ 60 giây các span của nhiều cạnh cùng tăng. '
             'Với lỗi Pod, B3 thường chỉ đúng dịch vụ nhưng gọi đó là cạn kiệt tài nguyên, có lẽ vì Pod mới khởi động có mức CPU tăng vọt. Ngược lại, B0 dựa vào bộ '
             'đếm khởi động lại và trạng thái Ready nên nhận đúng lỗi Pod ở hai trong ba ca, nhưng không đúng ca tài nguyên nào: ở hai ca không có luật nào kích hoạt '
             'trong cửa sổ 60 giây, và ở một ca B0 chọn nhầm shipping, dịch vụ vốn chạy sát limit bộ nhớ. Ca S0064 minh họa ranh giới mờ đã nêu ở mục 2.9.2: lỗi bộ nhớ làm orders bị OOM và khởi động lại, nên cả B0 và B3 đều gọi đây là lỗi Pod.')
        H('4.7. Chi phí và tài nguyên của các cấu hình',2)
        H('4.7.1. Token, độ trễ và chi phí theo cấu hình',3)
        lbl=T();import statistics as st
        u=ca['usage']
        para(f'Số token đầu vào, độ trễ API và chi phí ước tính của ba cấu hình dùng LLM trên cùng các ca được so sánh trong {lbl}.')
        table(lbl,'Token, độ trễ và chi phí theo cấu hình',['Cấu hình','Token đầu vào (trung vị)','Độ trễ API (s, trung vị)','Chi phí TB/ca (USD)'],
              [[m,num(st.median(u[m]['tokens']),0) if u[m]['tokens'] else '—',num(st.median(u[m]['latency'])) if u[m]['latency'] else '—',
                num(st.mean(u[m]['cost']),5) if u[m]['cost'] else '—'] for m in ('B1','B2','B3')],[2.5,4.5,4.5,3.5])
        if u['B3']['tokens'] and u['B1']['tokens']:
            ratio=st.median(u['B3']['tokens'])/max(st.median(u['B1']['tokens']),1)
            para(f'B3 dùng số token đầu vào gấp khoảng {num(ratio,1)} lần B1 do có thêm metric và trace, kéo theo chi phí và độ trễ cao hơn. Ngay cả vậy, chi phí mỗi '
                 'lần chẩn đoán vẫn ở mức vài xu Mỹ, nhỏ so với giá trị một phút làm việc của kỹ sư; điểm cần cân nhắc khi triển khai thực tế là độ trễ và hạn mức gọi '
                 'API hơn là tiền.')
        H('4.7.2. Ước tính chi phí vận hành',3)
        if u['B3']['cost']:
            per=st.mean(u['B3']['cost'])
            para(f'Với chi phí trung bình {num(per,4)} USD cho mỗi lần chẩn đoán B3, chạy toàn bộ 40 ca test của kế hoạch tốn khoảng {num(per*40,2)} USD, và một hệ '
                 f'thống nhận 100 cảnh báo mỗi ngày tốn khoảng {num(per*100*30,1)} USD mỗi tháng cho phần sinh văn bản, chưa gồm embedding và hạ tầng. Đây là ước tính '
                 'theo bảng giá công bố, chưa đối chiếu hóa đơn. Trong vận hành thật, nên gom các cảnh báo cùng một sự cố trước khi gọi mô hình để tránh chẩn đoán lặp.')

    if gr['available']:
        lbl=T();para(f'Kết quả chấm nhận định bởi hai người được trình bày trong {lbl}.')
        table(lbl,'Kết quả chấm nhận định',['Cấu hình','Báo cáo','Nhận định','Grounding','Hallucination'],
              [[m,v['reports'],v['units'],pct(v['supported']/v['units']),pct(v['reports_with_unsupported']/v['reports'])] for m,v in sorted(gr['per_mode'].items())],[2.6,2.6,3,3.4,3.4])
    else:wait('Grounding và hallucination do hai người chấm độc lập. '+gr.get('reason',''),
             formal='Việc chấm tính có căn cứ và hallucination cần hai người chấm độc lập trên từng nhận định của báo cáo. Bộ phiếu chấm đã được chuẩn bị (137 đơn vị nhận định từ 25 báo cáo giai đoạn phát triển) nhưng chưa có nhãn của người chấm tại thời điểm nộp, nên khóa luận không báo cáo hai chỉ số này; việc chấm được nêu là hướng tiếp theo.')
    H('4.9. Thời gian người dùng và giá trị kinh tế',2)
    if hu['available']:
        lbl=T();para(f'Kết quả phiên đo được trình bày trong {lbl}. Chênh lệch trung bình theo họ (dashboard trừ trợ lý) là '
                     f'{num(hu["mean_family_difference_seconds"],1)} giây trên {hu["valid_pair_count"]} cặp hợp lệ; đây là so sánh mô tả với một người tham gia.')
        table(lbl,'Kết quả phiên đo thời gian',['Điều kiện','Hoàn thành','Hợp lệ','Trung vị (s)','Trung bình (s)'],
              [[k,v['completed'],v['valid_timing'],num(v['median_seconds'],1),num(v['mean_seconds'],1)] for k,v in hu['conditions'].items()],[4,2.6,2.4,3,3])
        cost=off['per_mode']['B3']['cost_mean'] if off['available'] else None;delta=hu['mean_family_difference_seconds']
        if cost is not None and delta is not None:
            lbl=T();para(f'Phân tích độ nhạy theo chi phí giờ công giả định được trình bày trong {lbl}.')
            table(lbl,'Phân tích độ nhạy giá trị giờ công',['C_hour (VNĐ)','Giá trị giờ công/ca (VNĐ)','Chi phí API B3/ca (USD)'],
                  [[num(h,0),num(delta/3600*h,0),num(cost,5)] for h in (100_000,200_000,400_000)],[4.5,5.5,5])
        else:wait('Phân tích độ nhạy cần chi phí API B3 trên tập test.',formal='Phân tích độ nhạy chưa thực hiện vì chưa có chi phí API trên tập test chính thức.')
    elif hu.get('cancelled'):
        para('Phiên đo thời gian người dùng đã được hủy trước khi bắt đầu (ngày 26/11/2026) để kịp hạn nộp: 14 ca test được chỉ định trước '
             'không thể thu đủ trong thời gian còn lại, và việc mở review ca test khiến reviewer không còn ở trạng thái mù với đáp án. Vì vậy '
             'khóa luận không báo cáo thời gian chẩn đoán của người dùng, thời gian tiết kiệm hay giá trị ròng; RQ4 chỉ được trả lời một phần '
             'qua TTD live (mục 4.4) và chi phí API (mục 4.7).')
    else:
        wait('Phiên đo 14 nhiệm vụ ẩn đáp án chưa hoàn tất; chưa tính giờ công tiết kiệm hoặc giá trị ròng ('+HUMAN+').',
             formal='Phiên đo thời gian người dùng chưa được thực hiện, nên khóa luận không báo cáo giờ công tiết kiệm hay giá trị ròng.')
    H('4.10. Thảo luận',2)
    H('4.10.1. Trả lời câu hỏi nghiên cứu',3)
    if off['available']:
        s=off['summary']
        for rq,(a,b) in (('RQ1',('B0','B3')),('RQ3',('B1','B2')),('RQ2',('B2','B3'))):
            if (a,'all') not in s or (b,'all') not in s:continue
            ia,ib=s[(a,'all')]['top1_correct']['wilson_95_ci'],s[(b,'all')]['top1_correct']['wilson_95_ci']
            overlap=not (ia[1]<ib[0] or ib[1]<ia[0])
            para(f'{rq}: Top-1 của {a} là {pct(s[(a,"all")]["top1_correct"]["rate"])}, của {b} là {pct(s[(b,"all")]["top1_correct"]["rate"])}; hai khoảng tin cậy '
                 +('chồng nhau nên chưa đủ bằng chứng cho khác biệt.' if overlap else 'không chồng nhau.'))
        para('RQ4: '+('xem mục 4.9.' if hu['available'] else 'chỉ trả lời một phần: có TTD live và chi phí API, không có số đo thời gian người dùng nên không kết luận về giờ công tiết kiệm.'))
    elif facts.get('preliminary') and facts['preliminary']['reportable']:
        ps={(x['mode'],x['fault_class']):x for x in facts['preliminary']['summaries']}
        para('Các nhận xét sau dựa trên kết quả sơ bộ ở mục 4.5 (ca chưa qua review độc lập) nên chỉ mang tính định hướng.')
        for rq,(a,b) in (('RQ1',('B0','B3')),('RQ3',('B1','B2')),('RQ2',('B2','B3'))):
            ia,ib=ps[(a,'all')]['top1_correct']['wilson_95_ci'],ps[(b,'all')]['top1_correct']['wilson_95_ci']
            overlap=not (ia[1]<ib[0] or ib[1]<ia[0])
            para(f'{rq}: Top-1 sơ bộ của {a} là {pct(ps[(a,"all")]["top1_correct"]["rate"])}, của {b} là {pct(ps[(b,"all")]["top1_correct"]["rate"])}; '
                 +('khoảng tin cậy chồng nhau nên chưa đủ bằng chứng cho khác biệt.' if overlap else 'khoảng tin cậy không chồng nhau.'))
        para('RQ4: chỉ trả lời một phần: có TTD live và chi phí API, không có số đo thời gian người dùng.')
    else:wait('Câu trả lời RQ1–RQ4 chỉ viết khi có benchmark chính thức; kết quả phát triển ở mục 4.3 không dùng để kết luận.',
        formal='Chưa có kết quả trên tập test nên các câu hỏi nghiên cứu chưa được trả lời định lượng; kết quả phát triển ở mục 4.3 không được dùng để kết luận.')
    H('4.10.2. Các mối đe dọa đến tính hợp lệ',3)
    bullets(['Tính tổng quát: lỗi được tiêm trên một ứng dụng mẫu, chưa phản ánh đầy đủ sự cố production.',
             'Môi trường: phần lớn image chạy giả lập AMD64 trên ARM64, ảnh hưởng tới số đo CPU và độ trễ.',
             'Độ ổn định: testbed có lịch sử OOM nền; soak 600 giây chỉ xác nhận ổn định ngắn hạn.',
             'Duyệt dữ liệu: một reviewer độc lập; công cụ không xác thực danh tính người điền phiếu.',
             'Thời gian: cửa sổ neo theo thời điểm tiêm nên benchmark đo độ trễ phát lại; TTD live đo riêng trên ít ca.',
             'Chi phí: ước tính theo bảng giá công bố, chưa đối chiếu hóa đơn và chưa gồm embedding, hạ tầng.',
             'Người dùng: phiên đo thời gian người dùng đã hủy; không có số đo T_baseline/T_assistant.' if hu.get('cancelled') else 'Người dùng: một người tham gia, các cặp khác ca cùng họ; kết quả mang tính mô tả.',
             'Cỡ mẫu: nếu áp dụng quy tắc dừng sớm, tập test nhỏ hơn 40 ca kế hoạch nên khoảng tin cậy rộng; không ngoại suy lên 200 ca.'])

    H('4.11. Bài học kinh nghiệm',2)
    H('4.11.1. Về xây dựng testbed trên máy cá nhân',3)
    para('Chạy mười bốn dịch vụ, ba hệ thống telemetry, Chaos Mesh và cơ sở dữ liệu vector trên một laptop 16 GB là khả thi nhưng sát giới hạn. Phần lớn image Sock '
         'Shop chỉ có bản AMD64 nên phải chạy qua giả lập trên chip ARM64, làm tăng tải CPU. Ba dịch vụ viết bằng Go được build lại cho ARM64 từ mã nguồn, một '
         'dịch vụ cần bản vá nhỏ để giữ nguyên định dạng JSON cũ. Trong các lần chạy dài, payment, catalogue, user và một số cơ sở dữ liệu từng bị OOM; mỗi lần '
         'xử lý đều đi kèm đo đạc ở cấp cgroup trước khi thay đổi cấu hình, thay vì tăng tài nguyên theo cảm tính.')
    para('Bản thân công cụ thu thập cũng là một nguồn lỗi. Collector từng bị OOM ở giới hạn 192 MiB trong lúc thu một ca, làm ca đó không được tính. Phiên bản '
         'sửa lỗi xử lý tuần tự từng job, ghi JSON theo luồng và được kiểm chứng bằng ba lần thu thủ công cùng một phép soak trước khi dùng tiếp.')
    H('4.11.2. Về quy trình thực nghiệm',3)
    para('Thứ tự thu dữ liệu ảnh hưởng trực tiếp tới khả năng báo cáo. Lịch thu ban đầu đi tuần tự theo kế hoạch, nên sau 20 ca vẫn chưa có ca test nào. Lịch xen kẽ '
         'phân tầng được áp dụng trước khi thu bất kỳ ca validation hay test nào, nhờ vậy việc đổi lịch không làm thay đổi cấu hình hay tập dữ liệu, và 10 ca test '
         'đầu tiên có đủ ba nhóm lỗi.')
    para('Các cơ chế kiểm tra tự động đôi khi dừng đợt thu vì những lý do không liên quan tới chất lượng dữ liệu, như máy chuyển sang chế độ ngủ hay dịch vụ mục tiêu '
         'bị OOM bởi chính lỗi được tiêm. Thay vì nới lỏng kiểm tra, đề tài phân loại rõ từng lý do dừng và chỉ tự động tiếp tục với trường hợp đã chứng minh là vô '
         'hại. Cách làm này tốn thời gian hơn nhưng giữ được tính toàn vẹn của dữ liệu.')
    para('Cuối cùng, bước duyệt độc lập là nút thắt về thời gian. Thu một ca mất khoảng ba phút, nhưng duyệt kỹ một ca cần đối chiếu dữ liệu thô của cả ba nguồn. Với '
         'một người duyệt, tốc độ duyệt quyết định tốc độ có kết quả chính thức. Đây là lý do khóa luận tách rõ kết quả sơ bộ trên ca chưa duyệt và kết quả chính '
         'thức trên ca đã duyệt.')
    # ======================================================= KẾT LUẬN
    H('KẾT LUẬN')
    rich([('Kết quả đạt được. ',True),('Khóa luận đã xây dựng một pipeline chẩn đoán sự cố end-to-end trên Kubernetes gồm testbed Sock Shop, telemetry '
          'ba nguồn, Chaos Mesh, collector, ngữ cảnh có mã bằng chứng, truy xuất runbook và ca đã giải quyết, sinh báo cáo bằng Gemini, giao diện '
          'Streamlit, dashboard Grafana và worker chẩn đoán tự động; cùng protocol thu dữ liệu được ghim bằng hash, duyệt độc lập và ghi bằng transaction.',False)])
    if not (off['available'] and hu['available'] and d['complete']):
        wait('Kết luận định lượng về RQ1–RQ4 sẽ được viết khi đủ 200 ca, có benchmark test, chấm grounding và phiên đo người thật.',
             formal='Các kết luận định lượng ở trên dựa trên kết quả sơ bộ; kết luận chính thức cần benchmark trên các ca đã duyệt, việc chấm tính có căn cứ và phiên đo thời gian người dùng.')
    rich([('Hạn chế. ',True),('Phạm vi gồm ba nhóm lỗi trên một ứng dụng mẫu, chạy giả lập một phần trên một máy cá nhân, với một người duyệt dữ liệu. '
          'Tại thời điểm nộp, kết quả benchmark mới ở mức sơ bộ trên các ca test chưa qua duyệt độc lập, cỡ mẫu nhỏ nên khoảng tin cậy rộng và các so sánh giữa '
          'cấu hình chưa đủ để kết luận có ý nghĩa thống kê. Phiên đo thời gian người dùng đã được hủy, nên chưa có số liệu về thời gian kỹ sư tiết kiệm. Cửa sổ quan '
          'sát neo theo thời điểm tiêm lỗi là quy ước của benchmark ngoại tuyến; TTD trên đường live chỉ được đo trên ba ca minh họa.',False)])
    rich([('Đóng góp. ',True),('Ngoài sản phẩm, khóa luận đóng góp một quy trình thực nghiệm có thể kiểm tra lại: kế hoạch dữ liệu được ghim trước, lịch thu '
          'giữ tỷ lệ ở mọi điểm dừng, quy tắc dừng sớm được chốt trước khi có kết quả, và mọi bước từ dữ liệu thô tới con số trong báo cáo đều có thể chạy lại. '
          'Kết quả sơ bộ cho thấy hướng đi đáng tiếp tục: cấu hình đầy đủ B3 đứng đầu trên mọi chỉ số đã đo và tránh được nhiễu nền mà các cấu hình chỉ dùng '
          'log mắc phải.',False)])
    rich([('Việc tiếp theo. ',True),('Ba việc cần hoàn tất để có kết luận chính thức: duyệt độc lập các ca đã thu và chạy benchmark chính thức theo quy tắc dừng '
          'sớm hoặc trên đủ 40 ca test; chấm tính có căn cứ và hallucination bởi hai người trên các báo cáo của tập test; và thực hiện phiên đo thời gian người dùng '
          'với một người tham gia chưa xem đáp án để trả lời trọn vẹn RQ4. Đợt thu dữ liệu vẫn đang chạy và mọi công cụ cho ba việc này đã sẵn sàng.',False)])
    rich([('Hướng phát triển. ',True),('Kiểm tra ổn định dài hạn và build native cho toàn bộ dịch vụ; mở rộng nhóm lỗi (cấu hình sai, lỗi cơ sở dữ liệu); '
          'bổ sung reviewer thứ hai; giảm thời gian chờ cửa sổ trong TTD live; đánh giá hiệu chỉnh độ tin cậy do mô hình tự khai.',False)])

    # ======================================================= TÀI LIỆU THAM KHẢO (IEEE)
    H('TÀI LIỆU THAM KHẢO')
    refs=['S. Ghosh et al., “Mining root cause knowledge from cloud service incident investigations for AIOps,” in Proc. ICSE-SEIP, 2022, doi: 10.1145/3510457.3513030.',
          'S. Zhang et al., “Robust failure diagnosis of microservice system through multimodal data,” IEEE Trans. Services Comput., vol. 16, no. 6, 2023, doi: 10.1109/TSC.2023.3290018.',
          'T. Ahmed, S. Ghosh, C. Bansal, T. Zimmermann, X. Zhang, and S. Rajmohan, “Recommending root-cause and mitigation steps for cloud incidents using large language models,” in Proc. ICSE, 2023, doi: 10.1109/ICSE48619.2023.00149.',
          'L. Pham, H. Zhang, H. Ha, F. Salim, and X. Zhang, “RCAEval: A benchmark for root cause analysis of microservice systems with telemetry data,” arXiv:2412.17015, 2024.',
          '“MicroOps: Rapid microservice data simulation and AIOps model development platform,” in Proc. IEEE SANER, 2024, doi: 10.1109/SANER60148.2024.00012.',
          'B. Guan, H. Xu, and J. Rogers, “Leveraging resolved incident history for LLM-assisted software bug diagnosis,” arXiv:2607.21911, 2026.',
          'Google, “Gemini API – Models and pricing.” [Trực tuyến]. Có sẵn: https://aistudio.google.com/docs/models [Truy cập ngày: 20/11/2026].',
          'P. Lewis et al., “Retrieval-augmented generation for knowledge-intensive NLP tasks,” in Proc. NeurIPS, 2020, arXiv:2005.11401.',
          'A. Basiri et al., “Chaos engineering,” IEEE Software, vol. 33, no. 3, pp. 35–41, 2016, doi: 10.1109/MS.2016.60.',
          'B. Beyer, C. Jones, J. Petoff, and N. R. Murphy, Site Reliability Engineering: How Google Runs Production Systems. Sebastopol, CA, USA: O’Reilly, 2016.',
          'Weaveworks, “Sock Shop: A microservices demo application.” [Trực tuyến]. Có sẵn: https://github.com/microservices-demo/microservices-demo [Truy cập ngày: 20/11/2026].',
          'The Kubernetes Authors, “Kubernetes documentation.” [Trực tuyến]. Có sẵn: https://kubernetes.io/docs/ [Truy cập ngày: 20/11/2026].',
          'Prometheus Authors, “Prometheus documentation.” [Trực tuyến]. Có sẵn: https://prometheus.io/docs/ [Truy cập ngày: 20/11/2026].',
          'B. H. Sigelman et al., “Dapper, a large-scale distributed systems tracing infrastructure,” Google, Tech. Rep. dapper-2010-1, 2010.',
          'Chaos Mesh Authors, “Chaos Mesh documentation.” [Trực tuyến]. Có sẵn: https://chaos-mesh.org/docs/ [Truy cập ngày: 20/11/2026].',
          'A. Vaswani et al., “Attention is all you need,” in Proc. NeurIPS, 2017, arXiv:1706.03762.',
          'P. He, J. Zhu, Z. Zheng, and M. R. Lyu, “Drain: An online log parsing approach with fixed depth tree,” in Proc. IEEE ICWS, 2017, doi: 10.1109/ICWS.2017.13.',
          'E. B. Wilson, “Probable inference, the law of succession, and statistical inference,” J. Amer. Statist. Assoc., vol. 22, no. 158, pp. 209–212, 1927, doi: 10.1080/01621459.1927.10502953.',
          'Y. A. Malkov and D. A. Yashunin, “Efficient and robust approximate nearest neighbor search using hierarchical navigable small world graphs,” IEEE Trans. Pattern Anal. Mach. Intell., vol. 42, no. 4, pp. 824–836, 2020, doi: 10.1109/TPAMI.2018.2889473.',
          'C. Wohlin, P. Runeson, M. Höst, M. C. Ohlsson, B. Regnell, and A. Wesslén, Experimentation in Software Engineering. Berlin, Germany: Springer, 2012.']
    for i,ref in enumerate(refs,1):
        p=para(f'[{i}]\t{ref}',align=L);pf=p.paragraph_format;pf.left_indent=Cm(1);pf.first_line_indent=Cm(-1);pf.tab_stops.add_tab_stop(Cm(1))

    # ======================================================= PHỤ LỤC
    H('PHỤ LỤC')
    H('Phụ lục A. Lược đồ báo cáo chẩn đoán',2)
    state['chapter']='A';state['table']=0;lbl=T()
    para(f'Các trường của báo cáo chẩn đoán do mô hình sinh ra được mô tả trong {lbl}.')
    table(lbl,'Lược đồ báo cáo chẩn đoán',['Trường','Nội dung'],[['incident_id','CTX-… (hash nội dung ngữ cảnh)'],
        ['status','hypotheses_available hoặc trạng thái thiếu dữ liệu'],['hypotheses[]','service, fault_type, root_cause, evidence_ids, rationale; xếp hạng'],
        ['recommended_actions','Hành động kiểm tra hoặc khắc phục'],['missing_evidence','Bằng chứng còn thiếu để kết luận'],
        ['confidence','0–1, chỉ mang tính tham khảo'],['ledger','model_version, usage_metadata, api_latency_seconds, chi phí ước tính']],[4.5,10.5])
    H('Phụ lục B. Mã nguồn và tái lập',2)
    para('Mã nguồn được nộp dưới dạng tệp ZIP gồm thư mục Source và Readme.md, hoặc liên kết kho mã được cấp quyền truy cập cho giảng viên và Khoa. '
         'Quy trình tái lập, hash môi trường và runbook vận hành nằm trong phụ lục phương pháp (docs/submission/phu_luc_phuong_phap_va_tai_lap.docx) '
         'và các runbook RB01–RB18. Tài liệu này được sinh tự động bằng scripts/build_thesis_docx.py từ dữ liệu thực nghiệm đã lưu.')

    settings=doc.settings.element;upd=OxmlElement('w:updateFields');upd.set(qn('w:val'),'true')
    place(settings,upd,('hdrShapeDefaults','footnotePr','endnotePr','compat','docVars','rsids','mathPr','attachedSchema','themeFontLang',
                        'clrSchemeMapping','doNotIncludeSubdocsInStats','doNotAutoCompressPictures','forceUpgrade','captions',
                        'readModeInkLockDown','smartTagType','schemaLibrary','shapeDefaults','doNotEmbedSmartTags','decimalSymbol','listSeparator'))
    zoom=settings.find(qn('w:zoom'))
    if zoom is not None and zoom.get(qn('w:percent')) is None:zoom.set(qn('w:percent'),'100')
    output.parent.mkdir(parents=True,exist_ok=True);doc.save(output)
    return pending


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output',type=Path,default=OUT);args=parser.parse_args()
    facts=collect(ROOT);placeholders=build(facts,args.output)
    meta=json.loads(META.read_text())
    status={'built_at':facts['built_at'],'output':str(args.output.relative_to(ROOT)) if args.output.is_relative_to(ROOT) else str(args.output),
            'pending':pending_items(facts)+([] if (ROOT/meta.get('logo','-')).is_file() else ['Chèn logo NEU vào bìa ('+meta.get('logo','')+').']),
            'placeholder_blocks':len(placeholders),'admitted':facts['dataset']['funnel']['admitted'],
            'official_benchmark':facts['official']['available'],'grounding':facts['grounding']['available'],
            'human_timing':facts['human']['available'],'live_ttd':facts['live']['available'],
            'spine_for_printing':f'{meta["academic_term"]} | {meta["major"]} | {meta["student"].upper()} | {meta["student_id"]}'}
    args.output.with_suffix('.status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(status,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
