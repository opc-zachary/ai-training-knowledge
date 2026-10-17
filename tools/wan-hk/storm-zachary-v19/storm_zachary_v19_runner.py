# -*- coding: utf-8 -*-
"""Approved adaptation of the Project's manual-only GitHub WAN HK route.

Exact human approval permits one 4-second source-video edit POST with a fixed 8 billable seconds estimate.
An immutable root dispatch claim and exact remote readback guard submission.
No image bytes, provider keys, event bodies or result URLs are logged.
"""
from __future__ import annotations
import argparse, base64, copy, datetime, hashlib, json, os, re, shutil
import subprocess, sys, time, urllib.error, urllib.request, uuid
from pathlib import Path
from decimal import Decimal

ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'StormMV_Zachary_2026-10-17_JSON_ExecutorManifest_Approved_v19.json'
PINNED_MANIFEST_SHA256='7562cde649ad0a494e0d78f81b84200429b82c88a3d7d623d3d59d03392f8b32'
STAGED_ONLY_BUILD=False
EXPECTED_HOST='ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com'
EXPECTED_PARAMS={'resolution': '720P', 'ratio': '16:9', 'duration': 4, 'audio': False, 'prompt_extend': False, 'watermark': False}

class Stop(Exception): pass
def digest(b):return hashlib.sha256(b).hexdigest()
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(temp,p)
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def safe_code(value):return value if isinstance(value,str) and re.fullmatch('[A-Za-z0-9_.-]{1,100}',value) else 'PROVIDER_ERROR'
def load():
    raw=MANIFEST.read_bytes()
    if digest(raw)!=PINNED_MANIFEST_SHA256:raise Stop('MANIFEST_HASH_MISMATCH')
    m=json.loads(raw)
    if (m.get('project'),m.get('client'),m.get('version'))!=('StormMV_Zachary','Zachary Chan','v19'):raise Stop('PROJECT_IDENTITY_MISMATCH')
    request_path=ROOT/m['request_file']
    if digest(request_path.read_bytes())!=m['request_sha256']:raise Stop('REQUEST_HASH_MISMATCH')
    q=json.loads(request_path.read_text(encoding='utf-8'))
    if q['model']!='wan3.0-video' or q['parameters']!=EXPECTED_PARAMS:raise Stop('MODEL_OR_PARAMETER_MISMATCH')
    media=q['input']['media']
    if media!=[{'type':'reference_video','url':m['videos'][0]['public_url']},{'type':'reference_image','url':'__PRIVATE_IMAGE_1_DATA_URI__'}]:raise Stop('MEDIA_MAP_MISMATCH')
    if len(m['images'])!=1 or [x['id'] for x in m['images']]!=['Zachary']:raise Stop('CHARACTER_ORDER_MISMATCH')
    a=m['approval'];price=Decimal('8')*Decimal('0.082513')*Decimal('8.0')
    if Decimal(a['estimated_hkd'])!=price or Decimal(a['cost_cap_hkd'])!=Decimal('5.36') or price>Decimal(a['cost_cap_hkd']):raise Stop('COST_SCOPE_MISMATCH')
    if a['maximum_paid_submissions']!=1 or a['automatic_paid_retries']!=0:raise Stop('SUBMISSION_LIMIT_MISMATCH')
    return m,q
def validate_images(m,inputs):
    if len(inputs)!=1:raise Stop('ONE_IDENTITY_IMAGE_REQUIRED')
    if sum(map(len,inputs))>64000:raise Stop('PRIVATE_INPUT_TOTAL_TOO_LARGE')
    for value,image in zip(inputs,m['images']):
        try:data=base64.b64decode(value,validate=True)
        except Exception:raise Stop('PRIVATE_IMAGE_ENCODING_INVALID') from None
        if len(data)!=image['transport_bytes'] or digest(data)!=image['transport_sha256']:raise Stop('PRIVATE_IMAGE_HASH_MISMATCH')
        if data[:4]!=b'RIFF' or data[8:12]!=b'WEBP':raise Stop('PRIVATE_IMAGE_NOT_WEBP')
    return ['data:image/webp;base64,'+x for x in inputs]
