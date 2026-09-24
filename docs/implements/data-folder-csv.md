# データ用フォルダと CSV v1

`python -m clipchannel.app` で保存済み結果の閲覧画面を開く。フォルダ選択時に `catalog/`、`media/edits/`、`people/`、`projects/`、`exports/`、`archives/`、`work/`、`recovery/`、`logs/` を作る。既存フォルダを選ぶと、そのフォルダの解析結果を一覧に表示する。処理中または未保存入力がある場合、理由を表示して切り替えを拒む。画面のチェック欄は後続機能が状態を連携するまでの確認用である。

保存 API は `clipchannel.DataFolder`。解析結果は `save_result(source_name, kind, rows)`、再読込みは `load_result(source_name, kind, version)`。`kind` は `transcripts`、`segments`、`word-counts`。共通設定は `save_shared(kind, rows)` と `load_shared(kind)` で、`kind` は `people`、`registered-words`、`excluded-words`。人物の参照音声・特徴ファイルは CSV の `reference_audio` と `feature_file` に相対パスを記録し、実体は別ファイルに置く。現段階では実体の作成・存在確認は行わず、CSV の閲覧を妨げない。

CSV は UTF-8（BOM なし）、ヘッダーあり、カンマ区切り、LF 改行。フィールド内の引用符は二重引用符でエスケープし、改行は引用符で囲んで保持する。全ファイルの先頭列 `schema_version` は `1`。時刻列 `start_ms`、`end_ms` は元動画の先頭を 0 とする整数ミリ秒で、終了は開始より後。CSV の値は文字列として API に渡し、読込み時も文字列で返す。未知の列構成・版は拒む。

| 種類 | 列（先頭の `schema_version` を除く） |
| --- | --- |
| transcripts | `start_ms,end_ms,text,speaker_id` |
| segments | `start_ms,end_ms,kind,selected` |
| word-counts | `word,occurrences,utterances` |
| people | `person_id,name,reference_audio,feature_file` |
| registered-words / excluded-words | `word` |

解析結果は `catalog/<元動画名>/<種類>/<元動画名>_vN.csv` に新しい版として保存し、旧版を保持する。保存は同じフォルダの一時ファイルに書き込み、flush と fsync の後に置換する。途中で失敗した一時ファイルは削除し、既存版は変更しない。保存中断後の空の予約ファイルが残った場合は読込みで不正として表示し、次回保存は次の版を使う。共通設定も同方式で置換する。外部編集 CSV の修復は行わない。
