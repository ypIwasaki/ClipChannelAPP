# 対象話者処理の成立性調査

後続判断A86（2026-09-18）: 初版は特徴登録・照合＋文字起こしを第一候補とする。以下の方式選択に関する質問は回答済み。具体ツール・モデルの採用と実機成立は未確定。追加学習は未採用の研究候補として保持し、後続版への実装を決定したとは扱わない。

調査日: 2026-09-18。A84までの合意を前提とする資料調査。採用決定・実機実証ではない。モデル取得、依存導入、学習、推論、試作は行っていない。

## 結論

人物別の追加学習は研究開発候補として残せるが、現在用意できる「対象者だけが話す、ゲーム音・BGM入りの区間」だけで、そのまま使える人物専用学習手順は確認できなかった。追加学習を優先して調べた結果、WeSepの標準オンライン混合処理は異なる話者の素材を必要とすることが具体的に判明した。本人の素材を集めるだけでは標準手順を満たさない。

初版の実現候補としては、登録した参照音声から声の特徴を保存し、動画中の発話との照合によって対象を選び、ASRへ渡す構成を推奨する。これはA46で比較対象に残した方式であり、人物モデルの追加学習を採用したことにはならない。重なりや判定困難な箇所を「不明区間」として人が扱い、全文手修正も許容する合意との整合性が高いという設計上の判断である。自動的な対象者選択の機能を省略する案ではない。

## 候補と根拠

| 候補 | 確認した入口 | 判断 |
| --- | --- | --- |
| WeSepによる追加学習→対象話者抽出→ASR | 事前重み初期化、学習再開、対象波形と混合波形、登録発話を利用 | 研究候補を維持。本人以外の学習素材、正解波形、重みの許諾、環境固定が不足 |
| WeSpeakerで特徴登録・照合→ASR | 埋め込み抽出、類似度、話者分離、ONNX重みの公開 | 初版の比較候補。具体モデルのデータ由来ライセンスを固定する必要 |
| SpeechBrain ECAPAで特徴登録・照合→ASR | 公式モデルカードが埋め込み・照合・GPU推論とApache-2.0を明記 | 特徴登録の第一比較候補。重なり音声を分離するモデルではなく、配信日本語での挙動は未実証 |
| SpeakerBeam公式実装 | 対象話者抽出の研究実装 | 現在確認した評価用ライセンスのまま通常運用へ採用しない |
| faster-whisper | 音声から本文・時刻、CPU/GPU、VAD | ASR部分の候補。人物指定は別処理で必要。具体モデル・版は未採用 |

