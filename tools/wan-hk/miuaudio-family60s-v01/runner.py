"""Two pinned MiuAudio Wan segments, one paid submission per segment and GET-only recovery."""
from __future__ import annotations
import argparse, base64, datetime, hashlib, json, os, re, shutil
import subprocess, sys, tempfile, time, urllib.error, urllib.request, uuid
from pathlib import Path

ROOT=Path(__file__).resolve().parent
MANIFEST=ROOT/'manifest.json'
PINNED_MANIFEST_SHA256='3cd67a011301b76523e8ded5785e570d886eaef3933a1b01e783feab62fa2b10'
EXPECTED_HOST='ws-f71y900nmq5fpsef.cn-hongkong.maas.aliyuncs.com'
EXPECTED_PARAMS={'resolution':'720P','ratio':'16:9','duration':30,'audio':False,'prompt_extend':False,'watermark':False}
REPO='opc-zachary/ai-training-knowledge'
WORKFLOW='wan-hk-miuaudio-family60s-v01.yml'

class Stop(Exception): pass
def digest(b):return hashlib.sha256(b).hexdigest()
def save(p,v):
    p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix('.tmp');temp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(temp,p)
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def safe_code(value):return value if isinstance(value,str) and re.fullmatch('[A-Za-z0-9_.-]{1,100}',value) else 'PROVIDER_ERROR'
def load():
    raw=MANIFEST.read_bytes()
    if digest(raw)!=PINNED_MANIFEST_SHA256:
        raise Stop('MANIFEST_HASH_MISMATCH')
    m=json.loads(raw)
    identity=(m['project'],m['client'],m['version'],m['model'])
    if identity!=('MiuAudio','MiuAudio','fourways60s-v01','wan3.0-video') or m['parameters']!=EXPECTED_PARAMS:
        raise Stop('EXACT_IDENTITY_OR_SETTINGS_MISMATCH')
    bounds=(m['max_paid_posts'],m['automatic_paid_retries'],m['output_seconds'],m['input_video_seconds'])
    if bounds!=(2,0,60,0) or set(m['segments'])!={'a','b'} or len(m['images'])!=7:
        raise Stop('SCOPE_MISMATCH')
    return m

def payload_for(m,inputs):
    segment=inputs.get('segment')
    if segment not in m['segments']:
        raise Stop('INVALID_SEGMENT')
    spec=m['segments'][segment]
    prompt=inputs.get('prompt','')
    if inputs.get('confirmation')!=spec['confirmation'] or digest(prompt.encode())!=spec['prompt_sha256']:
        raise Stop('EXACT_CONFIRMATION_AND_PROMPT_REQUIRED')
    media=[dict(type='reference_image',url=f'__IMAGE_{i}__') for i in range(1,8)]
    payload=dict(model=m['model'],input=dict(prompt=prompt,media=media),parameters=EXPECTED_PARAMS)
    canonical=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    if digest(canonical)!=spec['request_sha256']:
        raise Stop('REQUEST_HASH_MISMATCH')
    text=inputs.get('images','')
    values=json.loads(text) if len(text)<60000 else None
    if not isinstance(values,list) or len(values)!=len(m['images']):
        raise Stop('INVALID_PRIVATE_TRANSPORT')
    for item,value,ref in zip(media,values,m['images']):
        data=base64.b64decode(value,validate=True)
        if len(data)!=ref['bytes'] or digest(data)!=ref['sha256'] or data[:4]!=b'RIFF' or data[8:12]!=b'WEBP':
            raise Stop('EXACT_REFERENCE_REQUIRED')
        item['url']='data:image/webp;base64,'+value
    return payload

def event_inputs():
    if os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('GITHUB_REPOSITORY')!=REPO:
        raise Stop('EXACT_GITHUB_RUNTIME_REQUIRED')
    return json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())['inputs']

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
    if not 29.9<=duration<=30.3 or not width>height or min(width,height)<720:raise Stop('OUTPUT_DURATION_OR_SIZE_MISMATCH')
    if abs(width/height-16/9)>.025:raise Stop('OUTPUT_RATIO_MISMATCH')
    if any(s['codec_type']=='audio' for s in meta['streams']):raise Stop('SILENT_NATIVE_TRACK_REQUIRED')
    frame_rate=video.get('r_frame_rate','0/1').split('/')
    if len(frame_rate)!=2 or abs(float(frame_rate[0])/float(frame_rate[1])-30)>.1:raise Stop('OUTPUT_FRAME_RATE_MISMATCH')
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
        try:
            value=api(host,key,task=task)
        except Stop as exc:
            if not re.fullmatch(r'PROVIDER_GET_FAILED|HTTP_(429|50[0234])_.+',str(exc)):
                raise
            time.sleep(15)
            continue
        output=value.get('output',{});status=output.get('task_status','UNKNOWN')
        receipt.update(status=status,updated_utc=utc())
        if status!=last_status:
            print('PROVIDER_TASK_STATE '+safe_code(status),flush=True);last_status=status
        usage=value.get('usage',{})
        if isinstance(usage,dict):receipt['usage']={k:v for k,v in usage.items() if k in ('video_duration','input_video_duration','output_video_duration','video_count','resolution','duration','fps','SR','ratio') and isinstance(v,(str,int,float))}
        save(receipt_path,receipt)
        if status=='SUCCEEDED':
            video=out/f'MiuAudio_MiuAudio_2026-11-11_MP4_FourWaysToListenPart{receipt["segment"].upper()}_Native_v01.mp4'
            # The repository is public. Only an encrypted video may enter the artifact directory.
            with tempfile.TemporaryDirectory(prefix='miuaudio-wan-') as temp:
                plaintext = Path(temp) / video.name
                download(output.get('video_url'), plaintext)
                validation = validate_video(plaintext)
                encrypted = Path(temp) / (video.name + '.cms')
                encryption = subprocess.run([
                    'openssl', 'cms', '-encrypt', '-binary', '-aes-256-gcm', '-outform', 'DER',
                    '-in', str(plaintext), '-out', str(encrypted), str(ROOT / 'recipient.pem')
                ], capture_output=True)
                if encryption.returncode or not encrypted.is_file() or encrypted.stat().st_size < validation['bytes']:
                    raise Stop('PRIVATE_ARTIFACT_ENCRYPTION_FAILED_GET_ONLY_RESUME')
                shutil.move(encrypted, video.with_suffix('.mp4.cms'))
            receipt.update(status='RESULT_DOWNLOADED_TECHNICAL_VALIDATION_PASS',validation=validation,updated_utc=utc())
            save(receipt_path,receipt);print('RESULT_DOWNLOADED_TECHNICAL_VALIDATION_PASS');return
        if status in ('FAILED','CANCELED'):
            receipt['provider_code']=safe_code(output.get('code'));save(receipt_path,receipt);raise Stop('TASK_'+status+'_NO_PAID_RETRY')
        time.sleep(15)
    raise Stop('TASK_PENDING_GET_ONLY_RESUME_REQUIRED')
