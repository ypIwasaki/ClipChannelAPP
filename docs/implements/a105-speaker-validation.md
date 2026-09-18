# A105 話者モデルのWindows CPU最小検証

実施日: 2026-09-18。A105で許可された分離環境・人工波形による最小検証。アプリ本体の実装ではない。

## 結果

**S1は今回のWindows環境で成功。S2は人工波形の特徴生成・保存・再読込みまで成功した。** 実人物の照合、日本語、BGM・重なり、別動画の人物再利用、ASR、長尺、中止、移行は検証していない。Windows公式サポートや全環境での動作を保証する結果ではない。

| 項目 | 実測結果 |
| --- | --- |
| 権限 | `IsUserAnAdmin() = false`、管理者権限なし |
| Python | 3.12.14、MSC v.1944、AMD64、win32 |
| torch / torchaudio | 2.8.0+cpu / 2.8.0+cpu、CUDAビルドなし |
| SpeechBrain | 1.1.1 |
| ECAPA | `speechbrain/spkrec-ecapa-voxceleb` revision `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286` |
| モデル読込み | ローカルsourceとpretrained_path、LocalStrategy.COPY、CPU明示で成功 |
| 生成入力 | 16kHz、単声道float32、32,000サンプル(2秒)、220Hzと440Hzの合成波。人声ではない |
| 特徴 | `[1, 1, 192]`、全要素有限、normalize=False |
| 保存再読込み | torch.save後にweights_only=True / map_location=cpuで読込み、torch.equal=True |
| 所要時間 | 初回importを含む読込み17.079秒、特徴生成0.05594秒(4スレッド)。単回の入口確認であり性能保証ではない |
| ネットワーク | 取得段階と推論を分離。推論プロセスのsocket接続関数を拒否し、HF offlineとFetchConfig(allow_network=False)も設定。接続試行記録0件 |
| コピー確認 | loaded-model内の5ファイルはいずれもis_symlink=False |
| 依存整合 | pip check: No broken requirements found |

ネットワーク拒否は検証プロセスのPython socket APIへ適用したもので、OS全体のファイアウォールやネイティブDLLの通信監査ではない。このモデル経路はローカルのみで成功した。torch_audio_backendのlist_audio_backends廃止予定警告は出たが、処理は完了した。2.9等へ変更して同じ成功を推定しない。

## 分離領域と証跡

作業領域は新規の `C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-speaker`。既存フォルダがあれば停止する条件で作成した。既存Pythonからvenvを作り、システムPATH、GPU、ドライバ、既存利用者データは変更していない。環境とモデルはこの領域に保持し、削除していない。Tempのため将来の自動整理で失われる可能性がある。

- `probe.py`: 最小検証コード。SHA256 `FFFD7340FF3D43E959E0B08A44F9E8D02D3B26724CF9607245A3556CC8681116`
- `result.json`, `probe.log`: 実測結果と警告。
- `requirements-resolved.txt`, `pip-check.txt`: 推移依存と整合確認。
- `install-torch.log`, `install-speechbrain.log`: 導入ログ。
- `model-api.json`, `model-sha256.json`, `model/`: 公式API取得時のrevision、取得ファイル指紋、一式。
- `loaded-model/`: COPY配置先。`person-feature.pt`: 人物データ保存入口を模した人工特徴。実人物登録ではない。

入力Tensorの生バイトSHA256: `4c5ccccd1a2e46958ab4746b008de335d29befcc3179ace94b15882172226793`。
特徴Tensorの生バイトSHA256: `3beea6dfac415c1935e6026b497d133beea63bc67719ea2723e34299c83a3891`。

## 実行条件

既存ランタイム `C:/Users/raimu/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe` から新規venvを生成した。以下のPYは隔離領域のvenv/Scripts/python.exeを指す。

