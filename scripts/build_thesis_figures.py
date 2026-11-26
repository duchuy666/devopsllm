#!/usr/bin/env python3
"""Draw thesis figures from persisted artifacts into docs/submission/figures/ (PNG, 200 dpi).

Every chart reads the same files as the thesis builder; a figure whose data is missing is skipped.
"""
import glob
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
OUT=ROOT/'docs/submission/figures'
plt.rcParams.update({'font.family':'Times New Roman','font.size':11,'axes.spines.top':False,'axes.spines.right':False})
INK='#1f2937';ACCENT='#1f4e9a';SOFT='#dbe6f6';GREY='#9ca3af'


def load(path):
    try:return json.loads(Path(path).read_text())
    except (OSError,ValueError):return None


def architecture(path):
    fig,ax=plt.subplots(figsize=(9.5,5.2));ax.set_xlim(0,100);ax.set_ylim(0,58);ax.axis('off')
    def box(x,y,w,h,text,fill=SOFT,bold=False):
        ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.4,rounding_size=1.2',fc=fill,ec=ACCENT,lw=1.2))
        ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=10,color=INK,weight='bold' if bold else 'normal',wrap=True)
    def arrow(a,b,label=None,dx=0,dy=0,ha='center'):
        ax.annotate('',xy=b,xytext=a,arrowprops=dict(arrowstyle='-|>',color=INK,lw=1.1))
        if label:ax.text((a[0]+b[0])/2+dx,(a[1]+b[1])/2+dy,label,fontsize=8.5,color='#4b5563',ha=ha,
                         bbox=dict(fc='white',ec='none',pad=0.6))
    box(2,40,20,12,'Sock Shop\ntrên Kubernetes\n(Minikube)',bold=True)
    box(2,20,20,12,'Chaos Mesh\nStress / Network / Pod',fill='#fde2e2')
    box(30,44,18,8,'Prometheus\n(metric)');box(30,32,18,8,'Loki + Alloy\n(log)');box(30,20,18,8,'Jaeger\n(trace)')
    box(30,6,18,8,'Alertmanager')
    box(56,30,18,14,'Incident collector\n(FastAPI)\ncửa sổ telemetry',bold=True)
    box(56,8,18,14,'Context Builder\nDrain3, chọn metric\nvà trace, mã bằng chứng',fill='#e6f4ea')
    box(80,40,18,12,'Qdrant\nrunbook + ca\nđã giải quyết')
    box(80,20,18,14,'LangChain\n+ Gemini\n(B1–B3)',bold=True);box(80,4,18,10,'Báo cáo chẩn đoán\nStreamlit / Grafana',fill='#fff3cd')
    arrow((12,32.5),(12,39.5),'tiêm lỗi',dx=1.2,ha='left')
    for y in (48,36,24):arrow((22.5,46),(29.5,y))
    arrow((39,19.5),(39,14.5),'luật cảnh báo',dx=1.2,ha='left');arrow((48.5,10),(55.5,33))
    for y in (48,36,24):arrow((48.5,y),(55.5,37))
    arrow((65,29.5),(65,22.5));arrow((74.5,15),(79.5,25));arrow((89,39.5),(89,34.5),'truy xuất',dx=1.2,ha='left')
    arrow((89,19.5),(89,14.5))
    ax.text(50,1,'Nhãn đúng, trạng thái chaos và qdisc được lưu riêng, không vào ngữ cảnh hoặc Qdrant.',ha='center',fontsize=9,style='italic',color='#6b7280')
    fig.tight_layout();fig.savefig(path,dpi=200);plt.close(fig)


def schedule(path):
    from scripts.run_dataset_collection import stratified_order
    rows=json.loads((ROOT/'experiments/scenario-plan.json').read_text())['scenarios']
    order=stratified_order(rows);xs=range(1,len(order)+1);counts={s:[] for s in ('reference','validation','test')};c={s:0 for s in counts}
    for r in order:
        c[r['split']]+=1
        for s in counts:counts[s].append(c[s])
    fig,ax=plt.subplots(figsize=(8,3.8))
    for s,color,label in (('reference',ACCENT,'Reference'),('validation','#d97706','Validation'),('test','#059669','Test')):
        ax.plot(xs,counts[s],color=color,lw=2,label=label)
    ax.axvline(50,color=GREY,ls='--',lw=1);ax.text(51,105,'dừng ở 50 ca:\n30 / 10 / 10',fontsize=9,color='#4b5563')
    ax.set_xlabel('Số cấu hình đã thu');ax.set_ylabel('Số cấu hình theo tập');ax.legend(frameon=False);ax.grid(alpha=.25)
    fig.tight_layout();fig.savefig(path,dpi=200);plt.close(fig)


