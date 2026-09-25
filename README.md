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

「補助素材」タブでは、現在作成した編集用動画に画像（PNG/JPEG/BMP）・BGM・効果音を追加できます。外部ファイルは `media/supporting/<編集フォルダ>/<素材識別子>/` へコピーし、原本を変更しません。開始フレーム・長さ・画像位置と拡大率・音声の素材開始秒と音量を指定して「配置をAviUtl2へ適用・プレビュー」を押します。上記の専用プラグインを更新し、対応する編集用動画を先頭に置いたプロジェクトを `projects/<編集フォルダ>/` に保存して開いてください。調整時は同じ素材の配置を更新し、重複追加しません。画像と、プレビュー位置から最大5秒のAviUtl2のミックス音声を確認できます。

BGMは全長で追加し、編集用動画の継ぎ目や終端では切り詰めません。音声の長さはフレーム単位で表現します。適用時に映像終端までをAviUtl2の選択範囲に設定し、プレビュー音声もその終端で止めます。完成動画の保存・書き出し制御は Issue 14 の対象です。配置の指示ファイル `.ccmedia` は版を分けて保存しますが、AviUtl2プロジェクト自体の保存は明示的に行ってください。新しい編集用動画には既存の補助素材配置を移しません。

補助素材の自動テストは `python -m unittest tests.test_supporting_media -v` で実行できます。Windows の隔離したAviUtl2にビルド済みプラグインとMP4入力環境を用意し、`CLIPCHANNEL_TEST_AVIUTL` をその `aviutl2.exe` に設定すると、`python -m unittest tests.test_supporting_media_editor -v` で実機の描画とミックス音声を検証できます。検証専用プロセスはテスト終了時に停止します。

- [別PCでの作業再開](docs/development-handoff.md)：読む順序、現在地、Git外のデータと実行環境
- [初版の編集受渡し方針](docs/implements/editor-handoff-scope.md)：動画一本化、字幕、保存・出力の簡易判定
- [初版範囲の縮小](docs/implements/initial-scope-pruning.md)：認証・特殊入力・配布対応の見送り
- [最新の話者・ASR検証](docs/implements/multi-speaker-validation.md)：指定動画の照合と10分の文字起こし
- [仕様再検討の状況](docs/implements/spec-review-status.md) / [合意履歴](docs/implements/spec-review.md)
- [原仕様（保持した草案）](docs/implements/spec.md) / [用語集](CONTEXT.md) / [設計判断](docs/adr/)

作業規則は [AGENTS.md](AGENTS.md) を参照してください。スキルは `.agents/skills/`、導入元の記録は `skills-lock.json` にあります。
