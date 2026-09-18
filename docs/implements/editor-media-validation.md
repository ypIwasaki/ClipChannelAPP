# 映像・音声素材の標準入力検証

2026-09-18。軽微な検証を連続して進める指示に基づき、分離済みAviUtl2 2.1.9で実施。製品コード・追加プラグイン・ドライバ変更はない。利用者の既存プロジェクトを開いていない。

## 結論

WAV単体は読込み・保存・同一プロセスでの再読込みを確認した。一方、音声入り非圧縮AVIを配置した試行では、映像オブジェクトが表示された後にAviUtl2が異常終了した。映像読込みは成立未確認から「今回の構成・素材で異常終了を観測」へ更新する。原因、再現性、他形式への適用範囲は未確定。

## 素材と確認方法

同梱aviutl2.txtは標準入力にAVI/WAV等を挙げているため、追加のMP4入力プラグインを導入せずに確認できる素材を作った。A106で取得・時刻補正済みのlxYJTSK0y50-420-720-corrected.mp4の先頭8秒を使用。FFmpeg 9.0.1で320×180 / 30fps / bgr24 rawvideo / PCM s16le / 44.1kHz / stereoのAVIを生成した。元ファイルは変更していない。

```text
ffmpeg -nostdin -hide_banner -loglevel error -n -i <補正済みMP4> -t 8 -vf scale=320:180,fps=30 -c:v rawvideo -pix_fmt bgr24 -c:a pcm_s16le -ar 44100 -ac 2 media-probe.avi
ffmpeg -nostdin -v error -i media-probe.avi -f null -
ffmpeg -nostdin -v error -n -i media-probe.avi -vn -c:a copy audio-probe.wav
```

全デコードは終了コード0。ffprobeで映像240フレーム・8秒、音声352800サンプルを確認した。[媒体情報](evidence/editor-normal/media-probe-info.json)。FFmpegで読めることはAviUtl2での互換性を保証しない。

## AVI試行

空プロジェクトへ素材ブラウザーからmedia-probe.aviをドラッグした。Layer1に8秒の動画オブジェクトができ、音声メーターも表示されたが、映像プレビューは黒のままだった。続く操作は `foreground window did not report a process id` となり、ウィンドウ一覧・プロセス確認では対象が消えていた。

Windows Applicationイベント1000は11:39:59（JST）に検証フォルダのaviutl2.exeで例外 `c0000005`、同モジュール内オフセット `00000000001d2226` を記録。イベント1001もAPPCRASHを記録している。[必要項目だけの障害証跡](evidence/editor-normal/media-import-crash.json)。ダンプ解析や原因特定は行っていない。1回の試行であり、繰り返して再現性を確定してはいない。

AVIのSHA256: `91CEA91223858C7AC8936BA393FF84882C43DE67A4904D8A900DA83B0A385A37`。

## WAV試行

新たに起動した空プロジェクトへaudio-probe.wavをドラッグ。8秒の音声オブジェクト・波形・音声メーター・再生範囲0〜8秒が表示された。Ctrl+Sでは保存ダイアログが出ず、ファイルメニューの「プロジェクトを保存」で保存した。キー送信だけを保存成功判定にはできないことも再確認した。

保存データはlayer=0 / frame=0,239、音声ファイル参照、再生範囲0.000〜8.000、再生速度100、音量100、左右0。同ファイルを「開く」から再読込みし、8秒のオブジェクトと同じ設定表示を確認した後、通常終了。試聴による音質確認や完成動画の出力はしていない。

- WAV SHA256: `2BB851434FF4C9AA0109D697230F6D87201BFEEF186C696A30481ABC52955A4B`
- [保存プロジェクト](evidence/editor-normal/audio-import.aup2) SHA256: `F442DA87F6F64DAE15600A50A809532456E5EAEC0C1198624983F062334B3B3E`

プロジェクトは検証フォルダの絶対パスを参照する。媒体はローカル検証領域に保持し、リポジトリには同梱しない。

## 既存証跡と次の境界

過去の字幕関連4ファイルについて、分離環境とリポジトリのコピーのSHA256がすべて一致し、記録済み値から不変と確認した。[照合結果](evidence/editor-normal/fixture-integrity.json)。元spec.mdも不変。

次は映像読込みの最小再現確認と、映像のみ／形式差など変数を限定した切り分けが必要。WAV成功だけから音声がAVI異常終了の原因でないとは断定しない。映像入力が安定する前に、映像を含む複合編集・出力を合格扱いしない。追加プラグイン採用や本体の修正は別の検討事項であり、今回自動的に変更していない。