def dataset(path):
    from app.admission_progress import progress
    f=progress(ROOT);split={s:[0,0] for s in ('reference','validation','test')}
    plan={s:0 for s in split}
    for r in f['scenarios']:
        plan[r['split']]+=1
        if r['state']!='not_captured':split[r['split']][0]+=1
        if r['state']=='admitted':split[r['split']][1]+=1
    fig,ax=plt.subplots(figsize=(7.5,3.4));names=list(split);xs=range(len(names))
    ax.bar(xs,[plan[n] for n in names],color='#e5e7eb',label='Kế hoạch',width=.6)
    ax.bar(xs,[split[n][0] for n in names],color=ACCENT,label='Đã thu',width=.6)
    ax.bar(xs,[split[n][1] for n in names],color='#059669',label='Đã duyệt',width=.6)
    for x,n in zip(xs,names):ax.text(x,split[n][0]+2,f'{split[n][0]}/{plan[n]}',ha='center',fontsize=10)
    ax.set_xticks(list(xs),['Reference','Validation','Test']);ax.set_ylabel('Số cấu hình');ax.legend(frameon=False)
    fig.tight_layout();fig.savefig(path,dpi=200);plt.close(fig)


def ttd(path):
    rows=[load(p) for p in sorted(glob.glob(str(ROOT/'results/live-diagnoses/*/ttd.json')))]
    rows=[r for r in rows if r and r.get('status')=='report_generated']
    if not rows:return False
    fig,ax=plt.subplots(figsize=(7.5,3.2));labels=[r['incident_id'][-8:] for r in rows]
    parts=[('alert_to_capture','Chờ cửa sổ sau cảnh báo',GREY),('capture_to_context','Dựng ngữ cảnh','#d97706'),('llm_and_retrieval','Truy xuất + Gemini',ACCENT)]
    left=[0]*len(rows)
    for key,label,color in parts:
        vals=[r['components_seconds'].get(key) or 0 for r in rows]
        ax.barh(labels,vals,left=left,color=color,label=label);left=[a+b for a,b in zip(left,vals)]
    for i,r in enumerate(rows):ax.text(left[i]+0.5,i,f'{r["ttd_seconds"]:.1f} s',va='center',fontsize=10)
    ax.set_xlabel('Giây từ lúc collector nhận cảnh báo');ax.legend(frameon=False,loc='lower right',fontsize=9);ax.set_xlim(0,max(left)*1.2)
    fig.tight_layout();fig.savefig(path,dpi=200);plt.close(fig);return True


def benchmark(path):
    data=load(ROOT/'results/evaluation/official-test-B0-B3.json') or load(ROOT/'results/evaluation/preliminary-test-B0-B3.json')
    if not data:return False
    s={(x['mode'],x['fault_class']):x for x in data['summaries']};modes=['B0','B1','B2','B3']
    fig,ax=plt.subplots(figsize=(7.5,3.6));xs=range(len(modes))
    for off,metric,color,label in ((-0.18,'top1_correct',ACCENT,'Top-1'),(0.18,'top3_correct','#93b4e0','Top-3')):
        rates=[s[(m,'all')][metric]['rate']*100 for m in modes]
        lo=[r-s[(m,'all')][metric]['wilson_95_ci'][0]*100 for r,m in zip(rates,modes)]
        hi=[s[(m,'all')][metric]['wilson_95_ci'][1]*100-r for r,m in zip(rates,modes)]
        ax.bar([x+off for x in xs],rates,width=.34,color=color,label=label,yerr=[lo,hi],capsize=3,ecolor='#4b5563')
    ax.set_xticks(list(xs),modes);ax.set_ylabel('Tỷ lệ đúng (%)');ax.set_ylim(0,100);ax.legend(frameon=False)
    ax.set_title(f'n = {data["case_count"]} ca test'+(' (sơ bộ, chưa qua review độc lập)' if data['dataset_role']!='official_test' else ''),fontsize=10)
    fig.tight_layout();fig.savefig(path,dpi=200);plt.close(fig);return True


def main():
    OUT.mkdir(parents=True,exist_ok=True);made=[]
    for name,fn in (('architecture',architecture),('schedule',schedule),('dataset',dataset),('ttd',ttd),('benchmark',benchmark)):
        path=OUT/(name+'.png')
        if fn(path) is not False:made.append(path.name)
        elif path.exists():path.unlink()
    print(json.dumps({'figures':made}))


if __name__=='__main__':main()
