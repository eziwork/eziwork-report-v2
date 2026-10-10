"""Presence-only onboarding; never calls a service or exposes a key."""
from key_input import masked_input
import json
import os
import platform
from pathlib import Path
import tempfile

BASIC = ('DATA_GO_KR_SERVICE_KEY','VWORLD_API_KEY','KOSIS_API_KEY','RONE_API_KEY','ECOS_API_KEY')
RETIRED = ('JUSO_CONFM_KEY','SCHOOLINFO_API_KEY','LAW_OC')

def managed_path():
    return Path.home()/'.config/eziwork-report-v2/environment.json'

def user_values(names=BASIC):
    if platform.system() != 'Windows':
        path=managed_path()
        if not path.exists(): return {}
        if path.is_symlink(): raise ValueError('UNSAFE_ENVIRONMENT_STORE')
        if os.name!='nt' and path.stat().st_mode & 0o077:
            raise ValueError('ENVIRONMENT_STORE_PERMISSIONS_REQUIRED')
        data=json.loads(path.read_text(encoding='utf-8'))
        return {k:v.strip() for k,v in data.items() if k in names and isinstance(v,str) and v.strip()}
    import winreg
    result={}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,'Environment') as key:
            for name in names:
                try:
                    value,kind=winreg.QueryValueEx(key,name)
                    if kind in (winreg.REG_SZ,winreg.REG_EXPAND_SZ) and isinstance(value,str) and value.strip():
                        result[name]=value.strip()
                except FileNotFoundError: pass
    except FileNotFoundError: pass
    return result

def legacy_values():
    root=Path(__file__).resolve().parents[1]
    path=Path(os.environ.get('EZIWORK_CREDENTIAL_FILE',root/'config/local-credentials.json'))
    if not path.is_absolute(): path=root/path
    if not path.is_file(): return {},str(path)
    data=json.loads(path.read_text(encoding='utf-8-sig'))
    return {k:v.strip() for k,v in data.items() if k in BASIC and isinstance(v,str) and v.strip()},str(path)

def check():
    saved=user_values();local,path=legacy_values();windows=platform.system()=='Windows';keys={}
    for name in BASIC:
        process=os.environ.get(name,'').strip();stored=saved.get(name,'')
        keys[name]={'present':bool(process or stored),'process_present':bool(process),'persistent_present':bool(stored),
            'user_environment_present':bool(stored) if windows else False,
            'managed_store_present':bool(stored) if not windows else False,
            'effective_location':'PROCESS' if process else ('WINDOWS_USER' if windows else 'EZIWORK_MANAGED') if stored else None,
            'conflict':bool(process and stored and process!=stored),
            'legacy_migration_available':bool(local.get(name)) and not bool(process or stored)}
    missing=[k for k,v in keys.items() if not v['present']]
    return {'status':'KEY_INPUT_REQUIRED' if missing else 'KEYS_PRESENT_NOT_VERIFIED','keys':keys,'missing':missing,
        'conflicts':[k for k,v in keys.items() if v['conflict']],
        'not_persistent':[k for k,v in keys.items() if v['present'] and not v['persistent_present']],
        'legacy_location':path if any(v['legacy_migration_available'] for v in keys.values()) else None,
        'live_call':False,'persistent_setup_supported':True}

def save_user(name,value):
    if name not in BASIC: raise ValueError('UNSUPPORTED_KEY_NAME')
    value=value.strip()
    if not value or any(c.isspace() or ord(c)<32 for c in value): raise ValueError('EMPTY_OR_INVALID_KEY_INPUT')
    if platform.system()=='Windows':
        import winreg
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,'Environment',0,winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key,name,0,winreg.REG_SZ,value)
    else:
        path=managed_path()
        if path.is_symlink() or path.parent.is_symlink(): raise ValueError('UNSAFE_ENVIRONMENT_STORE')
        path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);path.parent.chmod(0o700)
        user_values()  # Validate storage permissions before preserving unrelated settings.
        data=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        data[name]=value
        fd,tmp=tempfile.mkstemp(prefix='.environment-',dir=path.parent)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as out:
                json.dump(data,out,ensure_ascii=False);out.flush();os.fsync(out.fileno())
            Path(tmp).chmod(0o600);os.replace(tmp,path)
        finally: Path(tmp).unlink(missing_ok=True)
    if user_values((name,)).get(name)!=value: raise ValueError('ENVIRONMENT_SAVE_VERIFICATION_FAILED')
    if not os.environ.get(name,'').strip(): os.environ[name]=value

def setup(name=None, replace=False, reader=None, prompt_missing=True):
    state=check()
    if name and name not in BASIC: raise ValueError('UNSUPPORTED_KEY_NAME')
    if replace and not name: raise ValueError('REPLACE_REQUIRES_NAME')
    candidates=list(dict.fromkeys(state['missing']+state.get('not_persistent',[])))
    targets=[name] if replace else [name] if name in candidates else candidates if not name else []
    local,path=legacy_values();saved=[];migrated=[];cancelled=False
    for target in targets:
        try:
            process=os.environ.get(target,'').strip()
            if not replace and process:
                print(target+' : 현재 실행 환경의 값을 사용자 저장소에 저장합니다.')
                value=process;migrated.append(target)
            elif not replace and target in local:
                print(target+' : 기존 로컬 설정을 사용자 저장소로 이전합니다. '+path)
                value=local[target];migrated.append(target)
            elif prompt_missing:
                value=(reader or masked_input)(target+' : ')
            else:
                continue
            save_user(target,value);saved.append(target)
            if replace: os.environ[target]=value.strip()
            print(target+' : 저장 완료')
        except (KeyboardInterrupt,EOFError):
            cancelled=True;break
    result={**check(),'saved_names':saved,'migrated_names':[k for k in migrated if k in saved],
        'storage':'Windows current-user environment' if platform.system()=='Windows' else 'EZIWORK managed store; loaded into this process',
        'input_cancelled':cancelled}
    if cancelled: result['status']='INPUT_CANCELLED'
    return result


def ensure():
    # Explicit onboarding action; unlike check, may migrate existing values.
    result=setup(prompt_missing=False)
    if result['missing']:
        from key_window import open_window
        return open_window()
    return result


def apply_saved():
    for k,v in user_values().items():
        if not os.environ.get(k,'').strip(): os.environ[k]=v

def require_registered():
    result=check()
    if result['missing']: return result
    apply_saved()
    return None

