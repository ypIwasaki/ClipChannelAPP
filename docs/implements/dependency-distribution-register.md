# 依存物・配布境界の台帳（検討案）

> 最新範囲（2026-09-18）：既存2本の実取得に不要だった認証付き取得、HDR・用途別複数音声などの特殊入力、配布パッケージ・別環境での配布検証は初版から外す。[範囲判定と残す通常経路](initial-scope-pruning.md)を優先する。実行に必要なyt-dlp等、通常の変換・時刻対応、対象話者の照合は維持する。

2026-09-18。A104までの合意と[構成案](architecture-proposal.md)を前提にした一次資料調査。候補版を更新する文書ではない。インストール、配布物・モデルの新規ダウンロード、実行は行っていない。全推移依存を網羅したSBOMでも、法的適合性の保証でもない。

## 配布境界の案

アプリの画面・保存に必要な実行環境は同梱候補、編集本体・外部処理・共通モデルは別途準備を基本案とする。同梱候補とは配布可否の確認完了ではない。「別途準備」も利用条件の確認不要を意味しない。A89の移行パッケージには、アプリ・外部ツール・共通モデルを含めない。人物の参照音声と生成特徴は利用者データとして移行する。

下表のライセンス表示は読めた一次資料の要約である。master/developやモデルカードは可変のため、実際に採用する配布物内のLICENSE、NOTICE、第三者情報と版・ハッシュを固定して再照合する。