def event_inputs():
    if os.environ.get('GITHUB_ACTIONS')!='true':raise Stop('GITHUB_ACTIONS_RUNTIME_REQUIRED')
    p=Path(os.environ.get('GITHUB_EVENT_PATH',''))
    if not p.is_absolute():raise Stop('EVENT_PATH_INVALID')
    event=json.loads(p.read_text(encoding='utf-8'));data=event.get('inputs',{})
    values=[data.get(f'image_{i}_base64','') for i in range(1,2)]
    if not all(isinstance(x,str) for x in values):raise Stop('IMAGE_INPUT_TYPE_INVALID')
    return values,data
def binding():
    if os.environ.get('GITHUB_ACTIONS')!='true':raise Stop('GITHUB_ACTIONS_RUNTIME_REQUIRED')
    host=os.environ.get('ALIYUN_MODEL_STUDIO_HK_API_HOST','')
    key=os.environ.get('ALIYUN_MODEL_STUDIO_HK_API_KEY','')
    if host!=EXPECTED_HOST or not key:raise Stop('EXACT_HK_BINDING_NOT_READY')
    return host,key
def api(host,key,task=None,payload=None):
    url=f'https://{host}/api/v1/tasks/{task}' if task else f'https://{host}/api/v1/services/aigc/video-generation/video-synthesis'
    headers={'Authorization':'Bearer '+key}
    if payload is not None:headers.update({'Content-Type':'application/json','X-DashScope-Async':'enable'})
    data=json.dumps(payload).encode('utf-8') if payload is not None else None
    req=urllib.request.Request(url,data=data,headers=headers,method='POST' if payload is not None else 'GET')
    try:
        with urllib.request.urlopen(req,timeout=45) as response:raw=response.read(2*1024*1024)
        value=json.loads(raw)
        if not isinstance(value,dict):raise ValueError()
        return value
    except urllib.error.HTTPError as error:
        # Raw provider bodies may echo submitted media. Retain only safe fields.
        try:body=json.loads(error.read(500000));code=safe_code(body.get('code'))
        except Exception:code='HTTP_ERROR'
        raise Stop(f'HTTP_{error.code}_{code}') from None
    except Exception:raise Stop('PROVIDER_REQUEST_OUTCOME_UNCERTAIN' if payload is not None else 'PROVIDER_GET_FAILED') from None
def validate_video(path):
    if not shutil.which('ffprobe') or not shutil.which('ffmpeg'):raise Stop('MEDIA_VALIDATION_TOOLS_REQUIRED')
    probe=subprocess.run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)],capture_output=True,check=True)
    meta=json.loads(probe.stdout);video=next(s for s in meta['streams'] if s['codec_type']=='video')
    width,height=video['width'],video['height'];duration=float(meta['format']['duration'])
    if not 3.9<=duration<=4.3 or not width>height or min(width,height)<720:raise Stop('OUTPUT_DURATION_OR_SIZE_MISMATCH')
    if abs(width/height-16/9)>.025:raise Stop('OUTPUT_RATIO_MISMATCH')
    decoded=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],capture_output=True)
    if decoded.returncode or decoded.stderr:raise Stop('OUTPUT_FULL_DECODE_FAILED')
    return {'duration':duration,'width':width,'height':height,'sha256':digest(path.read_bytes()),'bytes':path.stat().st_size,'full_decode':'PASS',
            'audio_stream_present':any(s['codec_type']=='audio' for s in meta['streams'])}
