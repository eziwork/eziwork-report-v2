"""EZIWORK profile; uses unchanged upstream export and inspection tools."""
from pathlib import Path
import csv, json, math, os, subprocess, sys
import integrations as integ

def chart(spec,output):
 out=Path(output)
 if out.exists():raise ValueError('OUTPUT_EXISTS_USE_NEW_VERSION')
 raw=Path(spec['dataset']);data=integ.load(raw)
 if integ.sha(raw)!=spec['dataset_sha256']:raise ValueError('CHART_DATASET_CHANGED')
 def pointer(path):
  value=data
  for key in path.strip('/').split('/'):
   key=key.replace('~1','/').replace('~0','~')
   value=value[int(key)] if isinstance(value,list) else value[key]
  return value
 points=[]
 for p in spec['points']:
  v=pointer(p['pointer'])
  if v is not None and (isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v)):raise ValueError('CHART_NUMERIC_REQUIRED')
  points.append({'label':p['label'],'value':v})
 if not points or not any(p['value'] is not None for p in points):raise ValueError('CHART_NO_OBSERVATIONS')
 if not spec.get('basis_date') or not spec.get('unit') or not spec.get('scope'):raise ValueError('CHART_SCOPE_REQUIRED')
 out.mkdir(parents=True)
 upstream=integ.ROOT/'vendor/scientific-visualization'
 sys.path.insert(0,str(upstream/'scripts'));sys.path.insert(0,str(upstream/'assets'))
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 from matplotlib import font_manager
 from figure_export import export_figure
 selected=integ.font()
 if not selected:raise ValueError('KOREAN_FONT_REQUIRED')
 font_manager.fontManager.addfont(str(selected));name=font_manager.FontProperties(fname=selected).get_name()
 scale=spec.get('display_divisor',1)
 if not isinstance(scale,(int,float)) or scale<=0:raise ValueError('CHART_SCALE')
 labels=[p['label'] for p in points];ys=[p['value']/scale if p['value'] is not None else float('nan') for p in points]
 style=integ.load(integ.ROOT/'assets/scientific-style.json');color=style['color']
 with plt.rc_context({**style['rc'],'font.family':name}):
  fig,ax=plt.subplots(figsize=(style['width_inches'],max(style['minimum_height_inches'],style['height_per_point_inches']*len(points)+style['height_extra_inches'])),layout='constrained')
  kind=spec.get('kind','bar')
  if kind=='line':
   ax.plot(range(len(points)),ys,'o-',color=color,linewidth=2);ax.set_xticks(range(len(points)),labels,rotation=35,ha='right');ax.set_ylabel(spec.get('display_unit',spec['unit']))
  elif kind in ('bar','dot'):
   if kind=='bar':ax.barh(range(len(points)),ys,color=color,height=.44)
   else:ax.scatter(ys,range(len(points)),color=color,marker='D',s=48)
   ax.set_yticks(range(len(points)),labels);ax.invert_yaxis();ax.set_xlabel(spec.get('display_unit',spec['unit']))
   if kind=='bar':ax.axvline(0,color='#16263f',linewidth=.8)
   ax.margins(x=.18)
  else:raise ValueError('CHART_KIND')
  for i,v in enumerate(ys):
   if math.isnan(v):
    if kind!='line':ax.text(0,i,'자료 없음',va='center',color='#666666')
    continue
   xy=(i,v) if kind=='line' else (v,i)
   ax.annotate(f'{v:,.2f}'.rstrip('0').rstrip('.'),xy,xytext=(5,6 if kind=='line' else 0),textcoords='offset points',va='bottom' if kind=='line' else 'center',fontsize=10)
  ax.grid(axis='y' if kind=='line' else 'x',color='#e7ebf1',linewidth=.6);ax.set_axisbelow(True)
  # A newly-created exclusive output directory contains no previous artifacts.
  # Explicit overwrite selects upstream atomic replace instead of Windows hard links.
  export_figure(fig,out/'figure',formats=['svg','png'],dpi=180,font_mode='paths',overwrite=True,provenance={'input_sha256':spec['dataset_sha256'],'scope':spec['scope'],'basis_date':spec['basis_date'],'points':points,'unit':spec['unit'],'missing':'gaps; never zero','display_divisor':scale},write_manifest=True)
  plt.close(fig)
 audits={}
 for tool,args in [('palette_audit',['--color',color.lstrip('#'),'--background',style['background'].lstrip('#'),'--role','graphical']),('image_metadata',[str(out/'figure.png'),'--format','png'])]:
  env={**os.environ,'PYTHONPATH':str(integ.runtime()/'python')+os.pathsep+os.environ.get('PYTHONPATH','')}
  run=subprocess.run([sys.executable,'-X','utf8',str(upstream/'scripts'/f'{tool}.py'),*args],capture_output=True,text=True,encoding='utf-8',env=env)
  if run.returncode:raise ValueError('UPSTREAM_AUDIT_FAILED_'+tool)
  audits[tool]=json.loads(run.stdout);integ.write(out/f'{tool}.json',audits[tool])
 with (out/'data.csv').open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.writer(f);writer.writerow(['label','value','unit']);writer.writerows([p['label'],'' if p['value'] is None else p['value'],spec['unit']] for p in points)
 result={'status':'PASS','skill':'scientific-visualization','commit':integ.lock()['skills']['scientific-visualization']['commit'],'execution':['figure_export.export_figure','palette_audit.py','image_metadata.py'],'input_sha256':spec['dataset_sha256'],'source_pointers':[p['pointer'] for p in spec['points']],'points':points,'unit':spec['unit'],'basis_date':spec['basis_date'],'scope':spec['scope'],'output_sha256':{ext:integ.sha(out/f'figure.{ext}') for ext in ['svg','png']},'semantic_review':'REQUIRES_CODEX','accessibility_certified':False}
 integ.write(out/'provenance.json',result);return result