通常素材を読んだ際の実障害であり、意図的な失敗注入ではない。既定の模擬失敗3件やE5の復元試験を消化したとは数えない。E2はWAV単体の部分確認、E3〜E5の残件は維持。仕様確定・本体実装・Issue分割は行っていない。

## 2026-09-18追試：音声除去・画素形式・静止画の比較

軽微な比較を連続実施した。各試行は新たに起動した空プロジェクトへ素材ブラウザーから追加し、設定・追加プラグイン・ドライバは変更していない。

| 素材 | 変更点 | 結果 |
| --- | --- | --- |
| video-only.avi | 元のmedia-probe.aviから映像をstream copyし、音声だけ除去 | 8秒の動画オブジェクト表示後に異常終了。イベント1000、11:45:46、c0000005、offset 1d2214 |
| video-bgra.avi | video-only.aviのbgr24をbgraへ変換。320×180、30fps、240フレーム、音声なしを維持 | オブジェクト表示後に異常終了。イベント1000、11:46:46、c0000005、offset 2cb60c |
| a-image-probe.bmp | video-only.aviの先頭フレームをBMPへ出力 | 画像がプレビューへ表示され、2.70秒の画像オブジェクトとして保存成功。通常終了 |

元の音声入りAVIとvideo-only.aviの全映像をFFmpegでデコードし、SHA256がともに `ac2b28d17e17ff5fc3f29a62ee2050478e91969954124de7922289bf8cdd1354` と一致した。音声除去時に映像内容が変わった比較ではない。32bit版もffprobeでbgra・240フレーム・8秒を確認した。

```text
ffmpeg -nostdin -v error -n -i media-probe.avi -map 0:v:0 -c copy video-only.avi
ffmpeg -nostdin -v error -n -i video-only.avi -an -c:v rawvideo -pix_fmt bgra video-bgra.avi
ffmpeg -nostdin -v error -n -i video-only.avi -frames:v 1 a-image-probe.bmp
ffmpeg -nostdin -v error -i <比較対象AVI> -map 0:v:0 -f hash -hash sha256 -
```

[比較素材と保存ファイルのハッシュ](evidence/editor-normal/avi-comparison-hashes.json)、[3試行の障害イベント](evidence/editor-normal/avi-comparison-crashes.json)、[静止画の保存証跡](evidence/editor-normal/image-import.aup2)。静止画プロジェクトはlayer=0 / frame=0,80、画像参照、標準描画X=Y=0を保持。今回、静止画プロジェクトの再読込み・動画書き出しは未実施。

読取り専用の環境確認ではNVIDIA GeForce RTX 4070、DriverVersion 31.0.15.3205、DriverDate 2023-05-21。これだけからドライバ原因と判断しない。ドライバ更新やGPU設定変更は行っていない。

### 結果から言えることと残件

音声を持たないAVIでも異常終了するため、音声の併存は今回の症状の必須条件ではない。24bitだけに限った症状でもない。同じ素材の静止画を標準描画で表示できたため、描画全般が利用できないという結論も支持しない。

AVI入力処理、FFmpeg生成AVIの構造・互換性、環境依存のどこが原因かは未特定。例外の発生位置も同一ではなく、すべてを同一内部不具合と断定しない。各比較条件は1回ずつで、同一条件の再現率は未測定。

次の調査対象は、標準AVI経路の最小再現とファイル構造の確認、および既存候補の動画入力プラグインを使う場合の条件整理。形式を無制限に増やす試験、GPU・ドライバ変更、別編集基盤への切替は行わない。WAV・静止画・字幕の限定成功は維持するが、映像を含む複合編集の成立は引き続き未確認。今回は通常入力の診断であり、故意の失敗注入3件の消化には含めない。

### 利用者指摘による取得形式の優先確認

[形式監査](download-format-audit.md)で、yt-dlp取得直後の2本はMKV/H.264 High（720p60、8bit）/Opus、補正MP4はH.264/AAC-LCと再確認。両MKVの全デコード成功。追加入力プラグインのない検証用AviUtl2標準入力では元MKV・補正MP4は直接対応対象外。先行クラッシュは再エンコードした非圧縮AVIであり、元形式非対応と分ける。次は候補入力プラグイン構成との照合を優先。Premiere Proは検証しない。
