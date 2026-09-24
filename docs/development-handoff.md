# 別PCでの作業再開

更新：2026-09-18。開発作業の引き継ぎ手順であり、初版から除外した配布パッケージ・別PC配布検証を再追加するものではない。

## Gitで再開できる範囲

仕様・合意履歴・用語・ADR、導入済みスキル、検証コード・実測JSON・文字起こしはリポジトリにある。資料の確認と今後の設計作業はclone後に再開できる。モデル重み・媒体・人物特徴・ツール・仮想環境はGit外なので、同じ実測の再実行や音声の試聴は別途準備が必要。

```sh
git clone https://github.com/ypIwasaki/ClipChannelAPP.git
cd ClipChannelAPP
```

Windowsの通常フォルダへcloneしてよい。旧PCのWSL UNCパスやユーザー名を再現する必要はない。Windows専用検証を実行するときはWindows版Python/ツールを使い、WSL内Pythonでの同一動作を仮定しない。

## 最初に読むものと現在地

1. [共通指示](../AGENTS.md)、[用語集](../CONTEXT.md)、[現行の全体仕様](implements/spec.md)。[旧仕様草案](implements/spec-legacy-v0.1.md)は原文の履歴として保持する。Issueを作成・取得・更新するときは [ローカルIssue規則](agents/issue-tracker.md) を読む。
2. [編集受渡しの最新方針](implements/editor-handoff-scope.md)、[初版範囲の縮小](implements/initial-scope-pruning.md)、[ADR](adr/)。
3. [最新の複数人音声検証](implements/multi-speaker-validation.md)と[文字起こし全文](implements/evidence/multi-speaker/asr-first10-transcript.md)。
4. [初版の完成確認例](implements/acceptance-examples.md)と[現在の残件](implements/review-exit-criteria.md)を確認し、必要な領域について [検討状況](implements/spec-review-status.md)・[合意履歴](implements/spec-review.md)・各検証記録を参照する。

原仕様は再検討用の草案として保持している。日付が同じ追記も多いため、各資料冒頭の「最新方針」と後の利用者回答を優先する。本文には「未検証」「A105のみ」等の古い経緯が残り、現在の必須作業の全一覧とは限らない。

現在の重要な境界：

- 本アプリで区間と順序を決め一本の動画へ結合し、編集可能な字幕とともにAviUtl2へ渡す。
- AviUtl2の独立した事前検証は一区切り。保存・出力の簡易判定や画面設定等は実装時確認。競合防止、途中失敗復旧、本アプリのUndo/Redo・手編集後の履歴整合は今回見送り。
- 操作ごとの自動保存は不採用。未保存の扱いを含む明示保存の方針を維持する。
- 認証取得、HDR・用途別複数音声等の特殊入力、配布パッケージ・別環境配布検証は初版から外した。
- 代表8区間について利用者判定は「他者のみ」2件、「声が重なる」6件。対象者のみの正解例は未取得で、重なりに対象者が含まれるかも未判定。スコアは参考値であり閾値・精度の根拠にせず、今後は別動画で動作確認する。この人物専用の追加調整は行わない。
- 話者照合は20分、ASRは時間短縮指示により先頭10分（元動画20〜30分）を評価済み。同じ推論を理由なく再実行しない。
- 編集用動画の生成後に順番を変えるときは本アプリで組み直して別の編集用動画を生成する。画像・BGM・効果音は編集用動画に紐づける。新しい動画に対応する編集は既存AviUtl2プロジェクト・編集済み字幕・補助素材の配置と別物として管理し、自動移行しない。詳細は最新方針を読む。
- 編集用動画はMP4で、元動画1本の画質を上限にする。区間のアルファベット・数字を使用順に「_」でつなぐ。利用者指定のデータ用フォルダは[承認済みの用途別階層](implements/storage-transfer-validation-proposal.md)とし、編集用動画・プロジェクトを編集ごとの別フォルダに保持する。
- 素材・編集・処理／出力・解析結果は初版のDB管理から外す。解析結果は元動画名・種類別フォルダの版付きCSV、人物・共通設定もCSVで保存する。編集用MP4は完成動画の初期値を基準にし、異なる数値設定は元動画を優先する。過去の編集はAviUtl2プロジェクトを直接選んで開く。データ用フォルダは既存のものを選んで切り替え、複製・取り込み・別PC引き継ぎは初版対象外。[ADR-0009](adr/0009-limit-database-to-speaker-and-analysis.md)を参照。

この時点では仕様全体の確定・製品実装開始・Issue分割の承認は得ていない。会話そのもの・Codexのタスク状態や個人設定はGitに入らないため、上記文書を引き継ぎの基準にする。

## 同じ検証を再実行する場合だけ準備するもの

検証環境はWindows x64、Python 3.12.14、CPUで実測した。製品全体の完全なlockやインストーラーはない。既存venvのコピーではなく、必要なものだけ新しい検証フォルダで再作成する。