| 対象・既存候補版 | 配布区分案 | 一次資料で確認した条件と技術残件 |
| --- | --- | --- |
| CPython 3.12 x64（パッチ未固定） | 同梱候補 | PSF License v2はライセンス・著作権表示の保持、改変配布時の変更要約を規定。組込み第三者ライセンスも別に存在する。採用3.12配布物で再確認する。[公式ライセンス](https://docs.python.org/3/license.html) |
| PySide6 / Qt 6.11.2、Qt Multimedia | 同梱候補・条件確認待ち | Qt for PythonはLGPLまたは商用条件と第三者コードを区別する。LGPL経路では許諾文書、ライブラリ交換・再リンク等の条件に沿う配布形態を選ぶ。単一exeに包めば確認が不要になるとはしない。MultimediaのFFmpeg DLLも別項目として採録。[Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html)、[Qt LGPL](https://doc.qt.io/qt-6/lgpl.html) |
| SQLite（採用Pythonに含まれる版は未固定） | 同梱候補 | SQLiteコアはpublic domain。ただし有償拡張や別の配布ラッパーまで同じ扱いにしない。[公式著作権説明](https://www.sqlite.org/copyright.html) |
| AviUtl2 2.1.9 | 別途準備 | 公式ZIP内aviutl2.txtに商用業務利用可と「プログラムファイルの不特定多数への再配布はご遠慮ください。」の記載を確認。アプリへ本体を再梱包する案にはしない。[対象公式ZIP](https://spring-fragrance.mints.ne.jp/aviutl/aviutl2_v2.1.9.zip) |
| AviUtl2 SDK 2026-09-05 / 専用プラグイン | SDKは開発依存、作成プラグインは同梱候補 | 既読公式SDKのlicense.txtはMIT、著作権・許諾表示の保持を規定。本体の配布条件と混同しない。SDKのcredits、流用部分、専用プラグインの別依存も確認。[公式配布元](https://spring-fragrance.mints.ne.jp/aviutl/) |
| L-SMASH Works r1283 Mr-Ojii build-2026-09-13-02-46-28 | 別途準備・条件要確認 | 選定済み候補ZIP全体の利用条件と同梱codecを未監査。ソース公開だけで配布ZIP一式の許諾を判定しない。[候補release](https://github.com/Mr-Ojii/L-SMASH-Works-Auto-Builds/releases/tag/build-2026-09-13-02-46-28) |
| x264guiEx 4.12 AviUtl2向け | 別途準備・条件要確認 | プラグイン、x264、音声エンコーダー、多重化実行物は別項目。インストーラに含まれる実ファイルの一覧と許諾を未監査。[候補release](https://github.com/rigaya/x264guiEx/releases/tag/4.12) |
| FFmpeg / ffprobe CLI、libzimg（版・ビルド未固定） | 別途準備・ビルド確認待ち | FFmpegは通常LGPL2.1以降だがGPL部分を有効にしたビルドはGPLとなる。FFmpeg公式は再配布するバイナリと対応ソース・ビルド条件の一致を重視。zimgは独自に許諾表示保持を規定するライセンスを持つ。HDR→SDRで使うzscale等の有効化、必要encoder、ビルドの依存一覧を固定する。[FFmpeg公式](https://ffmpeg.org/legal.html)、[zimg COPYING](https://raw.githubusercontent.com/sekrit-twc/zimg/master/COPYING) |
| yt-dlp（採用版未固定、過去調査基準2026.08.19） | 別途準備。worker内Pythonパッケージ化は要確認 | ソース本体はUnlicense。一方、公式READMEはPyInstaller製standalone実行物にGPLv3+コードを含み合成物がGPLv3+になると明記。Windows exeとwheelを同じ許諾一覧にしない。[公式README Licensing](https://github.com/yt-dlp/yt-dlp#licensing) |
| yt-dlp-ejs、JS runtime（版未固定） | 別途準備 | EJSはUnlicenseに加えMITのastring・ISCのmeriyahを含む。Deno本体はMIT。runtimeにも第三者コードがあり本体MITだけで全体を確定しない。既案Deno優先、最低版と実際の固定版は区別。[EJS LICENSE](https://github.com/yt-dlp/ejs/blob/main/LICENSE)、[yt-dlp依存説明](https://github.com/yt-dlp/yt-dlp#dependencies)、[Deno LICENSE](https://raw.githubusercontent.com/denoland/deno/main/LICENSE.md) |
| SpeechBrain 1.1.1、Silero VAD 6.2.2 | 別途準備・worker用 | SpeechBrainはApache-2.0、Silero repositoryはMIT。ライブラリ許諾とモデルの許諾は分ける。torch/torchaudio 2.8.0等のwheel全体と音声I/O依存は追加監査対象。[SpeechBrain LICENSE](https://raw.githubusercontent.com/speechbrain/speechbrain/develop/LICENSE)、[Silero LICENSE](https://raw.githubusercontent.com/snakers4/silero-vad/master/LICENSE) |
| speechbrain/spkrec-ecapa-voxceleb、Silero重み | 別途準備・共通モデル | ECAPAモデルカードはApache-2.0。Sileroはコードと選んだ重みの配布元・同梱許諾を紐づけて固定する。モデル名だけでなくrevision・各ファイルhashが未固定。[ECAPAカード](https://huggingface.co/speechbrain/spkrec-ecapa-voxceleb)、[Silero公式](https://github.com/snakers4/silero-vad) |
| faster-whisper 1.2.1、CTranslate2 4.8.2 | 別途準備・worker用 | faster-whisperはMIT。CT2とPyAV、FFmpeg DLL、tokenizer、CUDA/cuDNN等は個別配布物で確認する。GPU関連の再配布可否をfaster-whisperのMITから推定しない。[faster-whisper LICENSE](https://raw.githubusercontent.com/SYSTRAN/faster-whisper/master/LICENSE) |
| Whisper large-v3 / CTranslate2変換モデル | 別途準備・共通モデル | Systranのfaster-whisper-large-v3カードはMITで、OpenAI large-v3を変換したものと説明。候補のモデル種は既案を維持し、具体的revision・量子化・付随tokenizerは未固定。[変換モデルカード](https://huggingface.co/Systran/faster-whisper-large-v3) |
| SudachiPy / sudachi.rs、SudachiDict（版・辞書種未固定） | 同梱候補・組合せ確認待ち | 解析器はApache-2.0。辞書もApache-2.0だがLEGALにUniDic・NEologd等の帰属・条件がある。辞書同梱時はLICENSEだけでなくLEGALも保持。辞書の形式と解析器の対応、採用辞書種・版を固定する。[解析器LICENSE](https://raw.githubusercontent.com/WorksApplications/sudachi.rs/develop/LICENSE)、[辞書LEGAL](https://raw.githubusercontent.com/WorksApplications/SudachiDict/develop/LEGAL) |
| 7-Zip / 7z CLI（版・配布形未固定） | 別途準備・実行物確認待ち | 公式条件はLGPL2.1以降を中心とし、7z.dllにBSD部分・unRAR制限付き部分を区別。バイナリ再配布時に該当ライセンス情報の保持を要求。7z形式だけ利用することから同梱DLLの条件が消えるとしない。[公式license.txt](https://www.7-zip.org/license.txt) |

## 台帳を確定するための有限の残件

1. **配布物を固定する。** 版だけでなく公式入手先、ファイル名、SHA256、CPU architecture、選択したwheel/ビルド/モデルrevisionを記録する。現時点で不明なものを仮の最新番号で埋めない。
2. **三つのFFmpeg系統を分ける。** 変換CLI、Qt Multimedia内DLL、PyAV内DLLは別に採録する。採用ビルドでlibzimg、必要codec、第三者ライブラリ、ライセンス・対応ソースを照合する。
3. **編集プラグイン配布物を確認する。** L-SMASH/x264guiExの候補版付属文書と実ファイル一覧を確認し、同梱encoder・muxerの条件を追加する。今回の調査で一式配布可能とはしない。
4. **機械学習workerの依存を閉じる。** torch/torchaudio、soundfile/libsndfile、PyAV、CTranslate2、ONNX Runtimeを採用する場合はそれも含め、解決された実依存とCPU/GPU別構成を記録する。現在の表は主要候補の入口である。
5. **配布形態と通知を整える。** 同梱するもののライセンス・著作権・NOTICEと、必要なソース入手/交換方法をアプリ配布物へ含める設計にする。実装したアプリ自身の許諾をこの台帳だけで決定しない。

不足する外部ツール・モデルはA90どおり依存機能だけを止める。ライセンス調査が済んだことをWindows動作・編集復元・認識品質の成立証拠にはしない。利用者へ新しい製品選択を求める項目は今回追加せず、上記を技術・配布の残件として扱う。

## 調査の限界

AviUtl2本体とSDKは以前取得済みの対象ZIP/展開資料を読み直した。その他は公開一次資料を参照しただけで、候補配布物の展開監査は未実施。公開ページに後の変更が混ざる可能性があるため、将来の実配布では固定版資料へ置き換える。対応OSと実証条件は[実行構成調査](runtime-candidate-research.md)、編集の未解決条件は[編集連携条件](editor-integration-gates.md)を維持する。

## A104後：検証対象の具体候補

以下は2026-09-18に配布元のページ・メタデータで特定した比較対象。ダウンロード・インストール・実行はしていない。公開SHA256は配布元の申告値であり、取得物をこちらで照合した結果ではない。全推移依存の解決済みlockfileではない。

| 用途 | 比較対象の版・ファイル | 選定理由と留保 |
| --- | --- | --- |
| 変換CLI | Gyan FFmpeg 9.0.1 essentials、`ffmpeg-9.0.1-essentials_build.zip` | FFmpeg公式が案内するWindows配布元。配布元のessentialsライブラリ一覧にlibx264・libzimgがあるため、H.264とHDR→SDR候補の入口を満たす。full版を必要とする根拠は現時点でない。GPLv3の実行物を別途準備する案。Qt/PyAV内のFFmpegは置換しない |
| 取得worker | `yt_dlp-2026.8.19-py3-none-any.whl` | 原本の調査基準版を維持。Python >=3.10。A95に対応するCookie書戻し抑止の制御を検討するためPython workerを第一経路にする。Python APIだけで全CLI互換や秘密値保護が成立済みとはしない |
| YouTube JS処理 | `yt_dlp_ejs-0.8.0-py3-none-any.whl` | 選定yt-dlpのdefault extraが指定する版。実行時に不定の最新版を取得する設計にしない |
| JS runtime | Deno 2.9.7、`deno-x86_64-pc-windows-msvc.zip` | 調査時の公式Windows x64公開版。yt-dlp metadataのdeno extraの下限2.6.6を満たす。pin-deno extraは2.9.5を示すので、それと同一構成とは主張しない。組合せの動作は未確認 |
| 可逆保管CLI | 7-Zip 26.03 x64、`7z2603-x64.exe`配布内のCLI | 公式Windows x64版。別途導入された実行物を指定する候補。7z/LZMA2保管・検査・展開の動作とCLI依存実体は未確認 |

FFmpeg本家はソース配布であり、上表のWindows実行物の製作者はGyan。9.0.1のreleaseを固定するのは比較条件を再現するための判断で、git版より常に安定しているとの保証ではない。[FFmpeg配布案内](https://ffmpeg.org/download.html)、[Gyan配布・ライブラリ一覧](https://www.gyan.dev/ffmpeg/builds/)

yt-dlpの一般Wikiで見たDeno最低2.3.0という過去の記述は、この候補構成の基準に使わない。選定版のメタデータはdeno extra >=2.6.6、EJS ==0.8.0を示す。default/pin extraの依存群も取得環境の候補条件として保存するが、実際のresolver結果は未取得。[yt-dlp固定版metadata](https://pypi.org/pypi/yt-dlp/2026.8.19/json)、[EJS metadata](https://pypi.org/pypi/yt-dlp-ejs/0.8.0/json)

### 配布元公表のSHA256

| ファイル | 公表SHA256 |
| --- | --- |
| ffmpeg-9.0.1-essentials_build.zip | `fec81ae03971d9dd4be3ebe02e263bd2ec1d789483f931bdba5f5715e65da2e9` |
| yt_dlp-2026.8.19-py3-none-any.whl | `1d57897e94c6665a0a6f9bc54b34e584284e32c034ffab3a7df25d8f7b24eedf` |
| yt_dlp_ejs-0.8.0-py3-none-any.whl | `79300e5fca7f937a1eeede11f0456862c1b41107ce1d726871e0207424f4bdb4` |
| deno-x86_64-pc-windows-msvc.zip（v2.9.7） | `a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238` |
| 7z2603-x64.exe | `0859c524b8a63551848f0c246abddcb1d0b7b656b0fbfe879f8d85e61a9e6edd` |

根拠: [FFmpeg固定版checksum](https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.1-essentials_build.zip.sha256)、上記PyPI metadata、[Deno公式release metadata](https://api.github.com/repos/denoland/deno/releases/tags/v2.9.7)、[7-Zip公式release metadata](https://api.github.com/repos/ip7z/7zip/releases/tags/26.03)。公開URLが差し替わった場合はハッシュ不一致を無視せず、候補更新として差分を確認する。

未固定はPythonパッチ版、Qt関連実体、機械学習環境の全推移依存・モデルrevision、編集プラグイン付属物など。主要実行物の版が決まったこととアプリ一式の環境が閉じたことを区別する。

集計候補も [tokenizer-candidate.md](tokenizer-candidate.md) でSudachiPy0.6.11＋SudachiDict-core20260723へ具体化した。配布元公表hash・Windows cp312 wheelを確認。全環境の解決済みlockではない。
