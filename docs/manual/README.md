# マニュアルの更新と検証

利用者向けの完成版は [index.html](index.html) と [manual.md](manual.md) です。HTMLは同梱画像を使い、オフラインで閲覧できます。

## 編集するファイル

- `workflow.md`: 起動、動画の準備、トリミング、解析、切り出しの手順。
- `editor-and-management.md`: 編集、保存、書き出し、管理の手順。
- `manual_content.json`: 画面の各コントロールIDに対応する項目名と操作説明、および画面ごとの注意事項。
- `scripts/manual_capture.py`: 現行UIを走査し、番号付きの画像と画面一覧を生成する撮影処理。

`manual.md` と `index.html` は生成物です。本文や説明表を直接編集すると、再生成で変更が失われます。

## 再生成

リポジトリのルートから、X11表示のあるWSL環境で実行します。撮影は一時データ用フォルダを作り、本番のデータ用フォルダを開きません。撮影環境にはTkinter、FFmpeg、Pillowと日本語フォントが必要です。Noto Sans CJK、またはWindows側のMeiryoを使用します。Windowsフォントを使う場合は撮影プロセス内だけのFontconfig設定を一時フォルダへ作り、画面・注釈の日本語を表示します。HTML生成にはPythonのMarkdownパッケージが必要です。

```bash
.venv/bin/python scripts/manual_capture.py --inventory-only
# control-inventory.json と実装を照合し、本文・manual_content.json を更新
.venv/bin/python scripts/manual_capture.py
.venv/bin/python scripts/build_manual.py
.venv/bin/python scripts/render_manual.py
.venv/bin/python scripts/build_manual.py --check
```

UIの項目を追加した場合は、撮影スクリプトのSCREEN_IDSにも固定IDを追加します。画面名を基にした固定ファイル名を使います。タブや項目が追加されても、既存画像が通し番号のずれで別画面に置き換わりません。

## 番号と説明の対応

撮影時の `screens.json` に、各画像の番号、項目名、コントロールID、枠の座標を記録します。画像の注釈と説明表はこの同じデータから生成します。

ビルドは次の場合に失敗します。

- 画像の番号が1から連続しない、画像がない、注釈が画像の外にある。
- 番号に対応する項目名・説明がない、画像と説明表の項目名が異なる。
- 現行UIの項目やコントロールが撮影されていない、古いコントロールや使われない説明が残っている。
- 現行UIのボタン名・コントロール種別が変わっている、番号の表示が画像の外にある・重なっている。
- MarkdownまたはHTMLで、画像の番号と説明表の番号・件数が一致しない。

検査が通った後も、画像を目視して番号が読めること、枠が正しい項目を指すこと、スクロール領域の項目が見切れていないことを確認してください。取得・解析・AviUtl2の外部処理を実行しない説明用画像を、実行成功の証拠として扱わないでください。