| 用途 | 版・準備情報 |
| --- | --- |
| 取得・変換 | yt-dlp 2026.8.19、EJS 0.8.0、Deno 2.9.7、FFmpeg/ffprobe 9.0.1 essentials。[依存記録](implements/evidence/a106/requirements-acquisition.txt)、[取得時の手順・証明書対応](implements/a106-source-validation.md)、[取得元とハッシュ](implements/dependency-distribution-register.md) |
| VAD・話者 | torch/torchaudio 2.8.0+cpu、SpeechBrain 1.1.1、Silero VAD 6.2.2、onnxruntime 1.30.0。[Windows CPU導入例](implements/a105-speaker-validation.md)、[VAD依存記録](implements/evidence/a106/requirements-vad.txt)。torchはCPU wheel用indexを使用した。requirements一覧だけで全環境の解決を保証しない |
| ASR | faster-whisper 1.2.1、CTranslate2 4.8.2、CPU int8・4スレッド。[依存記録](implements/evidence/a106/requirements-asr.txt)、[設定](implements/a107-vad-asr-validation.md) |
| ECAPAモデル | `speechbrain/spkrec-ecapa-voxceleb` revision `0f99f2d0ebe89ac095bcc5903c4dd8f72b367286`。[固定revision](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb/tree/0f99f2d0ebe89ac095bcc5903c4dd8f72b367286)、[ファイル指紋](implements/evidence/a105/speaker/model-sha256.json) |
| ASRモデル | `Systran/faster-whisper-large-v3` revision `edaa852ec7e145841d8ffdb056a99866b5f0a478`。[固定revision](https://huggingface.co/Systran/faster-whisper-large-v3/tree/edaa852ec7e145841d8ffdb056a99866b5f0a478)、[ファイル指紋](implements/evidence/a106/asr-model-hashes.json) |
| AviUtl2の過去検証を再現する場合 | 本体・入力/出力プラグインは別途準備。[構成](implements/editor-integration-options.md)、[SDK検証記録](implements/editor-sdk-observer-validation.md)。C++ビルドにはSDKヘッダー、MSVC/Windows SDKが必要。既存cmdはVS18 Community・Windows SDK10.0.28000.0等の旧PC配置を参照する。信頼確認が出る場合は利用者が行う |

モデルの取得と推論を分離し、記録したrevision・ファイル名・SHA256を確認してからローカルモデルを指定する。新しい依存版に変えた場合は旧版の成功をそのまま引き継がない。

## Git外の実データ

下表の相対名は旧PCの保管場所に対応する。必要なものだけGit外で移送するか、指定URLから再取得する。元のデータや検証証跡は上書きしない。

| 用途 | 移送するもの／再取得元 | 根拠 |
| --- | --- | --- |
| 登録済み人物の再利用 | `a106/accurate-first.wav`、`confirmed-reference.pt`、`confirmed-reuse.json`。先頭の音声はRWM4SdTZ1t8の03:00〜03:20。利用者A107で本人のみと確認済み | [移送3点の指紋](implements/evidence/a106/transfer-result.json)、[再生成コード](implements/evidence/a106/enroll_confirmed.py)。再生成コードは確認用のaccurate-second.wavも必要 |
| 本人の別動画比較 | `a106/accurate-second.wav`＝lxYJTSK0y50の07:00〜07:20 | [取得・本人確認](implements/a106-source-validation.md)、[音声指紋](implements/evidence/a106/confirmed-reuse.json) |
| 今回の20分音声・試聴 | `audio-20m40m.wav`、必要な`listen-*.wav`。8Xyb7UB3OlMの20:00〜40:00。ASR評価は先頭10分 | [取得指紋](implements/evidence/multi-speaker/acquisition-result.json)、[試聴区間](implements/multi-speaker-validation.md) |
| 編集の過去fixture | Git内の`.aup2`が参照する映像・画像・音声本体と対応プラグイン | 各検証記録。aup2はテキストでGitに含むが、素材は同梱しない。再開先のパスへ再接続する |

旧PCの場所：

- 既存音声・人物特徴：`%LOCALAPPDATA%/ClipChannelAPP-validation/a106/`
- 今回の音声：`%TEMP%/clipchannel-multi-speaker-8Xyb7UB3OlM/`
- 共通ECAPA：`%TEMP%/clipchannel-a105-speaker/model/`
- 共通ASR：`%LOCALAPPDATA%/ClipChannelAPP-validation/asr-probe/model/`

Windowsアプリのリダイレクトにより、実体が `%LOCALAPPDATA%/Packages/OpenAI.Codex_2p2nqsd0c76g0/LocalCache/Local/` 配下にある場合もある。Tempは永続保管先ではない。試聴リンクを別PCで利用する場合は移送先へ読み替える。モデル・人物特徴はバイナリのままGitに追加しない。

## 検証コードの再実行に関する注意

`docs/implements/evidence/`は実行当時の使い捨て検証コードと結果。汎用の製品CLIではない。再実行する場合は別の作業コピーで、絶対パスと出力先をそのPCへ設定する。

- `multi-speaker/prepare_audio.py`：FFmpeg/ffprobeの旧PC絶対パスを変更する。
- `multi-speaker/speaker_probe.py`：ECAPAモデルと人物特徴の絶対パスを変更する。入力は20分PCMを前提とする。
- `multi-speaker/asr_chunk_probe.py`：入力・モデル・出力先は引数だが、原本は20分と追加境界試験を処理する。今回の10分は停止後の抽出結果なので、そのまま実行せず、再試験する範囲に合わせて作業コピーを調整する。
- 古いプローブやビルドcmdにも固定パスがある。Git内の記録を出力先にせず、過去結果を上書きしない。

Codex等の会話UI・Computer Useの操作環境や接続権限はこのGitには含まれない。必要な場合に別PC側で準備する。通常の資料確認にこれらは不要。
