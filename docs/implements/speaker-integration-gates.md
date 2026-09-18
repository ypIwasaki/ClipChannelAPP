# 話者処理のWindows連携条件

> 最新実測（2026-09-18）：[複数人会話の検証](multi-speaker-validation.md)で指定20分のVAD・既存人物特徴との照合を実行。文字起こしは利用者の範囲変更により先頭10分（元動画20〜30分）を評価対象とし、追加推論を停止した。正解話者区間が不明のため、他者除外・重なり・閾値の品質判定はしていない。

調査日: 2026-09-18。A86・A91の第一候補を具体化する資料調査。モデル採用・実装・インストール・モデル取得・推論は行っていない。既存の `runtime-candidate-research.md` を補足する。

## 結論

SpeechBrain 1.1.1のECAPAをWindows CPUで検証する入口は具体化できる。**コピー方式でのモデル配置、ローカルモデル参照、16kHz単声道Tensorの直接入力**を組み合わせる。ただし、公式対応OSはLinux/macOSであり、入口があることをWindowsでの成立証拠にはしない。[公式導入資料](https://speechbrain.readthedocs.io/en/latest/installation.html)

この範囲の資料調査は終了できる。残件は下表の実証であり、同じWindows希望や手修正の許容を利用者へ聞き直さない。GPUはCPUでの最小経路確認後に扱い、GPU依存解決をCPU経路の開始条件にしない。

## 資料で確認した入口と落とし穴

| 項目 | 確認した事実 | 第一候補への反映案／限界 |
| --- | --- | --- |
| モデル配置 | `LocalStrategy.COPY` はコピー、既定は `SYMLINK`。Windowsのsymlinkには権限・設定上の注意があり、HFキャッシュのリンク方針は別管理 | `from_hparams` にCOPYを明示。管理者実行・開発者モードを前提にしない。COPYだけで全依存のリンク利用がなくなるとは断定しない |
| 読込み経路 | `pretrained_from_hparams` はlocal_strategyを設定ファイル取得と重み収集へ渡す。`FetchConfig` はネットワーク許可とrevisionを指定可能 | 確認済みローカル一式からCPU明示で読み込む候補。取得と実行を分離し、処理開始時の暗黙ダウンロードを避ける |
| モデル内の参照 | 公式YAMLの `pretrained_path` はHFのモデルID。重み等4ファイルのパスがこれを参照 | `source` だけをローカルに変えても十分とは限らない。`pretrained_path` もローカル一式へ上書きし、実行時ネットワーク禁止を併用する案 |
| 音声入力 | `encode_batch` はTensorと有効長を受け取る。16kHz入力は呼出側の責任 | デコード・単声道化・リサンプルを前段で行い、float32の短いTensorを渡す。全長PCMを一括展開しない |
| 音声ライブラリ | v1.1.1の `audio_io` はsoundfile基盤。`classifiers.py` 自体はtorchaudioをimportする | 古い `torchaudio.load` のバックエンド問題と混同しない。Tensor入力でもtorchaudioやsoundfileの導入依存は消えない |
| 照合 | `SpeakerRecognition.verify_batch` は特徴同士のcosine比較。既定の二値閾値は0.25 | 既定値を本アプリの対象／非対象／不明の閾値として無条件採用しない。音声分離や重なり解消機能とは扱わない |

根拠: [fetching.py v1.1.1](https://github.com/speechbrain/speechbrain/blob/v1.1.1/speechbrain/utils/fetching.py)、[interfaces.py v1.1.1](https://github.com/speechbrain/speechbrain/blob/v1.1.1/speechbrain/inference/interfaces.py)、[モデルYAML](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb/blob/main/hyperparams.yaml)、[classifiers.py v1.1.1](https://github.com/speechbrain/speechbrain/blob/v1.1.1/speechbrain/inference/classifiers.py)、[audio_io.py v1.1.1](https://github.com/speechbrain/speechbrain/blob/v1.1.1/speechbrain/dataio/audio_io.py)、[speaker.py v1.1.1](https://github.com/speechbrain/speechbrain/blob/v1.1.1/speechbrain/inference/speaker.py)、[HFキャッシュ説明](https://huggingface.co/docs/huggingface_hub/guides/manage-cache)。YAMLのmain参照は調査資料であり、採用時にはcommitと各ファイルのハッシュを固定する。

人物登録では既存の7205クラス分類ラベルを人物名として利用せず、参照音声から得た特徴と人物IDを関連付ける案とする。公式YAMLは192次元の特徴出力と別の分類器を定義し、`encode_batch` と `classify_batch` は別の入口である。人物再利用の互換条件にはモデルrevisionだけでなく、前処理・特徴正規化の設定も含める。これはアプリ側の設計案であり、公式の人物データ移行機能ではない。[モデルYAML](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb/blob/main/hyperparams.yaml)、[分類インターフェース](https://github.com/speechbrain/speechbrain/blob/v1.1.1/speechbrain/inference/classifiers.py)

## 同じモデルの代替実行経路

ONNXへの変換を、確認済みのWindows用公式配布として扱える根拠は今回の調査では得られなかった。公式リポジトリにはONNX対応を扱う議論があるが、それだけで当該重み・前処理・可変長入力の一致やWindows動作を保証できない。第三者の変換済みモデルへ無断で置き換えない。[公式ONNX議論](https://github.com/speechbrain/speechbrain/issues/2661)

したがって比較順は、同一モデルのCPU経路を確認し、成立しなければ原因を記録してWindowsネイティブ継続と別実行環境の比較へ戻る。WSL必須化・別モデル採用は今回決定しない。

## 有限の確認表

以下は将来の実証計画であり、このレビュー段階では実行しない。通常経路の確認であり、A40の模擬失敗3ケースを増やす提案ではない。

| ID | 最小確認 | 完了と判断する証拠 | 今回の状態 |
| --- | --- | --- | --- |
| S1 | 固定Python・CPU版torch/torchaudio・SpeechBrainのWindows通常権限での読込み | 依存版一覧、ローカル配置した固定モデルの読込み結果。symlink権限やGPUなしで実行できる | A105の固定構成で成功。全Windows環境の保証ではない |
| S2 | 同一の短い16kHz単声道入力から参照特徴を生成、保存、別動画照合に再利用 | 有限値の特徴、入力条件・モデル識別子、再読込み結果。人物データと共通モデルを分けて保持できる | A107で本人確認済みの別動画2素材について生成・保存・再読込み・比較に成功。識別精度や閾値の妥当性は未評価。[証跡](evidence/a106/confirmed-reuse.json) |
| S3 | 対象者のみ・他者のみ・重なり/BGM入りを含む少数の指定区間でVAD→照合→ASR | スコア・時刻付き結果と手修正経路。全文修正を許容し、誤り率・修正量の新たな合格上限は設けない | 本人確認済み20秒×2のVAD・照合・ASRを部分実証。VAD無検出でも全体ASRで本文が出る例あり。他者排除・重なり・手修正UI・製品閾値は未検証。[結果](a107-vad-asr-validation.md) |
| S4 | チャンクをまたぐ発言と長尺の通常処理、中止 | 元時刻への対応、欠落・重複処理の記録、有限メモリの推移、状態表示と中止完了、所要時間ログ | 通常中止は推論が返る境界で確認、要求から終了18.360秒。5分VADは状態と入力グリッド維持で一括時刻と一致。[分割比較](vad-chunk-validation.md)。長尺・ASR接続・GUI・強制停止は未実証。時間上限は追加しない |
| S5 | 別データフォルダへ人物情報を引き継ぎ、共通モデルを別途指定 | 参照音声・人物特徴・設定の再利用。依存不足時も保存済み情報の閲覧可能 | 同一PCの別フォルダコピーと共通モデル別指定で同じ照合値を再現。別PC・アプリ移行/閲覧は未実証。[記録](speaker-cancel-transfer-validation.md) |
| S6 | GPUを採用する場合のみ固定DLL・ドライバとの組合せ | 固定構成での処理記録。CPU成功からGPU成功を推定しない | 後段。CPU成立確認の前提ではない |

資料調査の終了条件は、S1〜S5へ渡す呼出入口・保存対象・既知の依存制約が一次資料で特定され、資料では判断できない点がこの表に残ること。現在この条件は満たす。一方、Windows対応成立・話者処理の採用可否・仕様全体の確定条件はまだ満たさない。S3の評価はASR文章をAIに採点させる処理を新設する意味ではない。


## A105の実測による更新

A105で分離環境の限定実証を承認・実施。編集E1は保存ダイアログ・Undo/Redo表示・標準出力メニューの入口を部分確認。話者S1はWindows通常権限CPUの固定構成で成立、S2は人工波形の特徴生成・保存再読込みのみ成功。実人物の照合・別動画再利用・ASR、編集保存成功・履歴実行・復元は未実証。詳細は [編集結果](a105-editor-validation.md)・[話者結果](a105-speaker-validation.md)。本体実装・仕様確定・Issue分割は行っていない。

本文の未起動・未導入・未推論・未観測の記述は資料調査時点の記録であり、上記の実測範囲について更新する。

### 2026-09-18：複数人会話の取得・照合と10分ASR

[新素材の検証](multi-speaker-validation.md)を追加。20:00〜40:00を認証なしで取得、20分VAD・既存参照との照合は73.798秒で完了。利用者の時間短縮指示に従いASRは先頭10分を評価し、60秒×10区間・モデル読込み込み720.09秒、時刻範囲逸脱0・加算誤り0、9境界の同文時刻重複候補26組の二重採用0を観測した。後半と追加境界認識は停止。本人／他者の正解区間が不明なため他者排除・閾値・認識品質は未判定。7時間全編の確認ではなく、同じ固定構成の部分実証として扱う。実装時に回した項目や、今回除外した認証・特殊入力・配布環境を事前必須検証へ戻さない。
