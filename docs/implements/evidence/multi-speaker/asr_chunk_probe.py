"""Throwaway all-speaker ASR chunk probe, not identity/accuracy scoring."""
import argparse, ctypes, hashlib, json, os, socket, threading, time, wave
from ctypes import wintypes
from pathlib import Path

class Memory:
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in ('PeakWorkingSetSize', 'WorkingSetSize', 'QuotaPeakPagedPoolUsage', 'QuotaPagedPoolUsage', 'QuotaPeakNonPagedPoolUsage', 'QuotaNonPagedPoolUsage', 'PagefileUsage', 'PeakPagefileUsage', 'PrivateUsage')]
    def __init__(self):
        self.stop_event=threading.Event(); self.started=time.perf_counter(); self.samples=[]
        self.psapi=ctypes.WinDLL('psapi', use_last_error=True); self.kernel=ctypes.WinDLL('kernel32', use_last_error=True)
        self.kernel.GetCurrentProcess.restype=wintypes.HANDLE
        self.psapi.GetProcessMemoryInfo.argtypes=[wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
        self.psapi.GetProcessMemoryInfo.restype=wintypes.BOOL
        self.thread=threading.Thread(target=self.run,daemon=True)
    def snapshot(self):
        v=self.Counters(); v.cb=ctypes.sizeof(v)
        if not self.psapi.GetProcessMemoryInfo(self.kernel.GetCurrentProcess(),ctypes.byref(v),v.cb): raise ctypes.WinError(ctypes.get_last_error())
        return dict(elapsed_seconds=round(time.perf_counter()-self.started,3),working_set_bytes=int(v.WorkingSetSize),peak_working_set_bytes=int(v.PeakWorkingSetSize),private_bytes=int(v.PrivateUsage))
    def run(self):
        while not self.stop_event.wait(.5): self.samples.append(self.snapshot())
    def start(self): self.samples.append(self.snapshot()); self.thread.start()
    def stop(self): self.stop_event.set(); self.thread.join(); self.samples.append(self.snapshot())

def deny_network(*args,**kwargs): raise RuntimeError('Network denied during offline ASR probe')
def sha256(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()
def write_json(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def summarize_first_ten(args):
    """Finalize persisted chunks after user-directed stop; performs no inference."""
    raw=json.loads(args.summarize_first_ten.read_text(encoding='utf-8-sig'))
    chunks=[c for c in raw['chunks'] if c['core_start']>=0 and c['core_end']<=600]
    assert len(chunks)==10 and chunks[0]['core_start']==0 and chunks[-1]['core_end']==600
    for left,right in zip(chunks,chunks[1:]): assert left['core_end']==right['core_start']
    words=[w for c in chunks for w in c['words']]
    violations=[dict(chunk=i,word=j,start=w['start'],end=w['end']) for i,c in enumerate(chunks) for j,w in enumerate(c['words']) if not(c['read_start']<=w['start']<=w['end']<=c['read_end']+.1)]
    mapping_errors=sum(abs(w['source_start']-w['start']-raw['source_offset'])>1e-8 or abs(w['source_end']-w['end']-raw['source_offset'])>1e-8 for w in words)
    boundaries=[]
    for left,right in zip(chunks,chunks[1:]):
        edge=left['core_end']; tail=[w for w in left['words'] if w['end']>=edge-2]; head=[w for w in right['words'] if w['start']<=edge+2]
        pairs=[dict(left=a,right=b,both_owned=a['owned'] and b['owned']) for a in tail for b in head if a['text'].strip() and a['text'].strip()==b['text'].strip() and max(a['start'],b['start'])<=min(a['end'],b['end'])]
        boundaries.append(dict(time=edge,source_time=raw['source_offset']+edge,left_words=tail,right_words=head,matching_text_with_time_overlap_candidates=pairs))
    report={k:v for k,v in raw.items() if k not in ('chunks','boundary_comparison','elapsed_seconds','status')}
    report.update(status='completed_requested_first_10min',stop_reason='User shortened analysis from20min to first10min; inference process was stopped after chunk13; no new inference for this summary.',input_file_seconds=raw['input_seconds'],analysis_core_start=0,analysis_core_end=600,source_analysis_start=1200,source_analysis_end=1800,max_read_end=chunks[-1]['read_end'],read_context_note='Final retained chunk reads through601s (source30:01) as pre-existing1s context; ownership core ends600s.',chunks=chunks,boundary_comparison=[],boundary_comparison_status='not_run_user_shortened',model_load_and_first_ten_chunks_seconds=raw['model_load_seconds']+sum(c['elapsed_seconds'] for c in chunks),first_ten_inference_seconds=sum(c['elapsed_seconds'] for c in chunks),retained_stopped_raw_chunk_count=len(raw['chunks']),retained_stopped_raw_elapsed_seconds=raw['elapsed_seconds'],stopped_processes=dict(launcher_pid=6300,inference_pid=11528,remaining_owned_processes=0,exec_exit_code=1,reason='user-directed termination, not inference failure or injected-failure test'),memory=dict(peak_working_set_bytes=max(c['memory_after']['peak_working_set_bytes'] for c in chunks),max_private_bytes_observed_at_chunk_end=max(c['memory_after']['private_bytes'] for c in chunks),note='OS peak working set through first10 chunks; private bytes are end-of-chunk samples only. Periodic in-memory samples were not persisted before forced stop.'))
    report['observations']=dict(raw_word_count=len(words),owned_word_count=sum(w['owned'] for w in words),nonowned_words_retained=sum(not w['owned'] for w in words),time_range_violations=violations,source_mapping_errors=int(mapping_errors),boundary_count=len(boundaries),boundaries=boundaries,max_pcm_read_seconds=max(c['read_end']-c['read_start'] for c in chunks),caveat='No identity or accuracy labels. Ownership assigns output words only; it does not prove no speech loss, no duplicate, or correct timing.')
    stopped=dict(raw)
    stopped.update(status='stopped_by_user_after_shortening',stop_reason=report['stop_reason'])
    args.output.mkdir(parents=True,exist_ok=True); args.evidence.mkdir(parents=True,exist_ok=True)
    for destination in (args.output,args.evidence):
        write_json(destination/'asr-stopped-raw.json',stopped)
        write_json(destination/'asr-first10-result.json',report)
    lines=['# 先頭10分の分割ASR試験','','対象: 8Xyb7UB3OlMの20:00〜30:00。20分音声のうち先頭10分へ利用者指示で短縮した。全話者を含む診断で、対象話者の文字起こし成果物ではない。','','60秒の本体区間×10、前後各1秒の重複読込み。最後の文脈読込みは30:01まで。元時刻は取得指定に基づき+1200秒し、全編との独立波形照合は未実施。','',f"モデル読込み＋先頭10区間: {report['model_load_and_first_ten_chunks_seconds']:.2f}秒。生語{len(words)}件、担当語{report['observations']['owned_word_count']}件。",f"単語時刻の読込み範囲逸脱: {len(violations)}件（末端0.1秒の検査許容）。元時刻加算誤差: {mapping_errors}件。",f"先頭10区間までのOS peak working set: {report['memory']['peak_working_set_bytes']/1024**2:.1f}MiB。区間末尾private bytes最大: {report['memory']['max_private_bytes_observed_at_chunk_end']/1024**2:.1f}MiB。",'','字幕・発話の正解、話者名、重複・脱落の正解注釈はない。語の中点で担当を分ける規則は実験用で、製品仕様の確定や品質合格を意味しない。','','## 各区間の概要','']
    for i,c in enumerate(chunks):
        text=''.join(s['text'] for s in c['segments'])
        lines.append(f"- 区間{i+1}、元動画{1200+c['core_start']:g}–{1200+c['core_end']:g}秒、処理{c['elapsed_seconds']:.2f}秒、生語{len(c['words'])}件。冒頭: {text[:100]}")
    lines+=['','## 境界の機械的観察','', '新たな一括／分割の比較推論は実行していない。下記は保存済み隣接区間の語を時刻と文字一致だけで比較した候補であり、実際の重複・認識漏れの断定ではない。','']
    for b in boundaries:
        pairs=b['matching_text_with_time_overlap_candidates']
        lines.append(f"- 元動画{b['source_time']:g}秒: 同文かつ時刻重複の候補{len(pairs)}組、そのうち両方が担当扱い{sum(p['both_owned'] for p in pairs)}組。")
    lines+=['','## 停止と保持','','先頭10区間の結果は停止前に保存済み。終了時点では13区間が保存されていたため、途中生結果は別ファイルに保持した。14区間目以降・新規の短境界比較は完了していない。停止は利用者による範囲短縮に従ったもので、ASR失敗や中止機能の検証とは扱わない。','']
    for destination in (args.output,args.evidence): (destination/'asr-first10-preview.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('status','model_load_and_first_ten_chunks_seconds','first_ten_inference_seconds','retained_stopped_raw_chunk_count','memory')},ensure_ascii=False))
    print(json.dumps({k:v for k,v in report['observations'].items() if k!='boundaries'},ensure_ascii=False))


def main():
    p=argparse.ArgumentParser()
    for key in ('audio','model','output','evidence'): p.add_argument('--'+key,type=Path,required=key in ('output','evidence'))
    p.add_argument('--summarize-first-ten',type=Path)
    p.add_argument('--source-offset',type=float,default=1200)
    args=p.parse_args()
    if args.summarize_first_ten: return summarize_first_ten(args)
    assert args.audio.is_file(),'Parent must finish preparing input before run'
    assert args.model.is_dir()
    args.output.mkdir(parents=True,exist_ok=True); args.evidence.mkdir(parents=True,exist_ok=True)
    os.environ['HF_HUB_OFFLINE']='1'; os.environ['TRANSFORMERS_OFFLINE']='1'; os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    socket.socket.connect=deny_network; socket.socket.connect_ex=deny_network; socket.create_connection=deny_network
    from faster_whisper import WhisperModel
    import numpy as np
    with wave.open(str(args.audio),'rb') as f:
        rate=f.getframerate(); frames=f.getnframes()
        assert rate==16000 and f.getnchannels()==1 and f.getsampwidth()==2
    duration=frames/rate
    assert duration==1200.0,f'Expected exact20min, got {duration}'
    settings=dict(language='ja',beam_size=5,temperature=0,condition_on_previous_text=False,vad_filter=False,word_timestamps=True)
    report=dict(status='running',purpose='all-speaker diagnostic, not target-only transcription',input=args.audio.name,input_sha256=sha256(args.audio),input_seconds=duration,source_offset=args.source_offset,source_alignment='1200-second offset follows acquisition accurate-seek request; not independently waveform-aligned against complete stream',model_revision='edaa852ec7e145841d8ffdb056a99866b5f0a478',compute_type='int8',cpu_threads=4,settings=settings,core_seconds=60,overlap_seconds=1,ownership_rule='word midpoint in [core_start,core_end); raw words retained',network='socket connect/connect_ex/create_connection denied; local_files_only=True',chunks=[],boundary_comparison=[])
    clock=time.perf_counter(); memory=Memory(); memory.start(); load=time.perf_counter()
    model=WhisperModel(str(args.model),device='cpu',compute_type='int8',cpu_threads=4,local_files_only=True)
    report['model_load_seconds']=time.perf_counter()-load
    def read_pcm(lo,hi):
        with wave.open(str(args.audio),'rb') as f:
            f.setpos(round(lo*rate)); raw=f.readframes(round((hi-lo)*rate))
        assert len(raw)==round((hi-lo)*rate)*2
        return np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768
    def transcribe(mode,lo,hi,core_lo,core_hi):
        begin=time.perf_counter(); audio=read_pcm(lo,hi)
        segments,info=model.transcribe(audio,**settings); rows=[]; words=[]
        for s in segments:
            rows.append(dict(start=float(lo+s.start),end=float(lo+s.end),text=s.text,source_start=float(args.source_offset+lo+s.start),source_end=float(args.source_offset+lo+s.end)))
            for w in s.words or []:
                start,end=float(lo+w.start),float(lo+w.end)
                words.append(dict(start=start,end=end,source_start=args.source_offset+start,source_end=args.source_offset+end,text=w.word,probability=float(w.probability),owned=bool(core_lo<=(start+end)/2<core_hi),crosses_core_boundary=bool(start<core_lo or end>core_hi)))
        return dict(mode=mode,read_start=lo,read_end=hi,core_start=core_lo,core_end=core_hi,input_array_bytes=int(audio.nbytes),segments=rows,words=words,elapsed_seconds=time.perf_counter()-begin,memory_after=memory.snapshot())
    try:
        for index,lo in enumerate(range(0,int(duration),60)):
            hi=min(duration,lo+60)
            run=transcribe('long_chunk',max(0,lo-1),min(duration,hi+1),lo,hi)
            report['chunks'].append(run); report['elapsed_seconds']=time.perf_counter()-clock
            write_json(args.output/'asr-chunk-result.json',report)
            print(f"chunk {index+1}/20 core={lo}-{hi}s words={len(run['words'])} elapsed={run['elapsed_seconds']:.2f}s total={report['elapsed_seconds']:.2f}s",flush=True)
        report['main_chunking_seconds_including_load']=time.perf_counter()-clock
        for mode,spans in [('full',[(50,70,50,70)]),('split',[(50,60,50,60),(60,70,60,70)]),('overlap',[(50,61,50,60),(59,70,60,70)])]:
            for span in spans:
                run=transcribe(mode,*span); report['boundary_comparison'].append(run)
                write_json(args.output/'asr-chunk-result.json',report)
                print(f"boundary {mode} {span[0]}-{span[1]} elapsed={run['elapsed_seconds']:.2f}s",flush=True)
        all_words=[w for c in report['chunks'] for w in c['words']]
        owned=[w for w in all_words if w['owned']]
        invalid=[dict(chunk=i,word=j,start=w['start'],end=w['end']) for i,c in enumerate(report['chunks']) for j,w in enumerate(c['words']) if not(c['read_start']<=w['start']<=w['end']<=c['read_end']+.1)]
        mapping=[w for w in all_words if abs(w['source_start']-w['start']-args.source_offset)>1e-8 or abs(w['source_end']-w['end']-args.source_offset)>1e-8]
        boundaries=[]
        for left,right in zip(report['chunks'],report['chunks'][1:]):
            edge=left['core_end']; tail=[w for w in left['words'] if w['end']>=edge-2]; head=[w for w in right['words'] if w['start']<=edge+2]
            pairs=[dict(left=a,right=b,both_owned=a['owned'] and b['owned']) for a in tail for b in head if a['text'].strip() and a['text'].strip()==b['text'].strip() and max(a['start'],b['start'])<=min(a['end'],b['end'])]
            boundaries.append(dict(time=edge,source_time=args.source_offset+edge,left_words=tail,right_words=head,matching_text_with_time_overlap_candidates=pairs))
        report['observations']=dict(raw_word_count=len(all_words),owned_word_count=len(owned),nonowned_words_retained=len(all_words)-len(owned),time_range_violations=invalid,source_mapping_errors=len(mapping),boundary_count=len(boundaries),boundaries=boundaries,max_pcm_read_seconds=max(c['read_end']-c['read_start'] for c in report['chunks']),caveat='Ownership only assigns model outputs. It does not prove speech coverage, identity, transcription accuracy, or absence of duplicates/omissions.')
        report['status']='completed'
    except BaseException as error:
        report['status']='error'; report['error']=dict(type=type(error).__name__,message=str(error)); raise
    finally:
        memory.stop(); report['elapsed_seconds']=time.perf_counter()-clock
        report['memory']=dict(sampling_seconds=.5,samples=memory.samples,peak_working_set_bytes=max(x['peak_working_set_bytes'] for x in memory.samples),sampled_peak_private_bytes=max(x['private_bytes'] for x in memory.samples))
        write_json(args.output/'asr-chunk-result.json',report); write_json(args.evidence/'asr-chunk-result.json',report)
    lines=['# 20分音声の分割ASR試験','','全話者を含む診断。対象話者の文字起こし成果物ではない。本文はモデル出力であり、正解・話者名の注釈ではない。','',f"60秒本体区間×{len(report['chunks'])}、前後各1秒重複。元動画時刻 = 入力内時刻 + {args.source_offset:g}秒。",'','## 各区間の出力概要','']
    for i,c in enumerate(report['chunks']):
        body=''.join(s['text'] for s in c['segments'])
        lines.append(f"- 区間{i+1}、元動画{args.source_offset+c['core_start']:g}–{args.source_offset+c['core_end']:g}秒、処理{c['elapsed_seconds']:.2f}秒、生語{len(c['words'])}件。冒頭: {body[:160]}")
    lines+=['','## 境界1点の比較','','入力内60秒（元動画21:00）周辺。同一PCMの20秒一括出力も正解テキストではない。','']
    for r in report['boundary_comparison']:
        body=''.join(s['text'] for s in r['segments']); own=''.join(w['text'] for w in r['words'] if w['owned'])
        lines += [f"- {r['mode']} read={r['read_start']:g}–{r['read_end']:g}: {body}",f'  - 中点担当分: {own}']
    for d in (args.output,args.evidence): (d/'asr-chunk-preview.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=report['status'],elapsed_seconds=report['elapsed_seconds'],raw_words=report['observations']['raw_word_count'],peak_working_set_bytes=report['memory']['peak_working_set_bytes'])),flush=True)
if __name__=='__main__': main()