def assert_single_submission_ledger(segment,confirmation):
    token=os.environ.get('GITHUB_TOKEN','')
    current=os.environ.get('GITHUB_RUN_ID','')
    if not token or not current.isdigit() or os.environ.get('GITHUB_EVENT_NAME')!='workflow_dispatch':
        raise Stop('LEDGER_BINDING_REQUIRED')
    url=f'https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=100'
    req=urllib.request.Request(url,headers={'Authorization':'Bearer '+token,'Accept':'application/vnd.github+json','User-Agent':'MiuAudio-Family60s'})
    with urllib.request.urlopen(req,timeout=45) as response:
        history=json.loads(response.read(2000000))
    if history.get('total_count',101)>100:
        raise Stop('LEDGER_HISTORY_TRUNCATED')
    title=f'MiuAudio Family60s | generate | {segment} | {confirmation}'
    paid=[x for x in history.get('workflow_runs',[]) if x.get('display_title')==title]
    if len(paid)!=1 or paid[0].get('id')!=int(current):
        raise Stop('EXACT_ONE_GENERATE_AUTHORIZATION_CONSUMED')

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--mode',choices=['offline-validate','check-binding','generate','resume'],required=True)
    parser.add_argument('--input-json',type=Path)
    args=parser.parse_args()
    m=load()
    inputs=json.loads(args.input_json.read_text())['inputs'] if args.input_json else event_inputs()
    if args.mode=='offline-validate':
        if inputs.get('mode')=='generate':
            payload_for(m,inputs)
        print('OFFLINE_VALIDATION_PASS_ZERO_PROVIDER_CALLS')
        return
    if args.input_json or inputs['mode']!=args.mode:
        raise Stop('EXACT_EVENT_OPERATION_REQUIRED')
    if inputs.get('expected_sha')!=os.environ.get('GITHUB_SHA') or not re.fullmatch('[0-9a-f]{40}',inputs.get('expected_sha','')):
        raise Stop('EXACT_SOURCE_COMMIT_REQUIRED')
    host,key=binding()
    if args.mode=='check-binding':
        print('EXACT_HK_BINDING_PRESENT_ZERO_PROVIDER_CALLS')
        return
    segment=inputs['segment']
    spec=m['segments'][segment]
    if inputs.get('confirmation')!=spec['confirmation']:
        raise Stop('EXACT_CONFIRMATION_REQUIRED')
    out=ROOT/'result'
    out.mkdir(exist_ok=True)
    receipt_path=out/'receipt.json'
    if receipt_path.exists():
        raise Stop('EXISTING_WRITE_EVIDENCE_DO_NOT_REPOST')
    receipt=dict(project='MiuAudio',segment=segment,request_sha256=spec['request_sha256'],
        workflow_run_id=os.environ['GITHUB_RUN_ID'],created_utc=utc(),actual_billed_amount=None)
    if args.mode=='generate':
        if os.environ.get('GITHUB_RUN_ATTEMPT')!='1':
            raise Stop('PAID_RERUN_FORBIDDEN')
        payload=payload_for(m,inputs)
        assert_single_submission_ledger(segment,spec['confirmation'])
        receipt.update(status='POST_INTENT_OUTCOME_UNKNOWN',paid_post_attempts=1)
        save(receipt_path,receipt)
        try:
            result=api(host,key,payload=payload)
            task=str(uuid.UUID(result.get('output',{}).get('task_id','')))
        except Exception as error:
            receipt.update(status='POST_OUTCOME_UNCERTAIN_DO_NOT_REPOST',safe_error=safe_code(str(error)),updated_utc=utc())
            save(receipt_path,receipt)
            raise Stop('POST_FAILED_OR_UNCERTAIN_INSPECT_RECEIPT_NO_RETRY') from None
        receipt.update(status='SUBMITTED',task_id=task,updated_utc=utc())
        save(receipt_path,receipt)
        print('PROVIDER_TASK_SUBMITTED '+task,flush=True)
    else:
        task=str(uuid.UUID(inputs['resume_task_id']))
        receipt.update(status='RESUME_GET_ONLY',task_id=task,paid_post_attempts=0)
        save(receipt_path,receipt)
    poll(host,key,task,receipt,out,receipt_path)

if __name__=='__main__':
    try:
        main()
    except Stop as error:
        print('SAFE_STOP '+str(error),file=sys.stderr)
        sys.exit(2)
    except Exception:
        print('SAFE_STOP LOCAL_OR_SCHEMA_ERROR',file=sys.stderr)
        sys.exit(3)