def download(url,path):
    if not isinstance(url,str) or not url.startswith('https://'):raise Stop('RESULT_URL_INVALID')
    try:
        with urllib.request.urlopen(url,timeout=90) as response,path.open('xb') as dest:
            count=0
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                count+=len(chunk)
                if count>512*1024*1024:raise Stop('RESULT_SIZE_CAP_EXCEEDED')
                dest.write(chunk)
    except Stop:raise
    except Exception:raise Stop('RESULT_DOWNLOAD_FAILED_GET_ONLY_RESUME') from None
def poll(host,key,task,receipt,out,receipt_path):
    last_status=None
    for _ in range(120):
        value=api(host,key,task=task);output=value.get('output',{});status=output.get('task_status','UNKNOWN')
        receipt.update(status=status,updated_utc=utc())
        if status!=last_status:
            print('PROVIDER_TASK_STATE '+safe_code(status),flush=True);last_status=status
        usage=value.get('usage',{})
        if isinstance(usage,dict):receipt['usage']={k:v for k,v in usage.items() if k in ('video_duration','input_video_duration','output_video_duration','video_count','resolution','duration','fps','SR','ratio') and isinstance(v,(str,int,float))}
        save(receipt_path,receipt)
        if status=='SUCCEEDED':
            video=out/'StormMV_Zachary_2026-10-17_MP4_WanSourceEdit4s720P_Native_v19.mp4'
            download(output.get('video_url'),video)
            receipt.update(status='RESULT_DOWNLOADED_TECHNICAL_VALIDATION_PASS',validation=validate_video(video),updated_utc=utc())
            save(receipt_path,receipt);print('RESULT_DOWNLOADED_TECHNICAL_VALIDATION_PASS');return
        if status in ('FAILED','CANCELED'):
            receipt['provider_code']=safe_code(output.get('code'));save(receipt_path,receipt);raise Stop('TASK_'+status+'_NO_PAID_RETRY')
        time.sleep(15)
    raise Stop('TASK_PENDING_GET_ONLY_RESUME_REQUIRED')
def validate_public_source(m):
    item=m['videos'][0]
    try:
        with urllib.request.urlopen(item['public_url'],timeout=40) as response:
            if response.status!=200 or response.headers.get_content_type()!='video/mp4':raise Stop('SOURCE_PUBLIC_TYPE_MISMATCH')
            raw=response.read(item['bytes']+1)
    except Stop:raise
    except Exception:raise Stop('SOURCE_PUBLIC_READBACK_REQUIRED') from None
    if len(raw)!=item['bytes'] or digest(raw)!=item['sha256']:raise Stop('SOURCE_PUBLIC_HASH_MISMATCH')

