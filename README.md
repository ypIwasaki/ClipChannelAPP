# ClipChannelAPP

アーカイブ動画の取得、対象話者の文字起こし、切り出し、編集、管理を一つのアプリから扱うプロジェクトです。

現在は機能を段階的に実装中です。保存済みデータの閲覧、ローカル動画登録、認証不要URLの取得を扱う簡易画面があります。

```sh
python -m pip install -r requirements.txt
python -m clipchannel.app
```

媒体の確認と編集互換変換には、別途 `ffprobe` と `ffmpeg` を実行パス上に用意してください。取得した元ファイルは `media/downloaded/` に保持し、登録した動画は `media/originals/` に置きます。変換が必要な場合のMP4は `media/prepared/<元ファイル名>/editing-<識別子>.mp4` に保存し、同名のJSONに映像・音声の開始時刻と元動画との対応を記録します。変換に失敗した場合も元動画を保持し、動画を選択して「媒体確認・変換（再試行）」を実行できます。音声のみの結果は `media/audio/` に保存します。

編集用字幕を追加するには、区間タブで編集用MP4を作成し、同じ元動画の保存済み文字起こしCSVを一覧で選んで「字幕をAviUtl2へ追加」を押します。`projects/<編集フォルダ>/` に取込みファイルを別版保存します。対応する編集用動画を置いたAviUtl2プロジェクトを同じフォルダに保存し、[字幕取込みプラグイン](editor-plugin/)の「ClipChannel → 字幕を追加」でファイルを選びます。再取込みは既存字幕を変更せず、別オブジェクトを追加します。元の文字起こしCSVも変更しません。

プラグインのビルドにはAviUtl2 SDKとWindows C++ビルド環境が必要です。Visual Studio の x64 Developer Command Prompt で、`AVIUTL2_SDK` に `plugin2.h` のあるフォルダ、`WIN_SDK_PACKAGES` に Windows SDK NuGet パッケージの親フォルダ、`WIN_SDK_VERSION` に SDK の版を設定して `editor-plugin/build.cmd` を実行します。生成した `clipchannel_subtitles.aux2` をAviUtl2のプラグインフォルダへ配置します。AviUtl2 2.1.9で字幕の追加・保存・再取込みを検証済みです。

- [別PCでの作業再開](docs/development-handoff.md)：読む順序、現在地、Git外のデータと実行環境
- [初版の編集受渡し方針](docs/implements/editor-handoff-scope.md)：動画一本化、字幕、保存・出力の簡易判定
- [初版範囲の縮小](docs/implements/initial-scope-pruning.md)：認証・特殊入力・配布対応の見送り
- [最新の話者・ASR検証](docs/implements/multi-speaker-validation.md)：指定動画の照合と10分の文字起こし
- [仕様再検討の状況](docs/implements/spec-review-status.md) / [合意履歴](docs/implements/spec-review.md)
- [原仕様（保持した草案）](docs/implements/spec.md) / [用語集](CONTEXT.md) / [設計判断](docs/adr/)

作業規則は [AGENTS.md](AGENTS.md) を参照してください。スキルは `.agents/skills/`、導入元の記録は `skills-lock.json` にあります。
