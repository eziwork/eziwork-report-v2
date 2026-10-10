"""Export only usable evidence after the selected report's required groups pass."""
import argparse
import json
from pathlib import Path
from collector import load,write,registry,report_readiness,CollectionError,dashboard,lock
from evidence_rules import revalidate,RULE_VERSION

def review_coverage(run,path):
    """A source list is a provider map, not proof that every grouped topic is covered."""
    run=Path(run);payload=load(path);manifest=load(run/'manifest.json');sources,reports=registry()
    request=load(run/'request.json')
    if payload.get('run_id')!=manifest['run_id']: raise CollectionError('REVIEW_RUN_MISMATCH')
    known={g['requirement_id']:g for r in reports for g in r['data_requirements']}
    accepted={}
    for review in payload.get('reviews',[]):
        if review.get('review_status')!='VERIFIED': continue
        group=known.get(review.get('requirement_id'))
        if not group or not review.get('review_note'): raise CollectionError('INVALID_COVERAGE_REVIEW')
        ids=set();proofs={}
        for item in group['coverage_checklist']:
            proof=review.get('coverage',{}).get(item,{})
            id=proof.get('source_id');index=proof.get('record_index');fields=proof.get('fields',[])
            state=manifest['sources'].get(id,{})
            if id not in group['sources'] or not state.get('complete') or type(index)!=int or index<0 or not fields:
                raise CollectionError('COVERAGE_EVIDENCE_REQUIRED')
            records=load(run/state['normalized_file'])
            if index>=len(records) or not records[index].get('usable'): raise CollectionError('COVERAGE_RECORD_UNUSABLE')
            if not revalidate(sources.get(id),records[index],request,run):
                raise CollectionError('COVERAGE_RECORD_SCOPE_INVALID')
            values=records[index]['values']
            if any(f not in values or values[f] is None or values[f]=='' for f in fields): raise CollectionError('COVERAGE_FIELD_MISSING')
            from collector import digest,encoded
            proofs[item]={**proof,'record_sha256':digest(encoded(records[index]))};ids.add(id)
        accepted[group['requirement_id']]=dict(review_status='VERIFIED',review_note=review['review_note'],sources=sorted(ids),proofs=proofs,validation_rule_version=RULE_VERSION)
    with lock(run):
        # Reload after locking; attach reviews to exact normalized records, not a future refresh.
        manifest=load(run/'manifest.json')
        manifest.setdefault('requirement_reviews',{}).update(accepted)
        write(run/'coverage-review.json',payload)
        manifest['readiness']=report_readiness(load(run/'request.json'),manifest,reports)
        write(run/'manifest.json',manifest);dashboard(run,manifest,sources,reports)

def current_reviews(run,manifest):
    from collector import digest,encoded
    sources,_=registry();request=load(run/'request.json')
    for id,review in list(manifest.get('requirement_reviews',{}).items()):
        if review.get('validation_rule_version')!=RULE_VERSION:
            review['review_status']='STALE'
        for proof in review.get('proofs',{}).values():
            try:
                state=manifest['sources'][proof['source_id']]
                row=load(run/state['normalized_file'])[proof['record_index']]
                if not row.get('usable') or digest(encoded(row))!=proof['record_sha256']: raise ValueError()
                if not revalidate(sources.get(proof['source_id']),row,request,run):raise ValueError()
            except (KeyError,IndexError,ValueError,OSError):
                manifest['requirement_reviews'][id]['review_status']='STALE';break
    return manifest

def prepare(run, report_id):
    run=Path(run);manifest=load(run/'manifest.json');request=load(run/'request.json')
    sources,reports=registry();manifest=current_reviews(run,manifest)
    # Saved usable flags from older versions do not bypass current target/date rules.
    for id,state in manifest['sources'].items():
        if id not in sources:
            state.update(usable_count=0,status='UNKNOWN_SOURCE_MIGRATION_REQUIRED',complete=False)
            continue
        if state.get('usable_count') and state.get('normalized_file'):
            records=load(run/state['normalized_file'])
            state['usable_count']=sum(revalidate(sources[id],row,request,run) for row in records)
            if not state['usable_count']:state['status']='CURRENT_RULE_REVIEW_REQUIRED'
    manifest['readiness']=report_readiness(request,manifest,reports)
    write(run/'manifest.json',manifest)
    dashboard(run,manifest,sources,reports)
    readiness=next((r for r in manifest['readiness'] if r['report_id']==report_id),None)
    if readiness is None: raise CollectionError('UNKNOWN_REPORT')
    destination=run/f'{report_id}-evidence.json'
    if readiness['status']=='HOLD':
        write(destination,dict(status='HOLD',report_id=report_id,readiness=readiness,records=[]))
        raise CollectionError('REPORT_REQUIRED_DATA_MISSING')
    selected={id for g in readiness['groups'] if g['status']=='AVAILABLE' for id in g['sources']}
    records=[]
    for id in selected:
        path=manifest['sources'][id].get('normalized_file')
        if path: records.extend(r for r in load(run/path) if r.get('usable') and
            revalidate(sources.get(id),r,request,run))
    write(destination,dict(schema_version=1,status='READY_WITH_DECLARED_SCOPE',report_id=report_id,
        target=request['target'],readiness=readiness,records=records,validation_rule_version=RULE_VERSION,
        excluded_groups=[g['data'] for g in readiness['groups'] if g['status']=='EXCLUDED']))
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--report',required=True);parser.add_argument('--review',type=Path);args=parser.parse_args()
    try:
        import sys
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
        import key_environment
        gate=key_environment.require_registered()
        if gate:print(json.dumps(gate));raise SystemExit(2)
        if args.review: review_coverage(args.run,args.review)
        print(prepare(args.run,args.report).resolve())
    except CollectionError as exc: print(json.dumps({'status':exc.code}));raise SystemExit(2)