def assert_single_submission_ledger():
    if os.environ.get('GITHUB_REPOSITORY')!='opc-zachary/ai-training-knowledge' or os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch':
        raise Stop('EXACT_PROJECT_DISPATCH_REQUIRED')
    token=os.environ.get('GITHUB_TOKEN','');current=os.environ.get('GITHUB_RUN_ID','')
    if not token or not current.isdigit():raise Stop('LEDGER_BINDING_REQUIRED')
    url='https://api.github.com/repos/opc-zachary/ai-training-knowledge/actions/workflows/wan-hk-storm-mv-zachary-v19.yml/runs?per_page=100'
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'Storm-Zachary-v19'})
    try:
        with urllib.request.urlopen(req,timeout=45) as response:history=json.loads(response.read(2000000))
    except Exception:raise Stop('LEDGER_READBACK_REQUIRED') from None
    if history.get('total_count',101)>100:raise Stop('LEDGER_HISTORY_TRUNCATED')
    paid=[x for x in history.get('workflow_runs',[]) if '| generate |' in x.get('display_title','')]
    if len(paid)!=1 or paid[0].get('id')!=int(current):raise Stop('EXACT_ONE_GENERATE_AUTHORIZATION_CONSUMED')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=['offline-validate','check-binding','generate','resume','validate-existing'],default='offline-validate')
    parser.add_argument('--transport-root',type=Path);parser.add_argument('--video',type=Path)
    args=parser.parse_args();m,q=load()
    if args.mode=='offline-validate':
        if args.transport_root:
            values=[base64.b64encode((args.transport_root/Path(i['transport']).name).read_bytes()).decode('ascii') for i in m['images']]
            validate_images(m,values)
        print(json.dumps({'status':'OFFLINE_VALIDATION_PASS_ZERO_PROVIDER_CALLS','staged_only':STAGED_ONLY_BUILD,'images':1,'video_inputs':1,'output_seconds':4,'estimated_hkd':m['approval']['estimated_hkd']}));return
    if args.mode=='validate-existing':
        print(json.dumps(validate_video(args.video)));return
    if args.mode=='check-binding':
        host,key=binding();print(json.dumps({'status':'EXACT_HK_BINDING_PRESENT_ZERO_PROVIDER_CALLS','host':host,'key_value_printed':False}));return
    if STAGED_ONLY_BUILD or not m['approval']['approved']:raise Stop('EXACT_PAID_APPROVAL_AND_REPIN_REQUIRED')
    values,inputs=event_inputs();out=ROOT/'output-storm-zachary-v19';out.mkdir(exist_ok=True)
    receipt_path=out/'StormMV_Zachary_2026-10-17_JSON_WanReceipt_v19.json'
    host,key=binding()
    if args.mode=='generate':
        validate_public_source(m)
        assert_single_submission_ledger()
        if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':raise Stop('PAID_RERUN_FORBIDDEN')
        if inputs.get('confirmation')!=m['approval']['confirmation']:raise Stop('EXACT_CONFIRMATION_REQUIRED')
        if receipt_path.exists():raise Stop('EXISTING_WRITE_EVIDENCE_DO_NOT_REPOST')
        uris=validate_images(m,values);payload=copy.deepcopy(q)
        payload['input']['media'][1]['url']=uris[0]
        receipt={'project':m['project'],'client':m['client'],'version':'v19','status':'POST_INTENT_OUTCOME_UNKNOWN',
          'created_utc':utc(),'request_sha256':m['request_sha256'],'workflow_run_id':os.environ.get('GITHUB_RUN_ID'),
          'workflow_run_attempt':os.environ.get('GITHUB_RUN_ATTEMPT'),'paid_post_attempts':1,'estimated_hkd':m['approval']['estimated_hkd'],
          'cost_cap_hkd':'5.36','actual_billed_amount':'UNAVAILABLE','automatic_paid_retries':0}
        save(receipt_path,receipt)
        try:
            result=api(host,key,payload=payload);task=str(uuid.UUID(result.get('output',{}).get('task_id','')))
        except Exception as error:
            receipt.update(status='POST_OUTCOME_UNCERTAIN_DO_NOT_REPOST',safe_error=safe_code(str(error)),updated_utc=utc());save(receipt_path,receipt)
            raise Stop('POST_FAILED_OR_UNCERTAIN_INSPECT_RECEIPT_NO_RETRY') from None
        receipt.update(status='SUBMITTED',task_id=task,updated_utc=utc());save(receipt_path,receipt)
        print('PROVIDER_TASK_SUBMITTED '+task,flush=True)
    else:
        try:task=str(uuid.UUID(inputs.get('resume_task_id','')))
        except ValueError:raise Stop('EXISTING_TASK_UUID_REQUIRED') from None
        receipt={'project':m['project'],'client':m['client'],'version':'v19','status':'RESUME_GET_ONLY','task_id':task,'paid_post_attempts':0,'created_utc':utc()}
        save(receipt_path,receipt)
    poll(host,key,task,receipt,out,receipt_path)

if __name__=='__main__':
    try:main()
    except Stop as error:print('SAFE_STOP '+str(error),file=sys.stderr);sys.exit(2)
    except Exception:print('SAFE_STOP LOCAL_OR_SCHEMA_ERROR',file=sys.stderr);sys.exit(3)
