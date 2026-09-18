# Windows実行構成の候補調査

調査日: 2026-09-18。A85〜A90を前提にした資料調査。採用決定ではなく、インストール・モデル取得・推論・試作・ドライバ変更は行っていない。

## 結論

WindowsネイティブのPython 3.12 x64とPySide6を画面側に置き、話者照合とASRをそれぞれ別プロセス・別環境で動かす案を第一候補とする。ただし、**SpeechBrainの公式サポートOSはLinux/macOSであり、全工程のWindows成立は未確認**。A44の「全ツールがWindowsで利用可能ならWindows中心」という条件を満たしたとはまだ判定しない。[SpeechBrain導入資料](https://speechbrain.readthedocs.io/en/latest/installation.html)

分離する理由は、GUI応答・中止を推論から独立させ、PyTorch側とCTranslate2側のDLL・依存更新を混ぜないためである。これは設計提案であり、プロセスを分ければ依存問題が自動解決するとの主張ではない。Windows成立が困難な場合は、話者処理だけWSLで動かす案を改めて比較する。WSL必須は現時点で採用しない。

## 確認できた版と候補の組合せ

以下は配布メタデータと一次資料に基づく**検証対象の候補**であり、解決済みlockfileではない。Pythonのパッチ版、推移依存、モデルrevision・ハッシュは採用前に固定する。

| 部分 | 具体候補 | 確認できたこと／残件 |
| --- | --- | --- |
| GUI | Python 3.12 x64、PySide6 6.11.2 | PySide6はPython >=3.10,<3.15、Windows x64のabi3 wheelあり。Python3.12は範囲内。Qtの関連wheelも同版指定 |
| 発話検出・特徴照合 | SpeechBrain 1.1.1、torch 2.8.0、torchaudio 2.8.0、Silero VAD 6.2.2 | SpeechBrainのtorch/torchaudio >=2.1とSileroのtorchaudio <2.10を満たす候補。torch/torchaudio 2.8.0双方にcp312 Windows x64 wheelあり。WindowsでECAPAまで動く証拠ではない |
| ASR | faster-whisper 1.2.1、CTranslate2 4.8.2 | faster-whisperはPython >=3.9、CT2 >=4,<5。CT2にcp312 Windows x64 wheelあり。GPU DLL組合せは未固定 |
| 人物の特徴モデル | speechbrain/spkrec-ecapa-voxceleb | 特徴ベクトルと話者照合の公式例あり。16kHzを利用。参照音声・モデル識別子と特徴を保存する案 |
| ASRモデル | large-v3を第一候補 | 日本語文字起こしを目的とし、速度上限を設けない合意に合わせた判断。turboは比較候補に留める。対象素材でlarge-v3が必ず優れると断定しない |

配布情報: [PySide6 6.11.2](https://pypi.org/pypi/PySide6/6.11.2/json)、[SpeechBrain 1.1.1](https://pypi.org/pypi/speechbrain/1.1.1/json)、[Silero VAD 6.2.2](https://pypi.org/pypi/silero-vad/6.2.2/json)、[torch 2.8.0](https://pypi.org/pypi/torch/2.8.0/json)、[torchaudio 2.8.0](https://pypi.org/pypi/torchaudio/2.8.0/json)、[faster-whisper 1.2.1](https://pypi.org/pypi/faster-whisper/1.2.1/json)、[CTranslate2 4.8.2](https://pypi.org/pypi/ctranslate2/4.8.2/json)。最新版同士を無条件で合わせず、Sileroの上限制約に合わせてtorch/torchaudioを揃える。[TorchAudioの版対応原則](https://docs.pytorch.org/audio/2.8/installation.html)

モデル根拠: [SpeechBrainモデルカード](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)、[faster-whisper公式例](https://github.com/SYSTRAN/faster-whisper)、[OpenAI turboモデルカード](https://huggingface.co/openai/whisper-large-v3-turbo)。turboはlarge-v3から縮小・調整された多言語モデルであり、英語専用distilモデルと混同しない。

## CPU・GPUと現在のPC

CPU経路を残す案とする。発話検出と特徴照合はまずCPU、ASRはGPUが利用可能ならCUDA、そうでなければ利用者がCPUでの実行を選べる構成を検証する。実行中のGPU失敗から勝手に再実行する案ではない。faster-whisperにはCPU int8、CUDA float16/int8_float16の公式例がある。[faster-whisper](https://github.com/SYSTRAN/faster-whisper)

SileroはCPUと8kHz/16kHzを扱う。発話があるかを検出する機能であり、誰の発話かは判定しない。ECAPAの照合と組み合わせても重なり音声の分離器にはならない。[Silero VAD](https://github.com/snakers4/silero-vad)、[ECAPAモデルカード](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)

現在確認済みのRTX4070約12GBとドライバ532.05だけからGPU実行可能とは判定しない。faster-whisper側はCUDA12用cuBLASとcuDNN9を案内し、CT2導入ページにはcuDNN8の記述も残る。選んだCT2 wheelに対応するDLLセットの確認が必要。CUDAメジャー内互換には機能上の制約もあるため、最低ドライバ表だけでは全モデル動作を保証できない。[CT2導入条件](https://opennmt.net/CTranslate2/installation.html)、[CUDA互換条件](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)

GPU採用時もPyTorchとASRモデルを同時常駐させず、必要な工程だけ読み込む案とする。12GBに収まること、10時間素材で中止できること、CPU経路で完了することは未実証。処理時間は記録し、品質・修正量・所要時間の数値合否基準は追加しない。

## Qtでの動画確認

QMediaPlayer、QAudioOutput、QVideoWidgetを動画確認の候補にする。Qt6.11の標準バックエンドはFFmpegで、Windows Media Foundationバックエンドは6.10から非推奨。Qt公式のFFmpeg依存版と配布方法を確認し、別用途のFFmpeg CLIやPyAVのDLLと同一視しない。プレビューで時刻を指定できることと、正確な切り出し境界が成立することは別に確認する。[Qt Multimedia](https://doc.qt.io/qt-6/qtmultimedia-index.html)

PySide6とQt Multimediaには商用契約以外のLGPL/GPL選択肢がある。ただし配布時は採用するモジュールと同梱ライブラリの条件を確認し、ライセンス・帰属情報を保存する。SpeechBrain対象モデルカードはApache-2.0、Sileroとfaster-whisperはMITを表示する。コードの許諾と個々の配布モデルの許諾を別に管理する。[PySide6配布情報](https://pypi.org/project/PySide6/)、[Qt Multimediaライセンス](https://doc.qt.io/qt-6/qtmultimedia-index.html)、[ECAPAモデル](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)

## アプリへの接続案と未解決事項

1. 元動画を一定長の16kHz音声チャンクとして処理し、元動画時刻との対応を保持する。全長PCMのメモリ展開はしない。
2. 参照音声の特徴登録と照合により対象話者の発話・非発話・不明区間を扱う。モデルの確信が低い箇所を対象者と断定しない。閾値と分割長は未固定。
3. 選択した対象者に対応する音声範囲をASRへ渡し、結果時刻を元動画へ戻す。重なりの混入、漏れ、不明は合意済みの手修正を残す。ASRが空だったことから非発話とは決めない。
4. 参照音声と人物データには特徴モデルrevision、処理設定、データ形式版を付ける。A89・90どおり共通モデルは移行先で準備し、欠けても取り込みと保存済み情報の閲覧を止めない。

未解決は、Windowsのモデル読込（取得キャッシュ・リンク方式を含む）、音声I/O、モデルと依存の組合せ、GPU DLL、BGM入り日本語での照合挙動、チャンクの時刻接続、配布パッケージである。資料だけで成立を確定しない。これらは利用者へ同じ希望を聞き直す項目ではなく、後の実証計画に載せる技術残件である。

追加調査: [Windows連携条件](speaker-integration-gates.md)でv1.1.1のモデルコピー・ローカル参照・Tensor入力を具体化した。音声I/Oはsoundfile基盤であり、古いtorchaudio.loadの説明と混同しない。通常権限でのWindows読込みを含む実証は未実施。