```text
python.exe -m venv C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-speaker/venv
PY -m pip install torch==2.8.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cpu
PY -m pip install speechbrain==1.1.1
PY -m pip freeze
PY -m pip check
PY C:/Users/raimu/AppData/Local/Temp/clipchannel-a105-speaker/probe.py
```

公式HF APIでrevisionを取得した後、その固定revisionのresolve URLから必要ファイルのみを取得。推論時にはsourceだけでなくYAMLのpretrained_pathもローカルディレクトリへ上書きした。

```python
model = EncoderClassifier.from_hparams(
    source=str(model_dir), savedir=str(root / 'loaded-model'),
    overrides={'pretrained_path': model_dir.as_posix()},
    run_opts={'device': 'cpu'}, local_strategy=LocalStrategy.COPY,
    fetch_config=FetchConfig(allow_network=False),
)
with torch.inference_mode():
    embedding = model.encode_batch(waveform, normalize=False)
```

## 取得モデルの指紋

[固定revisionの公式モデル](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb/tree/0f99f2d0ebe89ac095bcc5903c4dd8f72b367286)。以下は取得後のSHA256であり、別配布者による署名検証ではない。

| ファイル | SHA256 |
| --- | --- |
| embedding_model.ckpt | 0575CB64845E6B9A10DB9BCB74D5AC32B326B8DC90352671D345E2EE3D0126A2 |
| classifier.ckpt | FD9E3634FE68BD0A427C95E354C0C677374F62B3F434E45B78599950D860D535 |
| mean_var_norm_emb.ckpt | CD70225B05B37BE64FC5A95E24395D804231D43F74B2E1E5A513DB7B69B34C33 |
| hyperparams.yaml | 6F78854FA04BA59E761437B76A2575D3ABA5E5016DE3E9B69F0C9A5077FB1A41 |
| label_encoder.txt | E13C3A167BB4112685670EE896D20E2B565AF16B3A4CEEAA8689FA4D22ADB8B9 |
| config.json | 15FF7AFAD09ADEC0936C31493A7397C13F855914F4579A8393FE82649778A664 |
| README.md | 00F58C3CBD7A7510DE9374080DA0E82A4C4E8F4DF567F7338FE6EFE108BE705A |

## 残件への影響

WindowsネイティブCPUで当該候補を読めないという懸念は、この構成について最小実証で解消した。したがって現時点でWSL必須化や別モデルへ変更する理由はない。ただしS2の別動画での人物再利用とS3以降は未実証のまま。人工波形から192次元が出ることは、対象話者を実用的に識別できる証拠ではない。人物特徴の前処理・正規化・閾値はまだ製品設定として確定しない。

この実証は通常経路1件であり、A40の模擬失敗3ケースは実施していない。仕様確定・Issue分割・アプリ機能実装は行っていない。

## この実証で解決された依存一覧

```text
anyio==4.15.1
certifi==2026.7.22
cffi==2.1.1
charset-normalizer==3.5.1
click==8.5.0
cloudpickle==3.1.2
colorama==0.4.6
filelock==3.32.3
fsspec==2026.7.0
h11==0.16.0
hf-xet==1.6.0
httpcore==1.0.9
httpx==0.28.1
huggingface_hub==1.32.0
HyperPyYAML==1.2.3
idna==3.20
Jinja2==3.1.6
joblib==1.6.0
MarkupSafe==3.0.3
mpmath==1.3.0
networkx==3.6.1
numpy==2.5.3
packaging==26.3
pycparser==3.0
PyYAML==6.0.3
requests==2.34.2
ruamel.yaml==0.18.17
ruamel.yaml.clib==0.2.15
scipy==1.18.1
sentencepiece==0.2.2
setuptools==78.1.0
soundfile==0.14.0
speechbrain==1.1.1
sympy==1.14.0
torch==2.8.0+cpu
torchaudio==2.8.0+cpu
tqdm==4.70.1
typing_extensions==4.16.0
urllib3==2.8.0

```