根拠: [WeSep学習コード](https://raw.githubusercontent.com/wenet-e2e/wesep/master/wesep/bin/train.py)、[WeSpeaker公式](https://github.com/wenet-e2e/wespeaker)、[WeSpeaker配布モデル条件](https://raw.githubusercontent.com/wenet-e2e/wespeaker/master/docs/pretrained.md)、[SpeechBrain公式モデルカード](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)、[SpeakerBeamライセンス](https://github.com/BUTSpeechFIT/speakerbeam/blob/main/LICENSE.txt)、[faster-whisper公式](https://github.com/SYSTRAN/faster-whisper)。

## 追加学習について今回具体化したこと

WeSepの `train.py` は `model_init` から重みを読み、checkpointから最適化状態等を再開する。しかし、この入口だけで「一人物を登録する製品機能」が出来上がっているとはいえない。[学習実装](https://raw.githubusercontent.com/wenet-e2e/wesep/master/wesep/bin/train.py)

標準レシピは訓練・検証の混合音声、話者ID、登録発話等を指定する。オンライン混合の `mix_speakers` は違う話者IDを探して組み合わせる。そのため本人だけの素材をそのまま入力することは適切でない。同一話者だけの場合の選択ループもあり、単純流用できないことがコードから分かる。[標準レシピ](https://raw.githubusercontent.com/wenet-e2e/wesep/master/examples/librimix/tse/v1/run.sh)、[データ処理実装](https://raw.githubusercontent.com/wenet-e2e/wesep/master/wesep/dataset/processor.py)

同処理は各素材を対象波形として残した上で混合する。したがってBGM入り素材を正解にするとBGMも正解側に残る、というのがコードからの推論である。対象話者の文字起こしが目的なのでBGMが残ること自体は失格ではないが、別配信への汎化やASR改善は保証できない。雑音追加対応と、既存BGMを除いた正解音声の生成は別問題である。[データ処理実装](https://raw.githubusercontent.com/wenet-e2e/wesep/master/wesep/dataset/processor.py)

追加学習案を具体化するには、本人の選別素材に加え、利用条件を満たす他者素材、訓練と独立した確認素材、採用ベース重みを決める必要がある。前処理後の波形を正解とする場合も、疑似正解を用いた独自手順の検証が必要になる。これは既存公式レシピで成立確認済みの手順ではない。素材の最低分数や12GB GPUでの学習可否は資料から断定しない。

## コードと重みの利用条件を分ける

WeSepの学習ファイルにはApache-2.0の表記があるが、READMEの事前学習モデル項目は未完了表記で、今回確認した資料から特定の配布重み一式と利用許諾を固定できなかった。コードのライセンスから重みの利用条件を推定しない。[学習ファイル](https://raw.githubusercontent.com/wenet-e2e/wesep/master/wesep/bin/train.py)、[README](https://raw.githubusercontent.com/wenet-e2e/wesep/master/README.md)

WeSpeakerのモデル資料は対応データセットの条件に従うと説明し、VoxCelebモデルについてCC BY 4.0の例を示す。SpeechBrainの対象モデルカードはApache-2.0を表示する。採用時は選んだ配布物の版・ハッシュ・許諾文・帰属情報を保存する案とする。本人データの移行合意A66は、第三者のベース重みの再配布条件を自動的に解消するものではない。[WeSpeakerモデル資料](https://raw.githubusercontent.com/wenet-e2e/wespeaker/master/docs/pretrained.md)、[SpeechBrainモデルカード](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)

## Windows・WSL・CUDA

| 部分 | 資料から分かること | 採用前の残件 |
| --- | --- | --- |
| WeSep標準学習 | bash、torchrunを利用し、学習コードでNCCLを指定 | Windowsネイティブの完成手順は未確認。WSL/Linuxを現実的な候補とする |
| 特徴登録 | SpeechBrainにCUDA推論例、WeSpeakerにONNX版あり | アプリとして必要な音声読込・VAD・照合全工程のWindows動作は未実証 |
| faster-whisper/CTranslate2 | CTranslate2はWindows/LinuxのGPU wheelを明記 | Python、CUDA、cuDNN、CTranslate2の版を一組で固定する必要 |
| WSL GPU | NVIDIAはWindows側ドライバを利用し、WSLへLinux表示ドライバを入れないと説明 | 現在のWSL/ドライバが選んだ具体構成を満たすか確認が必要 |

根拠: [WeSepレシピ](https://raw.githubusercontent.com/wenet-e2e/wesep/master/examples/librimix/tse/v1/run.sh)、[学習コード](https://raw.githubusercontent.com/wenet-e2e/wesep/master/wesep/bin/train.py)、[CTranslate2導入条件](https://opennmt.net/CTranslate2/installation.html)、[NVIDIA WSL資料](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)。

資料間にも注意点がある。CTranslate2導入ページにはcuDNN 8の記載がある一方、faster-whisperは現行CTranslate2にCUDA 12/cuDNN 9を要求すると記載する。双方の最新ページの文言を混ぜた構成を採用せず、選んだリリースの依存と配布物で解決する。[CTranslate2](https://opennmt.net/CTranslate2/installation.html)、[faster-whisper](https://github.com/SYSTRAN/faster-whisper)

既存調査でRTX4070約12GB、ドライバ532.05、WSLのPython3.14.4等を確認しているが、これは学習・推論成功の証拠ではない。CUDAの同一メジャー内互換にも制約があるため、ドライバ番号だけから一律に対応/非対応としない。既存Pythonへ無理に合わせず、候補別の隔離実行環境を設計する案とする。[CUDA互換性資料](https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html)

## 次の判断と実証の境界

利用者に同じ希望を再質問する必要はない。A46は追加学習優先調査であって必須採用ではなく、A47・48の素材条件と選別許容も既知である。

今回提示できる選択は、(1)初版候補を特徴登録＋照合＋ASRへ絞り、追加学習は未採用候補として残す、または(2)本人以外の素材と独自訓練レシピを必要とする追加学習を引き続き初版候補の中心に据える、である。推奨は(1)。採用を確定するには利用者の方式判断と後の実証が必要であり、本資料だけで実装開始には進まない。

後の実証では、名前付き人物データを作成して別動画に再利用できること、対象者指定が処理へ反映されること、不明区間・漏れ・混入を修正できること、保存・引き継ぎ・中止が機能することを確認する。精度や修正量、処理時間の数値上限を追加しない。話者照合の閾値は自動判定の挙動設定であって、ユーザーが拒否した完成品質ゲートとは区別する。1〜10時間の素材を一括メモリ展開する前提は置かず、分割処理と時刻復元を設計する。
